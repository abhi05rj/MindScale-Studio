"""Content-package to Pinterest publication orchestration."""

import base64
import ipaddress
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

from app.content_engine import ContentStorage
from app.pinterest.client import PinterestApiClient
from app.pinterest.config import PinterestConfig


class PinterestPayloadError(ValueError):
    pass


class DuplicatePinError(RuntimeError):
    pass


@dataclass(frozen=True)
class PublicationResult:
    status: str
    payload: dict
    pin_id: str | None = None


class PinterestPublisher:
    def __init__(
        self,
        storage: ContentStorage,
        config: PinterestConfig | None = None,
        client: PinterestApiClient | None = None,
    ):
        self.storage = storage
        self.config = config or PinterestConfig.from_env()
        self.client = client or PinterestApiClient(self.config)

    def publish(self, publish_date: date, dry_run: bool = False) -> PublicationResult:
        record = self.storage.record_for_publish_date(publish_date)
        if record is None:
            raise PinterestPayloadError(
                f"No content package exists for publish date: {publish_date.isoformat()}"
            )
        prior = record.get("pinterest_publication", {})
        if prior.get("pin_id"):
            raise DuplicatePinError(f"Content package is already published as Pin {prior['pin_id']}")

        # Dry-run is deliberately read-only: validation failures and successes must
        # not create publication state that could be confused with an API attempt.
        if dry_run:
            payload = self.build_payload(record)
            return PublicationResult("dry_run_validated", payload)

        try:
            payload = self.build_payload(record)
            self.config.validate_for_live_publish()
            self._persist(publish_date, "publishing")
            self.client.get_board(self.config.board_id)
            response = self.client.create_pin(payload)
            pin_id = response.get("id")
            if not isinstance(pin_id, str) or not pin_id:
                raise PinterestPayloadError("Pinterest create Pin response did not contain a Pin ID")
            self._persist(publish_date, "published", pin_id=pin_id)
            return PublicationResult("published", payload, pin_id)
        except (DuplicatePinError, KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            self._persist(publish_date, "failed", error=str(error))
            raise

    def build_payload(self, record: dict) -> dict:
        pinterest = record.get("content_package", {}).get("pinterest", {})
        image_path = Path(record.get("image", {}).get("final_path", ""))
        title = pinterest.get("pinterest_title")
        description = pinterest.get("pinterest_description")
        destination_url = pinterest.get("destination_url") or pinterest.get("pinterest_destination_url")
        missing = [
            name
            for name, value in (
                ("title", title),
                ("description", description),
                ("PINTEREST_BOARD_ID", self.config.board_id),
            )
            if not isinstance(value, str) or not value.strip()
        ]
        if missing:
            raise PinterestPayloadError("Missing publishing payload fields: " + ", ".join(missing))
        if len(title.strip()) > 100:
            raise PinterestPayloadError("Pinterest title must be 100 characters or fewer")
        if len(description.strip()) > 500:
            raise PinterestPayloadError("Pinterest description must be 500 characters or fewer")
        clean_destination_url = None
        if isinstance(destination_url, str) and destination_url.strip():
            clean_destination_url = destination_url.strip()
            self._validate_public_destination_url(clean_destination_url)
        if not image_path.is_file():
            raise PinterestPayloadError(f"Final Pinterest image does not exist: {image_path}")
        try:
            with Image.open(image_path) as image:
                image.verify()
                if image.format != "PNG":
                    raise PinterestPayloadError("Final Pinterest image must be a PNG")
        except (UnidentifiedImageError, OSError) as error:
            raise PinterestPayloadError(f"Final Pinterest image is invalid: {image_path}") from error

        encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")
        payload = {
            "board_id": self.config.board_id,
            "title": title.strip(),
            "description": description.strip(),
            "media_source": {
                "source_type": "image_base64",
                "content_type": "image/png",
                "data": encoded_image,
            },
        }
        if clean_destination_url is not None:
            payload["link"] = clean_destination_url
        return payload

    @staticmethod
    def _validate_public_destination_url(destination_url: str) -> None:
        parsed = urlparse(destination_url)
        hostname = parsed.hostname
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or hostname.casefold() == "localhost"
            or hostname.casefold().endswith(".local")
        ):
            raise PinterestPayloadError(
                "Pinterest destination URL must be an explicitly configured public HTTP(S) URL"
            )
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            # A non-local hostname with a dot is structurally public. Deliberately
            # avoid DNS resolution here so dry-run remains fully offline.
            if "." not in hostname:
                raise PinterestPayloadError(
                    "Pinterest destination URL must be an explicitly configured public HTTP(S) URL"
                )
        else:
            if not address.is_global:
                raise PinterestPayloadError(
                    "Pinterest destination URL must be an explicitly configured public HTTP(S) URL"
                )

    def _persist(
        self,
        publish_date: date,
        status: str,
        *,
        pin_id: str | None = None,
        error: str | None = None,
    ) -> None:
        state = {
            "status": status,
            "pin_id": pin_id,
            "board_id": self.config.board_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error,
        }
        self.storage.update_pinterest_publication(publish_date, state)
