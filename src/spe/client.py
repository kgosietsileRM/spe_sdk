"""HTTP client for the Spatial Intelligence Engine Flask API.

The client defaults to a standard-library transport, so it adds no runtime
dependencies beyond the local-core requirements. It exposes one method per
documented route, performs multipart uploads for images and video, and raises
typed errors (:class:`~spe.exceptions.SPEAPIError`,
:class:`~spe.exceptions.SPEConnectionError`, ...) on failure.

An alternate transport (:mod:`~spe.transport`) can be injected for connection
pooling or HTTP/2 via :mod:`requests` or :mod:`httpx` when installed.
"""

from __future__ import annotations

import json
import mimetypes
import os
import time
import urllib.parse
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, BinaryIO

from .exceptions import SPEAPIError, SPETransportError, SPEValidationError
from .transport import Transport, get_default_transport

FileSource = bytes | bytearray | memoryview | str | os.PathLike | BinaryIO
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "PUT", "DELETE", "OPTIONS"})


def _read_binary(source: FileSource, filename: str | None = None) -> tuple[bytes, str]:
    """Return ``(bytes, filename)`` for a path, bytes, or binary file object."""
    if isinstance(source, (bytes, bytearray, memoryview)):
        return bytes(source), filename or "upload.bin"
    if isinstance(source, (str, os.PathLike)):
        path = Path(source)
        if not path.is_file():
            raise SPEValidationError(f"File not found: {path}")
        return path.read_bytes(), filename or path.name
    reader = getattr(source, "read", None)
    if callable(reader):
        data = reader()
        if isinstance(data, str):
            data = data.encode("utf-8")
        guessed = filename or getattr(source, "name", None) or "upload.bin"
        return bytes(data), Path(guessed).name
    raise SPEValidationError("Source must be a path, bytes, or a binary file object.")


def _content_type(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _calibration_payload(
    source_points: Sequence[Sequence[float]],
    source_width: int,
    source_height: int,
    *,
    reference_width: float = 1000,
    reference_height: float = 600,
    units: str = "normalized",
    rows: int = 3,
    columns: int = 3,
) -> dict[str, Any]:
    """Build the JSON body shared by calibration ``POST`` and ``PUT``."""
    return {
        "source": {"width": int(source_width), "height": int(source_height)},
        "source_points": [list(point) for point in source_points],
        "reference_plane": {
            "width": float(reference_width),
            "height": float(reference_height),
            "units": units,
        },
        "calibrated_grid_rows": int(rows),
        "calibrated_grid_columns": int(columns),
    }


class SPEClient:
    """A thin, typed client for a running SPE engine server.

    Args:
        base_url: Root URL of the server, e.g. ``http://127.0.0.1:5000``.
        timeout: Per-request timeout in seconds.
        retries: Automatic retries for idempotent requests on connection loss.
        backoff: Base backoff delay (seconds); doubles each retry.
        user_agent: Optional ``User-Agent`` header.
        transport: Optional custom :class:`~spe.transport.Transport`; defaults to
            the best available backend.
    """

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:5000",
        *,
        timeout: float = 30.0,
        retries: int = 2,
        backoff: float = 0.5,
        user_agent: str | None = None,
        transport: Transport | None = None,
    ) -> None:
        if not base_url or not isinstance(base_url, str):
            raise SPEValidationError("base_url must be a non-empty string.")
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)
        self.retries = max(0, int(retries))
        self.backoff = max(0.0, float(backoff))
        self._user_agent = user_agent
        self._transport = transport or get_default_transport()

    # -- context management ------------------------------------------------
    def __enter__(self) -> SPEClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        """Release transport resources (closes pooled connections if any)."""
        self._transport.close()

    @classmethod
    def from_env(cls, variable: str = "SPE_API_URL", **kwargs: Any) -> SPEClient:
        """Create a client from an environment variable base URL."""
        return cls(os.environ.get(variable, "http://127.0.0.1:5000"), **kwargs)

    # -- transport ---------------------------------------------------------
    def _url(self, path: str, params: Mapping[str, Any] | None = None) -> str:
        normalized = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{normalized}"
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url = f"{url}?{query}"
        return url

    @staticmethod
    def _encode_multipart(
        fields: Mapping[str, Any],
        files: Mapping[str, tuple[str, bytes, str]],
    ) -> tuple[str, bytes]:
        boundary = f"----spe-sdk-{uuid.uuid4().hex}"
        lines: list[bytes] = []
        for name, value in fields.items():
            if value is None:
                continue
            lines.append(f"--{boundary}\r\n".encode())
            lines.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
            lines.append(f"{value}\r\n".encode())
        for name, (filename, data, content_type) in files.items():
            lines.append(f"--{boundary}\r\n".encode())
            lines.append(
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode()
            )
            lines.append(f"Content-Type: {content_type}\r\n\r\n".encode())
            lines.append(data)
            lines.append(b"\r\n")
        lines.append(f"--{boundary}--\r\n".encode())
        body = b"".join(lines)
        return f"multipart/form-data; boundary={boundary}", body

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any | None = None,
        params: Mapping[str, Any] | None = None,
        fields: Mapping[str, Any] | None = None,
        files: Mapping[str, tuple[str, bytes, str]] | None = None,
        raw: bool = False,
        retries: int | None = None,
    ) -> Any:
        url = self._url(path, params)
        headers: dict[str, str] = {"Accept": "application/json"}
        data: bytes | None = None
        if files:
            content_type, data = self._encode_multipart(fields or {}, files)
            headers["Content-Type"] = content_type
        elif json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif fields is not None:
            data = urllib.parse.urlencode(fields).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        if self._user_agent:
            headers["User-Agent"] = self._user_agent

        attempts = self.retries if retries is None else max(0, int(retries))
        if method not in _IDEMPOTENT_METHODS:
            attempts = 0
        last_error: Exception | None = None
        for attempt in range(attempts + 1):
            try:
                status, response_headers, payload = self._transport.request(
                    method, url, headers=headers, data=data, timeout=self.timeout
                )
            except SPETransportError as error:
                last_error = error
                if attempt < attempts:
                    time.sleep(self.backoff * (2**attempt))
                continue
            if status >= 400:
                raise self._api_error(status, payload, url)
            if raw:
                return payload
            return self._decode(payload, response_headers.get("Content-Type"))
        raise last_error  # type: ignore[misc]

    @staticmethod
    def _decode(payload: bytes, _content_type: str | None = None) -> Any:
        if not payload:
            return None
        try:
            return json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return payload

    @staticmethod
    def _api_error(status: int, body: bytes, url: str) -> SPEAPIError:
        payload: Any | None = None
        message = f"HTTP {status} from {url}"
        try:
            payload = json.loads(body.decode("utf-8"))
            if isinstance(payload, Mapping) and payload.get("error"):
                message = str(payload["error"])
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = body or None
        return SPEAPIError(message, status_code=status, payload=payload, url=url)

    # -- health & state ----------------------------------------------------
    def health(self) -> dict[str, Any]:
        """Return the server health payload."""
        return self._request("GET", "/health")

    def get_state(self) -> dict[str, Any]:
        """Return the canonical master spatial state."""
        return self._request("GET", "/api/state")

    # -- sources -----------------------------------------------------------
    def create_source(
        self,
        source: FileSource,
        *,
        filename: str | None = None,
        source_type: str = "image",
        mime_type: str | None = None,
    ) -> dict[str, Any]:
        """Upload an image or video and register it as a runtime source."""
        data, resolved_name = _read_binary(source, filename)
        content_type = mime_type or _content_type(resolved_name)
        response = self._request(
            "POST",
            "/api/sources",
            fields={"type": source_type},
            files={"file": (resolved_name, data, content_type)},
        )
        return response["source"]

    def get_source(self, source_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/sources/{source_id}")["source"]

    def delete_source(self, source_id: str) -> None:
        self._request("DELETE", f"/api/sources/{source_id}")

    def source_media_url(self, source_id: str) -> str:
        """Return the absolute media URL for a source."""
        return self._url(f"/api/sources/{source_id}/media")

    def get_source_media(self, source_id: str) -> bytes:
        """Download the raw media bytes for a source."""
        return self._request("GET", f"/api/sources/{source_id}/media", raw=True)

    # -- calibration -------------------------------------------------------
    def calibrate(
        self,
        source_points: Sequence[Sequence[float]],
        source_width: int,
        source_height: int,
        *,
        reference_width: float = 1000,
        reference_height: float = 600,
        units: str = "normalized",
        rows: int = 3,
        columns: int = 3,
    ) -> dict[str, Any]:
        """Calculate and persist a four-point calibration."""
        payload = _calibration_payload(
            source_points,
            source_width,
            source_height,
            reference_width=reference_width,
            reference_height=reference_height,
            units=units,
            rows=rows,
            columns=columns,
        )
        return self._request("POST", "/api/calibration", json_body=payload)

    def get_calibration(self) -> dict[str, Any]:
        return self._request("GET", "/api/calibration")["calibration"]

    def update_calibration(
        self,
        source_points: Sequence[Sequence[float]],
        source_width: int,
        source_height: int,
        *,
        reference_width: float = 1000,
        reference_height: float = 600,
        units: str = "normalized",
        rows: int = 3,
        columns: int = 3,
    ) -> dict[str, Any]:
        """Replace the active calibration in place.

        Uses ``PUT /api/calibration`` (an idempotent verb), unlike
        :meth:`calibrate` which creates via ``POST``.
        """
        payload = _calibration_payload(
            source_points,
            source_width,
            source_height,
            reference_width=reference_width,
            reference_height=reference_height,
            units=units,
            rows=rows,
            columns=columns,
        )
        return self._request("PUT", "/api/calibration", json_body=payload)

    def delete_calibration(self) -> None:
        self._request("DELETE", "/api/calibration")

    def get_roi(self) -> dict[str, Any]:
        return self._request("GET", "/api/roi")["roi"]

    def create_roi(self, points: Sequence[Sequence[float]]) -> dict[str, Any]:
        return self._request("POST", "/api/roi", json_body={"points": [list(p) for p in points]})[
            "roi"
        ]

    def delete_roi(self) -> None:
        self._request("DELETE", "/api/roi")

    def get_grid(self) -> dict[str, Any]:
        return self._request("GET", "/api/grid")["grid"]

    def set_grid(self, rows: int, columns: int) -> dict[str, Any]:
        return self._request(
            "PUT", "/api/grid", json_body={"rows": int(rows), "columns": int(columns)}
        )["grid"]

    def delete_grid(self) -> None:
        self._request("DELETE", "/api/grid")

    # -- spatial queries ---------------------------------------------------
    def transform_points(
        self,
        points: Sequence[Sequence[float]],
        *,
        homography: Sequence[Sequence[float]] | None = None,
        calibration: Mapping[str, Any] | None = None,
        direction: str = "image_to_reference",
    ) -> dict[str, Any]:
        """Transform points through a homography in either direction."""
        payload: dict[str, Any] = {
            "points": [list(point) for point in points],
            "direction": direction,
        }
        if homography is not None:
            payload["homography"] = homography
        if calibration is not None:
            payload["calibration"] = calibration
        return self._request("POST", "/api/calibration/transform", json_body=payload)

    def inspect_point(
        self,
        point: Sequence[float] | None = None,
        *,
        x: float | None = None,
        y: float | None = None,
        calibration: Mapping[str, Any] | None = None,
        grid: Mapping[str, Any] | None = None,
        source_dimensions: Mapping[str, Any] | None = None,
        spatial_state: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Inspect a point against a stateless spatial payload."""
        payload: dict[str, Any] = {}
        if spatial_state is not None:
            payload["spatial_state"] = spatial_state
        else:
            if calibration is not None:
                payload["calibration"] = calibration
            if grid is not None:
                payload["grid"] = grid
            if source_dimensions is not None:
                payload["source_dimensions"] = source_dimensions
        if point is not None:
            payload["point"] = list(point)
        elif x is not None and y is not None:
            payload["x"], payload["y"] = x, y
        else:
            raise SPEValidationError("Provide a point or both x and y.")
        return self._request("POST", "/api/spatial/inspect-point", json_body=payload)

    # -- rendering ---------------------------------------------------------
    def generate_grid(
        self,
        image: FileSource,
        *,
        filename: str | None = None,
        rows: int = 8,
        columns: int = 12,
        line_thickness: int = 1,
        line_color: str = "#a8f35b",
        show_coordinates: bool = True,
        source_type: str = "image",
        fps: float | None = None,
        frame_count: int | None = None,
    ) -> dict[str, Any]:
        """Render an image-space grid and return ``{image, metadata}``."""
        data, resolved_name = _read_binary(image, filename)
        fields: dict[str, Any] = {
            "rows": rows,
            "columns": columns,
            "line_thickness": line_thickness,
            "line_color": line_color,
            "show_coordinates": str(show_coordinates).lower(),
            "source_type": source_type,
        }
        if fps is not None:
            fields["fps"] = fps
        if frame_count is not None:
            fields["frame_count"] = frame_count
        return self._request(
            "POST",
            "/api/grid",
            fields=fields,
            files={"image": (resolved_name, data, _content_type(resolved_name))},
        )

    def generate_calibrated_grid(
        self,
        image: FileSource,
        homography: Sequence[Sequence[float]],
        *,
        filename: str | None = None,
        rows: int = 4,
        columns: int = 6,
        reference_width: float = 1000,
        reference_height: float = 600,
        source_points: Sequence[Sequence[float]] | None = None,
        show_grid: bool = True,
        show_roi: bool = True,
        line_color: str = "#a8f35b",
        roi_color: str = "#ff3b30",
        overlay_only: bool = False,
    ) -> dict[str, Any]:
        """Render a perspective-correct calibrated grid overlay."""
        data, resolved_name = _read_binary(image, filename)
        fields: dict[str, Any] = {
            "homography": json.dumps(homography),
            "rows": rows,
            "columns": columns,
            "reference_width": reference_width,
            "reference_height": reference_height,
            "show_grid": str(show_grid).lower(),
            "show_roi": str(show_roi).lower(),
            "line_color": line_color,
            "roi_color": roi_color,
            "overlay_only": str(overlay_only).lower(),
        }
        if source_points is not None:
            fields["source_points"] = json.dumps(source_points)
        return self._request(
            "POST",
            "/api/calibrated-grid",
            fields=fields,
            files={"image": (resolved_name, data, _content_type(resolved_name))},
        )

    def video_metadata(self, video: FileSource, *, filename: str | None = None) -> dict[str, Any]:
        """Inspect an uploaded video's dimensions, FPS, and frame count."""
        data, resolved_name = _read_binary(video, filename)
        return self._request(
            "POST",
            "/api/video/metadata",
            files={"video": (resolved_name, data, _content_type(resolved_name))},
        )

    # -- models & analysis -------------------------------------------------
    def list_models(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/models")["models"]

    def get_model(self, model_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/models/{model_id}")["model"]

    def model_status(self, model_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/models/{model_id}/status")

    def load_model(self, model_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/models/{model_id}/load")

    def unload_model(self, model_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/models/{model_id}/unload")

    def model_classes(self, model_id: str) -> list[str]:
        return self._request("GET", f"/api/models/{model_id}/classes")["classes"]

    def detect(
        self,
        *,
        model_id: str = "model-a",
        confidence: float = 0.4,
        classes: Sequence[str] | None = None,
        source_id: str | None = None,
    ) -> dict[str, Any]:
        """Run detection on the active (or specified) image source."""
        payload: dict[str, Any] = {"model_id": model_id, "confidence": float(confidence)}
        if classes is not None:
            payload["classes"] = list(classes)
        if source_id is not None:
            payload["source_id"] = source_id
        return self._request("POST", "/api/analysis/detect", json_body=payload)

    def detect_frame(
        self,
        frame: FileSource,
        *,
        filename: str = "frame.jpg",
        model_id: str = "model-a",
        confidence: float = 0.4,
        classes: Sequence[str] | None = None,
        analysis_id: str = "analysis",
        source_id: str = "source",
        timestamp: float = 0.0,
        frame_index: int = 0,
        tracking: bool = False,
        tracking_mode: str | None = None,
        target_track_id: str | None = None,
        target_detection: Mapping[str, Any] | None = None,
        inference_context: Mapping[str, Any] | None = None,
        spatial_context: Mapping[str, Any] | None = None,
        interval_ms: float | None = None,
        effective_fps: float | None = None,
    ) -> dict[str, Any]:
        """Detect and (optionally) track, spatialize, and timestamp one frame."""
        data, _ = _read_binary(frame, filename)
        fields: dict[str, Any] = {
            "model_id": model_id,
            "confidence": confidence,
            "analysis_id": analysis_id,
            "source_id": source_id,
            "timestamp": timestamp,
            "frame_index": frame_index,
            "tracking": str(tracking).lower(),
        }
        if classes is not None:
            fields["classes"] = json.dumps(list(classes))
        if tracking_mode is not None:
            fields["tracking_mode"] = tracking_mode
        if target_track_id is not None:
            fields["target_track_id"] = target_track_id
        if target_detection is not None:
            fields["target_detection"] = json.dumps(target_detection)
        if inference_context is not None:
            fields["inference_context"] = json.dumps(inference_context)
        if spatial_context is not None:
            fields["spatial_context"] = json.dumps(spatial_context)
        if interval_ms is not None:
            fields["interval_ms"] = interval_ms
        if effective_fps is not None:
            fields["effective_fps"] = effective_fps
        return self._request(
            "POST",
            "/api/analysis/detect-frame",
            fields=fields,
            files={"frame": (filename, data, _content_type(filename))},
        )

    def start_analysis_session(
        self,
        analysis_id: str,
        source_id: str,
        model: Mapping[str, Any],
        *,
        spatial_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "analysis_id": analysis_id,
            "source_id": source_id,
            "model": dict(model),
        }
        if spatial_context is not None:
            payload["spatial_context"] = dict(spatial_context)
        return self._request("POST", "/api/analysis/session/start", json_body=payload)["analysis"]

    def update_analysis_status(
        self,
        analysis_id: str,
        status: str = "running",
        *,
        inference_fps: float | None = None,
        interval_ms: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"analysis_id": analysis_id, "status": status}
        if inference_fps is not None:
            payload["inference_fps"] = inference_fps
        if interval_ms is not None:
            payload["interval_ms"] = interval_ms
        return self._request("PATCH", "/api/analysis/session/status", json_body=payload)["analysis"]

    def complete_analysis_session(
        self, analysis_id: str, status: str = "complete"
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/analysis/session/complete",
            json_body={"analysis_id": analysis_id, "status": status},
        )


__all__ = ["FileSource", "SPEClient"]
