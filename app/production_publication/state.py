"""Atomic durable state for controlled Pinterest publication attempts."""

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ATTEMPT_DIRECTORY = PROJECT_ROOT / ".local-runtime" / "publication_attempts"
PUBLICATION_STATUSES = {
    "ready",
    "claimed",
    "publishing",
    "published",
    "failed",
    "publication_unknown",
}


class PublicationAttemptStorage:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory or DEFAULT_ATTEMPT_DIRECTORY)

    def path_for(self, item_id: str) -> Path:
        return self.directory / f"{item_id}.json"

    def load(self, item_id: str) -> dict | None:
        path = self.path_for(item_id)
        if not path.is_file():
            return None
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Publication attempt state is unreadable: {path}") from error
        if not isinstance(state, dict) or state.get("queue_item_id") != item_id:
            raise ValueError(f"Publication attempt state is invalid: {path}")
        if state.get("status") not in PUBLICATION_STATUSES:
            raise ValueError(f"Publication attempt status is invalid: {path}")
        return state

    def save(self, item_id: str, **updates) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        state = self.load(item_id) or {
            "queue_item_id": item_id,
            "status": "ready",
            "created_at": now,
            "updated_at": now,
            "claim_id": None,
            "claimed_at": None,
            "attempt_count": 0,
            "last_error": None,
            "pinterest_pin_id": None,
            "board_id": None,
            "status_history": [{"status": "ready", "timestamp": now}],
        }
        prior_status = state["status"]
        state.update(updates)
        if state.get("status") not in PUBLICATION_STATUSES:
            raise ValueError(f"Unsupported publication status: {state.get('status')!r}.")
        state["updated_at"] = now
        if state["status"] != prior_status:
            state.setdefault("status_history", []).append(
                {"status": state["status"], "timestamp": now}
            )
        self._write(item_id, state)
        return state

    def claim(self, item_id: str, board_id: str, max_attempts: int) -> dict:
        state = self.load(item_id) or self.save(item_id)
        if state["status"] in {"published", "publication_unknown"}:
            raise RuntimeError(f"Publication cannot be claimed from {state['status']} state.")
        if state["status"] in {"claimed", "publishing"}:
            raise RuntimeError(f"Publication is already {state['status']}.")
        if state["attempt_count"] >= max_attempts:
            raise RuntimeError(f"Publication retry limit of {max_attempts} has been reached.")
        now = datetime.now(timezone.utc).isoformat()
        return self.save(
            item_id,
            status="claimed",
            claim_id=str(uuid.uuid4()),
            claimed_at=now,
            attempt_count=state["attempt_count"] + 1,
            last_error=None,
            board_id=board_id,
        )

    def _write(self, item_id: str, state: dict) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        destination = self.path_for(item_id)
        temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(
                json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)
