"""Provider-neutral observation builders.

This mirrors the Spatial Intelligence Engine's :mod:`application.observations`
contract builders. An *observation* is a timestamped, provider-neutral record of
one perception result: it keeps detection geometry, calibrated spatial data, and
track identity, but never the source frame.

The SDK returns plain dictionaries for the builders. :class:`ObservationBatchWriter`
is an optional helper that persists observations as JSON Lines under a caller
chosen directory; nothing is written unless you instantiate it.

Usage::

    from spe import create_observation, create_image_observation

    observation = create_observation(
        result, analysis_id="run-1", source_id="src-1", timestamp=2.5, frame_index=75
    )
    image_record = create_image_observation(result, source_id="src-1")

    with ObservationBatchWriter(
        "run-1", "src-1", model, root="observations"
    ) as writer:
        writer.append(observation)
"""

from __future__ import annotations

import json
import math
import uuid
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .exceptions import SPEValidationError

__all__ = [
    "ObservationBatchWriter",
    "create_image_observation",
    "create_observation",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_component(value: str, label: str) -> str:
    name = str(value).strip()
    if not name:
        raise SPEValidationError(f"A {label} is required.")
    if name in {".", ".."} or "/" in name or "\\" in name or "\x00" in name:
        raise SPEValidationError(f"The {label} contains invalid path characters.")
    return name


def _normalized_detections(
    detection_result: Mapping[str, Any], *, include_spatial: bool
) -> list[dict[str, Any]]:
    detections: list[dict[str, Any]] = []
    for index, detection in enumerate(detection_result.get("detections") or [], start=1):
        bbox = detection.get("bbox") or {}
        normalized: dict[str, Any] = {
            "detection_id": detection.get("id") or f"det-{index:06d}",
            "class_id": detection.get("class_id"),
            "class_name": detection.get("class_name"),
            "confidence": detection.get("confidence"),
            "bbox": {key: bbox.get(key) for key in ("x", "y", "width", "height")},
            "center": detection.get("center"),
            "coordinate_system": detection.get("coordinate_system", "source_pixels"),
        }
        if include_spatial:
            normalized["spatial"] = detection.get("spatial")
        if detection.get("track_id") is not None:
            normalized["track_id"] = detection["track_id"]
        detections.append(normalized)
    return detections


def create_observation(
    detection_result: Mapping[str, Any],
    *,
    analysis_id: str,
    source_id: str,
    timestamp: float,
    frame_index: int,
) -> dict[str, Any]:
    """Build a timestamped, provider-neutral video observation."""
    if not analysis_id.strip() or not source_id.strip():
        raise SPEValidationError("Analysis and source identifiers are required.")
    if not math.isfinite(timestamp) or timestamp < 0:
        raise SPEValidationError("Observation timestamp must be a non-negative number.")
    if frame_index < 0:
        raise SPEValidationError("Observation frame index must be non-negative.")

    model = detection_result.get("model") or {}
    return {
        "observation_id": f"obs-{uuid.uuid4().hex}",
        "analysis_id": analysis_id,
        "source_id": source_id,
        "timestamp": timestamp,
        "timestamp_type": "media",
        "frame_index": frame_index,
        "coordinate_system": "source_pixels",
        "perception": {
            "provider": model.get("provider"),
            "model_id": model.get("id"),
            "model_version": model.get("version"),
        },
        "detections": _normalized_detections(detection_result, include_spatial=True),
    }


def create_image_observation(
    detection_result: Mapping[str, Any], *, source_id: str
) -> dict[str, Any]:
    """Wrap one normalized detection result with static-image context."""
    if not source_id.strip():
        raise SPEValidationError("A source identifier is required.")
    return {
        "observation_type": "image",
        "source_id": source_id,
        "coordinate_system": "source_pixels",
        "model": dict(detection_result.get("model") or {}),
        "detections": _normalized_detections(detection_result, include_spatial=False),
    }


class ObservationBatchWriter:
    """Write observations as JSON Lines with a manifest, in batches.

    Args:
        analysis_id: Analysis run identifier; also the output sub-directory.
        source_id: Source identifier stored in the manifest.
        model: Model metadata stored in the manifest.
        root: Directory under which ``<analysis_id>/observations.jsonl`` is written.
        batch_size: Number of buffered observations before an automatic flush.
        interval_ms: Optional sampling interval recorded in the manifest.
        effective_fps: Optional effective sampling rate recorded in the manifest.

    Notes:
        The writer appends to an existing ``observations.jsonl`` so a resumed run
        keeps prior records. It never writes outside ``root/<analysis_id>``.
    """

    def __init__(
        self,
        analysis_id: str,
        source_id: str,
        model: Mapping[str, Any],
        *,
        root: str | Path,
        batch_size: int = 25,
        interval_ms: float | None = None,
        effective_fps: float | None = None,
    ) -> None:
        if int(batch_size) < 1:
            raise SPEValidationError("batch_size must be a positive integer.")
        self.analysis_id = _safe_component(analysis_id, "analysis_id")
        self.source_id = _safe_component(source_id, "source_id")
        self.model = dict(model)
        self.root = Path(root)
        self.directory = self.root / self.analysis_id
        self.path = self.directory / "observations.jsonl"
        self.manifest_path = self.directory / "manifest.json"
        self.batch_size = int(batch_size)
        self.interval_ms = interval_ms
        self.effective_fps = effective_fps
        self._buffer: list[dict[str, Any]] = []
        self._created_at = _now()
        self._status = "running"
        self.directory.mkdir(parents=True, exist_ok=True)
        self._count = self._existing_count()
        self._write_manifest()

    def __enter__(self) -> ObservationBatchWriter:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _existing_count(self) -> int:
        if not self.path.is_file():
            return 0
        with self.path.open(encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())

    def _write_manifest(self) -> None:
        manifest = {
            "version": "1.0",
            "analysis_id": self.analysis_id,
            "source_id": self.source_id,
            "model": self.model,
            "status": self._status,
            "created_at": self._created_at,
            "updated_at": _now(),
            "batch_size": self.batch_size,
            "observation_count": self._count + len(self._buffer),
            "interval_ms": self.interval_ms,
            "effective_fps": self.effective_fps,
        }
        temporary = self.manifest_path.with_name(f".{self.manifest_path.name}.tmp")
        temporary.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
        temporary.replace(self.manifest_path)

    def append(self, observation: Mapping[str, Any]) -> None:
        """Buffer one observation, flushing when the batch is full."""
        if not isinstance(observation, Mapping) or not observation:
            raise SPEValidationError("An observation mapping is required.")
        self._buffer.append(dict(observation))
        if len(self._buffer) >= self.batch_size:
            self.flush()

    def update_sampling(self, interval_ms: float | None, effective_fps: float | None) -> None:
        """Record the current sampling configuration in the manifest."""
        self.interval_ms = interval_ms
        self.effective_fps = effective_fps
        self._write_manifest()

    def flush(self) -> Path | None:
        """Write buffered observations to disk and return the file path."""
        if not self._buffer:
            return None
        with self.path.open("a", encoding="utf-8") as handle:
            for observation in self._buffer:
                handle.write(json.dumps(observation, default=str))
                handle.write("\n")
        self._count += len(self._buffer)
        self._buffer.clear()
        self._write_manifest()
        return self.path

    def close(self, status: str = "complete") -> None:
        """Flush remaining observations and finalize the manifest status."""
        if status not in {"complete", "stopped", "error"}:
            raise SPEValidationError("Status must be complete, stopped, or error.")
        self.flush()
        self._status = status
        self._write_manifest()
