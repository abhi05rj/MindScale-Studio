"""CLI for creating and viewing deterministic weekly content plans."""

import argparse
import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

from app.planning import ContentPillar, ContentPlanner, WeeklyPlanStorage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create or view a local seven-day content plan.")
    parser.add_argument("--start-date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--show", action="store_true", help="Show the existing plan only")
    action.add_argument(
        "--replace", action="store_true", help="Explicitly regenerate and replace an existing plan"
    )
    parser.add_argument(
        "--pillar",
        action="append",
        dest="pillars",
        help="Custom content pillar; repeat at least twice to replace defaults",
    )
    parser.add_argument("--plan-directory", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--history-directory", type=Path, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        pillars = (
            tuple(ContentPillar.generic(name) for name in args.pillars)
            if args.pillars
            else None
        )
        options = {
            "storage": WeeklyPlanStorage(args.plan_directory),
            "content_history_directory": args.history_directory,
        }
        if pillars is not None:
            options["pillars"] = pillars
        planner = ContentPlanner(**options)
        plan = (
            planner.show_weekly_plan(args.start_date)
            if args.show
            else planner.create_weekly_plan(args.start_date, replace=args.replace)
        )
        print(json.dumps(asdict(plan), indent=2, ensure_ascii=False))
        return 0
    except Exception as error:
        print(f"Content planning failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
