"""Model-neutral contracts for local image generation providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ImageGenerationRequest:
    """Inputs shared by any local text-to-image implementation."""

    prompt: str
    output_path: Path
    width: int = 512
    height: int = 512
    seed: int = 0
    inference_steps: int = 20

    def __post_init__(self):
        if not self.prompt.strip():
            raise ValueError("An image prompt is required.")
        if self.width < 64 or self.height < 64:
            raise ValueError("Generated image dimensions must be at least 64 pixels.")
        if self.inference_steps < 1:
            raise ValueError("Inference steps must be at least one.")


@dataclass(frozen=True)
class ImageGenerationResult:
    """Portable metadata returned by every local image provider."""

    output_path: Path
    provider: str
    model: str
    width: int
    height: int
    seed: int


class LocalImageProvider(ABC):
    """Replaceable contract for a local, zero-recurring-cost image model."""

    @abstractmethod
    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        """Generate a background visual and persist it at the requested path."""
