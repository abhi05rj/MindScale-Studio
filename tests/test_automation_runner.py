import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.automation_runner import run_daily_automation
from app.content_engine import ContentCalendarEngine, ContentStorage
from app.image_engine import FakeImageProvider, PinterestImageValidator


class AutomationRunnerTests(unittest.TestCase):
    def test_generates_saves_and_then_no_ops_for_the_same_date(self):
        run_date = date(2026, 8, 8)

        with tempfile.TemporaryDirectory() as directory:
            storage = ContentStorage(Path(directory))
            engine = ContentCalendarEngine(content_storage=storage)
            first_logs = []

            image_directory = Path(directory) / "images"
            first_exit_code = run_daily_automation(
                run_date,
                engine,
                first_logs.append,
                image_provider=FakeImageProvider(),
                image_directory=image_directory,
            )

            saved_files = list(Path(directory).glob("*.json"))
            self.assertEqual(first_exit_code, 0)
            self.assertEqual(len(saved_files), 1)
            self.assertTrue(any(line.startswith("START") for line in first_logs))
            self.assertTrue(any(line.startswith("SELECTED TOPIC:") for line in first_logs))
            self.assertTrue(any(line.startswith("GENERATED CONTENT:") for line in first_logs))
            self.assertTrue(any(line.startswith("SAVED CONTENT:") for line in first_logs))
            self.assertTrue(first_logs[-1].startswith("COMPLETE"))

            record = json.loads(saved_files[0].read_text(encoding="utf-8"))
            self.assertEqual(record["publish_date"], run_date.isoformat())
            self.assertIn("pinterest_title", record["content_package"]["pinterest"])
            self.assertEqual(record["image"]["status"], "complete")
            self.assertEqual(record["pinterest_publication"]["status"], "not_published")
            self.assertIsNone(record["pinterest_publication"]["pin_id"])
            final_path = Path(record["image"]["final_path"])
            PinterestImageValidator().validate(final_path)

            second_logs = []
            before = final_path.stat().st_mtime_ns
            second_exit_code = run_daily_automation(
                run_date,
                engine,
                second_logs.append,
                image_provider=FakeImageProvider(),
                image_directory=image_directory,
            )

            self.assertEqual(second_exit_code, 0)
            self.assertEqual(len(list(Path(directory).glob("*.json"))), 1)
            self.assertEqual(final_path.stat().st_mtime_ns, before)
            self.assertTrue(any(line.startswith("IMAGE/NO-OP") for line in second_logs))
            self.assertTrue(second_logs[-1].startswith("COMPLETE"))

    def test_logs_errors_and_returns_failure(self):
        class FailingEngine:
            def __init__(self, storage):
                self.content_storage = storage

            def select_topic(self, publish_date):
                raise RuntimeError("topic selection failed")

        with tempfile.TemporaryDirectory() as directory:
            logs = []
            exit_code = run_daily_automation(
                date(2026, 8, 8),
                FailingEngine(ContentStorage(Path(directory))),
                logs.append,
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("ERROR daily content automation: topic selection failed", logs)
        self.assertEqual(logs[-1], "COMPLETE daily content automation (failed)")

    def test_records_failed_image_state_for_a_safe_retry(self):
        class FailingImageProvider:
            def generate(self, request):
                raise RuntimeError("local image generation failed")

        run_date = date(2026, 8, 9)
        with tempfile.TemporaryDirectory() as directory:
            storage = ContentStorage(Path(directory))
            exit_code = run_daily_automation(
                run_date,
                ContentCalendarEngine(content_storage=storage),
                log=lambda message: None,
                image_provider=FailingImageProvider(),
                image_directory=Path(directory) / "images",
            )

            record = storage.record_for_publish_date(run_date)

        self.assertEqual(exit_code, 1)
        self.assertEqual(record["image"]["status"], "failed")
        self.assertEqual(record["image"]["error"], "local image generation failed")
        self.assertNotIn("background_path", record["image"])
        self.assertNotIn("final_path", record["image"])
        self.assertEqual(record["pinterest_publication"]["status"], "not_published")
        self.assertIsNone(record["pinterest_publication"]["pin_id"])

    def test_interruption_cleans_partial_files_and_recovers_state(self):
        class InterruptedImageProvider:
            def generate(self, request):
                request.output_path.parent.mkdir(parents=True, exist_ok=True)
                request.output_path.write_bytes(b"partial")
                raise KeyboardInterrupt("generation interrupted")

        run_date = date(2026, 8, 10)
        with tempfile.TemporaryDirectory() as directory:
            storage = ContentStorage(Path(directory))
            image_directory = Path(directory) / "images"
            with self.assertRaises(KeyboardInterrupt):
                run_daily_automation(
                    run_date,
                    ContentCalendarEngine(content_storage=storage),
                    log=lambda message: None,
                    image_provider=InterruptedImageProvider(),
                    image_directory=image_directory,
                )

            record = storage.record_for_publish_date(run_date)

        self.assertEqual(record["image"]["status"], "failed")
        self.assertNotIn("background_path", record["image"])
        self.assertNotIn("final_path", record["image"])
        self.assertEqual(record["pinterest_publication"]["status"], "not_published")

    def test_recovers_a_stale_generating_state(self):
        run_date = date(2026, 8, 11)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = ContentStorage(root)
            engine = ContentCalendarEngine(content_storage=storage)
            image_directory = root / "images"
            self.assertEqual(
                run_daily_automation(
                    run_date,
                    engine,
                    log=lambda message: None,
                    image_provider=FakeImageProvider(),
                    image_directory=image_directory,
                ),
                0,
            )
            package_path = storage.path_for_publish_date(run_date)
            record = json.loads(package_path.read_text(encoding="utf-8"))
            record["image"]["status"] = "generating"
            package_path.write_text(json.dumps(record), encoding="utf-8")
            logs = []

            exit_code = run_daily_automation(
                run_date,
                engine,
                logs.append,
                image_provider=FakeImageProvider(),
                image_directory=image_directory,
            )
            recovered = storage.record_for_publish_date(run_date)

        self.assertEqual(exit_code, 0)
        self.assertEqual(recovered["image"]["status"], "complete")
        self.assertEqual(recovered["pinterest_publication"]["status"], "not_published")
        self.assertTrue(any(line == "RECOVERING IMAGE STATE: generating" for line in logs))

    def test_persisted_package_contains_all_automation_v1_fields(self):
        run_date = date(2026, 8, 12)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = ContentStorage(root)
            exit_code = run_daily_automation(
                run_date,
                ContentCalendarEngine(content_storage=storage),
                log=lambda message: None,
                image_provider=FakeImageProvider(),
                image_directory=root / "images",
            )
            record = storage.record_for_publish_date(run_date)
            package_path = storage.path_for_publish_date(run_date)

        self.assertEqual(exit_code, 0)
        self.assertIsNotNone(package_path)
        self.assertEqual(record["publish_date"], run_date.isoformat())
        self.assertEqual(record["topic"], record["content_package"]["topic"])
        self.assertTrue(record["content_package"]["pinterest"]["pinterest_title"])
        self.assertTrue(record["content_package"]["pinterest"]["pinterest_description"])
        self.assertEqual(record["image"]["width"], 1000)
        self.assertEqual(record["image"]["height"], 1500)
        self.assertEqual(record["image"]["format"], "PNG")
        self.assertEqual(record["pinterest_publication"]["status"], "not_published")
        self.assertIsNone(record["pinterest_publication"]["pin_id"])

    def test_dry_run_with_no_package_writes_nothing(self):
        run_date = date(2026, 8, 13)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = ContentStorage(root)
            logs = []
            exit_code = run_daily_automation(
                run_date,
                ContentCalendarEngine(content_storage=storage),
                logs.append,
                image_provider=FakeImageProvider(),
                image_directory=root / "images",
                dry_run=True,
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(list(root.glob("*.json")), [])
            self.assertFalse((root / "images").exists())
            self.assertTrue(any(line.startswith("DRY-RUN selected next topic:") for line in logs))


if __name__ == "__main__":
    unittest.main()
