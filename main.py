import argparse
from datetime import date

from app.automation_runner import run_daily_automation


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a scheduled content package and finished Pinterest image."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Publish date to generate in YYYY-MM-DD format (defaults to today).",
    )
    args = parser.parse_args()
    raise SystemExit(run_daily_automation(target_date=args.date))
