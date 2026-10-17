"""Tests for the pluggable HTTP transports."""

from __future__ import annotations

import email.message
import io
import sys
import types

import pytest

from spe import SPEConnectionError, SPETimeoutError
from spe.transport import (
    HttpxTransport,
    RequestsTransport,
    Transport,
    UrllibTransport,
    get_default_transport,
)


class _FakeResponse:
    def __init__(self, status_code, headers, content):
        self.status_code = status_code
        self.headers = headers
        self.content = content


class _RequestsTimeoutError(Exception):
    pass


class _RequestsExceptionError(Exception):
    pass


def _install_requests(monkeypatch, *, response=None, error=None):
    module = types.ModuleType("requests")
    module.exceptions = types.SimpleNamespace(  # type: ignore[attr-defined]
        Timeout=_RequestsTimeoutError, RequestException=_RequestsExceptionError
    )

    class Session:
        def __init__(self):
            self.closed = False

        def request(self, method, url, **kwargs):
            if error is not None:
                raise error
            return response

        def close(self):
            self.closed = True

    module.Session = Session  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "requests", module)


class _HttpxTimeoutError(Exception):
    pass


class _HttpxTransportError(Exception):
    pass


def _install_httpx(monkeypatch, *, response=None, error=None):
    module = types.ModuleType("httpx")
    module.TimeoutException = _HttpxTimeoutError  # type: ignore[attr-defined]
    module.TransportError = _HttpxTransportError  # type: ignore[attr-defined]

    class Client:
        def __init__(self):
            self.closed = False

        def request(self, method, url, **kwargs):
            if error is not None:
                raise error
            return response

        def close(self):
            self.closed = True

    module.Client = Client  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "httpx", module)


def test_default_transport_is_usable():
    transport = get_default_transport()
    assert isinstance(transport, Transport)
    assert hasattr(transport, "request")
    assert transport.close() is None


def test_get_default_transport_prefers_urllib_when_forced():
    assert isinstance(get_default_transport("urllib"), UrllibTransport)
    assert isinstance(get_default_transport("URLLIB"), UrllibTransport)


def test_get_default_transport_unknown_backend():
    with pytest.raises(ValueError):
        get_default_transport("nope")


def test_get_default_transport_missing_optional_backend():
    import importlib.util

    if importlib.util.find_spec("httpx") is not None:
        pytest.skip("httpx installed; cannot exercise missing-backend path")
    with pytest.raises(ImportError):
        get_default_transport("httpx")


def test_urllib_transport_maps_connection_error(monkeypatch):
    import urllib.request

    def _refuse(*_args, **_kwargs):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    with pytest.raises(SPEConnectionError):
        UrllibTransport().request("GET", "http://x", headers={}, data=None, timeout=1.0)


def test_urllib_transport_maps_timeout(monkeypatch):
    import urllib.request

    def _timeout(*_args, **_kwargs):
        raise urllib.error.URLError(TimeoutError("late"))

    monkeypatch.setattr(urllib.request, "urlopen", _timeout)
    with pytest.raises(SPETimeoutError):
        UrllibTransport().request("GET", "http://x", headers={}, data=None, timeout=1.0)


def test_urllib_transport_returns_http_error_status(monkeypatch):
    import urllib.request

    headers = email.message.Message()
    headers["Content-Type"] = "application/json"
    body = io.BytesIO(b'{"error": "boom"}')

    def _http_error(request, *args, **kwargs):
        raise urllib.error.HTTPError("http://x", 400, "Bad Request", headers, body)

    monkeypatch.setattr(urllib.request, "urlopen", _http_error)
    status, response_headers, payload = UrllibTransport().request(
        "GET", "http://x", headers={}, data=None, timeout=1.0
    )
    assert status == 400
    assert response_headers["Content-Type"] == "application/json"
    assert payload == b'{"error": "boom"}'


def test_urllib_transport_maps_builtin_timeout(monkeypatch):
    import urllib.request

    def _timeout(*_args, **_kwargs):
        raise TimeoutError("late")

    monkeypatch.setattr(urllib.request, "urlopen", _timeout)
    with pytest.raises(SPETimeoutError):
        UrllibTransport().request("GET", "http://x", headers={}, data=None, timeout=1.0)


# -- optional requests backend --------------------------------------------
def test_requests_transport_round_trip(monkeypatch):
    _install_requests(monkeypatch, response=_FakeResponse(200, {"X": "y"}, b"body"))
    transport = RequestsTransport()
    assert transport.request("GET", "http://x", headers={}, data=None, timeout=1.0) == (
        200,
        {"X": "y"},
        b"body",
    )
    assert transport.close() is None


def test_requests_transport_maps_timeout(monkeypatch):
    _install_requests(monkeypatch, error=_RequestsTimeoutError())
    with pytest.raises(SPETimeoutError):
        RequestsTransport().request("GET", "http://x", headers={}, data=None, timeout=1.0)


def test_requests_transport_maps_connection_error(monkeypatch):
    _install_requests(monkeypatch, error=_RequestsExceptionError())
    with pytest.raises(SPEConnectionError):
        RequestsTransport().request("GET", "http://x", headers={}, data=None, timeout=1.0)


# -- optional httpx backend ------------------------------------------------
def test_httpx_transport_round_trip(monkeypatch):
    _install_httpx(monkeypatch, response=_FakeResponse(200, {"X": "y"}, b"body"))
    transport = HttpxTransport()
    assert transport.request("GET", "http://x", headers={}, data=None, timeout=1.0) == (
        200,
        {"X": "y"},
        b"body",
    )
    assert transport.close() is None


def test_httpx_transport_maps_timeout(monkeypatch):
    _install_httpx(monkeypatch, error=_HttpxTimeoutError())
    with pytest.raises(SPETimeoutError):
        HttpxTransport().request("GET", "http://x", headers={}, data=None, timeout=1.0)


def test_httpx_transport_maps_connection_error(monkeypatch):
    _install_httpx(monkeypatch, error=_HttpxTransportError())
    with pytest.raises(SPEConnectionError):
        HttpxTransport().request("GET", "http://x", headers={}, data=None, timeout=1.0)


def test_get_default_transport_prefers_installed_backend(monkeypatch):
    _install_httpx(monkeypatch, response=_FakeResponse(200, {}, b""))
    assert isinstance(get_default_transport(), HttpxTransport)


def test_get_default_transport_falls_back_to_requests(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _no_httpx(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("no httpx")
        return real_import(name, *args, **kwargs)

    _install_requests(monkeypatch, response=_FakeResponse(200, {}, b""))
    monkeypatch.setattr(builtins, "__import__", _no_httpx)
    assert isinstance(get_default_transport(), RequestsTransport)


def test_get_default_transport_forced_backends(monkeypatch):
    _install_requests(monkeypatch, response=_FakeResponse(200, {}, b""))
    _install_httpx(monkeypatch, response=_FakeResponse(200, {}, b""))
    assert isinstance(get_default_transport("requests"), RequestsTransport)
    assert isinstance(get_default_transport("httpx"), HttpxTransport)


def test_get_default_transport_falls_back_to_urllib(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name in {"httpx", "requests"}:
            raise ImportError(f"no {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    assert isinstance(get_default_transport(), UrllibTransport)
