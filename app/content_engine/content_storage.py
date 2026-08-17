import json
import os
import re
import uuid
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.content_engine.content_calendar_engine import ScheduledContent


class DuplicateTopicError(ValueError):
    """Raised when a topic has already been stored as a scheduled post."""


class DuplicatePublishDateError(ValueError):
    """Raised when content has already been stored for a publish date."""


class ContentStorage:
    """Persists scheduled Pinterest content packages as timestamped JSON files."""

    def __init__(self, storage_directory: Path | None = None):
        project_root = Path(__file__).resolve().parents[2]
        self.storage_directory = storage_directory or project_root / "output" / "content_packages"

    def has_topic(self, topic: str) -> bool:
        normalized_topic = topic.casefold()
        return normalized_topic in self.stored_topics()

    def has_publish_date(self, publish_date: date) -> bool:
        return self.path_for_publish_date(publish_date) is not None

    def path_for_publish_date(self, publish_date: date) -> Path | None:
        target_date = publish_date.isoformat()
        for path, record in self._stored_records():
            if record.get("publish_date") == target_date:
                return path
        return None

    def record_for_publish_date(self, publish_date: date) -> dict | None:
        target_date = publish_date.isoformat()
        for _, record in self._stored_records():
            if record.get("publish_date") == target_date:
                return record
        return None

    def update_image_state(self, publish_date: date, image_state: dict) -> Path:
        return self._update_state(publish_date, "image", image_state)

    def update_pinterest_publication(self, publish_date: date, publication_state: dict) -> Path:
        """Atomically persist Pinterest publication metadata on a content package."""
        return self._update_state(publish_date, "pinterest_publication", publication_state)

    def _update_state(self, publish_date: date, key: str, state: dict) -> Path:
        path = self.path_for_publish_date(publish_date)
        if path is None:
            raise RuntimeError(
                f"No content package exists for publish date: {publish_date.isoformat()}"
            )

        record = json.loads(path.read_text(encoding="utf-8"))
        record[key] = state
        temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return path

    def stored_topics(self) -> set[str]:
        topics = set()
        for _, record in self._stored_records():
            topic = record.get("topic")
            if isinstance(topic, str):
                topics.add(topic.casefold())

        return topics

    def save(self, scheduled_content: "ScheduledContent") -> Path:
        if self.has_publish_date(scheduled_content.publish_date):
            raise DuplicatePublishDateError(
                "A scheduled content package already exists for publish date: "
                f"{scheduled_content.publish_date.isoformat()}"
            )

        if self.has_topic(scheduled_content.topic):
            raise DuplicateTopicError(
                f"A scheduled content package already exists for topic: {scheduled_content.topic}"
            )

        created_at = datetime.now(timezone.utc)
        timestamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
        filename = f"{timestamp}_{self._slugify(scheduled_content.topic)}.json"
        record = {
            "created_at": created_at.isoformat(),
            "publish_date": scheduled_content.publish_date.isoformat(),
            "topic": scheduled_content.topic,
            "content_package": asdict(scheduled_content.content_package),
        }

        self.storage_directory.mkdir(parents=True, exist_ok=True)
        path = self.storage_directory / filename
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def _stored_records(self):
        if not self.storage_directory.exists():
            return

        for path in self.storage_directory.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            if isinstance(record, dict):
                yield path, record

    @staticmethod
    def _slugify(topic: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", topic.casefold()).strip("-")
        return slug or "topic"
