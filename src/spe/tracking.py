"""Provider-neutral multi-object tracking for normalized detections.

This mirrors the Spatial Intelligence Engine's :mod:`application.tracking`
module. The tracker associates source-pixel detections across observations,
assigns stable ``track-<n>`` identifiers, and reports lifecycle diagnostics. It
is deterministic, model agnostic, and requires no calibration.

Usage::

    from spe import ModelAgnosticTracker

    tracker = ModelAgnosticTracker()
    first = tracker.update(detections, timestamp=0.0)
    second = tracker.update(detections, timestamp=0.5)
    print(second["detections"][0]["track_id"], second["diagnostics"])
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["ModelAgnosticTracker", "TrackingConfig"]


@dataclass(frozen=True)
class TrackingConfig:
    """Association thresholds in source-pixel units and seconds."""

    min_iou: float = 0.01
    max_center_distance_scale: float = 2.5
    max_missing_seconds: float = 1.5
    confirmation_observations: int = 2


@dataclass
class _Track:
    track_id: str
    class_id: Any
    class_name: str | None
    bbox: dict[str, float]
    last_timestamp: float
    observations: int = 0
    status: str = "tentative"


def _box(value: Mapping[str, Any] | None) -> tuple[float, float, float, float] | None:
    if not isinstance(value, Mapping):
        return None
    try:
        x, y = float(value["x"]), float(value["y"])
        width, height = float(value["width"]), float(value["height"])
    except (KeyError, TypeError, ValueError):
        return None
    if (
        not all(math.isfinite(item) for item in (x, y, width, height))
        or x < 0
        or y < 0
        or width <= 0
        or height <= 0
    ):
        return None
    return x, y, width, height


def _iou(
    left: tuple[float, float, float, float], right: tuple[float, float, float, float]
) -> float:
    lx, ly, lw, lh = left
    rx, ry, rw, rh = right
    intersection = max(0.0, min(lx + lw, rx + rw) - max(lx, rx)) * max(
        0.0, min(ly + lh, ry + rh) - max(ly, ry)
    )
    union = lw * lh + rw * rh - intersection
    return intersection / union if union > 0 else 0.0


def _center_distance(
    left: tuple[float, float, float, float], right: tuple[float, float, float, float]
) -> float:
    return math.hypot(
        (left[0] + left[2] / 2) - (right[0] + right[2] / 2),
        (left[1] + left[3] / 2) - (right[1] + right[3] / 2),
    )


@dataclass
class ModelAgnosticTracker:
    """Associate normalized detections into stable tracks over time.

    The tracker holds only identity and geometry state; it never inspects image
    pixels or calibration. :meth:`update` returns the detections with a
    ``track_id`` added where a track could be assigned, plus a diagnostics
    snapshot.
    """

    config: TrackingConfig = field(default_factory=TrackingConfig)
    _tracks: dict[str, _Track] = field(default_factory=dict)
    _next_id: int = 1
    _last_timestamp: float | None = None
    diagnostics: dict[str, int] = field(default_factory=dict)

    def _count(self, key: str, amount: int = 1) -> None:
        self.diagnostics[key] = self.diagnostics.get(key, 0) + amount

    def reset(self) -> None:
        """Discard all tracks and diagnostics for a new analysis run."""
        self._tracks.clear()
        self._next_id = 1
        self._last_timestamp = None
        self.diagnostics.clear()

    def update(
        self,
        detections: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...],
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """Associate one observation, rejecting stale input without mutation."""
        now = float(timestamp) if timestamp is not None else (self._last_timestamp or 0.0) + 1.0
        if not math.isfinite(now) or (
            self._last_timestamp is not None and now < self._last_timestamp
        ):
            self._count("out_of_order_rejected")
            return {
                "detections": [dict(item) for item in detections],
                "diagnostics": self.snapshot(),
            }
        if self._last_timestamp is not None and now == self._last_timestamp:
            self._count("duplicate_observations_rejected")
            return {
                "detections": [dict(item) for item in detections],
                "diagnostics": self.snapshot(),
            }

        valid: list[tuple[int, Mapping[str, Any], tuple[float, float, float, float]]] = []
        output = [dict(item) for item in detections]
        for index, detection in enumerate(detections):
            box = _box(detection.get("bbox"))
            if (
                box is not None
                and detection.get("coordinate_system", "source_pixels") == "source_pixels"
            ):
                valid.append((index, detection, box))
            else:
                self._count("invalid_detections")

        candidates: list[tuple[float, str, int]] = []
        for index, detection, box in valid:
            for track_id, track in self._tracks.items():
                if now - track.last_timestamp > self.config.max_missing_seconds:
                    continue
                if (
                    track.class_id is not None
                    and detection.get("class_id") is not None
                    and track.class_id != detection.get("class_id")
                ):
                    continue
                old_box = _box(track.bbox)
                if old_box is None:
                    continue
                overlap = _iou(old_box, box)
                scale = max(old_box[2], old_box[3], box[2], box[3], 1.0)
                distance = _center_distance(old_box, box)
                if (
                    overlap >= self.config.min_iou
                    or distance <= self.config.max_center_distance_scale * scale
                ):
                    # Sort by strongest geometry, then identity and detection order.
                    score = -(
                        overlap
                        + max(
                            0.0,
                            1.0 - distance / (scale * self.config.max_center_distance_scale),
                        )
                        / 2
                    )
                    candidates.append((score, track_id, index))

        assigned_tracks: set[str] = set()
        assigned_detections: set[int] = set()
        matched = 0
        for _score, track_id, index in sorted(
            candidates, key=lambda item: (item[0], item[1], item[2])
        ):
            if track_id in assigned_tracks or index in assigned_detections:
                continue
            track = self._tracks[track_id]
            detection = detections[index]
            track.bbox = dict(detection["bbox"])
            track.last_timestamp = now
            track.observations += 1
            if track.observations >= self.config.confirmation_observations:
                track.status = "confirmed"
            output[index]["track_id"] = track_id
            assigned_tracks.add(track_id)
            assigned_detections.add(index)
            matched += 1

        for index, detection, _box_value in valid:
            if index in assigned_detections:
                continue
            track_id = f"track-{self._next_id}"
            self._next_id += 1
            self._tracks[track_id] = _Track(
                track_id,
                detection.get("class_id"),
                detection.get("class_name"),
                dict(detection["bbox"]),
                now,
            )
            output[index]["track_id"] = track_id
            self._count("tracks_created")

        for track_id, track in list(self._tracks.items()):
            if track_id not in assigned_tracks and track.last_timestamp != now:
                if now - track.last_timestamp > self.config.max_missing_seconds:
                    track.status = "terminated"
                    self._tracks.pop(track_id)
                    self._count("tracks_terminated")
                else:
                    track.status = "missing"
                    self._count("tracks_missing")

        self._last_timestamp = now
        self._count("detections", len(detections))
        self._count("matched_detections", matched)
        self._count("unassigned_detections", len(valid) - matched)
        return {"detections": output, "diagnostics": self.snapshot()}

    def snapshot(self) -> dict[str, Any]:
        """Return a diagnostics snapshot including active track identities."""
        return {
            **self.diagnostics,
            "active_tracks": len(self._tracks),
            "tracks": [
                {"track_id": track.track_id, "status": track.status}
                for track in sorted(self._tracks.values(), key=lambda item: item.track_id)
            ],
        }
