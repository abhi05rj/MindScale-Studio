import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from app.content_engine import ContentStorage
from app.pinterest import PinterestConfig, PinterestPublisher, PublicationResult
from app.scheduling import (
    DuplicateQueueItemError,
    InvalidQueueTransitionError,
    PublicationQueue,
    QueueProcessor,
)


class NoNetworkPinterestClient:
    def __init__(self):
        self.board_calls = []
        self.pin_calls = []

    def get_board(self, board_id):
        self.board_calls.append(board_id)
        raise AssertionError("Dry-run must not look up a Pinterest board")

    def create_pin(self, payload):
        self.pin_calls.append(payload)
        raise AssertionError("Dry-run must not create a Pinterest Pin")


class StubPublisher:
    def __init__(self, *, pin_id="pin-123", error=None):
        self.pin_id = pin_id
        self.error = error
        self.calls = []

    def publish(self, publish_date, dry_run=False):
        self.calls.append((publish_date, dry_run))
        if self.error:
            raise self.error
        return PublicationResult(
            "dry_run_validated" if dry_run else "published",
            payload={},
            pin_id=None if dry_run else self.pin_id,
        )


class PublicationQueueTests(unittest.TestCase):
    publish_date = date(2026, 8, 18)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.content_directory = self.root / "content"
        self.content_directory.mkdir()
        self.image_path = self.root / "pin.png"
        Image.new("RGB", (1000, 1500), "navy").save(self.image_path)
        self.package_path = self.content_directory / "package.json"
        self.package_path.write_text(
            json.dumps(
                {
                    "publish_date": self.publish_date.isoformat(),
                    "topic": "Time",
                    "content_package": {
                        "topic": "Time",
                        "pinterest": {
                            "pinterest_title": "What Makes Time So Fascinating?",
                            "pinterest_description": "A clear visual explanation of time.",
                        },
                    },
                    "image": {"status": "complete", "final_path": str(self.image_path)},
                    "pinterest_publication": {
                        "status": "not_published",
                        "pin_id": None,
                    },
                }
            ),
            encoding="utf-8",
        )
        self.queue_path = self.root / ".local-runtime" / "queue.json"
        self.queue = PublicationQueue(self.queue_path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def schedule(self, when=None):
        return self.queue.schedule(
            self.package_path,
            when or self.now,
            now=self.now - timedelta(hours=1),
        )

    def test_scheduling_persists_all_required_fields_across_instances(self):
        scheduled = self.schedule(self.now + timedelta(days=1))
        restored = PublicationQueue(self.queue_path).get(scheduled.id)

        self.assertEqual(restored, scheduled)
        self.assertEqual(restored.platform, "pinterest")
        self.assertEqual(restored.status, "scheduled")
        self.assertEqual(restored.attempt_count, 0)
        self.assertIsNone(restored.last_error)
        self.assertIsNone(restored.pinterest_pin_id)
        self.assertEqual(restored.scheduled_for, "2026-08-19T12:00:00+00:00")
        self.assertTrue(self.queue_path.is_file())

    def test_due_detection_returns_only_due_scheduled_or_failed_items(self):
        due = self.schedule(self.now - timedelta(minutes=1))
        future_package = self.content_directory / "future.json"
        future_record = json.loads(self.package_path.read_text(encoding="utf-8"))
        future_record["publish_date"] = "2026-08-19"
        future_package.write_text(json.dumps(future_record), encoding="utf-8")
        self.queue.schedule(future_package, self.now + timedelta(minutes=1), now=self.now)

        self.assertEqual([item.id for item in self.queue.due_items(self.now)], [due.id])

    def test_cancellation_persists_and_cancelled_item_is_not_due(self):
        item = self.schedule(self.now - timedelta(minutes=1))
        cancelled = self.queue.cancel(item.id)

        self.assertEqual(cancelled.status, "cancelled")
        self.assertEqual(PublicationQueue(self.queue_path).due_items(self.now), [])
        with self.assertRaises(InvalidQueueTransitionError):
            self.queue.cancel(item.id)

    def test_duplicate_active_content_package_is_rejected(self):
        self.schedule()
        with self.assertRaises(DuplicateQueueItemError):
            self.schedule(self.now + timedelta(hours=1))

    def test_offline_processing_validates_without_network_or_state_changes(self):
        item = self.schedule(self.now - timedelta(minutes=1))
        client = NoNetworkPinterestClient()
        publisher = PinterestPublisher(
            ContentStorage(self.content_directory),
            PinterestConfig(board_id="offline-board-placeholder"),
            client=client,
        )
        before = self.queue_path.read_bytes()

        results = QueueProcessor(self.queue, publisher).process_due(now=self.now)

        self.assertEqual(results[0].outcome, "dry_run_validated")
        self.assertEqual(client.board_calls, [])
        self.assertEqual(client.pin_calls, [])
        self.assertEqual(self.queue_path.read_bytes(), before)
        persisted = self.queue.get(item.id)
        self.assertEqual(persisted.status, "scheduled")
        self.assertEqual(persisted.attempt_count, 0)
        self.assertIsNone(persisted.pinterest_pin_id)

    def test_live_success_persists_pin_and_repeat_processing_does_not_publish_again(self):
        item = self.schedule(self.now - timedelta(minutes=1))
        publisher = StubPublisher(pin_id="pin-987")
        processor = QueueProcessor(self.queue, publisher)

        first = processor.process_due(now=self.now, live=True)
        second = processor.process_item(self.queue.get(item.id), live=True)

        persisted = PublicationQueue(self.queue_path).get(item.id)
        self.assertEqual(first[0].outcome, "published")
        self.assertEqual(second.outcome, "already_published")
        self.assertEqual(publisher.calls, [(self.publish_date, False)])
        self.assertEqual(persisted.status, "published")
        self.assertEqual(persisted.pinterest_pin_id, "pin-987")
        self.assertEqual(persisted.attempt_count, 1)

    def test_live_failure_is_persisted_and_can_be_retried(self):
        item = self.schedule(self.now - timedelta(minutes=1))
        failing = StubPublisher(error=RuntimeError("publisher unavailable"))

        result = QueueProcessor(self.queue, failing).process_due(now=self.now, live=True)

        failed = self.queue.get(item.id)
        self.assertEqual(result[0].outcome, "failed")
        self.assertEqual(failed.status, "failed")
        self.assertEqual(failed.attempt_count, 1)
        self.assertEqual(failed.last_error, "publisher unavailable")

        success = StubPublisher(pin_id="retry-pin")
        QueueProcessor(self.queue, success).process_due(now=self.now, live=True)
        published = self.queue.get(item.id)
        self.assertEqual(published.status, "published")
        self.assertEqual(published.attempt_count, 2)
        self.assertEqual(published.pinterest_pin_id, "retry-pin")

    def test_offline_validation_failure_does_not_mutate_persisted_state(self):
        item = self.schedule(self.now - timedelta(minutes=1))
        publisher = StubPublisher(error=RuntimeError("invalid package"))
        before = self.queue_path.read_bytes()

        result = QueueProcessor(self.queue, publisher).process_due(now=self.now)

        self.assertEqual(result[0].outcome, "validation_failed")
        self.assertEqual(self.queue_path.read_bytes(), before)
        self.assertEqual(self.queue.get(item.id).status, "scheduled")


if __name__ == "__main__":
    unittest.main()
