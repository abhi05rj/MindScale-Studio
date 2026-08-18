import json
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.content_engine import ContentStorage
from app.hosted_runtime import HostedRuntimeStateAdapter
from app.image_engine import FakeImageProvider
from app.pipeline import PipelineOrchestrator, PipelineStateStorage
from app.planning import ContentPlanner, WeeklyPlanStorage
from app.production_publication import PublicationAttemptStorage
from app.scheduling import PublicationQueue


class HostedRuntimeStateTests(unittest.TestCase):
    target_date = date(2027, 3, 1)
    fixed_time = datetime(2027, 2, 25, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def paths(self, root):
        return {
            "plans": root / ".local-runtime" / "content_plans",
            "pipeline": root / ".local-runtime" / "pipeline",
            "queue": root / ".local-runtime" / "publication_queue.json",
            "packages": root / "output" / "content_packages",
            "images": root / "output" / "images",
        }

    def orchestrator(self, root, image_provider):
        paths = self.paths(root)
        return PipelineOrchestrator(
            plan_storage=WeeklyPlanStorage(paths["plans"]),
            content_storage=ContentStorage(paths["packages"]),
            publication_queue=PublicationQueue(paths["queue"]),
            state_storage=PipelineStateStorage(paths["pipeline"]),
            image_provider=image_provider,
            image_directory=paths["images"],
            log=lambda message: None,
        )

    def create_plan(self, root):
        paths = self.paths(root)
        return ContentPlanner(
            storage=WeeklyPlanStorage(paths["plans"]),
            content_history_directory=paths["packages"],
            clock=lambda: self.fixed_time,
        ).create_weekly_plan(self.target_date)

    def test_missing_snapshot_starts_fresh_without_writes(self):
        runner = self.root / "runner"
        report = HostedRuntimeStateAdapter(runner).import_state(self.root / "missing")

        self.assertTrue(report.fresh)
        self.assertFalse((runner / ".local-runtime").exists())

    def test_export_contains_json_metadata_only_and_portable_references(self):
        runner = self.root / "runner"
        snapshot = self.root / "snapshot"
        self.create_plan(runner)
        with patch.dict(os.environ, {"MINDSCALE_PROJECT_ROOT": str(runner)}):
            result = self.orchestrator(runner, FakeImageProvider()).run(self.target_date)

        report = HostedRuntimeStateAdapter(runner).export_state(
            snapshot,
            image_artifact_run_id="12345",
            image_artifact_name="mindscale-images-12345",
        )

        self.assertEqual(result.status, "queued")
        self.assertEqual(report.content_plans, 1)
        self.assertEqual(report.pipeline_states, 1)
        self.assertEqual(report.content_packages, 1)
        self.assertTrue(report.queue_present)
        self.assertTrue(all(path.suffix == ".json" for path in snapshot.rglob("*") if path.is_file()))
        package = json.loads(next((snapshot / "content_packages").glob("*.json")).read_text())
        self.assertTrue(package["image"]["final_path"].startswith("output/images/"))
        self.assertTrue(package["image"]["final_path"].endswith("_pinterest.png"))
        self.assertFalse(Path(package["image"]["final_path"]).is_absolute())
        self.assertFalse(any(snapshot.rglob("*.png")))
        self.assertEqual(
            HostedRuntimeStateAdapter(runner).read_image_artifact(snapshot),
            ("12345", "mindscale-images-12345"),
        )

    def test_state_restoration_on_fresh_runner_preserves_documents(self):
        first = self.root / "first"
        second = self.root / "second"
        snapshot = self.root / "snapshot"
        self.create_plan(first)
        with patch.dict(os.environ, {"MINDSCALE_PROJECT_ROOT": str(first)}):
            self.orchestrator(first, FakeImageProvider()).run(self.target_date)
        HostedRuntimeStateAdapter(first).export_state(snapshot)

        PublicationAttemptStorage(
            first / ".local-runtime" / "publication_attempts"
        ).save("queue-item-1", status="failed", attempt_count=1, last_error="safe failure")
        HostedRuntimeStateAdapter(first).export_state(snapshot)

        report = HostedRuntimeStateAdapter(second).import_state(snapshot)

        self.assertEqual(report.content_packages, 1)
        self.assertEqual(len(list(self.paths(second)["plans"].glob("*.json"))), 1)
        self.assertEqual(len(list(self.paths(second)["pipeline"].glob("*.json"))), 1)
        self.assertEqual(len(list(self.paths(second)["packages"].glob("*.json"))), 1)
        self.assertEqual(len(PublicationQueue(self.paths(second)["queue"]).list_items()), 1)
        restored_attempt = PublicationAttemptStorage(
            second / ".local-runtime" / "publication_attempts"
        ).load("queue-item-1")
        self.assertEqual(report.publication_attempts, 1)
        self.assertEqual(restored_attempt["status"], "failed")
        self.assertEqual(restored_attempt["attempt_count"], 1)

    def test_missing_restored_image_is_rejected_before_pipeline_execution(self):
        first = self.root / "first"
        second = self.root / "second"
        snapshot = self.root / "snapshot"
        self.create_plan(first)
        with patch.dict(os.environ, {"MINDSCALE_PROJECT_ROOT": str(first)}):
            self.orchestrator(first, FakeImageProvider()).run(self.target_date)
        HostedRuntimeStateAdapter(first).export_state(snapshot)
        HostedRuntimeStateAdapter(second).import_state(snapshot)

        with self.assertRaisesRegex(ValueError, "does not exist or is empty"):
            HostedRuntimeStateAdapter(second).validate_restored_images()

    def test_repeat_run_on_new_runner_is_idempotent_after_state_and_image_restore(self):
        class ExplodingImageProvider:
            def generate(self, request):
                raise AssertionError("The completed image must not be regenerated.")

        first = self.root / "first"
        second = self.root / "second"
        snapshot = self.root / "snapshot"
        artifact = self.root / "artifact"
        self.create_plan(first)
        with patch.dict(os.environ, {"MINDSCALE_PROJECT_ROOT": str(first)}):
            first_result = self.orchestrator(first, FakeImageProvider()).run(self.target_date)
        shutil.copytree(self.paths(first)["images"], artifact)
        HostedRuntimeStateAdapter(first).export_state(snapshot)

        HostedRuntimeStateAdapter(second).import_state(snapshot)
        shutil.copytree(artifact, self.paths(second)["images"])
        before = next(self.paths(second)["images"].glob("*_pinterest.png")).read_bytes()
        with patch.dict(os.environ, {"MINDSCALE_PROJECT_ROOT": str(second)}):
            second_result = self.orchestrator(second, ExplodingImageProvider()).run(
                self.target_date
            )

        self.assertEqual(second_result.status, "queued")
        self.assertEqual(second_result.queue_item_id, first_result.queue_item_id)
        self.assertEqual(len(list(self.paths(second)["packages"].glob("*.json"))), 1)
        self.assertEqual(len(list(self.paths(second)["images"].glob("*_pinterest.png"))), 1)
        self.assertEqual(len(PublicationQueue(self.paths(second)["queue"]).list_items()), 1)
        self.assertEqual(next(self.paths(second)["images"].glob("*_pinterest.png")).read_bytes(), before)

    def test_corrupt_snapshot_is_rejected_before_local_state_changes(self):
        runner = self.root / "runner"
        snapshot = self.root / "snapshot"
        snapshot.mkdir()
        (snapshot / "manifest.json").write_text(
            json.dumps({"version": 1, "counts": {}}), encoding="utf-8"
        )
        (snapshot / "content_packages").mkdir()
        (snapshot / "content_packages" / "broken.json").write_text("{", encoding="utf-8")
        sentinel = runner / ".local-runtime" / "content_plans" / "sentinel.json"
        sentinel.parent.mkdir(parents=True)
        sentinel.write_text('{"safe": true}', encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Invalid hosted runtime JSON"):
            HostedRuntimeStateAdapter(runner).import_state(snapshot)

        self.assertEqual(sentinel.read_text(encoding="utf-8"), '{"safe": true}')
        self.assertFalse((runner / "output" / "content_packages" / "broken.json").exists())

    def test_corrupt_manifest_is_rejected_before_local_state_changes(self):
        runner = self.root / "runner"
        snapshot = self.root / "snapshot"
        (snapshot / "content_plans").mkdir(parents=True)
        (snapshot / "manifest.json").write_text(
            json.dumps({"version": 1, "counts": {"content_plans": "invalid"}}),
            encoding="utf-8",
        )
        (snapshot / "content_plans" / "would-write.json").write_text(
            '{"otherwise": "valid JSON"}', encoding="utf-8"
        )

        with self.assertRaisesRegex(ValueError, "manifest counts are invalid"):
            HostedRuntimeStateAdapter(runner).import_state(snapshot)

        self.assertFalse((runner / ".local-runtime").exists())


if __name__ == "__main__":
    unittest.main()
