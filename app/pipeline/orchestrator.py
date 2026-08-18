"""Offline end-to-end orchestration from a planned day to the local queue."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timezone
from pathlib import Path

from app.automation_runner import DEFAULT_IMAGE_DIRECTORY, run_daily_automation
from app.content_engine import (
    ContentPackage,
    ContentPipelineController,
    ContentStorage,
    ScheduledContent,
)
from app.content_engine.content_quality import format_pattern_text, pattern_for_angle
from app.image_engine import LocalImageProvider, PillowTemplateProvider
from app.pipeline.state import PipelineStateStorage
from app.planning import PlannedDay, WeeklyPlan, WeeklyPlanStorage
from app.runtime_paths import resolve_runtime_reference, stable_runtime_reference
from app.scheduling import DuplicateQueueItemError, PublicationQueue, QueueItem


@dataclass(frozen=True)
class PipelineResult:
    target_date: date
    status: str
    content_package_path: Path | None
    queue_item_id: str | None


class PlannedContentEngine:
    """Adapter that lets Automation V1 generate the exact planned editorial item."""

    def __init__(
        self,
        planned_day: PlannedDay,
        content_storage: ContentStorage,
        pipeline_controller: ContentPipelineController | None = None,
    ):
        self.planned_day = planned_day
        self.content_storage = content_storage
        self.pipeline_controller = pipeline_controller or ContentPipelineController()

    def select_topic(self, publish_date: date) -> str:
        self._validate_date(publish_date)
        return self.planned_day.topic

    def create_scheduled_content(self, publish_date: date) -> ScheduledContent:
        self._validate_date(publish_date)
        base_strategy = self.pipeline_controller.idea_generator.generate(self.planned_day.topic)
        planned_pattern = pattern_for_angle(
            self.planned_day.angle_pattern or self.planned_day.content_angle
        )
        strategy = replace(
            base_strategy,
            title=self.planned_day.working_title,
            hook=self.planned_day.hook or self.planned_day.content_angle,
            **(
                {
                    "story_structure": {
                        "opening": format_pattern_text(
                            planned_pattern.opening, self.planned_day.topic
                        ),
                        "escalation": format_pattern_text(
                            planned_pattern.escalation, self.planned_day.topic
                        ),
                        "takeaway": format_pattern_text(
                            planned_pattern.takeaway, self.planned_day.topic
                        ),
                    },
                    "visual_direction": format_pattern_text(
                        planned_pattern.visual_direction, self.planned_day.topic
                    ),
                }
                if planned_pattern
                else {}
            ),
        )
        package = ContentPackage(
            topic=self.planned_day.topic,
            strategy=strategy,
            pinterest=self.pipeline_controller.pinterest_formatter.format(strategy),
            scores=self.pipeline_controller.scoring_engine.score(strategy),
            local_editorial_angle=self.planned_day.content_angle,
        )
        scheduled = ScheduledContent(
            publish_date=publish_date,
            topic=self.planned_day.topic,
            content_package=package,
        )
        self.content_storage.save(scheduled, allow_repeated_topic=True)
        return scheduled

    def _validate_date(self, publish_date: date) -> None:
        if self.planned_day.publish_date != publish_date.isoformat():
            raise ValueError("Planned content date does not match the pipeline target date.")


class PipelineOrchestrator:
    def __init__(
        self,
        *,
        plan_storage: WeeklyPlanStorage | None = None,
        content_storage: ContentStorage | None = None,
        publication_queue: PublicationQueue | None = None,
        state_storage: PipelineStateStorage | None = None,
        pipeline_controller: ContentPipelineController | None = None,
        image_provider: LocalImageProvider | None = None,
        image_directory: Path | None = None,
        publication_time_utc: time = time(9, 0),
        log: Callable[[str], None] = print,
    ):
        self.plan_storage = plan_storage or WeeklyPlanStorage()
        self.content_storage = content_storage or ContentStorage()
        self.publication_queue = publication_queue or PublicationQueue()
        self.state_storage = state_storage or PipelineStateStorage()
        self.pipeline_controller = pipeline_controller or ContentPipelineController()
        self.image_provider = image_provider or PillowTemplateProvider()
        self.image_directory = Path(image_directory or DEFAULT_IMAGE_DIRECTORY)
        self.publication_time_utc = publication_time_utc
        self.log = log

    def run(self, target_date: date) -> PipelineResult:
        plan, planned_day = self._planned_day_for(target_date)
        state = self.state_storage.initialize(
            target_date, plan_start_date=plan.start_date, topic=planned_day.topic
        )
        self.log(f"PIPELINE START: {target_date.isoformat()} ({planned_day.topic})")

        existing_queue_item = self._queue_item_from_state(state)
        if state.get("status") == "queued" and existing_queue_item is not None:
            package_path = self._optional_path(state.get("content_package_ref"))
            self.log(f"PIPELINE/NO-OP already queued: {existing_queue_item.id}")
            return PipelineResult(target_date, "queued", package_path, existing_queue_item.id)

        try:
            self.state_storage.transition(target_date, "generating", last_error=None)
            engine = PlannedContentEngine(
                planned_day, self.content_storage, self.pipeline_controller
            )
            exit_code = run_daily_automation(
                target_date,
                engine,
                log=lambda message: self.log(f"AUTOMATION: {message}"),
                image_provider=self.image_provider,
                image_directory=self.image_directory,
            )
            if exit_code != 0:
                record = self.content_storage.record_for_publish_date(target_date) or {}
                detail = record.get("image", {}).get("error") or "Automation V1 failed."
                raise RuntimeError(detail)

            package_path = self.content_storage.path_for_publish_date(target_date)
            if package_path is None:
                raise RuntimeError("Automation completed without a persisted content package.")
            package_path = package_path.resolve()
            self.state_storage.transition(
                target_date,
                "generated",
                content_package_ref=stable_runtime_reference(package_path),
                last_error=None,
            )
            self.log(f"PIPELINE GENERATED: {package_path}")

            queue_item = self._schedule_or_find(package_path, target_date)
            self.state_storage.transition(
                target_date,
                "queued",
                content_package_ref=stable_runtime_reference(package_path),
                queue_item_id=queue_item.id,
                last_error=None,
            )
            self.log(f"PIPELINE QUEUED: {queue_item.id}")
            self.log("PIPELINE COMPLETE: queued")
            return PipelineResult(target_date, "queued", package_path, queue_item.id)
        except Exception as error:
            package_path = self.content_storage.path_for_publish_date(target_date)
            self.state_storage.transition(
                target_date,
                "failed",
                content_package_ref=(
                    stable_runtime_reference(package_path) if package_path else None
                ),
                last_error=str(error),
            )
            self.log(f"PIPELINE FAILED: {error}")
            return PipelineResult(target_date, "failed", package_path, None)

    def _planned_day_for(self, target_date: date) -> tuple[WeeklyPlan, PlannedDay]:
        matches = []
        for plan in self.plan_storage.load_all():
            for planned_day in plan.days:
                if planned_day.publish_date == target_date.isoformat():
                    matches.append((plan, planned_day))
        if not matches:
            raise ValueError(f"No content plan contains target date {target_date.isoformat()}.")
        if len(matches) > 1:
            raise ValueError(f"Multiple content plans contain target date {target_date.isoformat()}.")
        plan, planned_day = matches[0]
        if planned_day.status == "needs_review":
            raise ValueError(
                f"Planned content for {target_date.isoformat()} requires editorial review."
            )
        return plan, planned_day

    def _schedule_or_find(self, package_path: Path, target_date: date) -> QueueItem:
        scheduled_for = datetime.combine(
            target_date, self.publication_time_utc, tzinfo=timezone.utc
        )
        try:
            return self.publication_queue.schedule(package_path, scheduled_for)
        except DuplicateQueueItemError:
            resolved = package_path.resolve()
            for item in self.publication_queue.list_items():
                if resolve_runtime_reference(item.content_package_ref) == resolved:
                    return item
            raise

    def _queue_item_from_state(self, state: dict) -> QueueItem | None:
        item_id = state.get("queue_item_id")
        if not item_id:
            return None
        try:
            return self.publication_queue.get(item_id)
        except KeyError:
            return None

    @staticmethod
    def _optional_path(value: str | None) -> Path | None:
        return resolve_runtime_reference(value) if value else None
