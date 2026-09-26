"""The canonical package for the Kalium library."""

__version__ = "0.1.0"

from .client import API_BASE_URL, KaliumClient
from .exceptions import (
	APIError,
	AuthenticationError,
	ForbiddenError,
	InvalidResponseError,
	KaliumError,
	NetworkError,
	NotFoundError,
	RateLimitError,
)

__all__ = [
	"API_BASE_URL",
	"APIError",
	"AuthenticationError",
	"ForbiddenError",
	"InvalidResponseError",
	"KaliumClient",
	"KaliumError",
	"NetworkError",
	"NotFoundError",
	"RateLimitError",
	"__version__",
]