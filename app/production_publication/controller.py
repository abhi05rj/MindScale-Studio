"""Fail-closed controller for the first manual Pinterest Trial publication."""

import json
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.content_engine import ContentStorage
from app.image_engine import PinterestImageValidator
from app.pinterest import PinterestConfig, PinterestPublisher
from app.pinterest.payload import PinterestPayloadBuilder, PinterestPayloadError
from app.pinterest.publisher import PublicationOutcomeUnknownError
from app.production_publication.state import PublicationAttemptStorage
from app.runtime_paths import resolve_runtime_reference, stable_runtime_reference
from app.scheduling import PublicationQueue


class PublicationPreflightError(RuntimeError):
    pass


class LivePublishConfirmationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ControlledPublicationResult:
    queue_item_id: str
    status: str
    publish_date: str
    title: str
    board_id: str
    image_path: str
    attempt_count: int
    pin_id: str | None = None
    error: str | None = None

    def safe_summary(self) -> dict:
        return {
            "queue_item_id": self.queue_item_id,
            "status": self.status,
            "publish_date": self.publish_date,
            "title": self.title,
            "board_id": self.board_id,
            "image_path": self.image_path,
            "attempt_count": self.attempt_count,
            "pin_id": self.pin_id,
            "error": self.error,
        }


class ControlledPublicationController:
    MAX_ATTEMPTS = 3
    STALE_CLAIM_AFTER = timedelta(minutes=20)

    def __init__(
        self,
        queue: PublicationQueue,
        content_storage: ContentStorage,
        attempt_storage: PublicationAttemptStorage,
        *,
        config: PinterestConfig | None = None,
        publisher_factory: Callable[..., PinterestPublisher] = PinterestPublisher,
        clock: Callable[[], datetime] | None = None,
    ):
        self.queue = queue
        self.content_storage = content_storage
        self.attempt_storage = attempt_storage
        self.config = config or PinterestConfig.from_env()
        self.publisher_factory = publisher_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def preflight(self, item_id: str) -> ControlledPublicationResult:
        details = self._validate(item_id)
        current = self.attempt_storage.load(item_id)
        if current:
            if current["status"] == "publication_unknown":
                raise PublicationPreflightError(
                    "Publication outcome is unknown; manual Pinterest reconciliation is required."
                )
            if current["status"] == "published" or current.get("pinterest_pin_id"):
                raise PublicationPreflightError("Publication attempt is already published.")
            if current["status"] in {"claimed", "publishing"}:
                raise PublicationPreflightError(
                    f"Publication attempt is already {current['status']}."
                )
        attempt_count = current["attempt_count"] if current else 0
        self.attempt_storage.save(
            item_id,
            status="ready",
            last_error=None,
            board_id=details["board_id"],
        )
        return ControlledPublicationResult(attempt_count=attempt_count, status="ready", **details)

    def publish(
        self, item_id: str, *, confirm_live_publish: bool = False
    ) -> ControlledPublicationResult:
        if not confirm_live_publish:
            raise LivePublishConfirmationError(
                "Live Pinterest publication requires confirm_live_publish=true."
            )
        self._validate_live_credentials()
        self._recover_stale_claim(item_id)
        details = self._validate(item_id)
        prior = self.attempt_storage.load(item_id)
        if prior and prior["status"] == "publication_unknown":
            raise PublicationPreflightError(
                "Publication outcome is unknown; automatic retry is forbidden."
            )
        self.attempt_storage.claim(item_id, details["board_id"], self.MAX_ATTEMPTS)
        processing_started = False
        try:
            self.queue.mark_processing(item_id)
            processing_started = True
            self.attempt_storage.save(item_id, status="publishing")
            publisher = self.publisher_factory(
                self.content_storage,
                config=self.config,
            )
            result = publisher.publish(
                datetime.fromisoformat(details["publish_date"]).date(), dry_run=False
            )
            if not result.pin_id:
                raise PublicationOutcomeUnknownError(
                    "Pinterest publication returned without a Pin ID."
                )
            self.queue.mark_published(item_id, result.pin_id)
            final = self.attempt_storage.save(
                item_id,
                status="published",
                pinterest_pin_id=result.pin_id,
                last_error=None,
            )
            return ControlledPublicationResult(
                status="published",
                attempt_count=final["attempt_count"],
                pin_id=result.pin_id,
                **details,
            )
        except PublicationOutcomeUnknownError as error:
            final = self.attempt_storage.save(
                item_id, status="publication_unknown", last_error=str(error)
            )
            return ControlledPublicationResult(
                status="publication_unknown",
                attempt_count=final["attempt_count"],
                error=str(error),
                **details,
            )
        except Exception as error:
            if processing_started:
                current_item = self.queue.get(item_id)
                if current_item.status == "processing":
                    self.queue.mark_failed(item_id, str(error))
            final = self.attempt_storage.save(item_id, status="failed", last_error=str(error))
            return ControlledPublicationResult(
                status="failed",
                attempt_count=final["attempt_count"],
                error=str(error),
                **details,
            )

    def _validate(self, item_id: str) -> dict:
        try:
            item = self.queue.get(item_id)
        except KeyError as error:
            raise PublicationPreflightError(f"Queue item does not exist: {item_id}") from error
        if item.status == "published" or item.pinterest_pin_id:
            raise PublicationPreflightError("Queue item is already published.")
        if item.status not in {"scheduled", "failed"}:
            raise PublicationPreflightError(f"Queue item is not publishable: {item.status}.")
        now = self.clock().astimezone(timezone.utc)
        if item.scheduled_datetime > now:
            raise PublicationPreflightError("Queue item is not due for publication.")
        self.queue.validate_reference(item)
        package_path = resolve_runtime_reference(item.content_package_ref)
        try:
            record = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise PublicationPreflightError("Content package is unreadable.") from error
        image = record.get("image", {})
        if image.get("status") != "complete":
            raise PublicationPreflightError("Content package image is not complete.")
        final_path = resolve_runtime_reference(image.get("final_path", ""))
        try:
            PinterestImageValidator().validate(final_path)
        except ValueError as error:
            raise PublicationPreflightError(str(error)) from error
        publication = record.get("pinterest_publication", {})
        if publication.get("status") == "published" or publication.get("pin_id"):
            raise PublicationPreflightError("Content package is already published.")
        board_id = self.config.board_id or "configured-at-live-publication"
        validation_config = replace(self.config, board_id=board_id)
        try:
            payload = PinterestPayloadBuilder(validation_config).build(record)
        except PinterestPayloadError as error:
            raise PublicationPreflightError(str(error)) from error
        return {
            "queue_item_id": item.id,
            "publish_date": item.content_publish_date,
            "title": payload["title"],
            "board_id": board_id,
            "image_path": stable_runtime_reference(final_path),
        }

    def _validate_live_credentials(self) -> None:
        required = {
            "PINTEREST_APP_ID": self.config.app_id,
            "PINTEREST_APP_SECRET": self.config.app_secret,
            "PINTEREST_ACCESS_TOKEN": self.config.access_token,
            "PINTEREST_REFRESH_TOKEN": self.config.refresh_token,
            "PINTEREST_BOARD_ID": self.config.board_id,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise PublicationPreflightError(
                "Missing production Pinterest configuration: " + ", ".join(missing)
            )

    def _recover_stale_claim(self, item_id: str) -> None:
        state = self.attempt_storage.load(item_id)
        if not state or state["status"] not in {"claimed", "publishing"}:
            return
        claimed_at = datetime.fromisoformat(state["claimed_at"])
        if self.clock().astimezone(timezone.utc) - claimed_at <= self.STALE_CLAIM_AFTER:
            raise PublicationPreflightError(f"Publication is already {state['status']}.")
        if state["status"] == "publishing":
            self.attempt_storage.save(
                item_id,
                status="publication_unknown",
                last_error="Publishing was interrupted; outcome requires manual reconciliation.",
            )
            raise PublicationPreflightError(
                "Stale publishing attempt has an unknown outcome; automatic retry is forbidden."
            )
        item = self.queue.get(item_id)
        if item.status == "processing":
            self.queue.mark_failed(item_id, "Recovered stale pre-publication claim.")
        self.attempt_storage.save(
            item_id,
            status="failed",
            claim_id=None,
            claimed_at=None,
            last_error="Recovered stale pre-publication claim.",
        )
