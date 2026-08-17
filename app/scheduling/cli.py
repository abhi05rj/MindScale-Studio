"""CLI for the local publication queue."""

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from app.content_engine import ContentStorage
from app.pinterest import PinterestConfig, PinterestPublisher
from app.scheduling import PublicationQueue, QueueProcessor
from app.scheduling.queue import parse_datetime


def _print(value) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage the local Pinterest publication queue.")
    parser.add_argument("--queue-path", type=Path, help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="command", required=True)

    schedule = commands.add_parser("schedule", help="Schedule a content package in UTC.")
    schedule.add_argument("--package", required=True, type=Path)
    schedule.add_argument("--at", required=True, type=parse_datetime, help="ISO 8601 datetime")

    commands.add_parser("list", help="List all queue items.")
    get = commands.add_parser("get", help="Retrieve one queue item.")
    get.add_argument("item_id")
    cancel = commands.add_parser("cancel", help="Cancel a scheduled queue item.")
    cancel.add_argument("item_id")
    process = commands.add_parser("process", help="Process items due at the current UTC time.")
    process.add_argument(
        "--live",
        action="store_true",
        help="EXPLICITLY enable live Pinterest publishing; default is offline validation.",
    )
    process.add_argument("--now", type=parse_datetime, help="Override current time for testing")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    queue = PublicationQueue(args.queue_path)
    try:
        if args.command == "schedule":
            _print(asdict(queue.schedule(args.package, args.at)))
        elif args.command == "list":
            _print([asdict(item) for item in queue.list_items()])
        elif args.command == "get":
            _print(asdict(queue.get(args.item_id)))
        elif args.command == "cancel":
            _print(asdict(queue.cancel(args.item_id)))
        elif args.command == "process":
            publisher = PinterestPublisher(ContentStorage(), PinterestConfig.from_env())
            results = QueueProcessor(queue, publisher).process_due(now=args.now, live=args.live)
            _print([asdict(result) for result in results])
        return 0
    except Exception as error:
        print(f"Queue command failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
