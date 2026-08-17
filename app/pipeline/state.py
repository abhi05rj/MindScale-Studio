"""Atomic runtime state for Pipeline Orchestrator V1."""

import json
import os
import uuid
from datetime import date, datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STATE_DIRECTORY = PROJECT_ROOT / ".local-runtime" / "pipeline"
PIPELINE_STATUSES = {"planned", "generating", "generated", "queued", "failed"}


class PipelineStateStorage:
    def __init__(self, state_directory: Path | None = None):
        self.state_directory = Path(state_directory or DEFAULT_STATE_DIRECTORY)

    def path_for(self, target_date: date) -> Path:
        return self.state_directory / f"{target_date.isoformat()}.json"

    def load(self, target_date: date) -> dict | None:
        path = self.path_for(target_date)
        if not path.is_file():
            return None
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Pipeline state is unreadable: {path}") from error
        if not isinstance(state, dict) or state.get("target_date") != target_date.isoformat():
            raise ValueError(f"Pipeline state is invalid: {path}")
        return state

    def initialize(self, target_date: date, *, plan_start_date: str, topic: str) -> dict:
        existing = self.load(target_date)
        if existing is not None:
            return existing
        timestamp = datetime.now(timezone.utc).isoformat()
        state = {
            "target_date": target_date.isoformat(),
            "plan_start_date": plan_start_date,
            "topic": topic,
            "status": "planned",
            "created_at": timestamp,
            "updated_at": timestamp,
            "content_package_ref": None,
            "queue_item_id": None,
            "last_error": None,
            "status_history": [{"status": "planned", "timestamp": timestamp}],
        }
        self._write(target_date, state)
        return state

    def transition(self, target_date: date, status: str, **updates) -> dict:
        if status not in PIPELINE_STATUSES:
            raise ValueError(f"Unsupported pipeline status: {status!r}.")
        state = self.load(target_date)
        if state is None:
            raise RuntimeError(f"Pipeline state does not exist for {target_date.isoformat()}.")
        timestamp = datetime.now(timezone.utc).isoformat()
        state.update(updates)
        state["status"] = status
        state["updated_at"] = timestamp
        state.setdefault("status_history", []).append({"status": status, "timestamp": timestamp})
        self._write(target_date, state)
        return state

    def _write(self, target_date: date, state: dict) -> None:
        self.state_directory.mkdir(parents=True, exist_ok=True)
        path = self.path_for(target_date)
        temporary_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary_path.write_text(
                json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)
