"""Atomic JSON-backed publication queue using UTC timestamps."""

import json
import os
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path

from app.runtime_paths import resolve_runtime_reference, stable_runtime_reference


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_QUEUE_PATH = PROJECT_ROOT / ".local-runtime" / "publication_queue.json"
QUEUE_STATUSES = {"scheduled", "processing", "published", "failed", "cancelled"}


class QueueValidationError(ValueError):
    pass


class QueueItemNotFoundError(KeyError):
    pass


class DuplicateQueueItemError(ValueError):
    pass


class InvalidQueueTransitionError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def require_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise QueueValidationError(f"{field_name} must include a timezone offset.")
    return value.astimezone(timezone.utc)


def parse_datetime(value: str, field_name: str = "datetime") -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise QueueValidationError(f"{field_name} must be a valid ISO 8601 datetime.") from error
    return require_utc(parsed, field_name)


@dataclass(frozen=True)
class QueueItem:
    id: str
    content_package_ref: str
    content_publish_date: str
    scheduled_for: str
    platform: str
    status: str
    created_at: str
    attempt_count: int
    last_error: str | None
    pinterest_pin_id: str | None

    @classmethod
    def from_dict(cls, value: dict) -> "QueueItem":
        try:
            item = cls(**value)
        except (TypeError, KeyError) as error:
            raise QueueValidationError("Queue item has missing or unexpected fields.") from error
        item.validate()
        return item

    def validate(self) -> None:
        try:
            uuid.UUID(self.id)
        except (ValueError, AttributeError) as error:
            raise QueueValidationError("Queue item ID must be a UUID.") from error
        if self.platform != "pinterest":
            raise QueueValidationError("Queue item platform must be pinterest.")
        if self.status not in QUEUE_STATUSES:
            raise QueueValidationError(f"Unsupported queue status: {self.status!r}.")
        if not isinstance(self.attempt_count, int) or self.attempt_count < 0:
            raise QueueValidationError("Queue attempt count must be a non-negative integer.")
        parse_datetime(self.scheduled_for, "scheduled_for")
        parse_datetime(self.created_at, "created_at")
        try:
            date.fromisoformat(self.content_publish_date)
        except ValueError as error:
            raise QueueValidationError("Content publish date must use YYYY-MM-DD.") from error
        if self.status == "published" and not self.pinterest_pin_id:
            raise QueueValidationError("A published queue item must contain a Pinterest Pin ID.")
        if not self.content_package_ref:
            raise QueueValidationError("Content package reference is required.")

    @property
    def scheduled_datetime(self) -> datetime:
        return parse_datetime(self.scheduled_for, "scheduled_for")


class PublicationQueue:
    """Persistent queue with atomic whole-file updates."""

    def __init__(self, queue_path: Path | None = None):
        self.queue_path = Path(queue_path or DEFAULT_QUEUE_PATH)

    def schedule(
        self,
        content_package_path: Path,
        scheduled_for: datetime,
        *,
        now: datetime | None = None,
    ) -> QueueItem:
        package_path = Path(content_package_path).resolve()
        publish_date = self._validate_content_package(package_path)
        scheduled_utc = require_utc(scheduled_for, "scheduled_for")
        created_utc = require_utc(now or utc_now(), "created_at")
        items = self.list_items()
        for existing in items:
            if (
                resolve_runtime_reference(existing.content_package_ref) == package_path
                and existing.status in {"scheduled", "processing", "published"}
            ):
                raise DuplicateQueueItemError(
                    f"Content package is already queued as item {existing.id}."
                )
        item = QueueItem(
            id=str(uuid.uuid4()),
            content_package_ref=stable_runtime_reference(package_path),
            content_publish_date=publish_date,
            scheduled_for=scheduled_utc.isoformat(),
            platform="pinterest",
            status="scheduled",
            created_at=created_utc.isoformat(),
            attempt_count=0,
            last_error=None,
            pinterest_pin_id=None,
        )
        self._write(items + [item])
        return item

    def list_items(self) -> list[QueueItem]:
        if not self.queue_path.exists():
            return []
        try:
            document = json.loads(self.queue_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise QueueValidationError(f"Publication queue is unreadable: {self.queue_path}") from error
        if not isinstance(document, dict) or document.get("version") != 1:
            raise QueueValidationError("Publication queue has an unsupported format version.")
        values = document.get("items")
        if not isinstance(values, list):
            raise QueueValidationError("Publication queue items must be a list.")
        return [QueueItem.from_dict(value) for value in values]

    def get(self, item_id: str) -> QueueItem:
        for item in self.list_items():
            if item.id == item_id:
                return item
        raise QueueItemNotFoundError(f"Queue item not found: {item_id}")

    def cancel(self, item_id: str) -> QueueItem:
        item = self.get(item_id)
        if item.status != "scheduled":
            raise InvalidQueueTransitionError(
                f"Only a scheduled queue item can be cancelled; found {item.status}."
            )
        return self._replace(replace(item, status="cancelled"))

    def due_items(self, now: datetime | None = None) -> list[QueueItem]:
        current = require_utc(now or utc_now(), "now")
        due = [
            item
            for item in self.list_items()
            if item.status in {"scheduled", "failed"} and item.scheduled_datetime <= current
        ]
        return sorted(due, key=lambda item: (item.scheduled_for, item.created_at, item.id))

    def mark_processing(self, item_id: str) -> QueueItem:
        item = self.get(item_id)
        if item.status not in {"scheduled", "failed"}:
            raise InvalidQueueTransitionError(
                f"Queue item cannot enter processing from {item.status}."
            )
        return self._replace(
            replace(
                item,
                status="processing",
                attempt_count=item.attempt_count + 1,
                last_error=None,
            )
        )

    def mark_published(self, item_id: str, pin_id: str) -> QueueItem:
        if not pin_id:
            raise QueueValidationError("Pinterest Pin ID is required for published status.")
        item = self.get(item_id)
        if item.status != "processing":
            raise InvalidQueueTransitionError(
                f"Queue item cannot be published from {item.status}."
            )
        return self._replace(
            replace(item, status="published", pinterest_pin_id=pin_id, last_error=None)
        )

    def mark_failed(self, item_id: str, error: str) -> QueueItem:
        item = self.get(item_id)
        if item.status != "processing":
            raise InvalidQueueTransitionError(f"Queue item cannot fail from {item.status}.")
        return self._replace(replace(item, status="failed", last_error=error or "Unknown error"))

    def validate_reference(self, item: QueueItem) -> None:
        publish_date = self._validate_content_package(
            resolve_runtime_reference(item.content_package_ref)
        )
        if publish_date != item.content_publish_date:
            raise QueueValidationError("Queued content reference publish date has changed.")

    def _replace(self, replacement: QueueItem) -> QueueItem:
        replacement.validate()
        items = self.list_items()
        for index, item in enumerate(items):
            if item.id == replacement.id:
                items[index] = replacement
                self._write(items)
                return replacement
        raise QueueItemNotFoundError(f"Queue item not found: {replacement.id}")

    def _write(self, items: list[QueueItem]) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.queue_path.with_name(
            f".{self.queue_path.name}.{uuid.uuid4().hex}.tmp"
        )
        document = {"version": 1, "items": [asdict(item) for item in items]}
        try:
            temporary_path.write_text(
                json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(temporary_path, self.queue_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    @staticmethod
    def _validate_content_package(package_path: Path) -> str:
        if not package_path.is_file():
            raise QueueValidationError(f"Content package does not exist: {package_path}")
        try:
            record = json.loads(package_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise QueueValidationError(f"Content package is unreadable: {package_path}") from error
        publish_date = record.get("publish_date") if isinstance(record, dict) else None
        try:
            date.fromisoformat(publish_date)
        except (TypeError, ValueError) as error:
            raise QueueValidationError("Content package must contain a valid publish_date.") from error
        return publish_date
