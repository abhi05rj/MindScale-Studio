"""Local automation entry point for generating the daily Pinterest package."""

from collections.abc import Callable
from datetime import date

from app.content_engine import ContentCalendarEngine, DuplicatePublishDateError


def run_daily_automation(
    target_date: date | None = None,
    engine: ContentCalendarEngine | None = None,
    log: Callable[[str], None] = print,
) -> int:
    """Generate and save one package for the date, returning a process exit code."""
    run_date = target_date or date.today()
    calendar = engine or ContentCalendarEngine()
    storage = calendar.content_storage

    log(f"START daily content automation for {run_date.isoformat()}")

    existing_path = storage.path_for_publish_date(run_date)
    if existing_path is not None:
        log(f"DUPLICATE/NO-OP content already exists for {run_date.isoformat()}: {existing_path}")
        log("COMPLETE daily content automation (successful no-op)")
        return 0

    try:
        topic = calendar.select_topic(run_date)
        log(f"SELECTED TOPIC: {topic}")

        scheduled_content = calendar.create_scheduled_content(run_date)
        log(f"GENERATED CONTENT: {scheduled_content.content_package.pinterest['pinterest_title']}")

        saved_path = storage.path_for_publish_date(run_date)
        if saved_path is None:
            raise RuntimeError("Content generation completed, but the saved package could not be found.")

        log(f"SAVED CONTENT: {saved_path}")
        log("COMPLETE daily content automation")
        return 0
    except DuplicatePublishDateError:
        # Another runner may have saved the same date after our initial check.
        saved_path = storage.path_for_publish_date(run_date)
        log(f"DUPLICATE/NO-OP content already exists for {run_date.isoformat()}: {saved_path}")
        log("COMPLETE daily content automation (successful no-op)")
        return 0
    except Exception as error:
        log(f"ERROR daily content automation: {error}")
        log("COMPLETE daily content automation (failed)")
        return 1


if __name__ == "__main__":
    raise SystemExit(run_daily_automation())
