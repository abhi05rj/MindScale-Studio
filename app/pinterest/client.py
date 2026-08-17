"""Small injectable client for Pinterest API v5."""

import json
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.pinterest.config import PinterestConfig


class PinterestApiError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class PinterestApiClient:
    def __init__(
        self,
        config: PinterestConfig,
        opener: Callable[..., Any] = urlopen,
    ):
        self.config = config
        self._opener = opener

    def get_board(self, board_id: str | None = None) -> dict:
        return self._request("GET", f"/boards/{board_id or self.config.board_id}")

    def create_pin(self, payload: dict) -> dict:
        return self._request("POST", "/pins", payload)

    def _request(self, method: str, path: str, payload: dict | None = None) -> dict:
        if not self.config.access_token:
            raise ValueError("Missing Pinterest configuration: PINTEREST_ACCESS_TOKEN")
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.config.api_base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.config.access_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with self._opener(request, timeout=self.config.timeout_seconds) as response:
                result = json.loads(response.read().decode("utf-8"))
                if not isinstance(result, dict):
                    raise PinterestApiError("Pinterest returned an invalid JSON response")
                return result
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(detail)
                detail = parsed.get("message") or parsed.get("error", {}).get("message") or detail
            except (json.JSONDecodeError, AttributeError):
                pass
            raise PinterestApiError(
                f"Pinterest API request failed ({error.code}): {detail}", error.code
            ) from error
        except URLError as error:
            raise PinterestApiError(f"Pinterest API request failed: {error.reason}") from error
