"""Deterministic image provider for tests and local compositor previews."""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

from app.image_engine.local_image_provider import (
    ImageGenerationRequest,
    ImageGenerationResult,
    LocalImageProvider,
)


class FakeImageProvider(LocalImageProvider):
    """Creates abstract background art without invoking an AI model."""

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        randomizer = random.Random(request.seed)
        image = Image.new("RGB", (request.width, request.height), "#13213b")
        pixels = image.load()

        top = (24, 42, 73)
        bottom = (51, 22, 78)
        for y in range(request.height):
            blend = y / max(request.height - 1, 1)
            color = tuple(round(a + (b - a) * blend) for a, b in zip(top, bottom))
            for x in range(request.width):
                glow = max(0.0, 1.0 - math.dist((x, y), (request.width * 0.7, request.height * 0.25)) / request.width)
                pixels[x, y] = tuple(min(255, round(channel + glow * 32)) for channel in color)

        draw = ImageDraw.Draw(image, "RGBA")
        palette = ("#78d6c6", "#a78bfa", "#f6c177", "#f08ba6")
        for index in range(9):
            radius = randomizer.randint(request.width // 18, request.width // 5)
            center_x = randomizer.randint(-radius, request.width + radius)
            center_y = randomizer.randint(-radius, request.height + radius)
            color = palette[index % len(palette)]
            draw.ellipse(
                (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
                fill=f"{color}{randomizer.randint(24, 62):02x}",
            )

        destination = Path(request.output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="PNG", optimize=True)

        return ImageGenerationResult(
            output_path=destination,
            provider=self.__class__.__name__,
            model="deterministic-fake-background-v1",
            width=request.width,
            height=request.height,
            seed=request.seed,
        )
