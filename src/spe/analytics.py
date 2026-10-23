"""Higher-level analytics built on tracks, motion, and spatialized detections.

The helpers in this module are pure Python and deliberately dependency-free.
They accept the JSON-shaped detections produced by the engine (or the SDK's
tracker) and return plain, serializable summaries.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .exceptions import SPEValidationError


def _track_id(detection: Mapping[str, Any]) -> str | None:
    value = detection.get("track_id") or detection.get("id")
    return None if value is None else str(value)


def _zone(detection: Mapping[str, Any]) -> str | None:
    spatial = detection.get("spatial")
    if isinstance(spatial, Mapping) and spatial.get("status") == "valid":
        zone = spatial.get("zone")
        if zone is not None:
            return str(zone)
    zone = detection.get("zone")
    return None if zone is None else str(zone)


def _position(detection: Mapping[str, Any]) -> tuple[float, float] | None:
    spatial = detection.get("spatial")
    if isinstance(spatial, Mapping) and spatial.get("status") == "valid":
        position = spatial.get("position")
        if isinstance(position, Mapping) and "x" in position and "y" in position:
            return float(position["x"]), float(position["y"])
    for key in ("position", "foot_point", "center"):
        value = detection.get(key)
        if isinstance(value, Mapping) and "x" in value and "y" in value:
            return float(value["x"]), float(value["y"])
    bbox = detection.get("bbox")
    if isinstance(bbox, Mapping) and {"x", "y", "width", "height"} <= set(bbox):
        return (
            float(bbox["x"]) + float(bbox["width"]) / 2,
            float(bbox["y"]) + float(bbox["height"]),
        )
    return None


def _timestamp(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise SPEValidationError("Timestamps must be numeric.") from error


def _point(value: Sequence[float], name: str) -> tuple[float, float]:
    if len(value) != 2:
        raise SPEValidationError(f"{name} must contain exactly two coordinates.")
    x, y = float(value[0]), float(value[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise SPEValidationError(f"{name} must contain finite coordinates.")
    return x, y


class ZoneOccupancyTracker:
    """Accumulate per-zone occupancy, entries, and dwell time over frames.

    Detections are matched by ``track_id`` (falling back to ``id``) and their
    zone is read from ``spatial.zone`` (falling back to ``zone``). Detections
    without a stable identity or zone are ignored.
    """

    def __init__(self) -> None:
        self._entries: dict[str, int] = {}
        self._dwell: dict[str, dict[str, float]] = {}
        self._current: dict[str, str] = {}
        self._last_seen: dict[str, float] = {}
        self._first_seen: dict[str, float] = {}
        self._occupancy: dict[str, set[str]] = {}
        self._timestamp: float | None = None

    def reset(self) -> None:
        """Clear all accumulated state."""
        self._entries.clear()
        self._dwell.clear()
        self._current.clear()
        self._last_seen.clear()
        self._first_seen.clear()
        self._occupancy.clear()
        self._timestamp = None

    def update(
        self,
        detections: Sequence[Mapping[str, Any]],
        timestamp: float | None = None,
    ) -> dict[str, Any]:
        """Add one frame of detections and return a snapshot."""
        moment = _timestamp(timestamp)
        if moment is not None:
            self._timestamp = moment
        occupancy: dict[str, set[str]] = {}
        for detection in detections:
            track_id = _track_id(detection)
            zone = _zone(detection)
            if track_id is None or zone is None:
                continue
            occupancy.setdefault(zone, set()).add(track_id)
            previous_zone = self._current.get(track_id)
            previous_time = self._last_seen.get(track_id)
            delta = (
                max(0.0, moment - previous_time)
                if moment is not None and previous_time is not None
                else 0.0
            )
            self._first_seen.setdefault(track_id, moment if moment is not None else 0.0)
            self._dwell.setdefault(zone, {})
            if previous_zone == zone:
                self._dwell[zone][track_id] = self._dwell[zone].get(track_id, 0.0) + delta
            else:
                self._entries[zone] = self._entries.get(zone, 0) + 1
                self._dwell[zone].setdefault(track_id, 0.0)
            self._current[track_id] = zone
            if moment is not None:
                self._last_seen[track_id] = moment
        self._occupancy = occupancy
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """Return the current cumulative zone statistics."""
        zones = set(self._entries) | set(self._dwell) | set(self._occupancy)
        payload: dict[str, Any] = {}
        for zone in sorted(zones):
            payload[zone] = {
                "occupancy": len(self._occupancy.get(zone, set())),
                "entries": int(self._entries.get(zone, 0)),
                "dwell_seconds": round(sum(self._dwell.get(zone, {}).values()), 6),
                "tracks": sorted(self._occupancy.get(zone, set())),
            }
        return {
            "timestamp": self._timestamp,
            "active_tracks": len(
                {track for tracks in self._occupancy.values() for track in tracks}
            ),
            "zones": payload,
        }


@dataclass
class TrackSummary:
    """A compact summary of one track observed across frames."""

    track_id: str
    class_name: str | None = None
    first_seen: float | None = None
    last_seen: float | None = None
    frames: int = 0
    distance: float = 0.0
    average_speed: float = 0.0
    zones: list[str] = field(default_factory=list)
    start_position: tuple[float, float] | None = None
    end_position: tuple[float, float] | None = None

    @property
    def duration(self) -> float:
        """Return the observed duration in the timestamp's units."""
        if self.first_seen is None or self.last_seen is None:
            return 0.0
        return max(0.0, self.last_seen - self.first_seen)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "track_id": self.track_id,
            "class_name": self.class_name,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "duration": round(self.duration, 6),
            "frames": self.frames,
            "distance": round(self.distance, 6),
            "average_speed": round(self.average_speed, 6),
            "zones": list(self.zones),
            "start_position": list(self.start_position) if self.start_position else None,
            "end_position": list(self.end_position) if self.end_position else None,
        }


def summarize_tracks(
    frames: Iterable[Mapping[str, Any]],
    *,
    distance_units: str = "source_pixels",
) -> list[dict[str, Any]]:
    """Summarize tracks across an iterable of ``{"timestamp", "detections"}`` frames.

    Positions are read from ``spatial.position`` when available, falling back to
    ``position``, ``foot_point``, ``center``, or the bounding-box foot point. All
    positions must share a coordinate space for distances to be meaningful.

    Args:
        frames: Frames with an optional numeric ``timestamp`` and ``detections``.
        distance_units: Label stored in each summary for the distance unit.

    Returns:
        One dictionary per track, sorted by ``track_id``.
    """
    state: dict[str, TrackSummary] = {}
    last_position: dict[str, tuple[float, float]] = {}
    for frame in frames:
        moment = _timestamp(frame.get("timestamp"))
        for detection in frame.get("detections") or []:
            track_id = _track_id(detection)
            if track_id is None:
                continue
            summary = state.setdefault(track_id, TrackSummary(track_id=track_id))
            class_name = detection.get("class_name")
            if class_name is not None and summary.class_name is None:
                summary.class_name = str(class_name)
            if moment is not None:
                if summary.first_seen is None:
                    summary.first_seen = moment
                summary.last_seen = moment
            summary.frames += 1
            zone = _zone(detection)
            if zone is not None and zone not in summary.zones:
                summary.zones.append(zone)
            position = _position(detection)
            if position is None:
                continue
            if summary.start_position is None:
                summary.start_position = position
            previous = last_position.get(track_id)
            if previous is not None:
                summary.distance += math.hypot(position[0] - previous[0], position[1] - previous[1])
            last_position[track_id] = position
            summary.end_position = position
    payload: list[dict[str, Any]] = []
    for track_id in sorted(state):
        summary = state[track_id]
        duration = summary.duration
        summary.average_speed = summary.distance / duration if duration > 0 else 0.0
        item = summary.to_dict()
        item["distance_units"] = distance_units
        payload.append(item)
    return payload


class LineCrossingCounter:
    """Count directional track crossings over a virtual line segment.

    Positions are read with the same precedence as :func:`summarize_tracks`, so
    the line and the detections must share a coordinate space. Crossings are
    reported as ``positive`` for a left-to-right (counter-clockwise) transit and
    ``negative`` for the reverse.
    """

    def __init__(
        self,
        start: Sequence[float],
        end: Sequence[float],
        *,
        name: str = "line",
        max_events: int = 1000,
    ) -> None:
        self.start = _point(start, "Line start")
        self.end = _point(end, "Line end")
        if self.start == self.end:
            raise SPEValidationError("Line start and end must differ.")
        self.name = name
        self.max_events = max(0, int(max_events))
        self._side: dict[str, int] = {}
        self._counts = {"positive": 0, "negative": 0}
        self._events: list[dict[str, Any]] = []

    def reset(self) -> None:
        """Clear counts and remembered track sides."""
        self._side.clear()
        self._counts = {"positive": 0, "negative": 0}
        self._events.clear()

    def _sign(self, point: tuple[float, float]) -> int:
        x1, y1 = self.start
        x2, y2 = self.end
        cross = (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1)
        return 0 if cross == 0 else (1 if cross > 0 else -1)

    def update(self, detections: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        """Process one frame of detections and return current counts."""
        for detection in detections:
            track_id = _track_id(detection)
            position = _position(detection)
            if track_id is None or position is None:
                continue
            side = self._sign(position)
            if side == 0:
                continue
            previous = self._side.get(track_id)
            self._side[track_id] = side
            if previous is None or previous == side:
                continue
            direction = "positive" if side > 0 else "negative"
            self._counts[direction] += 1
            if len(self._events) < self.max_events:
                self._events.append(
                    {
                        "track_id": track_id,
                        "direction": direction,
                        "from_side": previous,
                        "to_side": side,
                        "position": [position[0], position[1]],
                    }
                )
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        """Return counts and the recorded crossing events."""
        return {
            "name": self.name,
            "line": {"start": list(self.start), "end": list(self.end)},
            "positive": self._counts["positive"],
            "negative": self._counts["negative"],
            "total": self._counts["positive"] + self._counts["negative"],
            "events": list(self._events),
        }


__all__ = [
    "LineCrossingCounter",
    "TrackSummary",
    "ZoneOccupancyTracker",
    "summarize_tracks",
]
