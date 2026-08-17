"""Command-line entry point for explicitly publishing one prepared package."""

import argparse
from datetime import date

from app.content_engine import ContentStorage
from app.pinterest import PinterestConfig, PinterestPublisher


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a prepared content package to Pinterest.")
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true", help="Validate without contacting Pinterest")
    args = parser.parse_args()
    try:
        result = PinterestPublisher(ContentStorage(), PinterestConfig.from_env()).publish(
            args.date, dry_run=args.dry_run
        )
    except Exception as error:
        print(f"Pinterest publication failed: {error}")
        return 1
    print(f"Pinterest publication status: {result.status}")
    if result.pin_id:
        print(f"Pinterest Pin ID: {result.pin_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
