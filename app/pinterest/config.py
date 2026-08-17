"""Environment-backed Pinterest configuration."""

import os
from dataclasses import dataclass
from typing import Mapping


PINTEREST_OAUTH_SCOPES = ("boards:read", "boards:write", "pins:read", "pins:write")


@dataclass(frozen=True)
class PinterestConfig:
    app_id: str | None = None
    app_secret: str | None = None
    access_token: str | None = None
    refresh_token: str | None = None
    board_id: str | None = None
    api_base_url: str = "https://api.pinterest.com/v5"
    timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "PinterestConfig":
        env = environ if environ is not None else os.environ
        return cls(
            app_id=env.get("PINTEREST_APP_ID"),
            app_secret=env.get("PINTEREST_APP_SECRET"),
            access_token=env.get("PINTEREST_ACCESS_TOKEN"),
            refresh_token=env.get("PINTEREST_REFRESH_TOKEN"),
            board_id=env.get("PINTEREST_BOARD_ID"),
            api_base_url=env.get("PINTEREST_API_BASE_URL", "https://api.pinterest.com/v5").rstrip("/"),
            timeout_seconds=float(env.get("PINTEREST_API_TIMEOUT_SECONDS", "30")),
        )

    def validate_for_live_publish(self) -> None:
        missing = []
        if not self.access_token:
            missing.append("PINTEREST_ACCESS_TOKEN")
        if not self.board_id:
            missing.append("PINTEREST_BOARD_ID")
        if missing:
            raise ValueError("Missing Pinterest configuration: " + ", ".join(missing))
