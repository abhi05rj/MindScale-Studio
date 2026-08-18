"""Content-package to Pinterest publication orchestration."""

from dataclasses import dataclass
from datetime import date, datetime, timezone

from app.content_engine import ContentStorage
from app.pinterest.client import PinterestApiClient, PinterestApiError
from app.pinterest.config import PinterestConfig
from app.pinterest.payload import PinterestPayloadBuilder, PinterestPayloadError


class DuplicatePinError(RuntimeError):
    pass


class PublicationOutcomeUnknownError(RuntimeError):
    """The create request may have succeeded, so retrying could create a duplicate Pin."""

    pass


@dataclass(frozen=True)
class PublicationResult:
    status: str
    payload: dict
    pin_id: str | None = None


class PinterestPublisher:
    def __init__(
        self,
        storage: ContentStorage,
        config: PinterestConfig | None = None,
        client: PinterestApiClient | None = None,
    ):
        self.storage = storage
        self.config = config or PinterestConfig.from_env()
        self.client = client or PinterestApiClient(self.config)

    def publish(self, publish_date: date, dry_run: bool = False) -> PublicationResult:
        record = self.storage.record_for_publish_date(publish_date)
        if record is None:
            raise PinterestPayloadError(
                f"No content package exists for publish date: {publish_date.isoformat()}"
            )
        prior = record.get("pinterest_publication", {})
        if prior.get("pin_id"):
            raise DuplicatePinError(f"Content package is already published as Pin {prior['pin_id']}")

        # Dry-run is deliberately read-only: validation failures and successes must
        # not create publication state that could be confused with an API attempt.
        if dry_run:
            payload = self.build_payload(record)
            return PublicationResult("dry_run_validated", payload)

        try:
            payload = self.build_payload(record)
            self.config.validate_for_live_publish()
            self._persist(publish_date, "publishing")
            self.client.get_board(self.config.board_id)
            try:
                response = self.client.create_pin(payload)
            except PinterestApiError as error:
                if error.status_code is None or error.status_code >= 500:
                    self._raise_unknown(publish_date, str(error), error)
                raise
            except Exception as error:
                self._raise_unknown(publish_date, str(error), error)
            if not isinstance(response, dict):
                self._raise_unknown(publish_date, "Pinterest create Pin response was invalid")
            pin_id = response.get("id")
            if not isinstance(pin_id, str) or not pin_id:
                error = "Pinterest create Pin response did not contain a Pin ID"
                self._raise_unknown(publish_date, error)
            self._persist(publish_date, "published", pin_id=pin_id)
            return PublicationResult("published", payload, pin_id)
        except (DuplicatePinError, PublicationOutcomeUnknownError, KeyboardInterrupt, SystemExit):
            raise
        except Exception as error:
            self._persist(publish_date, "failed", error=str(error))
            raise

    def build_payload(self, record: dict) -> dict:
        return PinterestPayloadBuilder(self.config).build(record)

    def _raise_unknown(
        self, publish_date: date, message: str, cause: Exception | None = None
    ) -> None:
        try:
            self._persist(publish_date, "publication_unknown", error=message)
        except Exception:
            # The caller's independent attempt state must still be told never to retry.
            pass
        raise PublicationOutcomeUnknownError(message) from cause

    def _persist(
        self,
        publish_date: date,
        status: str,
        *,
        pin_id: str | None = None,
        error: str | None = None,
    ) -> None:
        state = {
            "status": status,
            "pin_id": pin_id,
            "board_id": self.config.board_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": error,
        }
        self.storage.update_pinterest_publication(publish_date, state)
