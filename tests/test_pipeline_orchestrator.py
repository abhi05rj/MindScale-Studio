import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from app.content_engine import ContentStorage
from app.image_engine import FakeImageProvider, PinterestImageValidator
from app.pipeline import PipelineOrchestrator, PipelineStateStorage
from app.planning import ContentPlanner, WeeklyPlanStorage
from app.scheduling import PublicationQueue


class PipelineOrchestratorTests(unittest.TestCase):
    start_date = date(2027, 1, 4)
    fixed_time = datetime(2027, 1, 1, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.plan_storage = WeeklyPlanStorage(self.root / ".local-runtime" / "plans")
        self.content_storage = ContentStorage(self.root / "content_packages")
        self.queue = PublicationQueue(self.root / ".local-runtime" / "queue.json")
        self.state_storage = PipelineStateStorage(self.root / ".local-runtime" / "pipeline")
        self.image_directory = self.root / "images"
        self.plan = ContentPlanner(
            storage=self.plan_storage,
            content_history_directory=self.root / "content_history",
            clock=lambda: self.fixed_time,
        ).create_weekly_plan(self.start_date)
        self.target_date = date.fromisoformat(self.plan.days[0].publish_date)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def orchestrator(self, **overrides):
        options = {
            "plan_storage": self.plan_storage,
            "content_storage": self.content_storage,
            "publication_queue": self.queue,
            "state_storage": self.state_storage,
            "image_provider": FakeImageProvider(),
            "image_directory": self.image_directory,
            "log": lambda message: None,
        }
        options.update(overrides)
        return PipelineOrchestrator(**options)

    def test_runs_planned_item_through_generation_and_queue(self):
        result = self.orchestrator().run(self.target_date)

        record = self.content_storage.record_for_publish_date(self.target_date)
        state = self.state_storage.load(self.target_date)
        queue_item = self.queue.get(result.queue_item_id)
        planned_day = self.plan.days[0]
        self.assertEqual(result.status, "queued")
        self.assertEqual(record["topic"], planned_day.topic)
        self.assertEqual(
            record["content_package"]["pinterest"]["pinterest_title"],
            planned_day.working_title,
        )
        self.assertEqual(
            record["content_package"]["local_editorial_angle"], planned_day.content_angle
        )
        self.assertEqual(record["image"]["status"], "complete")
        PinterestImageValidator().validate(Path(record["image"]["final_path"]))
        self.assertEqual(queue_item.status, "scheduled")
        self.assertEqual(queue_item.content_publish_date, self.target_date.isoformat())
        self.assertEqual(state["status"], "queued")
        self.assertEqual(
            [entry["status"] for entry in state["status_history"]],
            ["planned", "generating", "generated", "queued"],
        )

    def test_repeat_execution_reuses_package_image_and_queue_item(self):
        orchestrator = self.orchestrator()
        first = orchestrator.run(self.target_date)
        record = self.content_storage.record_for_publish_date(self.target_date)
        image_path = Path(record["image"]["final_path"])
        image_timestamp = image_path.stat().st_mtime_ns
        state_before = self.state_storage.path_for(self.target_date).read_bytes()

        second = orchestrator.run(self.target_date)

        self.assertEqual(second, first)
        self.assertEqual(len(list((self.root / "content_packages").glob("*.json"))), 1)
        self.assertEqual(len(self.queue.list_items()), 1)
        self.assertEqual(image_path.stat().st_mtime_ns, image_timestamp)
        self.assertEqual(self.state_storage.path_for(self.target_date).read_bytes(), state_before)

    def test_failed_image_generation_recovers_without_queue_corruption(self):
        class FailingImageProvider:
            def generate(self, request):
                raise RuntimeError("offline image failure")

        failed = self.orchestrator(image_provider=FailingImageProvider()).run(self.target_date)

        failed_state = self.state_storage.load(self.target_date)
        failed_record = self.content_storage.record_for_publish_date(self.target_date)
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed_state["status"], "failed")
        self.assertEqual(failed_state["last_error"], "offline image failure")
        self.assertEqual(failed_record["image"]["status"], "failed")
        self.assertEqual(self.queue.list_items(), [])

        recovered = self.orchestrator().run(self.target_date)
        self.assertEqual(recovered.status, "queued")
        self.assertEqual(len(self.queue.list_items()), 1)
        self.assertEqual(
            self.content_storage.record_for_publish_date(self.target_date)["image"]["status"],
            "complete",
        )

    def test_queue_failure_preserves_completed_package_for_retry(self):
        class FailingQueue(PublicationQueue):
            def schedule(self, content_package_path, scheduled_for, **kwargs):
                raise RuntimeError("queue storage unavailable")

        failing_queue = FailingQueue(self.root / ".local-runtime" / "failing-queue.json")
        failed = self.orchestrator(publication_queue=failing_queue).run(self.target_date)
        record = self.content_storage.record_for_publish_date(self.target_date)

        self.assertEqual(failed.status, "failed")
        self.assertEqual(record["image"]["status"], "complete")
        self.assertEqual(failing_queue.list_items(), [])
        image_path = Path(record["image"]["final_path"])
        before = image_path.stat().st_mtime_ns

        recovered = self.orchestrator().run(self.target_date)
        self.assertEqual(recovered.status, "queued")
        self.assertEqual(image_path.stat().st_mtime_ns, before)
        self.assertEqual(len(self.queue.list_items()), 1)

    def test_existing_queue_entry_is_reused_if_pipeline_state_needs_recovery(self):
        first = self.orchestrator().run(self.target_date)
        self.state_storage.transition(self.target_date, "generated", queue_item_id=None)

        recovered = self.orchestrator().run(self.target_date)

        self.assertEqual(recovered.status, "queued")
        self.assertEqual(recovered.queue_item_id, first.queue_item_id)
        self.assertEqual(len(self.queue.list_items()), 1)

    def test_missing_plan_fails_before_creating_runtime_state(self):
        missing_date = date(2030, 1, 1)
        with self.assertRaisesRegex(ValueError, "No content plan"):
            self.orchestrator().run(missing_date)

        self.assertIsNone(self.state_storage.load(missing_date))
        self.assertEqual(self.queue.list_items(), [])


if __name__ == "__main__":
    unittest.main()
