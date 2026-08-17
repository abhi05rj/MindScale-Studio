"""Import/export commands for the hosted runtime-state branch."""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from app.hosted_runtime import HostedRuntimeStateAdapter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage JSON-only hosted runtime snapshots.")
    commands = parser.add_subparsers(dest="command", required=True)
    import_command = commands.add_parser("import-state")
    import_command.add_argument("--source", required=True, type=Path)
    export_command = commands.add_parser("export-state")
    export_command.add_argument("--destination", required=True, type=Path)
    export_command.add_argument("--image-artifact-run-id")
    export_command.add_argument("--image-artifact-name")
    artifact_command = commands.add_parser("artifact-info")
    artifact_command.add_argument("--source", required=True, type=Path)
    commands.add_parser("validate-images")
    args = parser.parse_args(argv)

    adapter = HostedRuntimeStateAdapter()
    try:
        if args.command == "import-state":
            result = asdict(adapter.import_state(args.source))
        elif args.command == "export-state":
            result = asdict(
                adapter.export_state(
                    args.destination,
                    image_artifact_run_id=args.image_artifact_run_id,
                    image_artifact_name=args.image_artifact_name,
                )
            )
        elif args.command == "artifact-info":
            run_id, name = adapter.read_image_artifact(args.source)
            result = {"run_id": run_id, "name": name}
        else:
            result = {"validated_images": adapter.validate_restored_images()}
        print(json.dumps(result, indent=2))
        return 0
    except Exception as error:
        print(f"Hosted runtime state command failed: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
