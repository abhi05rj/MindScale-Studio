"""Core ML Stable Diffusion adapter for Apple's local command-line pipeline."""

import shutil
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from app.image_engine.local_image_provider import (
    ImageGenerationRequest,
    ImageGenerationResult,
    LocalImageProvider,
)


CommandRunner = Callable[..., subprocess.CompletedProcess]


class CoreMLStableDiffusionProvider(LocalImageProvider):
    """Runs one preconverted Core ML model without exposing it to callers.

    The Apple runtime and model are deliberately external assets. Constructing this
    adapter does not import, install, download, or initialize either one.
    """

    def __init__(
        self,
        model_directory: Path,
        python_executable: Path,
        model: str = "stable-diffusion-v1-5/stable-diffusion-v1-5",
        compute_unit: str = "CPU_AND_GPU",
        model_width: int = 512,
        model_height: int = 512,
        command_runner: CommandRunner = subprocess.run,
    ):
        self.model_directory = Path(model_directory)
        self.python_executable = Path(python_executable)
        self.model = model
        self.compute_unit = compute_unit
        self.model_width = model_width
        self.model_height = model_height
        self.command_runner = command_runner

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        if (request.width, request.height) != (self.model_width, self.model_height):
            raise ValueError(
                "The requested dimensions do not match this fixed-shape Core ML model: "
                f"expected {self.model_width}x{self.model_height}."
            )
        if not self.model_directory.is_dir():
            raise RuntimeError(f"Core ML model directory not found: {self.model_directory}")
        if not self.python_executable.is_file():
            raise RuntimeError(f"Core ML Python executable not found: {self.python_executable}")

        destination = Path(request.output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="mindscale-coreml-", dir=destination.parent
        ) as temporary_directory:
            command = self._build_command(request, Path(temporary_directory))
            try:
                self.command_runner(command, check=True, capture_output=True, text=True)
            except FileNotFoundError as error:
                raise RuntimeError("The configured Core ML Python executable is unavailable.") from error
            except subprocess.CalledProcessError as error:
                details = (error.stderr or error.stdout or str(error)).strip()
                raise RuntimeError(f"Core ML image generation failed: {details}") from error

            candidates = sorted(Path(temporary_directory).glob("*.png"))
            if len(candidates) != 1:
                raise RuntimeError(
                    "Core ML generation must produce exactly one PNG; "
                    f"found {len(candidates)}."
                )
            shutil.move(str(candidates[0]), destination)

        return ImageGenerationResult(
            output_path=destination,
            provider=self.__class__.__name__,
            model=self.model,
            width=request.width,
            height=request.height,
            seed=request.seed,
        )

    def _build_command(
        self, request: ImageGenerationRequest, output_directory: Path
    ) -> Sequence[str]:
        return (
            str(self.python_executable),
            "-m",
            "app.image_engine.coreml_runner",
            "--prompt",
            request.prompt,
            "--compute-unit",
            self.compute_unit,
            "--seed",
            str(request.seed),
            "--num-inference-steps",
            str(request.inference_steps),
            "-i",
            str(self.model_directory),
            "-o",
            str(output_directory),
        )
