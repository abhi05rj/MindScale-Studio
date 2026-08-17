"""Export and import portable JSON-only runtime snapshots."""

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.image_engine import PinterestImageValidator


@dataclass(frozen=True)
class StateTransferReport:
    content_plans: int = 0
    pipeline_states: int = 0
    content_packages: int = 0
    queue_present: bool = False
    fresh: bool = False


class HostedRuntimeStateAdapter:
    """Moves durable metadata between a checkout and a JSON-only state branch tree."""

    SNAPSHOT_VERSION = 1

    def __init__(self, project_root: Path | None = None):
        self.project_root = Path(project_root or Path(__file__).resolve().parents[2]).resolve()
        self.local_runtime = self.project_root / ".local-runtime"
        self.output_packages = self.project_root / "output" / "content_packages"

    def export_state(
        self,
        destination: Path,
        *,
        image_artifact_run_id: str | None = None,
        image_artifact_name: str | None = None,
    ) -> StateTransferReport:
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent)
        )
        try:
            plan_count = self._export_directory(
                self.local_runtime / "content_plans", temporary / "content_plans", "plan"
            )
            pipeline_count = self._export_directory(
                self.local_runtime / "pipeline", temporary / "pipeline", "pipeline"
            )
            package_count = self._export_directory(
                self.output_packages, temporary / "content_packages", "package"
            )
            queue_source = self.local_runtime / "publication_queue.json"
            queue_present = queue_source.is_file()
            if queue_present:
                self._write_json(
                    temporary / "publication_queue.json",
                    self._portable_document(self._read_json(queue_source), "queue"),
                )
            manifest = {
                "version": self.SNAPSHOT_VERSION,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "image_artifact": {
                    "run_id": image_artifact_run_id,
                    "name": image_artifact_name,
                },
                "counts": {
                    "content_plans": plan_count,
                    "pipeline_states": pipeline_count,
                    "content_packages": package_count,
                    "queue_present": queue_present,
                },
            }
            self._write_json(temporary / "manifest.json", manifest)
            self._assert_json_only(temporary)
            if destination.exists():
                shutil.rmtree(destination)
            os.replace(temporary, destination)
            return StateTransferReport(
                content_plans=plan_count,
                pipeline_states=pipeline_count,
                content_packages=package_count,
                queue_present=queue_present,
            )
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def import_state(self, source: Path) -> StateTransferReport:
        source = Path(source)
        if not source.exists() or not any(source.iterdir()):
            return StateTransferReport(fresh=True)
        manifest_path = source / "manifest.json"
        if not manifest_path.is_file():
            raise ValueError("Hosted runtime snapshot is missing manifest.json.")
        manifest = self._read_json(manifest_path)
        if manifest.get("version") != self.SNAPSHOT_VERSION:
            raise ValueError("Hosted runtime snapshot has an unsupported version.")
        self._assert_json_only(source)
        counts = manifest.get("counts")
        if not isinstance(counts, dict):
            raise ValueError("Hosted runtime snapshot manifest counts are invalid.")
        try:
            plan_count = int(counts.get("content_plans", 0))
            pipeline_count = int(counts.get("pipeline_states", 0))
            package_count = int(counts.get("content_packages", 0))
        except (TypeError, ValueError) as error:
            raise ValueError("Hosted runtime snapshot manifest counts are invalid.") from error

        transfers = []
        transfers.extend(
            self._collect_directory_transfers(
                source / "content_plans", self.local_runtime / "content_plans", "plan"
            )
        )
        transfers.extend(
            self._collect_directory_transfers(
                source / "pipeline", self.local_runtime / "pipeline", "pipeline"
            )
        )
        transfers.extend(
            self._collect_directory_transfers(
                source / "content_packages", self.output_packages, "package"
            )
        )
        queue_source = source / "publication_queue.json"
        if queue_source.is_file():
            transfers.append(
                (
                    self.local_runtime / "publication_queue.json",
                    self._portable_document(self._read_json(queue_source), "queue"),
                )
            )

        # Every document is parsed and transformed before the first local write.
        for destination, document in transfers:
            self._write_json_atomic(destination, document)
        return StateTransferReport(
            content_plans=plan_count,
            pipeline_states=pipeline_count,
            content_packages=package_count,
            queue_present=queue_source.is_file(),
        )

    def read_image_artifact(self, source: Path) -> tuple[str | None, str | None]:
        manifest_path = Path(source) / "manifest.json"
        if not manifest_path.is_file():
            return None, None
        artifact = self._read_json(manifest_path).get("image_artifact", {})
        return artifact.get("run_id"), artifact.get("name")

    def validate_restored_images(self) -> int:
        """Fail closed when durable metadata references an unavailable final PNG."""
        validated = 0
        validator = PinterestImageValidator()
        if not self.output_packages.exists():
            return validated
        for path in sorted(self.output_packages.glob("*.json")):
            package = self._read_json(path)
            image = package.get("image", {}) if isinstance(package, dict) else {}
            if image.get("status") != "complete":
                continue
            reference = image.get("final_path")
            if not isinstance(reference, str) or not reference:
                raise ValueError(f"Completed package is missing its final image reference: {path}")
            image_path = Path(reference)
            if not image_path.is_absolute():
                image_path = self.project_root / image_path
            validator.validate(image_path)
            validated += 1
        return validated

    def _export_directory(self, source: Path, destination: Path, kind: str) -> int:
        count = 0
        if not source.exists():
            return count
        for path in sorted(source.glob("*.json")):
            self._write_json(
                destination / path.name,
                self._portable_document(self._read_json(path), kind),
            )
            count += 1
        return count

    def _collect_directory_transfers(
        self, source: Path, destination: Path, kind: str
    ) -> list[tuple[Path, object]]:
        if not source.exists():
            return []
        return [
            (
                destination / path.name,
                self._portable_document(self._read_json(path), kind),
            )
            for path in sorted(source.glob("*.json"))
        ]

    def _portable_document(self, document, kind: str):
        # Round-trip through JSON so callers' in-memory values are never mutated.
        value = json.loads(json.dumps(document))
        if kind == "package" and isinstance(value, dict):
            image = value.get("image", {})
            for key in ("background_path", "final_path"):
                if isinstance(image.get(key), str):
                    image[key] = self._portable_reference(image[key])
        elif kind == "pipeline" and isinstance(value, dict):
            reference = value.get("content_package_ref")
            if isinstance(reference, str):
                value["content_package_ref"] = self._portable_reference(reference)
        elif kind == "queue" and isinstance(value, dict):
            for item in value.get("items", []):
                reference = item.get("content_package_ref") if isinstance(item, dict) else None
                if isinstance(reference, str):
                    item["content_package_ref"] = self._portable_reference(reference)
        return value

    def _portable_reference(self, reference: str) -> str:
        path = Path(reference)
        if not path.is_absolute():
            return path.as_posix()
        try:
            return path.resolve().relative_to(self.project_root).as_posix()
        except ValueError:
            raise ValueError(f"Runtime reference is outside the project checkout: {reference}")

    @staticmethod
    def _read_json(path: Path):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid hosted runtime JSON: {path}") from error

    @staticmethod
    def _write_json(path: Path, document) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def _write_json_atomic(cls, path: Path, document) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.import.tmp")
        try:
            cls._write_json(temporary, document)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    @staticmethod
    def _assert_json_only(root: Path) -> None:
        invalid = [path for path in root.rglob("*") if path.is_file() and path.suffix != ".json"]
        if invalid:
            raise ValueError(
                "Hosted runtime snapshot may contain JSON only: "
                + ", ".join(str(path) for path in invalid)
            )
