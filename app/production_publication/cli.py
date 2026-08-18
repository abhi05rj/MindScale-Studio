"""CLI for manual, controlled Pinterest Trial publication."""

import argparse
import json
import os
from pathlib import Path

from app.content_engine import ContentStorage
from app.production_publication import (
    ControlledPublicationController,
    PublicationAttemptStorage,
)
from app.scheduling import PublicationQueue


def _write_summary(title: str, values: dict) -> None:
    destination = os.getenv("GITHUB_STEP_SUMMARY")
    if not destination:
        return
    safe = {
        key: str(value)
        .replace("\r", " ")
        .replace("\n", " ")
        .replace("|", "\\|")[:500]
        for key, value in values.items()
        if value is not None
    }
    lines = [f"## {title}", "", "| Field | Value |", "|---|---|"]
    lines.extend(f"| {key} | {value} |" for key, value in safe.items())
    with Path(destination).open("a", encoding="utf-8") as summary:
        summary.write("\n".join(lines) + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Controlled Pinterest Trial publication.")
    parser.add_argument("--queue-item-id", required=True)
    parser.add_argument("--mode", choices=("preflight", "live"), default="preflight")
    parser.add_argument("--confirm-live-publish", default="false")
    args = parser.parse_args(argv)
    controller = ControlledPublicationController(
        PublicationQueue(), ContentStorage(), PublicationAttemptStorage()
    )
    try:
        if args.mode == "preflight":
            result = controller.preflight(args.queue_item_id)
        else:
            result = controller.publish(
                args.queue_item_id,
                confirm_live_publish=args.confirm_live_publish.casefold() == "true",
            )
        summary = result.safe_summary()
        print(json.dumps(summary, indent=2))
        _write_summary("MindScale controlled Pinterest publication", summary)
        return 0 if result.status in {"ready", "published"} else 1
    except Exception as error:
        summary = {
            "queue_item_id": args.queue_item_id,
            "mode": args.mode,
            "status": "blocked",
            "error": str(error),
        }
        print(json.dumps(summary, indent=2))
        _write_summary("MindScale publication blocked", summary)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
