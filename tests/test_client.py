"""Tests for the stdlib HTTP client against a local mock server."""

from __future__ import annotations

import io
import json

import pytest

from spe import SPEAPIError, SPEClient, SPEConnectionError, SPEValidationError
from spe.transport import UrllibTransport
from tests.conftest import MODEL

HOMEOGRAPHY = [[1.0, 0, 0], [0, 1.0, 0], [0, 0, 1.0]]


def _last_body(server) -> dict:
    return json.loads(server.requests[-1]["body"])


# -- health & state --------------------------------------------------------
def test_health(client):
    assert client.health() == {"status": "ok"}


def test_get_state(client):
    assert client.get_state()["state"]["calibrated"] is True


# -- sources ---------------------------------------------------------------
def test_create_source_multipart(server, client):
    source = client.create_source(b"binary-image-bytes", filename="x.jpg", source_type="image")
    assert source["id"] == "src-1"
    request = server.requests[-1]
    assert request["method"] == "POST"
    assert request["headers"]["Content-Type"].startswith("multipart/form-data; boundary=")
    assert b'filename="x.jpg"' in request["body"]
    assert b"binary-image-bytes" in request["body"]
    assert b'name="type"' in request["body"]


def test_create_source_from_path(server, client, tmp_path):
    uploaded = tmp_path / "pic.png"
    uploaded.write_bytes(b"\x89PNGdata")
    source = client.create_source(uploaded)
    assert source["id"] == "src-1"
    assert b'filename="pic.png"' in server.requests[-1]["body"]


def test_get_source(client):
    assert client.get_source("src-1")["id"] == "src-1"


def test_delete_source(client):
    assert client.delete_source("src-1") is None


def test_source_media_url(client):
    assert client.source_media_url("src-1").endswith("/api/sources/src-1/media")


def test_get_source_media(client):
    assert client.get_source_media("src-1").startswith(b"\x89PNG")


def test_read_binary_rejects_missing_path(client):
    from spe import SPEValidationError

    with pytest.raises(SPEValidationError):
        client.create_source("does-not-exist.png")


# -- calibration -----------------------------------------------------------
def test_calibrate_payload(server, client):
    client.calibrate([[0, 0], [10, 0], [10, 10], [0, 10]], 1000, 600, rows=4, columns=6)
    request = server.requests[-1]
    assert request["method"] == "POST"
    body = json.loads(request["body"])
    assert body["source"] == {"width": 1000, "height": 600}
    assert body["calibrated_grid_rows"] == 4
    assert body["calibrated_grid_columns"] == 6


def test_update_calibration_uses_put(server, client):
    client.update_calibration([[0, 0], [10, 0], [10, 10], [0, 10]], 1000, 600)
    request = server.requests[-1]
    assert request["method"] == "PUT"
    assert request["path"] == "/api/calibration"


def test_get_and_delete_calibration(client):
    assert client.get_calibration()["status"] == "uncalibrated"
    assert client.delete_calibration() is None


# -- roi & grid ------------------------------------------------------------
def test_roi_lifecycle(server, client):
    assert "points" in client.get_roi()
    assert client.create_roi([[0, 0], [10, 0], [10, 10], [0, 10]])["status"] == "defined"
    assert client.delete_roi() is None
    assert server.requests[-1]["method"] == "DELETE"


def test_grid_lifecycle(server, client):
    assert client.get_grid()["rows"] == 3
    assert client.set_grid(4, 6)["columns"] == 6
    assert server.requests[-1]["method"] == "PUT"
    assert client.delete_grid() is None


# -- spatial queries -------------------------------------------------------
def test_transform_points_payload(server, client):
    result = client.transform_points([[1, 2]], homography=HOMEOGRAPHY)
    assert result["direction"] == "image_to_reference"
    body = _last_body(server)
    assert body["homography"] == HOMEOGRAPHY


def test_inspect_point_payload(server, client):
    client.inspect_point([123, 45], calibration={"homography": HOMEOGRAPHY})
    body = _last_body(server)
    assert body["point"] == [123, 45]
    assert "calibration" in body


def test_inspect_point_xy(server, client):
    client.inspect_point(x=10, y=20)
    assert _last_body(server)["x"] == 10


def test_inspect_point_requires_coordinates(client):
    from spe import SPEValidationError

    with pytest.raises(SPEValidationError):
        client.inspect_point()


# -- rendering -------------------------------------------------------------
def test_generate_grid_multipart(server, client):
    result = client.generate_grid(b"\x89PNG", filename="f.png", rows=4, columns=5)
    assert result["metadata"]["rows"] == 8
    request = server.requests[-1]
    assert request["headers"]["Content-Type"].startswith("multipart/form-data")
    assert b'name="rows"' in request["body"]


def test_generate_calibrated_grid_multipart(server, client):
    result = client.generate_calibrated_grid(b"\x89PNG", HOMEOGRAPHY, filename="f.png")
    assert "image" in result
    assert b'name="homography"' in server.requests[-1]["body"]


def test_video_metadata(server, client):
    meta = client.video_metadata(b"video-bytes", filename="clip.mp4")
    assert meta["fps"] == 30.0
    assert b'name="video"' in server.requests[-1]["body"]


# -- models & analysis -----------------------------------------------------
def test_list_and_load_models(client):
    models = client.list_models()
    assert models[0]["id"] == "model-a"
    assert client.get_model("model-a")["id"] == "model-a"
    assert client.model_status("model-a")["runtime"]["status"] == "ready"
    assert client.load_model("model-a")["runtime"]["status"] == "ready"
    assert client.unload_model("model-a")["runtime"]["status"] == "idle"
    assert client.model_classes("model-a") == ["person", "car"]


def test_detect(client):
    result = client.detect(model_id="model-a", confidence=0.5, classes=["person"])
    assert result["model"]["id"] == "model-a"


def test_detect_frame_multipart(server, client):
    client.detect_frame(b"jpegbytes", filename="frame.jpg", analysis_id="a1", source_id="src-1")
    request = server.requests[-1]
    assert request["headers"]["Content-Type"].startswith("multipart/form-data")
    assert b'name="frame"' in request["body"]
    assert b"jpegbytes" in request["body"]


def test_analysis_session_methods(client):
    started = client.start_analysis_session("a1", "src-1", MODEL)
    assert started["analysis_id"] == "a1"
    assert client.update_analysis_status("a1", inference_fps=12.0)["status"] == "running"
    assert client.complete_analysis_session("a1")["status"] == "complete"


# -- errors ----------------------------------------------------------------
def test_api_error_raises_typed_error(client):
    with pytest.raises(SPEAPIError) as error:
        client._request("GET", "/api/error")
    assert error.value.status_code == 400
    assert str(error.value) == "boom"
    assert error.value.url.endswith("/api/error")


def test_connection_error_is_typed(monkeypatch):
    import urllib.error
    import urllib.request

    def _refuse(*_args, **_kwargs):
        raise urllib.error.URLError(ConnectionRefusedError("refused"))

    monkeypatch.setattr(urllib.request, "urlopen", _refuse)
    with pytest.raises(SPEConnectionError):
        SPEClient("http://127.0.0.1:5000", retries=0, transport=UrllibTransport()).health()


def test_timeout_error_is_typed(monkeypatch):
    import urllib.error
    import urllib.request

    def _timeout(*_args, **_kwargs):
        raise urllib.error.URLError(TimeoutError("timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", _timeout)
    from spe import SPETimeoutError

    with pytest.raises(SPETimeoutError):
        SPEClient("http://127.0.0.1:5000", retries=0, transport=UrllibTransport()).health()


def test_unreachable_server_raises_transport_error():
    from spe import SPETransportError

    failing = SPEClient("http://127.0.0.1:1", timeout=1.0, retries=0, transport=UrllibTransport())
    with pytest.raises(SPETransportError):
        failing.health()


def test_retries_idempotent_request():
    from spe import SPEConnectionError as _ConnErr

    class _FlakyTransport:
        def __init__(self, failures: int) -> None:
            self.failures = failures
            self.calls = 0

        def request(self, method, url, *, headers, data, timeout):
            self.calls += 1
            if self.calls <= self.failures:
                raise _ConnErr("boom")
            return 200, {"Content-Type": "application/json"}, b'{"status": "ok"}'

        def close(self) -> None:
            return None

    transport = _FlakyTransport(failures=1)
    client = SPEClient("http://example.test", retries=1, backoff=0.0, transport=transport)
    assert client.health() == {"status": "ok"}
    assert transport.calls == 2


def test_post_is_not_retried():
    from spe import SPEConnectionError as _ConnErr

    class _AlwaysFails:
        def __init__(self) -> None:
            self.calls = 0

        def request(self, method, url, *, headers, data, timeout):
            self.calls += 1
            raise _ConnErr("boom")

        def close(self) -> None:
            return None

    transport = _AlwaysFails()
    client = SPEClient("http://example.test", retries=3, backoff=0.0, transport=transport)
    with pytest.raises(SPEConnectionError):
        client.calibrate([[0, 0], [1, 0], [1, 1], [0, 1]], 10, 10)
    assert transport.calls == 1


def test_api_error_non_json_body():
    error = SPEClient._api_error(500, b"<html>oops</html>", "http://x")
    assert error.status_code == 500
    assert error.payload == b"<html>oops</html>"


# -- optional parameters ---------------------------------------------------
def test_create_source_accepts_file_object(server, client):
    buffer = io.BytesIO(b"\x89PNG-file-object")
    source = client.create_source(buffer, filename="stream.png", mime_type="image/png")
    assert source["id"] == "src-1"
    assert b'filename="stream.png"' in server.requests[-1]["body"]


def test_generate_grid_with_video_options(server, client):
    client.generate_grid(
        b"\x89PNG",
        filename="clip.mp4",
        source_type="video",
        fps=24.0,
        frame_count=120,
        show_coordinates=False,
    )
    body = server.requests[-1]["body"]
    assert b'name="fps"' in body
    assert b'name="frame_count"' in body
    assert b"false" in body


def test_generate_calibrated_grid_with_source_points(server, client):
    client.generate_calibrated_grid(
        b"\x89PNG",
        HOMEOGRAPHY,
        filename="f.png",
        rows=3,
        columns=3,
        reference_width=500.0,
        reference_height=300.0,
        source_points=[[0, 0], [10, 0], [10, 10], [0, 10]],
        show_grid=False,
        show_roi=False,
        overlay_only=True,
    )
    assert b'name="source_points"' in server.requests[-1]["body"]


def test_detect_frame_all_options(server, client):
    client.detect_frame(
        b"jpeg",
        filename="frame.jpg",
        model_id="model-a",
        confidence=0.7,
        classes=["person"],
        analysis_id="a1",
        source_id="src-1",
        timestamp=1.5,
        frame_index=3,
        tracking=True,
        tracking_mode="iou",
        target_track_id="t1",
        target_detection={"id": "t1"},
        inference_context={"scope": "roi"},
        spatial_context={"grid": {"rows": 1, "columns": 1}},
        interval_ms=40.0,
        effective_fps=25.0,
    )
    body = server.requests[-1]["body"]
    assert b'name="tracking_mode"' in body
    assert b'name="target_detection"' in body
    assert b'name="spatial_context"' in body


def test_transform_points_with_calibration(server, client):
    client.transform_points(
        [[1, 2]], calibration={"homography": HOMEOGRAPHY}, direction="reference_to_image"
    )
    body = _last_body(server)
    assert body["direction"] == "reference_to_image"
    assert "calibration" in body


def test_inspect_point_with_spatial_state(server, client):
    client.inspect_point([1, 2], spatial_state={"calibration": {"homography": HOMEOGRAPHY}})
    assert "spatial_state" in _last_body(server)


def test_inspect_point_with_source_dimensions(server, client):
    client.inspect_point(
        [1, 2],
        calibration={"homography": HOMEOGRAPHY},
        grid={"rows": 1, "columns": 1},
        source_dimensions={"width": 10, "height": 10},
    )
    body = _last_body(server)
    assert body["source_dimensions"] == {"width": 10, "height": 10}


def test_request_with_fields_only(server, client):
    client._request("POST", "/api/video/metadata", fields={"a": "1"})
    request = server.requests[-1]
    assert request["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_encode_multipart_skips_none_fields():
    content_type, body = SPEClient._encode_multipart({"present": "yes", "absent": None}, {})
    assert content_type.startswith("multipart/form-data")
    assert b'name="present"' in body
    assert b'name="absent"' not in body


def test_url_builds_query_skipping_none(client):
    url = client._url("api/thing", {"a": 1, "b": None, "c": "x"})
    assert url.endswith("/api/thing?a=1&c=x")


def test_url_without_params(client):
    assert client._url("health") == f"{client.base_url}/health"


def test_url_skips_when_all_params_none(client):
    assert client._url("/x", {"a": None}) == f"{client.base_url}/x"


def test_api_error_without_error_field():
    error = SPEClient._api_error(500, b'{"detail": "x"}', "http://y")
    assert "HTTP 500" in str(error)
    assert error.payload == {"detail": "x"}


def test_create_source_from_text_stream(server, client):
    buffer = io.StringIO("text-content")
    client.create_source(buffer, filename="notes.txt")
    assert b"text-content" in server.requests[-1]["body"]


def test_create_source_rejects_unsupported_object(client):
    with pytest.raises(SPEValidationError):
        client.create_source(12345)


def test_user_agent_header(base_url, server):
    client = SPEClient(base_url, retries=0, transport=UrllibTransport(), user_agent="spe-test/1")
    client.health()
    assert server.requests[-1]["headers"]["User-Agent"] == "spe-test/1"


def test_detect_with_source_id(server, client):
    client.detect(source_id="src-1")
    assert _last_body(server)["source_id"] == "src-1"


def test_start_analysis_session_with_context(server, client):
    client.start_analysis_session("a1", "src-1", MODEL, spatial_context={"grid": {"rows": 1}})
    assert "spatial_context" in _last_body(server)


def test_update_analysis_status_with_metrics(server, client):
    client.update_analysis_status("a1", inference_fps=12.0, interval_ms=40.0)
    body = _last_body(server)
    assert body["inference_fps"] == 12.0
    assert body["interval_ms"] == 40.0


def test_update_analysis_status_without_metrics(server, client):
    client.update_analysis_status("a1")
    body = _last_body(server)
    assert "inference_fps" not in body
    assert "interval_ms" not in body


# -- configuration ---------------------------------------------------------
def test_from_env(monkeypatch):
    monkeypatch.setenv("SPE_API_URL", "http://example.test:9000")
    client = SPEClient.from_env(transport=UrllibTransport())
    assert client.base_url == "http://example.test:9000"


def test_base_url_validation():
    from spe import SPEValidationError

    with pytest.raises(SPEValidationError):
        SPEClient("")


def test_context_manager_closes(base_url):
    with SPEClient(base_url, transport=UrllibTransport()) as client:
        assert client.health()["status"] == "ok"


def test_decode_handles_empty_and_non_json():
    assert SPEClient._decode(b"") is None
    assert SPEClient._decode(b"not json") == b"not json"
    assert SPEClient._decode(b'{"a": 1}') == {"a": 1}
