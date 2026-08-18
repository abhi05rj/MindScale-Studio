"""Pure, offline construction and validation of Pinterest API v5 payloads."""

import base64
import ipaddress
from urllib.parse import urlparse

from PIL import Image, UnidentifiedImageError

from app.pinterest.config import PinterestConfig
from app.runtime_paths import resolve_runtime_reference


class PinterestPayloadError(ValueError):
    pass


class PinterestPayloadBuilder:
    def __init__(self, config: PinterestConfig):
        self.config = config

    def build(self, record: dict) -> dict:
        pinterest = record.get("content_package", {}).get("pinterest", {})
        image_path = resolve_runtime_reference(record.get("image", {}).get("final_path", ""))
        title = pinterest.get("pinterest_title")
        description = pinterest.get("pinterest_description")
        destination_url = pinterest.get("destination_url") or pinterest.get(
            "pinterest_destination_url"
        )
        missing = [
            name
            for name, value in (
                ("title", title),
                ("description", description),
                ("PINTEREST_BOARD_ID", self.config.board_id),
            )
            if not isinstance(value, str) or not value.strip()
        ]
        if missing:
            raise PinterestPayloadError("Missing publishing payload fields: " + ", ".join(missing))
        if len(title.strip()) > 100:
            raise PinterestPayloadError("Pinterest title must be 100 characters or fewer")
        if len(description.strip()) > 500:
            raise PinterestPayloadError("Pinterest description must be 500 characters or fewer")
        clean_destination_url = None
        if isinstance(destination_url, str) and destination_url.strip():
            clean_destination_url = destination_url.strip()
            self._validate_public_destination_url(clean_destination_url)
        if not image_path.is_file():
            raise PinterestPayloadError(f"Final Pinterest image does not exist: {image_path}")
        try:
            with Image.open(image_path) as image:
                image.verify()
                if image.format != "PNG":
                    raise PinterestPayloadError("Final Pinterest image must be a PNG")
        except (UnidentifiedImageError, OSError) as error:
            raise PinterestPayloadError(f"Final Pinterest image is invalid: {image_path}") from error

        payload = {
            "board_id": self.config.board_id,
            "title": title.strip(),
            "description": description.strip(),
            "media_source": {
                "source_type": "image_base64",
                "content_type": "image/png",
                "data": base64.b64encode(image_path.read_bytes()).decode("ascii"),
            },
        }
        if clean_destination_url is not None:
            payload["link"] = clean_destination_url
        return payload

    @staticmethod
    def _validate_public_destination_url(destination_url: str) -> None:
        parsed = urlparse(destination_url)
        hostname = parsed.hostname
        if (
            parsed.scheme not in {"http", "https"}
            or not hostname
            or parsed.username is not None
            or parsed.password is not None
            or hostname.casefold() == "localhost"
            or hostname.casefold().endswith(".local")
        ):
            raise PinterestPayloadError(
                "Pinterest destination URL must be an explicitly configured public HTTP(S) URL"
            )
        try:
            address = ipaddress.ip_address(hostname)
        except ValueError:
            if "." not in hostname:
                raise PinterestPayloadError(
                    "Pinterest destination URL must be an explicitly configured public HTTP(S) URL"
                )
        else:
            if not address.is_global:
                raise PinterestPayloadError(
                    "Pinterest destination URL must be an explicitly configured public HTTP(S) URL"
                )
