"""Exception hierarchy for the Spatial Intelligence Engine SDK.

Every error raised by the SDK derives from :class:`SPEError`, so callers can
guard an entire workflow with a single ``except SPEError``. Validation errors
also derive from :class:`ValueError` and HTTP/transport errors from
:class:`RuntimeError` to remain friendly to generic Python code.
"""

from __future__ import annotations

from typing import Any


class SPEError(Exception):
    """Base class for every error raised by the SPE SDK."""


class SPEValidationError(SPEError, ValueError):
    """Raised when caller-supplied geometry or parameters are invalid."""


class SPEEngineError(SPEError, RuntimeError):
    """Raised when local spatial processing cannot complete."""


class SPEModelUnavailableError(SPEEngineError):
    """Raised when a perception model has no usable runtime or weights."""


class SPETransportError(SPEError, RuntimeError):
    """Base class for HTTP transport failures (connection or timeout)."""


class SPEConnectionError(SPETransportError):
    """Raised when the SPE HTTP API cannot be reached."""


class SPETimeoutError(SPETransportError):
    """Raised when an SPE HTTP API request exceeds its timeout."""


class SPEAPIError(SPEError):
    """Raised when the SPE HTTP API returns a non-success response.

    Attributes:
        status_code: The HTTP status code returned by the server.
        payload: The decoded JSON body, when the response was JSON.
        url: The absolute request URL.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        payload: Any | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.url = url


__all__ = [
    "SPEAPIError",
    "SPEConnectionError",
    "SPEEngineError",
    "SPEError",
    "SPEModelUnavailableError",
    "SPETimeoutError",
    "SPETransportError",
    "SPEValidationError",
]
