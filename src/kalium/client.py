"""Synchronous HTTP client for the public KaliumLabs API."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
from typing import Any, Iterator
from urllib.parse import quote, urlsplit

import requests

from . import __version__
from .exceptions import (
    APIError,
    AuthenticationError,
    ForbiddenError,
    InvalidResponseError,
    NetworkError,
    NotFoundError,
    RateLimitError,
)

API_BASE_URL = "https://kaliumlab.com/api/public/labs"
MAX_PAGE_SIZE = 100
_RETRYABLE_STATUSES = {429, 500, 502, 503, 504}


class KaliumClient:
    """Access labs, statistics, and images from the KaliumLabs API.

    The API key can be passed explicitly or read from ``KALIUM_API_KEY``.
    This client does not load ``.env`` files; applications should load their
    own environment configuration.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = API_BASE_URL,
        timeout: float = 10.0,
        max_retries: int = 2,
        backoff_factor: float = 0.5,
        max_retry_wait: float = 300.0,
        user_agent: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        api_key = api_key or os.getenv("KALIUM_API_KEY")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError(
                "An API key is required; pass api_key or set KALIUM_API_KEY."
            )
        if not isinstance(base_url, str):
            raise TypeError("base_url must be a string.")
        parsed_url = urlsplit(base_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError("base_url must be an absolute HTTPS URL.")
        if parsed_url.query or parsed_url.fragment:
            raise ValueError("base_url must not contain a query or fragment.")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)):
            raise TypeError("timeout must be a positive number.")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be a positive number.")
        if isinstance(max_retries, bool) or not isinstance(max_retries, int):
            raise TypeError("max_retries must be a non-negative integer.")
        if max_retries < 0:
            raise ValueError("max_retries must be a non-negative integer.")
        if isinstance(backoff_factor, bool) or not isinstance(
            backoff_factor, (int, float)
        ):
            raise TypeError("backoff_factor must be a non-negative number.")
        if not math.isfinite(backoff_factor) or backoff_factor < 0:
            raise ValueError("backoff_factor must be a non-negative number.")
        if isinstance(max_retry_wait, bool) or not isinstance(
            max_retry_wait, (int, float)
        ):
            raise TypeError("max_retry_wait must be a non-negative number.")
        if not math.isfinite(max_retry_wait) or max_retry_wait < 0:
            raise ValueError("max_retry_wait must be a non-negative number.")
        if user_agent is not None and (
            not isinstance(user_agent, str) or not user_agent.strip()
        ):
            raise ValueError("user_agent must be a non-empty string or None.")

        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.max_retries = max_retries
        self.backoff_factor = float(backoff_factor)
        self.max_retry_wait = float(max_retry_wait)
        self._session = session if session is not None else requests.Session()
        self._owns_session = session is None
        self._closed = False
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key.strip()}",
                "Accept": "application/json",
                "User-Agent": user_agent or f"KaliumPython/{__version__}",
            }
        )

    def __enter__(self) -> KaliumClient:
        self._ensure_open()
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying session if this client created it."""
        if not self._closed and self._owns_session:
            self._session.close()
        self._closed = True

    def list_labs(
        self,
        *,
        category: str | None = None,
        difficulty: str | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return one page of labs as the API's original JSON mapping."""
        self._validate_pagination(limit, offset)
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        for name, value in (
            ("category", category),
            ("difficulty", difficulty),
            ("status", status),
            ("search", search),
        ):
            if value is not None:
                if not isinstance(value, str):
                    raise TypeError(f"{name} must be a string or None.")
                params[name] = value
        response = self._request("GET", "", params=params)
        return self._json_object(response)

    def iter_labs(
        self,
        *,
        page_size: int = 50,
        category: str | None = None,
        difficulty: str | None = None,
        status: str | None = None,
        search: str | None = None,
        offset: int = 0,
    ) -> Iterator[dict[str, Any]]:
        """Yield labs across pages, stopping at the API's reported total."""
        self._validate_pagination(page_size, offset)
        current_offset = offset
        seen_ids: set[str] = set()
        while True:
            page = self.list_labs(
                category=category,
                difficulty=difficulty,
                status=status,
                search=search,
                limit=page_size,
                offset=current_offset,
            )
            labs = page.get("labs")
            if not isinstance(labs, list):
                raise InvalidResponseError(
                    "The list response does not contain a labs array.",
                    status_code=200,
                    url=self.base_url,
                    content_type="application/json",
                )
            if not labs:
                return
            new_labs = []
            for lab in labs:
                if not isinstance(lab, dict):
                    raise InvalidResponseError(
                        "The labs array contains a non-object item.",
                        status_code=200,
                        url=self.base_url,
                        content_type="application/json",
                    )
                lab_id = lab.get("id")
                if (
                    isinstance(lab_id, bool)
                    or not isinstance(lab_id, (str, int))
                    or not str(lab_id).strip()
                ):
                    raise InvalidResponseError(
                        "A lab in the list response has no valid ID.",
                        status_code=200,
                        url=self.base_url,
                        content_type="application/json",
                    )
                normalized_id = str(lab_id)
                if normalized_id in seen_ids:
                    continue
                seen_ids.add(normalized_id)
                new_labs.append(lab)
            if not new_labs:
                raise InvalidResponseError(
                    "Pagination returned a page with no new lab IDs.",
                    status_code=200,
                    url=self.base_url,
                    content_type="application/json",
                )
            yield from new_labs
            current_offset += len(labs)
            total = page.get("total")
            if isinstance(total, int) and not isinstance(total, bool):
                if current_offset >= total:
                    return
            if len(labs) < page_size:
                return

    def get_lab(self, lab_id: str | int) -> dict[str, Any]:
        """Return the detail mapping for one lab ID."""
        encoded_id = self._encode_id(lab_id)
        response = self._request("GET", encoded_id)
        payload = self._json_object(response)
        lab = payload.get("lab")
        if not isinstance(lab, dict):
            raise InvalidResponseError(
                "The detail response does not contain a lab object.",
                status_code=response.status_code,
                url=response.url,
                content_type=response.headers.get("Content-Type"),
            )
        return lab

    def get_lab_image(self, lab_id: str | int) -> bytes:
        """Download and return the image bytes for a lab."""
        encoded_id = self._encode_id(lab_id)
        response = self._request("GET", f"{encoded_id}/image", accept="image/*")
        return response.content

    def get_stats(self) -> dict[str, Any]:
        """Return the aggregate statistics mapping."""
        response = self._request("GET", "stats")
        return self._json_object(response)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        accept: str = "application/json",
    ) -> requests.Response:
        self._ensure_open()
        url = self.base_url if not path else f"{self.base_url}/{path}"
        headers = {"Accept": accept}
        for attempt in range(self.max_retries + 1):
            try:
                response = self._session.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout,
                )
            except requests.RequestException as exc:
                if attempt < self.max_retries:
                    time.sleep(self._backoff_delay(attempt))
                    continue
                raise NetworkError(f"Request to {url} failed: {exc}") from exc

            if response.status_code in _RETRYABLE_STATUSES:
                delay = self._retry_delay(response, attempt)
                if attempt < self.max_retries:
                    if delay > self.max_retry_wait:
                        raise self._http_error(response)
                    response.close()
                    time.sleep(delay)
                    continue
                raise self._http_error(response)
            if response.status_code >= 400:
                raise self._http_error(response)
            return response

        raise RuntimeError("Request retry loop exited unexpectedly.")

    def _http_error(self, response: requests.Response) -> APIError:
        try:
            payload = self._parse_json(response)
        except InvalidResponseError:
            payload = None
        error = payload.get("error") if isinstance(payload, dict) else None
        message = None
        if isinstance(payload, dict):
            message = payload.get("message") or error
        message = str(message or f"API request failed with HTTP {response.status_code}.")
        common = {
            "status_code": response.status_code,
            "error": error,
            "payload": payload,
        }
        if response.status_code == 401:
            return AuthenticationError(message, **common)
        if response.status_code == 403:
            return ForbiddenError(message, **common)
        if response.status_code == 404:
            return NotFoundError(message, **common)
        if response.status_code == 429:
            return RateLimitError(
                message,
                **common,
                retry_after=self._retry_after_seconds(response),
                limit=self._header_int(response, "X-RateLimit-Limit"),
                remaining=self._header_int(response, "X-RateLimit-Remaining"),
                reset_at=self._reset_at(response),
            )
        return APIError(message, **common)

    def _json_object(self, response: requests.Response) -> dict[str, Any]:
        payload = self._parse_json(response)
        if not isinstance(payload, dict):
            raise InvalidResponseError(
                "Expected a JSON object from the API.",
                status_code=response.status_code,
                url=response.url,
                content_type=response.headers.get("Content-Type"),
            )
        if payload.get("success") is False:
            message = payload.get("message") or payload.get("error")
            raise APIError(
                str(message or "The API reported an unsuccessful response."),
                status_code=response.status_code,
                error=payload.get("error"),
                payload=payload,
            )
        return payload

    @staticmethod
    def _parse_json(response: requests.Response) -> Any:
        try:
            return response.json()
        except (requests.exceptions.JSONDecodeError, ValueError) as exc:
            raise InvalidResponseError(
                "The API response was not valid JSON.",
                status_code=response.status_code,
                url=response.url,
                content_type=response.headers.get("Content-Type"),
            ) from exc

    def _retry_delay(self, response: requests.Response, attempt: int) -> float:
        retry_after = self._retry_after_seconds(response)
        if retry_after is not None:
            return retry_after
        if response.status_code == 429:
            reset_at = self._reset_at(response)
            if reset_at is not None:
                return max(0.0, (reset_at - datetime.now(timezone.utc)).total_seconds())
        return self._backoff_delay(attempt)

    def _backoff_delay(self, attempt: int) -> float:
        return min(self.backoff_factor * (2**attempt), 30.0)

    @staticmethod
    def _retry_after_seconds(response: requests.Response) -> float | None:
        value = response.headers.get("Retry-After")
        if value is None:
            return None
        try:
            seconds = float(value)
            return max(0.0, seconds) if math.isfinite(seconds) else None
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(value)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=timezone.utc)
                return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    @staticmethod
    def _reset_at(response: requests.Response) -> datetime | None:
        value = response.headers.get("X-RateLimit-Reset")
        if value is None:
            return None
        try:
            timestamp = float(value)
            if not math.isfinite(timestamp):
                return None
            if timestamp > 1_000_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None

    @staticmethod
    def _header_int(response: requests.Response, name: str) -> int | None:
        value = response.headers.get(name)
        try:
            return int(value) if value is not None else None
        except ValueError:
            return None

    @staticmethod
    def _validate_pagination(limit: int, offset: int) -> None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an integer.")
        if not 1 <= limit <= MAX_PAGE_SIZE:
            raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}.")
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise TypeError("offset must be an integer.")
        if offset < 0:
            raise ValueError("offset must be zero or greater.")

    @staticmethod
    def _encode_id(lab_id: str | int) -> str:
        if isinstance(lab_id, bool) or not isinstance(lab_id, (str, int)):
            raise TypeError("lab_id must be a string or integer.")
        value = str(lab_id).strip()
        if not value:
            raise ValueError("lab_id must not be empty.")
        return quote(value, safe="")

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("This KaliumClient has been closed.")