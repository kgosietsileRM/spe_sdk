"""Provider-neutral observation builders.

This mirrors the Spatial Intelligence Engine's :mod:`application.observations`
contract builders. An *observation* is a timestamped, provider-neutral record of
one perception result: it keeps detection geometry, calibrated spatial data, and
track identity, but never the source frame.

The SDK returns plain dictionaries and performs no file I/O; persist them with
whatever storage suits your application.

Usage::

    from spe import create_observation, create_image_observation

    observation = create_observation(
        result, analysis_id="run-1", source_id="src-1", timestamp=2.5, frame_index=75
    )
    image_record = create_image_observation(result, source_id="src-1")
"""

from __future__ import annotations

import math
import uuid
from collections.abc import Mapping
from typing import Any

from .exceptions import SPEValidationError

__all__ = ["create_image_observation", "create_observation"]


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
