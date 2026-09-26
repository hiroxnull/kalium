"""Public exception types raised by the Kalium client."""

from __future__ import annotations

from datetime import datetime
from typing import Any


class KaliumError(Exception):
    """Base class for errors raised by this library."""


class APIError(KaliumError):
    """An unsuccessful response returned by the KaliumLabs API."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error: Any = None,
        payload: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error = error
        self.payload = payload


class AuthenticationError(APIError):
    """The API key is missing or invalid."""


class ForbiddenError(APIError):
    """The API or its edge protection denied the request."""


class NotFoundError(APIError):
    """The requested lab or image does not exist."""


class RateLimitError(APIError):
    """The request exceeded the API rate limit."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        error: Any = None,
        payload: Any = None,
        retry_after: float | None = None,
        limit: int | None = None,
        remaining: int | None = None,
        reset_at: datetime | None = None,
    ) -> None:
        super().__init__(
            message,
            status_code=status_code,
            error=error,
            payload=payload,
        )
        self.retry_after = retry_after
        self.limit = limit
        self.remaining = remaining
        self.reset_at = reset_at


class NetworkError(KaliumError):
    """A connection or timeout error prevented an API response."""


class InvalidResponseError(KaliumError):
    """The API returned a response with an unexpected format."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        url: str,
        content_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.content_type = content_type