"""Tests for the asyncio client wrapper."""

from __future__ import annotations

import asyncio

import pytest

from spe import AsyncSPEClient, SPEAPIError
from spe.transport import UrllibTransport
from tests.conftest import MODEL


def _run(coro):
    return asyncio.run(coro)


def test_async_health_and_context_manager(base_url):
    async def scenario():
        async with AsyncSPEClient(base_url, transport=UrllibTransport()) as client:
            assert client.base_url == base_url
            return await client.health()

    assert _run(scenario()) == {"status": "ok"}


def test_async_core_methods(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, retries=0, transport=UrllibTransport())
        try:
            state = await client.get_state()
            models = await client.list_models()
            updated = await client.set_grid(4, 6)
            grid = await client.get_grid()
            transformed = await client.transform_points([[1, 2]])
            detected = await client.detect(model_id="model-a")
            source = await client.create_source(b"bytes", filename="x.jpg")
            media_url = client.source_media_url(source["id"])
            await client.aclose()
            return state, models, updated, grid, transformed, detected, media_url
        finally:
            await client.aclose()

    state, models, updated, grid, transformed, detected, media_url = _run(scenario())
    assert state["state"]["calibrated"] is True
    assert models[0]["id"] == "model-a"
    assert updated["columns"] == 6
    assert grid["rows"] == 3
    assert transformed["direction"] == "image_to_reference"
    assert detected["model"]["id"] == "model-a"
    assert media_url.endswith("/media")


def test_async_roi_lifecycle(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, retries=0, transport=UrllibTransport())
        created = await client.create_roi([[0, 0], [10, 0], [10, 10], [0, 10]])
        updated = await client.update_roi([[0, 0], [10, 0], [10, 10], [0, 10]])
        current = await client.get_roi()
        await client.delete_roi()
        await client.aclose()
        return created, updated, current

    created, updated, current = _run(scenario())
    assert created["status"] == "defined"
    assert updated["status"] == "defined"
    assert "points" in current


def test_async_analysis_and_rendering(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, transport=UrllibTransport())
        started = await client.start_analysis_session("a1", "src-1", MODEL)
        await client.update_analysis_status("a1", inference_fps=12.0)
        completed = await client.complete_analysis_session("a1")
        grid = await client.generate_grid(b"img", filename="f.png")
        metadata = await client.video_metadata(b"vid", filename="c.mp4")
        await client.aclose()
        return started, completed, grid, metadata

    started, completed, grid, metadata = _run(scenario())
    assert started["analysis_id"] == "a1"
    assert completed["status"] == "complete"
    assert "image" in grid
    assert metadata["fps"] == 30.0


def test_async_propagates_api_error(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, retries=0, transport=UrllibTransport())
        try:
            with pytest.raises(SPEAPIError):
                await client._call("_request", "GET", "/api/error")
        finally:
            await client.aclose()

    _run(scenario())


def test_async_from_env(monkeypatch):
    monkeypatch.setenv("SPE_API_URL", "http://example.test:9000")
    client = AsyncSPEClient.from_env(transport=UrllibTransport())
    assert client.base_url == "http://example.test:9000"


def test_async_from_env_default(monkeypatch):
    monkeypatch.delenv("SPE_API_URL", raising=False)
    client = AsyncSPEClient.from_env(transport=UrllibTransport())
    assert client.base_url == "http://127.0.0.1:5000"


def test_async_remaining_source_and_calibration_methods(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, retries=0, transport=UrllibTransport())
        try:
            source = await client.get_source("src-1")
            await client.delete_source("src-1")
            media = await client.get_source_media("src-1")
            calibration = await client.calibrate([[0, 0], [10, 0], [10, 10], [0, 10]], 100, 100)
            fetched = await client.get_calibration()
            updated = await client.update_calibration(
                [[0, 0], [10, 0], [10, 10], [0, 10]], 100, 100, units="m"
            )
            await client.delete_calibration()
            return source, media, calibration, fetched, updated
        finally:
            await client.aclose()

    source, media, calibration, fetched, updated = _run(scenario())
    assert source["id"] == "src-1"
    assert media.startswith(b"\x89PNG")
    assert calibration["calibration"]["status"] == "calibrated"
    assert fetched["status"] == "uncalibrated"
    assert updated["calibration"]["status"] == "calibrated"


def test_async_roi_and_grid_methods(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, retries=0, transport=UrllibTransport())
        try:
            roi = await client.get_roi()
            created = await client.create_roi([[0, 0], [1, 0], [1, 1], [0, 1]])
            await client.delete_roi()
            await client.delete_grid()
            return roi, created
        finally:
            await client.aclose()

    roi, created = _run(scenario())
    assert roi["status"] == "defined"
    assert created["status"] == "defined"


def test_async_spatial_and_rendering_methods(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, retries=0, transport=UrllibTransport())
        try:
            inspected = await client.inspect_point([1, 2], spatial_state={"a": 1})
            calibrated = await client.generate_calibrated_grid(
                b"img",
                [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                source_points=[[0, 0], [1, 0], [1, 1], [0, 1]],
            )
            return inspected, calibrated
        finally:
            await client.aclose()

    inspected, calibrated = _run(scenario())
    assert inspected["inspection"]["status"] == "valid"
    assert calibrated["metadata"]["rows"] == 4


def test_async_model_methods(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, retries=0, transport=UrllibTransport())
        try:
            model = await client.get_model("model-a")
            status = await client.model_status("model-a")
            loaded = await client.load_model("model-a")
            unloaded = await client.unload_model("model-a")
            classes = await client.model_classes("model-a")
            return model, status, loaded, unloaded, classes
        finally:
            await client.aclose()

    model, status, loaded, unloaded, classes = _run(scenario())
    assert model["id"] == "model-a"
    assert status["runtime"]["status"] == "ready"
    assert loaded["runtime"]["status"] == "ready"
    assert unloaded["runtime"]["status"] == "idle"
    assert classes == ["person", "car"]


def test_async_detect_frame(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, retries=0, transport=UrllibTransport())
        try:
            return await client.detect_frame(
                b"frame", filename="f.jpg", tracking=True, tracking_mode="iou", interval_ms=40.0
            )
        finally:
            await client.aclose()

    result = _run(scenario())
    assert result["model"]["id"] == "model-a"


def test_async_models_returns_descriptors(base_url):
    async def scenario():
        client = AsyncSPEClient(base_url, retries=0, transport=UrllibTransport())
        try:
            return await client.models()
        finally:
            await client.aclose()

    models = _run(scenario())
    assert models[0].id == "model-a"
    assert models[0].supports_tracking is False


def test_async_auth_headers(base_url, server):
    async def scenario():
        client = AsyncSPEClient(
            base_url,
            retries=0,
            transport=UrllibTransport(),
            api_key="k",
            token="t",
            headers={"X-Trace": "v"},
        )
        try:
            await client.health()
        finally:
            await client.aclose()

    _run(scenario())
    headers = {key.lower(): value for key, value in server.requests[-1]["headers"].items()}
    assert headers["x-api-key"] == "k"
    assert headers["authorization"] == "Bearer t"
    assert headers["x-trace"] == "v"
