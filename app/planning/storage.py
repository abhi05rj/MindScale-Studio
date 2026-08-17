"""Atomic local storage for weekly content plans."""

import json
import os
import uuid
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from app.planning.planner import WeeklyPlan


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN_DIRECTORY = PROJECT_ROOT / ".local-runtime" / "content_plans"


class DuplicateWeeklyPlanError(ValueError):
    pass


class WeeklyPlanStorage:
    def __init__(self, plan_directory: Path | None = None):
        self.plan_directory = Path(plan_directory or DEFAULT_PLAN_DIRECTORY)

    def path_for(self, start_date: date) -> Path:
        return self.plan_directory / f"{start_date.isoformat()}.json"

    def exists(self, start_date: date) -> bool:
        return self.path_for(start_date).is_file()

    def load(self, start_date: date) -> "WeeklyPlan":
        from app.planning.planner import WeeklyPlan

        path = self.path_for(start_date)
        if not path.is_file():
            raise FileNotFoundError(f"No weekly plan exists for {start_date.isoformat()}.")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Weekly plan is unreadable: {path}") from error
        return WeeklyPlan.from_dict(value)

    def save(self, plan: "WeeklyPlan", *, replace: bool = False) -> Path:
        path = self.path_for(plan.start_date_value)
        if path.exists() and not replace:
            raise DuplicateWeeklyPlanError(
                f"A weekly plan already exists for {plan.start_date}. Use --replace explicitly."
            )
        plan.validate()
        self.plan_directory.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(asdict(plan), indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
        return path

    def load_all(self, *, exclude_start_date: date | None = None) -> list["WeeklyPlan"]:
        plans = []
        if not self.plan_directory.exists():
            return plans
        for path in sorted(self.plan_directory.glob("*.json")):
            try:
                start_date = date.fromisoformat(path.stem)
                if start_date == exclude_start_date:
                    continue
                plans.append(self.load(start_date))
            except (ValueError, OSError):
                continue
        return plans
