"""Shared pytest fixtures for the SPE SDK test suite."""

from __future__ import annotations

import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

from spe import SpatialEngine, SPEClient
from spe.transport import UrllibTransport

# A non-degenerate quadrilateral in TL, TR, BR, BL order inside a 1000x600 frame.
RECTANGLE = [[120, 80], [880, 110], [940, 520], [60, 540]]
SOURCE_WIDTH = 1000
SOURCE_HEIGHT = 600

MODEL = {"id": "model-a", "name": "Model A", "provider": "ultralytics", "version": "YOLOv8n"}

# (method, path) -> (status, payload). A ``None`` payload produces an empty body.
ROUTES: dict[tuple[str, str], tuple[int, object]] = {
    ("GET", "/health"): (200, {"status": "ok"}),
    ("GET", "/api/state"): (200, {"version": "1.0", "state": {"calibrated": True}}),
    ("GET", "/api/models"): (200, {"models": [MODEL]}),
    ("GET", "/api/models/model-a"): (200, {"model": MODEL}),
    ("GET", "/api/models/model-a/status"): (200, {"model": MODEL, "runtime": {"status": "ready"}}),
    ("POST", "/api/models/model-a/load"): (200, {"model": MODEL, "runtime": {"status": "ready"}}),
    ("POST", "/api/models/model-a/unload"): (200, {"model": MODEL, "runtime": {"status": "idle"}}),
    ("GET", "/api/models/model-a/classes"): (200, {"classes": ["person", "car"]}),
    ("POST", "/api/sources"): (201, {"source": {"id": "src-1", "type": "image"}}),
    ("GET", "/api/sources/src-1"): (200, {"source": {"id": "src-1", "type": "image"}}),
    ("DELETE", "/api/sources/src-1"): (204, None),
    ("GET", "/api/calibration"): (200, {"calibration": {"status": "uncalibrated"}}),
    ("POST", "/api/calibration"): (
        200,
        {"calibration": {"status": "calibrated"}, "source": {"width": 1000}},
    ),
    ("PUT", "/api/calibration"): (
        200,
        {"calibration": {"status": "calibrated"}, "source": {"width": 1000}},
    ),
    ("DELETE", "/api/calibration"): (204, None),
    ("GET", "/api/roi"): (
        200,
        {"roi": {"status": "defined", "points": [[0, 0], [1, 0], [1, 1], [0, 1]]}},
    ),
    ("POST", "/api/roi"): (
        201,
        {"roi": {"status": "defined", "points": [[0, 0], [1, 0], [1, 1], [0, 1]]}},
    ),
    ("PUT", "/api/roi"): (
        200,
        {"roi": {"status": "defined", "points": [[0, 0], [1, 0], [1, 1], [0, 1]]}},
    ),
    ("DELETE", "/api/roi"): (204, None),
    ("GET", "/api/grid"): (200, {"grid": {"enabled": True, "rows": 3, "columns": 3}}),
    ("PUT", "/api/grid"): (200, {"grid": {"enabled": True, "rows": 4, "columns": 6}}),
    ("DELETE", "/api/grid"): (204, None),
    ("POST", "/api/grid"): (200, {"image": "base64", "metadata": {"rows": 8, "columns": 12}}),
    ("POST", "/api/calibrated-grid"): (
        200,
        {"image": "base64", "metadata": {"rows": 4, "columns": 6}},
    ),
    ("POST", "/api/video/metadata"): (
        200,
        {"width": 1920, "height": 1080, "fps": 30.0, "frame_count": 300},
    ),
    ("POST", "/api/calibration/transform"): (
        200,
        {"points": [[0, 0]], "direction": "image_to_reference"},
    ),
    ("POST", "/api/spatial/inspect-point"): (200, {"inspection": {"status": "valid"}}),
    ("POST", "/api/analysis/detect"): (200, {"model": MODEL, "detections": []}),
    ("POST", "/api/analysis/detect-frame"): (200, {"model": MODEL, "detections": []}),
    ("POST", "/api/analysis/session/start"): (200, {"analysis": {"analysis_id": "a1"}}),
    ("PATCH", "/api/analysis/session/status"): (
        200,
        {"analysis": {"analysis_id": "a1", "status": "running"}},
    ),
    ("POST", "/api/analysis/session/complete"): (
        200,
        {"analysis_id": "a1", "status": "complete"},
    ),
    ("GET", "/api/error"): (400, {"error": "boom"}),
}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        return

    def _handle(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        self.server.requests.append(
            {"method": self.command, "path": self.path, "headers": dict(self.headers), "body": body}
        )
        path = urllib.parse.urlparse(self.path).path
        if path.endswith("/media"):
            data, status, content_type = b"\x89PNG\r\n\x1a\n", 200, "application/octet-stream"
        else:
            status, payload = ROUTES.get((self.command, path), (404, {"error": "not found"}))
            if payload is None:
                self.send_response(status)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data, content_type = json.dumps(payload).encode(), "application/json"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if data:
            self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _handle


@pytest.fixture
def server():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    httpd.requests = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield httpd
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def base_url(server) -> str:
    return f"http://127.0.0.1:{server.server_address[1]}"


@pytest.fixture
def client(base_url) -> SPEClient:
    return SPEClient(base_url, retries=0, transport=UrllibTransport())


@pytest.fixture
def rectangle() -> list[list[float]]:
    return [list(point) for point in RECTANGLE]


@pytest.fixture
def engine() -> SpatialEngine:
    engine = SpatialEngine(
        grid_rows=3,
        grid_columns=3,
        source_dimensions={"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
    )
    engine.calibrate(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    return engine


@pytest.fixture
def sample_image() -> np.ndarray:
    return np.zeros((SOURCE_HEIGHT, SOURCE_WIDTH, 3), dtype=np.uint8)
