"""Safe queue processing with offline validation as the default."""

from dataclasses import dataclass
from datetime import date, datetime

from app.pinterest import PinterestPublisher
from app.scheduling.queue import PublicationQueue, QueueItem


@dataclass(frozen=True)
class ProcessResult:
    item_id: str
    outcome: str
    pin_id: str | None = None
    error: str | None = None


class QueueProcessor:
    def __init__(self, queue: PublicationQueue, publisher: PinterestPublisher):
        self.queue = queue
        self.publisher = publisher

    def process_due(self, *, now: datetime | None = None, live: bool = False) -> list[ProcessResult]:
        results = []
        for item in self.queue.due_items(now):
            results.append(self.process_item(item, live=live))
        return results

    def process_item(self, item: QueueItem, *, live: bool = False) -> ProcessResult:
        current = self.queue.get(item.id)
        if current.status == "published":
            return ProcessResult(current.id, "already_published", current.pinterest_pin_id)
        if current.status not in {"scheduled", "failed"}:
            return ProcessResult(current.id, "not_processable", error=current.status)
        self.queue.validate_reference(current)
        publish_date = date.fromisoformat(current.content_publish_date)

        if not live:
            try:
                self.publisher.publish(publish_date, dry_run=True)
            except Exception as error:
                return ProcessResult(current.id, "validation_failed", error=str(error))
            return ProcessResult(current.id, "dry_run_validated")

        processing = self.queue.mark_processing(current.id)
        try:
            publication = self.publisher.publish(publish_date, dry_run=False)
            if not publication.pin_id:
                raise RuntimeError("Pinterest publisher returned no Pin ID.")
            published = self.queue.mark_published(processing.id, publication.pin_id)
            return ProcessResult(published.id, "published", published.pinterest_pin_id)
        except Exception as error:
            self.queue.mark_failed(processing.id, str(error))
            return ProcessResult(processing.id, "failed", error=str(error))
