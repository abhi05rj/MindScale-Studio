"""Deterministic composition and validation for finished Pinterest assets."""

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


PINTEREST_SIZE = (1000, 1500)


@dataclass(frozen=True)
class PinterestCompositionRequest:
    background_path: Path
    title: str
    output_path: Path

    def __post_init__(self):
        if not self.title.strip():
            raise ValueError("A content title is required for Pinterest composition.")


@dataclass(frozen=True)
class PinterestCompositionResult:
    output_path: Path
    width: int
    height: int
    image_format: str


class PinterestImageValidator:
    """Ensures a final asset is a readable, correctly sized RGB/RGBA PNG."""

    def validate(self, image_path: Path) -> PinterestCompositionResult:
        path = Path(image_path)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Pinterest image does not exist or is empty: {path}")

        try:
            with Image.open(path) as image:
                image.verify()
            with Image.open(path) as image:
                size = image.size
                image_format = image.format
                mode = image.mode
        except (OSError, SyntaxError) as error:
            raise ValueError(f"Pinterest image is unreadable: {path}") from error

        if size != PINTEREST_SIZE:
            raise ValueError(f"Pinterest image must be 1000x1500; found {size[0]}x{size[1]}.")
        if image_format != "PNG":
            raise ValueError(f"Pinterest image must be PNG; found {image_format}.")
        if mode not in {"RGB", "RGBA"}:
            raise ValueError(f"Pinterest image must use RGB or RGBA pixels; found {mode}.")

        return PinterestCompositionResult(path, size[0], size[1], image_format)


class PinterestImageCompositor:
    """Builds a Pinterest asset while keeping typography out of the AI model."""

    _FONT_CANDIDATES = (
        # DejaVu and Liberation are commonly available under open-source licenses
        # on GitHub-hosted Ubuntu runners.
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/Library/Fonts/Arial Bold.ttf"),
    )

    def __init__(self, font_path: Path | None = None, validator=None):
        self.font_path = Path(font_path) if font_path else self._find_font()
        self.validator = validator or PinterestImageValidator()

    def compose(self, request: PinterestCompositionRequest) -> PinterestCompositionResult:
        background_path = Path(request.background_path)
        if not background_path.is_file():
            raise ValueError(f"Background image not found: {background_path}")

        try:
            with Image.open(background_path) as source:
                canvas = ImageOps.fit(
                    source.convert("RGB"),
                    PINTEREST_SIZE,
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5),
                )
        except (OSError, SyntaxError) as error:
            raise ValueError(f"Background image is unreadable: {background_path}") from error

        self._draw_overlay(canvas)
        self._draw_typography(canvas, request.title.strip())

        destination = Path(request.output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
        try:
            canvas.save(temporary_path, format="PNG", optimize=True)
            self.validator.validate(temporary_path)
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)

        return self.validator.validate(destination)

    @staticmethod
    def _draw_overlay(canvas: Image.Image):
        overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        pixels = overlay.load()
        start_y = 690
        for y in range(start_y, canvas.height):
            opacity = round(220 * ((y - start_y) / (canvas.height - start_y)) ** 0.8)
            for x in range(canvas.width):
                pixels[x, y] = (6, 12, 28, opacity)
        canvas.paste(overlay, (0, 0), overlay)

    def _draw_typography(self, canvas: Image.Image, title: str):
        draw = ImageDraw.Draw(canvas)
        label_font = ImageFont.truetype(str(self.font_path), 29)
        max_width = 820
        title_font, lines = self._fit_title(draw, title, max_width)
        line_height = round(title_font.size * 1.2)
        title_height = len(lines) * line_height
        title_y = 1320 - title_height

        accent = "#79e0ce"
        label = "MINDSCALE STUDIO"
        label_box = draw.textbbox((0, 0), label, font=label_font)
        label_width = label_box[2] - label_box[0]
        draw.rounded_rectangle(
            (90, title_y - 78, 90 + label_width + 54, title_y - 32),
            radius=23,
            fill=accent,
        )
        draw.text((117, title_y - 70), label, font=label_font, fill="#0b1830")

        for line in lines:
            draw.text(
                (90, title_y),
                line,
                font=title_font,
                fill="white",
                stroke_width=2,
                stroke_fill="#08101f",
            )
            title_y += line_height

        draw.rectangle((90, 1393, 270, 1404), fill=accent)

    def _fit_title(self, draw: ImageDraw.ImageDraw, title: str, max_width: int):
        for font_size in range(88, 55, -4):
            font = ImageFont.truetype(str(self.font_path), font_size)
            lines = self._wrap_title(draw, title, font, max_width)
            if len(lines) <= 4:
                return font, lines
        raise ValueError("The title is too long for the Pinterest layout.")

    @staticmethod
    def _wrap_title(draw: ImageDraw.ImageDraw, title: str, font, max_width: int) -> list[str]:
        words = title.split()
        lines = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            width = draw.textbbox((0, 0), candidate, font=font, stroke_width=2)[2]
            if current and width > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)

        return lines

    def _find_font(self) -> Path:
        for candidate in self._FONT_CANDIDATES:
            if candidate.is_file():
                return candidate
        raise RuntimeError("No supported local font was found for Pinterest composition.")
