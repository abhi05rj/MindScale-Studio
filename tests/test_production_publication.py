import json
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from PIL import Image

from app.content_engine import ContentStorage
from app.pinterest import PinterestConfig, PublicationOutcomeUnknownError, PublicationResult
from app.production_publication import (
    ControlledPublicationController,
    LivePublishConfirmationError,
    PublicationAttemptStorage,
    PublicationPreflightError,
)
from app.scheduling import PublicationQueue


class PublisherFactory:
    def __init__(self, *, result=None, error=None):
        self.result = result
        self.error = error
        self.constructed = 0
        self.publish_calls = []

    def __call__(self, storage, config):
        self.constructed += 1
        factory = self

        class Publisher:
            def publish(self, publish_date, dry_run=False):
                factory.publish_calls.append((publish_date, dry_run))
                if factory.error:
                    raise factory.error
                return factory.result or PublicationResult(
                    "published", payload={}, pin_id="pin-trial-123"
                )

        return Publisher()


class ProductionPublicationTests(unittest.TestCase):
    publish_date = date(2026, 8, 18)
    now = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.packages = self.root / "output" / "content_packages"
        self.images = self.root / "output" / "images"
        self.packages.mkdir(parents=True)
        self.images.mkdir(parents=True)
        self.image_path = self.images / "pin.png"
        Image.new("RGB", (1000, 1500), "navy").save(self.image_path)
        self.package_path = self.packages / "package.json"
        self.record = {
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
            "pinterest_publication": {"status": "not_published", "pin_id": None},
        }
        self._write_record()
        self.queue = PublicationQueue(self.root / ".local-runtime" / "queue.json")
        self.item = self.queue.schedule(
            self.package_path,
            self.now - timedelta(minutes=1),
            now=self.now - timedelta(hours=1),
        )
        self.attempts = PublicationAttemptStorage(
            self.root / ".local-runtime" / "publication_attempts"
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _write_record(self):
        self.package_path.write_text(json.dumps(self.record), encoding="utf-8")

    @staticmethod
    def live_config():
        return PinterestConfig(
            app_id="app-id",
            app_secret="app-secret",
            access_token="access-token",
            refresh_token="refresh-token",
            board_id="board-id",
        )

    def controller(self, factory, config=None):
        return ControlledPublicationController(
            self.queue,
            ContentStorage(self.packages),
            self.attempts,
            config=config or PinterestConfig(board_id="board-placeholder"),
            publisher_factory=factory,
            clock=lambda: self.now,
        )

    def test_missing_credentials_fails_before_publisher_construction(self):
        factory = PublisherFactory()
        with self.assertRaisesRegex(PublicationPreflightError, "Missing production"):
            self.controller(factory).publish(self.item.id, confirm_live_publish=True)

        self.assertEqual(factory.constructed, 0)
        self.assertIsNone(self.attempts.load(self.item.id))
        self.assertEqual(self.queue.get(self.item.id).status, "scheduled")

    def test_live_flag_absent_fails_before_credentials_or_publisher(self):
        factory = PublisherFactory()
        with self.assertRaises(LivePublishConfirmationError):
            self.controller(factory, self.live_config()).publish(self.item.id)

        self.assertEqual(factory.constructed, 0)
        self.assertIsNone(self.attempts.load(self.item.id))

    def test_successful_preflight_is_offline_and_persists_ready(self):
        factory = PublisherFactory(error=AssertionError("publisher must remain untouched"))
        before = self.queue.queue_path.read_bytes()

        result = self.controller(factory).preflight(self.item.id)

        self.assertEqual(result.status, "ready")
        self.assertEqual(result.title, "What Makes Time So Fascinating?")
        self.assertEqual(factory.constructed, 0)
        self.assertEqual(self.queue.queue_path.read_bytes(), before)
        self.assertEqual(self.attempts.load(self.item.id)["status"], "ready")

    def test_content_package_pin_id_prevents_duplicate(self):
        self.record["pinterest_publication"] = {
            "status": "published",
            "pin_id": "existing-package-pin",
        }
        self._write_record()
        factory = PublisherFactory()

        with self.assertRaisesRegex(PublicationPreflightError, "already published"):
            self.controller(factory).preflight(self.item.id)

        self.assertEqual(factory.constructed, 0)

    def test_stale_claim_is_recovered_before_safe_retry(self):
        factory = PublisherFactory()
        self.attempts.save(
            self.item.id,
            status="claimed",
            claim_id="old-claim",
            claimed_at=(self.now - timedelta(hours=1)).isoformat(),
            attempt_count=1,
        )

        result = self.controller(factory, self.live_config()).publish(
            self.item.id, confirm_live_publish=True
        )

        self.assertEqual(result.status, "published")
        self.assertEqual(result.attempt_count, 2)
        self.assertEqual(self.queue.get(self.item.id).pinterest_pin_id, "pin-trial-123")
        self.assertEqual(factory.constructed, 1)

    def test_failed_api_call_is_safe_and_bounded(self):
        factory = PublisherFactory(error=RuntimeError("Pinterest rejected request"))
        controller = self.controller(factory, self.live_config())

        for expected_attempt in range(1, controller.MAX_ATTEMPTS + 1):
            result = controller.publish(self.item.id, confirm_live_publish=True)
            self.assertEqual(result.status, "failed")
            self.assertEqual(result.attempt_count, expected_attempt)

        with self.assertRaisesRegex(RuntimeError, "retry limit"):
            controller.publish(self.item.id, confirm_live_publish=True)
        self.assertEqual(factory.constructed, controller.MAX_ATTEMPTS)

    def test_ambiguous_result_becomes_unknown_and_is_never_retried(self):
        factory = PublisherFactory(
            error=PublicationOutcomeUnknownError("response lost after create request")
        )
        controller = self.controller(factory, self.live_config())

        result = controller.publish(self.item.id, confirm_live_publish=True)

        self.assertEqual(result.status, "publication_unknown")
        self.assertEqual(self.attempts.load(self.item.id)["status"], "publication_unknown")
        with self.assertRaises(PublicationPreflightError):
            controller.publish(self.item.id, confirm_live_publish=True)
        self.assertEqual(factory.constructed, 1)

    def test_already_published_queue_item_is_blocked(self):
        self.queue.mark_processing(self.item.id)
        self.queue.mark_published(self.item.id, "existing-queue-pin")
        factory = PublisherFactory()

        with self.assertRaisesRegex(PublicationPreflightError, "already published"):
            self.controller(factory).preflight(self.item.id)

        self.assertEqual(factory.constructed, 0)


if __name__ == "__main__":
    unittest.main()
