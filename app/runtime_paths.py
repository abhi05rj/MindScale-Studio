"""Portable references for runtime files that may move between checkouts."""

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT_ENV = "MINDSCALE_PROJECT_ROOT"


def runtime_project_root() -> Path:
    configured = os.getenv(PROJECT_ROOT_ENV)
    return Path(configured).resolve() if configured else PROJECT_ROOT


def stable_runtime_reference(path: Path, root: Path | None = None) -> str:
    """Return a repo-relative reference when possible, otherwise an absolute path."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to((root or runtime_project_root()).resolve()).as_posix()
    except ValueError:
        return str(resolved)


def resolve_runtime_reference(reference: str, root: Path | None = None) -> Path:
    path = Path(reference)
    return path if path.is_absolute() else (root or runtime_project_root()).resolve() / path
