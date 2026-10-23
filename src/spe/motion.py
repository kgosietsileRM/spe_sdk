"""Bounded per-track temporal state, motion estimates, and predictions.

This mirrors the Spatial Intelligence Engine's :mod:`application.motion` module.
Given timestamped, tracked detections it maintains a bounded trajectory history,
derives finite-difference velocity and direction, and optionally predicts the
next position. It prefers calibrated ``spatial.position`` coordinates when
present and otherwise falls back to source-pixel foot points.

Usage::

    from spe import SpatialTrackStateManager

    manager = SpatialTrackStateManager()
    manager.update(detections, timestamp=0.0)
    state = manager.update(detections, timestamp=0.5, prediction_enabled=True)
    print(state["tracks"][0]["motion"])
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = ["MotionConfig", "SpatialTrackStateManager"]


@dataclass(frozen=True)
class MotionConfig:
    """Bounds and thresholds for trajectory, velocity, and prediction."""

    max_trajectory_samples: int = 32
    max_velocity_gap_seconds: float = 2.0
    prediction_horizon_seconds: float = 0.5
    max_prediction_horizon_seconds: float = 2.0
    max_prediction_age_seconds: float = 1.5
    max_tracks: int = 256


@dataclass
class _MotionTrack:
    track_id: str
    class_name: str | None
    samples: list[dict[str, Any]] = field(default_factory=list)
    last_seen: float | None = None
    status: str = "missing"


def _position(detection: Mapping[str, Any]) -> tuple[float, float, str, str] | None:
    spatial = detection.get("spatial")
    if (
        isinstance(spatial, Mapping)
        and spatial.get("status") == "valid"
        and isinstance(spatial.get("position"), Mapping)
    ):
        point = spatial["position"]
        coordinate_system = str(
            point.get("coordinate_system") or spatial.get("coordinate_system") or "reference_pixels"
        )
        units = str(point.get("units") or spatial.get("units") or "pixels")
    else:
        bbox = detection.get("bbox") or {}
        try:
            point = {
                "x": float(bbox["x"]) + float(bbox["width"]) / 2,
                "y": float(bbox["y"]) + float(bbox["height"]),
            }
        except (KeyError, TypeError, ValueError):
            return None
        coordinate_system, units = "source_pixels", "px"
    try:
        x, y = float(point["x"]), float(point["y"])
    except (KeyError, TypeError, ValueError):
        return None
    if not all(math.isfinite(item) for item in (x, y)):
        return None
    return x, y, coordinate_system, units


class SpatialTrackStateManager:
    """Derive observed positions, finite-difference motion, and predictions."""

    def __init__(self, config: MotionConfig | None = None) -> None:
        self.config = config or MotionConfig()
        self._tracks: dict[str, _MotionTrack] = {}
        self.diagnostics: dict[str, int] = {}

    def _count(self, key: str) -> None:
        self.diagnostics[key] = self.diagnostics.get(key, 0) + 1

    def reset(self) -> None:
        """Discard all trajectory state and diagnostics."""
        self._tracks.clear()
        self.diagnostics.clear()

    def update(
        self,
        detections: list[Mapping[str, Any]],
        timestamp: float,
        prediction_enabled: bool = False,
    ) -> dict[str, Any]:
        """Ingest one timestamped observation and return the trajectory snapshot."""
        if not math.isfinite(timestamp) or timestamp < 0:
            self._count("invalid_timestamps")
            return self.snapshot(timestamp, prediction_enabled)

        observed_ids: set[str] = set()
        for detection in detections:
            track_id = detection.get("track_id")
            position = _position(detection)
            if not track_id or position is None:
                self._count("invalid_samples")
                continue
            track = self._tracks.setdefault(
                str(track_id), _MotionTrack(str(track_id), detection.get("class_name"))
            )
            if track.last_seen is not None and timestamp <= track.last_seen:
                self._count("duplicate_or_out_of_order_samples")
                continue
            x, y, coordinate_system, units = position
            sample = {
                "timestamp_seconds": timestamp,
                "x": x,
                "y": y,
                "coordinate_system": coordinate_system,
                "units": units,
                "status": "observed",
                "detection_id": detection.get("id"),
            }
            track.samples.append(sample)
            if len(track.samples) > self.config.max_trajectory_samples:
                del track.samples[: -self.config.max_trajectory_samples]
                self._count("trajectory_samples_truncated")
            track.last_seen = timestamp
            track.status = "observed"
            observed_ids.add(track.track_id)
            self._count("trajectory_samples_accepted")

        for track in self._tracks.values():
            if track.track_id not in observed_ids and track.last_seen is not None:
                age = timestamp - track.last_seen
                if age >= self.config.max_prediction_age_seconds:
                    track.status = "terminated"
                else:
                    track.status = "missing"
        return self.snapshot(timestamp, prediction_enabled)

    def _motion(self, track: _MotionTrack) -> dict[str, Any]:
        if len(track.samples) < 2:
            return {
                "velocity": {"status": "unavailable", "reason": "insufficient_observations"},
                "direction": {"status": "unavailable", "reason": "insufficient_observations"},
            }
        first, second = track.samples[-2:]
        if (first["coordinate_system"], first["units"]) != (
            second["coordinate_system"],
            second["units"],
        ):
            return {
                "velocity": {"status": "unavailable", "reason": "incompatible_coordinates"},
                "direction": {"status": "unavailable", "reason": "incompatible_coordinates"},
            }
        dt = second["timestamp_seconds"] - first["timestamp_seconds"]
        if dt <= 0 or dt > self.config.max_velocity_gap_seconds:
            return {
                "velocity": {"status": "unavailable", "reason": "invalid_or_excessive_interval"},
                "direction": {"status": "unavailable", "reason": "invalid_or_excessive_interval"},
            }
        vx, vy = (second["x"] - first["x"]) / dt, (second["y"] - first["y"]) / dt
        speed = math.hypot(vx, vy)
        velocity = {
            "vx": vx,
            "vy": vy,
            "speed": speed,
            "units": f"{second['units']}_per_second",
            "coordinate_system": second["coordinate_system"],
            "status": "valid",
            "based_on_observations": 2,
            "time_interval_seconds": dt,
        }
        # Image/reference coordinates use x-right/y-down axes; zero degrees is +x.
        direction = {
            "angle_degrees": math.degrees(math.atan2(vy, vx)),
            "status": "valid",
            "convention": "atan2(vy, vx), x-right/y-down",
        }
        return {"velocity": velocity, "direction": direction}

    def snapshot(
        self, timestamp: float | None = None, prediction_enabled: bool = False
    ) -> dict[str, Any]:
        """Return the current per-track trajectory and motion state."""
        tracks: list[dict[str, Any]] = []
        for track in sorted(self._tracks.values(), key=lambda item: item.track_id):
            last = track.samples[-1] if track.samples else None
            motion = self._motion(track)
            item: dict[str, Any] = {
                "track_id": track.track_id,
                "class_name": track.class_name,
                "status": track.status,
                "last_observed": last,
                "trajectory": list(track.samples),
                "motion": motion,
            }
            if timestamp is not None and track.last_seen is not None:
                item["last_seen_age_seconds"] = max(0.0, timestamp - track.last_seen)
            prediction: dict[str, Any] = {"status": "unavailable", "reason": "disabled"}
            velocity = motion["velocity"]
            if (
                prediction_enabled
                and last
                and velocity.get("status") == "valid"
                and timestamp is not None
            ):
                age = timestamp - last["timestamp_seconds"]
                horizon = min(
                    self.config.prediction_horizon_seconds,
                    self.config.max_prediction_horizon_seconds,
                )
                if (
                    0 <= age <= self.config.max_prediction_age_seconds
                    and track.status != "terminated"
                ):
                    prediction = {
                        "x": last["x"] + velocity["vx"] * horizon,
                        "y": last["y"] + velocity["vy"] * horizon,
                        "coordinate_system": last["coordinate_system"],
                        "units": last["units"],
                        "status": "valid",
                        "source_track_id": track.track_id,
                        "last_observation_timestamp_seconds": last["timestamp_seconds"],
                        "target_timestamp_seconds": last["timestamp_seconds"] + horizon,
                        "horizon_seconds": horizon,
                    }
                else:
                    prediction = {"status": "unavailable", "reason": "stale_track"}
            item["prediction"] = prediction
            tracks.append(item)
        return {
            "tracks": tracks,
            "diagnostics": {
                **self.diagnostics,
                "trajectory_limit": self.config.max_trajectory_samples,
            },
        }
