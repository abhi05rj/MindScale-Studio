"""Automation V1 entry point for generating a complete Pinterest-ready package."""

import argparse
from collections.abc import Callable
from datetime import date
from pathlib import Path

from app.content_engine import ContentCalendarEngine, DuplicatePublishDateError
from app.image_engine import (
    ImageGenerationRequest,
    LocalImageProvider,
    PillowTemplateProvider,
    PinterestCompositionRequest,
    PinterestImageCompositor,
    PinterestImageValidator,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_IMAGE_DIRECTORY = PROJECT_ROOT / "output" / "images"
UNPUBLISHED_STATE = {
    "status": "not_published",
    "pin_id": None,
    "board_id": None,
    "timestamp": None,
    "error": None,
}


def _default_image_provider() -> PillowTemplateProvider:
    return PillowTemplateProvider()


def validate_complete_package(record: dict, target_date: date) -> Path:
    """Validate all fields required before a package can enter publishing."""
    if record.get("publish_date") != target_date.isoformat():
        raise ValueError("Content package publish date does not match the automation date.")

    topic = record.get("topic")
    content_package = record.get("content_package", {})
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError("Content package topic is missing.")
    if content_package.get("topic") != topic:
        raise ValueError("Stored topic does not match the generated content package topic.")

    pinterest = content_package.get("pinterest", {})
    for field in ("pinterest_title", "pinterest_description"):
        value = pinterest.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Content package {field} is missing.")

    image_state = record.get("image", {})
    if image_state.get("status") != "complete":
        raise ValueError("Pinterest image state is not complete.")
    final_path_value = image_state.get("final_path")
    if not isinstance(final_path_value, str) or not final_path_value:
        raise ValueError("Final Pinterest image path is missing.")
    final_path = Path(final_path_value)
    image = PinterestImageValidator().validate(final_path)
    if (
        image_state.get("width") != image.width
        or image_state.get("height") != image.height
        or image_state.get("format") != image.image_format
    ):
        raise ValueError("Persisted image metadata does not match the final Pinterest PNG.")

    publication = record.get("pinterest_publication")
    if not isinstance(publication, dict):
        raise ValueError("Pinterest publication state is missing.")
    status = publication.get("status")
    if status not in {"not_published", "published"}:
        raise ValueError(f"Pinterest publication state is invalid: {status!r}.")
    if status == "not_published" and publication.get("pin_id") is not None:
        raise ValueError("An unpublished package cannot contain a Pinterest Pin ID.")
    if status == "published" and not publication.get("pin_id"):
        raise ValueError("A published package must contain a Pinterest Pin ID.")
    return final_path


def run_daily_automation(
    target_date: date | None = None,
    engine: ContentCalendarEngine | None = None,
    log: Callable[[str], None] = print,
    image_provider: LocalImageProvider | None = None,
    compositor: PinterestImageCompositor | None = None,
    image_directory: Path | None = None,
    dry_run: bool = False,
) -> int:
    """Generate content and its finished Pinterest image, returning a process exit code."""
    run_date = target_date or date.today()
    calendar = engine or ContentCalendarEngine()
    storage = calendar.content_storage
    provider = image_provider or _default_image_provider()
    image_compositor = compositor or PinterestImageCompositor()
    output_directory = Path(image_directory or DEFAULT_IMAGE_DIRECTORY)

    log(f"START daily content automation for {run_date.isoformat()}")

    existing_path = storage.path_for_publish_date(run_date)
    background_path = None
    final_path = None
    image_work_started = False

    try:
        if dry_run:
            if existing_path is None:
                topic = calendar.select_topic(run_date)
                log(f"DRY-RUN selected next topic: {topic}")
                log("DRY-RUN no files generated or persisted")
            else:
                record = storage.record_for_publish_date(run_date)
                if record is None:
                    raise RuntimeError("The saved content package could not be loaded.")
                final_image = validate_complete_package(record, run_date)
                log(f"DRY-RUN validated package: {existing_path}")
                log(f"DRY-RUN validated image: {final_image}")
            log("COMPLETE daily content automation (dry-run)")
            return 0

        if existing_path is None:
            topic = calendar.select_topic(run_date)
            log(f"SELECTED TOPIC: {topic}")
            scheduled_content = calendar.create_scheduled_content(run_date)
            log(
                "GENERATED CONTENT: "
                f"{scheduled_content.content_package.pinterest['pinterest_title']}"
            )
            existing_path = storage.path_for_publish_date(run_date)
            if existing_path is None:
                raise RuntimeError(
                    "Content generation completed, but the saved package could not be found."
                )
            log(f"SAVED CONTENT: {existing_path}")
        else:
            log(f"FOUND CONTENT: {existing_path}")

        record = storage.record_for_publish_date(run_date)
        if record is None:
            raise RuntimeError("The saved content package could not be loaded.")

        if "pinterest_publication" not in record:
            storage.update_pinterest_publication(run_date, dict(UNPUBLISHED_STATE))
            record = storage.record_for_publish_date(run_date)
            if record is None:
                raise RuntimeError("The saved content package could not be reloaded.")
            log("INITIALIZED PUBLICATION STATE: not_published")

        image_state = record.get("image", {})
        completed_path = Path(image_state.get("final_path", ""))
        if image_state.get("status") == "complete" and completed_path.is_file():
            validate_complete_package(record, run_date)
            log(f"IMAGE/NO-OP already complete: {completed_path}")
            log(f"VALIDATED PACKAGE: {existing_path}")
            log("COMPLETE daily content automation (successful no-op)")
            return 0

        if image_state.get("status") in {"generating", "failed"}:
            log(f"RECOVERING IMAGE STATE: {image_state.get('status')}")

        pinterest = record["content_package"]["pinterest"]
        slug = existing_path.stem.split("_", 1)[-1]
        background_path = output_directory / f"{run_date.isoformat()}_{slug}_background.png"
        final_path = output_directory / f"{run_date.isoformat()}_{slug}_pinterest.png"
        image_work_started = True
        storage.update_image_state(
            run_date,
            {
                "status": "generating",
            },
        )

        generated = provider.generate(
            ImageGenerationRequest(
                prompt=pinterest["image_prompt"],
                output_path=background_path,
                width=1000,
                height=1500,
                seed=run_date.toordinal(),
                inference_steps=1,
            )
        )
        composed = image_compositor.compose(
            PinterestCompositionRequest(
                background_path=generated.output_path,
                title=pinterest["pinterest_title"],
                output_path=final_path,
            )
        )
        storage.update_image_state(
            run_date,
            {
                "status": "complete",
                "background_path": str(generated.output_path.resolve()),
                "final_path": str(composed.output_path.resolve()),
                "provider": generated.provider,
                "model": generated.model,
                "seed": generated.seed,
                "width": composed.width,
                "height": composed.height,
                "format": composed.image_format,
            },
        )
        completed_record = storage.record_for_publish_date(run_date)
        if completed_record is None:
            raise RuntimeError("Completed content package could not be reloaded.")
        validate_complete_package(completed_record, run_date)
        log(f"GENERATED IMAGE: {composed.output_path}")
        log(f"VALIDATED PACKAGE: {existing_path}")
        log("COMPLETE daily content automation")
        return 0
    except DuplicatePublishDateError:
        # Another runner may have saved the same date after our initial check.
        saved_path = storage.path_for_publish_date(run_date)
        log(f"DUPLICATE/NO-OP content already exists for {run_date.isoformat()}: {saved_path}")
        log("COMPLETE daily content automation (successful no-op)")
        return 0
    except BaseException as error:
        for incomplete_path in (background_path, final_path):
            if incomplete_path is not None:
                incomplete_path.unlink(missing_ok=True)
        if storage.path_for_publish_date(run_date) is not None:
            record = storage.record_for_publish_date(run_date) or {}
            if image_work_started:
                storage.update_image_state(
                    run_date,
                    {
                        "status": "failed",
                        "error": str(error),
                    },
                )
        if not isinstance(error, Exception):
            raise
        log(f"ERROR daily content automation: {error}")
        log("COMPLETE daily content automation (failed)")
        return 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate and validate one complete local Pinterest content package."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help="Publish date in YYYY-MM-DD format (defaults to today).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate an existing package or preview topic selection without writing files.",
    )
    arguments = parser.parse_args()
    raise SystemExit(
        run_daily_automation(target_date=arguments.date, dry_run=arguments.dry_run)
    )
