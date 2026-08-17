"""Offline hosted execution: ensure a plan, then run the existing pipeline."""

import argparse
from datetime import date, datetime, timezone

from app.pipeline import PipelineOrchestrator
from app.planning import ContentPlanner, WeeklyPlanStorage


def ensure_plan_for_date(target_date: date) -> None:
    storage = WeeklyPlanStorage()
    matches = [
        plan
        for plan in storage.load_all()
        if any(day.publish_date == target_date.isoformat() for day in plan.days)
    ]
    if len(matches) > 1:
        raise RuntimeError(f"Multiple plans contain hosted target date {target_date.isoformat()}.")
    if not matches:
        ContentPlanner(storage=storage).create_weekly_plan(target_date)
        print(f"HOSTED PLAN CREATED: {target_date.isoformat()}")
    else:
        print(f"HOSTED PLAN RESTORED: {matches[0].start_date}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run MindScale offline on a hosted runner.")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=datetime.now(timezone.utc).date(),
        help="UTC target date in YYYY-MM-DD format",
    )
    args = parser.parse_args(argv)
    ensure_plan_for_date(args.date)
    result = PipelineOrchestrator().run(args.date)
    print(f"HOSTED PIPELINE STATUS: {result.status}")
    return 0 if result.status == "queued" else 1


if __name__ == "__main__":
    raise SystemExit(main())
