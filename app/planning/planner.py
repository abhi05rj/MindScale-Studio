"""Deterministic seven-day content planner with history-aware de-duplication."""

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from app.planning.storage import WeeklyPlanStorage


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONTENT_HISTORY_DIRECTORY = PROJECT_ROOT / "output" / "content_packages"


@dataclass(frozen=True)
class ContentPillar:
    name: str
    objective: str
    title_patterns: tuple[str, ...]
    angles: tuple[str, ...]

    @classmethod
    def generic(cls, name: str) -> "ContentPillar":
        clean_name = name.strip()
        if not clean_name:
            raise ValueError("Content pillar names cannot be empty.")
        return cls(
            name=clean_name,
            objective=f"Help curious learners understand {clean_name.lower()} through visual storytelling.",
            title_patterns=(
                "A Visual Guide to {topic}",
                "{topic}: The Big Picture",
                "Understanding {topic} at a Glance",
                "A New Way to See {topic}",
            ),
            angles=(
                "Scale and perspective",
                "A surprising everyday comparison",
                "Three ideas explained visually",
                "A misconception made clear",
            ),
        )


DEFAULT_CONTENT_PILLARS = tuple(
    ContentPillar.generic(name)
    for name in (
        "Universe",
        "Space",
        "Time",
        "Human Perspective",
        "Ocean",
        "Brain",
        "Nature",
    )
)


@dataclass(frozen=True)
class PlannedDay:
    publish_date: str
    topic: str
    working_title: str
    content_angle: str
    objective: str
    status: str = "planned"

    @classmethod
    def from_dict(cls, value: dict) -> "PlannedDay":
        try:
            day = cls(**value)
        except TypeError as error:
            raise ValueError("Planned day has missing or unexpected fields.") from error
        day.validate()
        return day

    def validate(self) -> None:
        try:
            date.fromisoformat(self.publish_date)
        except (TypeError, ValueError) as error:
            raise ValueError("Planned publish date must use YYYY-MM-DD.") from error
        for field_name in ("topic", "working_title", "content_angle", "objective"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Planned day {field_name} is required.")
        if self.status != "planned":
            raise ValueError("New content plan entries must use planned status.")


@dataclass(frozen=True)
class WeeklyPlan:
    start_date: str
    created_at: str
    status: str
    days: tuple[PlannedDay, ...]

    @classmethod
    def from_dict(cls, value: dict) -> "WeeklyPlan":
        try:
            plan = cls(
                start_date=value["start_date"],
                created_at=value["created_at"],
                status=value["status"],
                days=tuple(PlannedDay.from_dict(day) for day in value["days"]),
            )
        except (KeyError, TypeError) as error:
            raise ValueError("Weekly plan has missing or invalid fields.") from error
        plan.validate()
        return plan

    @property
    def start_date_value(self) -> date:
        return date.fromisoformat(self.start_date)

    def validate(self) -> None:
        start = self.start_date_value
        try:
            created = datetime.fromisoformat(self.created_at)
        except (TypeError, ValueError) as error:
            raise ValueError("Weekly plan created_at must be an ISO 8601 datetime.") from error
        if created.tzinfo is None or created.utcoffset() is None:
            raise ValueError("Weekly plan created_at must include a timezone.")
        if self.status != "planned":
            raise ValueError("Weekly plan status must be planned.")
        if len(self.days) != 7:
            raise ValueError("A weekly content plan must contain exactly seven days.")
        for offset, day in enumerate(self.days):
            day.validate()
            if day.publish_date != (start + timedelta(days=offset)).isoformat():
                raise ValueError("Weekly plan dates must be seven consecutive days.")
            if offset and day.topic.casefold() == self.days[offset - 1].topic.casefold():
                raise ValueError("Consecutive planned days cannot repeat a topic.")


class ContentPlanner:
    def __init__(
        self,
        *,
        pillars: tuple[ContentPillar, ...] = DEFAULT_CONTENT_PILLARS,
        storage: WeeklyPlanStorage | None = None,
        content_history_directory: Path | None = None,
        clock: Callable[[], datetime] | None = None,
        history_limit: int = 50,
    ):
        unique_pillars = []
        names = set()
        for pillar in pillars:
            normalized = pillar.name.strip().casefold()
            if normalized and normalized not in names:
                unique_pillars.append(pillar)
                names.add(normalized)
        if len(unique_pillars) < 2:
            raise ValueError("At least two distinct content pillars are required.")
        if history_limit < 1:
            raise ValueError("History limit must be at least one.")
        self.pillars = tuple(unique_pillars)
        self.storage = storage or WeeklyPlanStorage()
        self.content_history_directory = Path(
            content_history_directory or DEFAULT_CONTENT_HISTORY_DIRECTORY
        )
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.history_limit = history_limit

    def create_weekly_plan(self, start_date: date, *, replace: bool = False) -> WeeklyPlan:
        if self.storage.exists(start_date) and not replace:
            from app.planning.storage import DuplicateWeeklyPlanError

            raise DuplicateWeeklyPlanError(
                f"A weekly plan already exists for {start_date.isoformat()}. Use --replace explicitly."
            )
        recent_titles, recent_angles = self._recent_history(exclude_start_date=start_date)
        start_index = start_date.toordinal() % len(self.pillars)
        days = []
        for offset in range(7):
            publish_date = start_date + timedelta(days=offset)
            pillar = self.pillars[(start_index + offset) % len(self.pillars)]
            title = self._unique_value(
                pillar.title_patterns,
                recent_titles,
                publish_date,
                pillar.name,
                value_type="title",
            )
            angle = self._unique_value(
                pillar.angles,
                recent_angles,
                publish_date,
                pillar.name,
                value_type="angle",
            )
            recent_titles.add(self._normalize(title))
            recent_angles.add(self._normalize(angle))
            days.append(
                PlannedDay(
                    publish_date=publish_date.isoformat(),
                    topic=pillar.name,
                    working_title=title,
                    content_angle=angle,
                    objective=pillar.objective,
                )
            )
        created_at = self.clock()
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("Planner clock must return a timezone-aware datetime.")
        plan = WeeklyPlan(
            start_date=start_date.isoformat(),
            created_at=created_at.astimezone(timezone.utc).isoformat(),
            status="planned",
            days=tuple(days),
        )
        self.storage.save(plan, replace=replace)
        return plan

    def show_weekly_plan(self, start_date: date) -> WeeklyPlan:
        return self.storage.load(start_date)

    def _recent_history(self, *, exclude_start_date: date) -> tuple[set[str], set[str]]:
        records = []
        if self.content_history_directory.exists():
            for path in self.content_history_directory.glob("*.json"):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(record, dict):
                        records.append(record)
                except (OSError, json.JSONDecodeError):
                    continue
        records.sort(key=lambda record: str(record.get("publish_date", "")), reverse=True)
        titles = set()
        angles = set()
        for record in records[: self.history_limit]:
            package = record.get("content_package", {})
            strategy = package.get("strategy", {})
            pinterest = package.get("pinterest", {})
            for value in (strategy.get("title"), pinterest.get("pinterest_title")):
                if isinstance(value, str) and value.strip():
                    titles.add(self._normalize(value))
            for value in (
                package.get("local_editorial_angle"),
                strategy.get("hook"),
                strategy.get("visual_direction"),
            ):
                if isinstance(value, str) and value.strip():
                    angles.add(self._normalize(value))
        for plan in self.storage.load_all(exclude_start_date=exclude_start_date):
            for day in plan.days:
                titles.add(self._normalize(day.working_title))
                angles.add(self._normalize(day.content_angle))
        return titles, angles

    def _unique_value(
        self,
        candidates: tuple[str, ...],
        used: set[str],
        publish_date: date,
        topic: str,
        *,
        value_type: str,
    ) -> str:
        if not candidates:
            raise ValueError(f"Content pillar {topic!r} has no {value_type} variants.")
        start_index = publish_date.toordinal() % len(candidates)
        for offset in range(len(candidates)):
            candidate = candidates[(start_index + offset) % len(candidates)].format(topic=topic)
            if self._normalize(candidate) not in used:
                return candidate
        base = candidates[start_index].format(topic=topic)
        fallback = f"{base} — {topic}, {publish_date.isoformat()}"
        sequence = 2
        while self._normalize(fallback) in used:
            fallback = f"{base} — {topic}, {publish_date.isoformat()} ({sequence})"
            sequence += 1
        return fallback

    @staticmethod
    def _normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
