"""CLI for Pipeline Orchestrator V1."""

import argparse
from datetime import date

from app.pipeline import PipelineOrchestrator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate and queue the planned Pinterest item for one date, fully offline."
    )
    parser.add_argument("--date", required=True, type=date.fromisoformat, help="YYYY-MM-DD")
    args = parser.parse_args(argv)
    result = PipelineOrchestrator().run(args.date)
    print(f"Pipeline status: {result.status}")
    if result.content_package_path:
        print(f"Content package: {result.content_package_path}")
    if result.queue_item_id:
        print(f"Queue item: {result.queue_item_id}")
    return 0 if result.status == "queued" else 1


if __name__ == "__main__":
    raise SystemExit(main())
