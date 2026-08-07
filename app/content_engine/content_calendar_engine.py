from dataclasses import asdict, dataclass
from datetime import date, timedelta

from app.content_engine.content_pipeline_controller import ContentPackage, ContentPipelineController
from app.content_engine.content_storage import ContentStorage


@dataclass(frozen=True)
class ScheduledContent:
    publish_date: date
    topic: str
    content_package: ContentPackage

    def to_dict(self) -> dict:
        return asdict(self)


class ContentCalendarEngine:
    """Selects rotating topics and produces ready-to-publish Pinterest packages."""

    DEFAULT_TOPICS = (
        "Universe",
        "Space",
        "Time",
        "Human Perspective",
        "Ocean",
        "Brain",
        "Nature",
    )

    def __init__(
        self,
        pipeline_controller: ContentPipelineController | None = None,
        content_storage: ContentStorage | None = None,
        topics: tuple[str, ...] = DEFAULT_TOPICS,
    ):
        if not topics:
            raise ValueError("At least one calendar topic is required.")

        self.pipeline_controller = pipeline_controller or ContentPipelineController()
        self.content_storage = content_storage or ContentStorage()
        self.topics = topics

    def select_topic(self, publish_date: date | None = None) -> str:
        target_date = publish_date or date.today()
        start_index = target_date.toordinal() % len(self.topics)

        for offset in range(len(self.topics)):
            topic = self.topics[(start_index + offset) % len(self.topics)]
            if not self.content_storage.has_topic(topic):
                return topic

        raise RuntimeError("All calendar topics have already been scheduled.")

    def create_scheduled_content(self, publish_date: date | None = None) -> ScheduledContent:
        target_date = publish_date or date.today()
        topic = self.select_topic(target_date)
        content_package = self.pipeline_controller.create_content_package(topic)

        scheduled_content = ScheduledContent(
            publish_date=target_date,
            topic=topic,
            content_package=content_package,
        )
        self.content_storage.save(scheduled_content)
        return scheduled_content

    def build_calendar(self, start_date: date | None = None, days: int = 7) -> list[ScheduledContent]:
        if days < 1:
            raise ValueError("Calendar length must be at least one day.")

        first_date = start_date or date.today()
        return [
            self.create_scheduled_content(first_date + timedelta(days=offset))
            for offset in range(days)
        ]
