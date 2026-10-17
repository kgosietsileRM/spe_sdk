"""Pluggable HTTP transports for the SPE client.

The SDK ships a zero-dependency transport built on the standard library's
:mod:`urllib`. When :mod:`requests` or :mod:`httpx` happen to be installed, the
client can use them instead for connection pooling and HTTP/2, without adding a
hard dependency.

Each transport performs exactly **one** request and returns a
``(status, headers, body)`` triple. It never retries and never raises for a
non-success status; retries and status handling live in
:class:`~spe.client.SPEClient`. Transport-level failures are surfaced as
:class:`~spe.exceptions.SPEConnectionError` or
:class:`~spe.exceptions.SPETimeoutError`.
"""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from .exceptions import SPEConnectionError, SPETimeoutError

__all__ = [
    "Transport",
    "UrllibTransport",
    "get_default_transport",
]


@runtime_checkable
class Transport(Protocol):
    """Structural interface implemented by every transport backend."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, str], bytes]:
        """Perform one HTTP request and return ``(status, headers, body)``."""
        ...

    def close(self) -> None:
        """Release any pooled connections. May be a no-op."""
        ...


class UrllibTransport:
    """Default transport built on :mod:`urllib.request` (no dependencies)."""

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, str], bytes]:
        request = urllib.request.Request(url, data=data, headers=dict(headers), method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers or {}), error.read()
        except TimeoutError as error:
            raise SPETimeoutError(f"Request to {url} timed out after {timeout}s.") from error
        except urllib.error.URLError as error:
            reason = getattr(error, "reason", error)
            if isinstance(reason, (socket.timeout, TimeoutError)):
                raise SPETimeoutError(f"Request to {url} timed out after {timeout}s.") from error
            raise SPEConnectionError(f"Unable to reach {url}: {reason}") from error

    def close(self) -> None:
        """No-op; the stdlib transport holds no persistent state."""
        return None


class RequestsTransport:
    """Transport backed by :mod:`requests` (used only when installed)."""

    def __init__(self) -> None:
        import requests

        self._session = requests.Session()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, str], bytes]:
        import requests

        try:
            response = self._session.request(
                method, url, headers=dict(headers), data=data, timeout=timeout
            )
        except requests.exceptions.Timeout as error:
            raise SPETimeoutError(f"Request to {url} timed out after {timeout}s.") from error
        except requests.exceptions.RequestException as error:
            raise SPEConnectionError(f"Unable to reach {url}: {error}") from error
        return response.status_code, dict(response.headers), response.content

    def close(self) -> None:
        self._session.close()


class HttpxTransport:
    """Transport backed by :mod:`httpx` (used only when installed)."""

    def __init__(self) -> None:
        import httpx

        self._client = httpx.Client()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        data: bytes | None,
        timeout: float,
    ) -> tuple[int, Mapping[str, str], bytes]:
        import httpx

        try:
            response = self._client.request(
                method, url, headers=dict(headers), content=data, timeout=timeout
            )
        except httpx.TimeoutException as error:
            raise SPETimeoutError(f"Request to {url} timed out after {timeout}s.") from error
        except httpx.TransportError as error:
            raise SPEConnectionError(f"Unable to reach {url}: {error}") from error
        return response.status_code, dict(response.headers), response.content

    def close(self) -> None:
        self._client.close()


def get_default_transport(prefer: str | None = None) -> Transport:
    """Return the best available transport.

    Args:
        prefer: Force a backend by name (``"urllib"``, ``"requests"``, or
            ``"httpx"``). When omitted, ``httpx`` then ``requests`` are used if
            importable, otherwise the stdlib transport.
    """
    if prefer is not None:
        chosen = prefer.lower()
        if chosen == "urllib":
            return UrllibTransport()
        if chosen == "requests":
            return RequestsTransport()
        if chosen == "httpx":
            return HttpxTransport()
        raise ValueError(f"Unknown transport: {prefer!r}")

    for factory in (HttpxTransport, RequestsTransport):
        try:
            return factory()
        except ImportError:
            continue
    return UrllibTransport()
