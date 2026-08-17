import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from PIL import Image

from app.content_engine import ContentStorage
from app.pinterest import (
    DuplicatePinError,
    PinterestApiError,
    PinterestConfig,
    PinterestPayloadError,
    PinterestPublisher,
)


class FakePinterestClient:
    def __init__(self, error=None):
        self.error = error
        self.board_lookups = []
        self.pin_payloads = []

    def get_board(self, board_id):
        self.board_lookups.append(board_id)
        if self.error:
            raise self.error
        return {"id": board_id, "name": "Mind Scale"}

    def create_pin(self, payload):
        self.pin_payloads.append(payload)
        if self.error:
            raise self.error
        return {"id": "987654321"}


class PinterestPublisherTests(unittest.TestCase):
    run_date = date(2026, 8, 17)

    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_directory.name)
        self.image_path = self.root / "final.png"
        Image.new("RGB", (1000, 1500), "navy").save(self.image_path)
        self.package_path = self.root / "package.json"
        self.package_path.write_text(
            json.dumps(
                {
                    "publish_date": self.run_date.isoformat(),
                    "content_package": {
                        "pinterest": {
                            "pinterest_title": "A useful visual guide",
                            "pinterest_description": "Learn the concept through one clear visual.",
                        }
                    },
                    "image": {"status": "complete", "final_path": str(self.image_path)},
                }
            ),
            encoding="utf-8",
        )
        self.storage = ContentStorage(self.root)
        self.config = PinterestConfig(access_token="test-token", board_id="board-123")

    def tearDown(self):
        self.temp_directory.cleanup()

    def publisher(self, client=None, config=None):
        return PinterestPublisher(
            self.storage,
            config=config or self.config,
            client=client or FakePinterestClient(),
        )

    def record(self):
        return json.loads(self.package_path.read_text(encoding="utf-8"))

    def test_successful_publish_looks_up_board_creates_pin_and_persists_result(self):
        client = FakePinterestClient()
        result = self.publisher(client).publish(self.run_date)

        state = self.record()["pinterest_publication"]
        self.assertEqual(result.pin_id, "987654321")
        self.assertEqual(client.board_lookups, ["board-123"])
        self.assertEqual(len(client.pin_payloads), 1)
        self.assertNotIn("link", client.pin_payloads[0])
        self.assertEqual(client.pin_payloads[0]["media_source"]["source_type"], "image_base64")
        self.assertEqual(state["status"], "published")
        self.assertEqual(state["pin_id"], "987654321")
        self.assertEqual(state["board_id"], "board-123")
        self.assertIsNotNone(state["timestamp"])
        self.assertIsNone(state["error"])

    def test_missing_live_credentials_fails_and_persists_error(self):
        config = PinterestConfig(board_id="board-123")
        with self.assertRaisesRegex(ValueError, "PINTEREST_ACCESS_TOKEN"):
            self.publisher(config=config).publish(self.run_date)

        state = self.record()["pinterest_publication"]
        self.assertEqual(state["status"], "failed")
        self.assertIn("PINTEREST_ACCESS_TOKEN", state["error"])

    def test_missing_or_invalid_image_is_rejected(self):
        self.image_path.unlink()
        with self.assertRaisesRegex(PinterestPayloadError, "does not exist"):
            self.publisher().publish(self.run_date, dry_run=True)

        self.image_path.write_text("not an image", encoding="utf-8")
        with self.assertRaisesRegex(PinterestPayloadError, "is invalid"):
            self.publisher().publish(self.run_date, dry_run=True)

    def test_api_failure_is_persisted(self):
        client = FakePinterestClient(PinterestApiError("Pinterest unavailable", 503))
        with self.assertRaisesRegex(PinterestApiError, "Pinterest unavailable"):
            self.publisher(client).publish(self.run_date)

        state = self.record()["pinterest_publication"]
        self.assertEqual(state["status"], "failed")
        self.assertEqual(state["error"], "Pinterest unavailable")
        self.assertIsNone(state["pin_id"])

    def test_existing_pin_id_prevents_duplicate_and_does_not_call_api(self):
        record = self.record()
        record["pinterest_publication"] = {"status": "published", "pin_id": "existing-pin"}
        self.package_path.write_text(json.dumps(record), encoding="utf-8")
        client = FakePinterestClient()

        with self.assertRaisesRegex(DuplicatePinError, "existing-pin"):
            self.publisher(client).publish(self.run_date)

        self.assertEqual(client.board_lookups, [])
        self.assertEqual(client.pin_payloads, [])

    def test_dry_run_validates_without_credentials_state_changes_or_api_calls(self):
        client = FakePinterestClient()
        config = PinterestConfig(board_id="board-123")
        before = self.package_path.read_bytes()
        result = self.publisher(client, config).publish(self.run_date, dry_run=True)

        self.assertEqual(result.status, "dry_run_validated")
        self.assertEqual(client.board_lookups, [])
        self.assertEqual(client.pin_payloads, [])
        self.assertIsNone(result.pin_id)
        self.assertNotIn("link", result.payload)
        self.assertIn("data", result.payload["media_source"])
        self.assertGreater(len(result.payload["media_source"]["data"]), 0)
        self.assertEqual(self.package_path.read_bytes(), before)

    def test_explicit_public_destination_url_is_included(self):
        record = self.record()
        record["content_package"]["pinterest"]["destination_url"] = (
            "https://example.com/visual-guide"
        )
        self.package_path.write_text(json.dumps(record), encoding="utf-8")

        result = self.publisher().publish(self.run_date, dry_run=True)

        self.assertEqual(result.payload["link"], "https://example.com/visual-guide")

    def test_non_public_destination_url_is_rejected(self):
        for destination_url in ("http://localhost/pin", "http://127.0.0.1/pin", "not-a-url"):
            with self.subTest(destination_url=destination_url):
                record = self.record()
                record["content_package"]["pinterest"]["destination_url"] = destination_url
                self.package_path.write_text(json.dumps(record), encoding="utf-8")
                with self.assertRaisesRegex(PinterestPayloadError, "public HTTP"):
                    self.publisher().publish(self.run_date, dry_run=True)


if __name__ == "__main__":
    unittest.main()
