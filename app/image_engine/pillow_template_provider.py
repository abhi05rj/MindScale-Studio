"""Lightweight deterministic artwork for production Pinterest backgrounds."""

import hashlib
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.image_engine.local_image_provider import (
    ImageGenerationRequest,
    ImageGenerationResult,
    LocalImageProvider,
)


class PillowTemplateProvider(LocalImageProvider):
    """Creates polished topic-aware visuals without a model or network access."""

    _PALETTES = {
        "cosmic_orbits": ((8, 16, 43), (42, 30, 91), (107, 226, 211), (246, 193, 119)),
        "organic_layers": ((9, 48, 55), (20, 104, 91), (128, 218, 166), (248, 209, 126)),
        "connected_minds": ((19, 24, 60), (62, 47, 105), (170, 139, 250), (103, 232, 218)),
    }

    def generate(self, request: ImageGenerationRequest) -> ImageGenerationResult:
        template = self.select_template(request.prompt)
        palette = self._PALETTES[template]
        image = self._gradient(request.width, request.height, palette[0], palette[1])
        randomizer = random.Random(self._stable_seed(request.prompt, request.seed))

        if template == "cosmic_orbits":
            self._draw_cosmic_orbits(image, randomizer, palette)
        elif template == "organic_layers":
            self._draw_organic_layers(image, randomizer, palette)
        else:
            self._draw_connected_minds(image, randomizer, palette)

        destination = Path(request.output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, format="PNG", optimize=True)
        return ImageGenerationResult(
            output_path=destination,
            provider=self.__class__.__name__,
            model=f"pillow-{template}-v1",
            width=request.width,
            height=request.height,
            seed=request.seed,
        )

    @staticmethod
    def select_template(prompt: str) -> str:
        normalized = prompt.casefold()
        if any(word in normalized for word in ("universe", "space", "cosmic", "star", "planet")):
            return "cosmic_orbits"
        if any(word in normalized for word in ("nature", "ocean", "earth", "forest", "organic")):
            return "organic_layers"
        if any(word in normalized for word in ("brain", "human", "time", "mind", "network")):
            return "connected_minds"
        variants = ("cosmic_orbits", "organic_layers", "connected_minds")
        digest = hashlib.sha256(normalized.encode("utf-8")).digest()
        return variants[digest[0] % len(variants)]

    @staticmethod
    def _stable_seed(prompt: str, seed: int) -> int:
        digest = hashlib.sha256(f"{seed}:{prompt}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big")

    @staticmethod
    def _gradient(width: int, height: int, top: tuple[int, ...], bottom: tuple[int, ...]) -> Image.Image:
        strip = Image.new("RGB", (1, height))
        pixels = strip.load()
        for y in range(height):
            blend = y / max(height - 1, 1)
            pixels[0, y] = tuple(round(a + (b - a) * blend) for a, b in zip(top, bottom))
        return strip.resize((width, height))

    @staticmethod
    def _add_glow(image: Image.Image, center: tuple[int, int], radius: int, color: tuple[int, ...]):
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        x, y = center
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, 150))
        glow = glow.filter(ImageFilter.GaussianBlur(radius // 2))
        image.paste(glow, (0, 0), glow)

    def _draw_cosmic_orbits(self, image, randomizer, palette):
        draw = ImageDraw.Draw(image, "RGBA")
        width, height = image.size
        self._add_glow(image, (round(width * 0.72), round(height * 0.27)), width // 4, palette[2])
        for _ in range(85):
            x = randomizer.randrange(width)
            y = randomizer.randrange(round(height * 0.72))
            radius = randomizer.choice((1, 2, 2, 3, 4))
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(255, 255, 255, 150))
        center = (round(width * 0.69), round(height * 0.29))
        for index, scale in enumerate((0.22, 0.35, 0.49)):
            rx, ry = round(width * scale), round(width * scale * 0.48)
            box = (center[0] - rx, center[1] - ry, center[0] + rx, center[1] + ry)
            draw.ellipse(box, outline=(*palette[2 + index % 2], 145), width=max(3, width // 180))
        draw.ellipse((center[0] - 58, center[1] - 58, center[0] + 58, center[1] + 58), fill=(*palette[3], 255))

    def _draw_organic_layers(self, image, randomizer, palette):
        width, height = image.size
        self._add_glow(image, (round(width * 0.75), round(height * 0.22)), width // 3, palette[3])
        draw = ImageDraw.Draw(image, "RGBA")
        layer_colors = ((*palette[2], 210), (*palette[1], 235), (*palette[0], 245))
        for index, color in enumerate(layer_colors):
            base = round(height * (0.42 + index * 0.13))
            points = [(0, height)]
            for x in range(0, width + 80, 80):
                wave = math.sin(x / width * math.pi * (1.4 + index * 0.25))
                jitter = randomizer.randint(-18, 18)
                points.append((x, round(base + wave * 105 + jitter)))
            points.extend(((width, height), (0, height)))
            draw.polygon(points, fill=color)
        for x, y, radius in ((180, 300, 78), (780, 440, 112), (530, 230, 42)):
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), outline=(255, 255, 255, 75), width=4)

    def _draw_connected_minds(self, image, randomizer, palette):
        width, height = image.size
        self._add_glow(image, (width // 2, round(height * 0.3)), width // 3, palette[2])
        draw = ImageDraw.Draw(image, "RGBA")
        nodes = [
            (randomizer.randint(90, width - 90), randomizer.randint(100, round(height * 0.68)))
            for _ in range(24)
        ]
        for index, first in enumerate(nodes):
            nearest = sorted(nodes[index + 1 :], key=lambda point: math.dist(first, point))[:2]
            for second in nearest:
                if math.dist(first, second) < width * 0.38:
                    draw.line((first, second), fill=(*palette[3], 80), width=3)
        for index, (x, y) in enumerate(nodes):
            radius = 8 + index % 4 * 3
            fill = palette[2] if index % 3 else palette[3]
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*fill, 235))
            draw.ellipse((x - radius * 2, y - radius * 2, x + radius * 2, y + radius * 2), outline=(*fill, 75), width=2)
