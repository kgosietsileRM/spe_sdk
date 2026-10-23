"""Tests for trajectory state and motion estimation."""

from __future__ import annotations

from spe import MotionConfig, SpatialTrackStateManager


def detection(track_id="track-1", x=0, y=0, timestamp=None, spatial=None):
    item = {
        "id": f"det-{x}-{y}",
        "track_id": track_id,
        "class_name": "person",
        "bbox": {"x": x, "y": y, "width": 10, "height": 10},
        "coordinate_system": "source_pixels",
    }
    if spatial is not None:
        item["spatial"] = spatial
    return item


def test_reference_pixel_velocity_direction_and_prediction():
    manager = SpatialTrackStateManager()
    manager.update([detection(x=0, y=0)], 1.0)
    state = manager.update([detection(x=10, y=20)], 2.0, prediction_enabled=True)
    track = state["tracks"][0]

    assert track["last_observed"]["coordinate_system"] == "source_pixels"
    assert track["motion"]["velocity"]["vx"] == 10
    assert track["motion"]["velocity"]["vy"] == 20
    assert track["motion"]["velocity"]["speed"] == 22.360679774997898
    assert track["motion"]["direction"]["angle_degrees"] > 0
    assert track["prediction"]["x"] == 20
    assert track["prediction"]["y"] == 40


def test_calibrated_units_are_preserved_and_incompatible_units_disable_velocity():
    manager = SpatialTrackStateManager()
    manager.update(
        [
            detection(
                spatial={
                    "status": "valid",
                    "position": {
                        "x": 1,
                        "y": 2,
                        "coordinate_system": "calibrated_reference_plane",
                        "units": "m",
                    },
                }
            )
        ],
        1,
    )
    first = manager.update(
        [
            detection(
                spatial={
                    "status": "valid",
                    "position": {
                        "x": 2,
                        "y": 2,
                        "coordinate_system": "calibrated_reference_plane",
                        "units": "m",
                    },
                }
            )
        ],
        2,
    )["tracks"][0]
    assert first["motion"]["velocity"]["units"] == "m_per_second"

    incompatible = manager.update(
        [
            detection(
                spatial={
                    "status": "valid",
                    "position": {
                        "x": 3,
                        "y": 2,
                        "coordinate_system": "calibrated_reference_plane",
                        "units": "cm",
                    },
                }
            )
        ],
        3,
    )["tracks"][0]
    assert incompatible["motion"]["velocity"]["status"] == "unavailable"


def test_duplicate_timestamps_do_not_add_samples_and_history_is_bounded():
    manager = SpatialTrackStateManager(MotionConfig(max_trajectory_samples=2))
    manager.update([detection(x=0)], 1)
    manager.update([detection(x=1)], 2)
    manager.update([detection(x=2)], 2)
    state = manager.update([detection(x=3)], 3)
    track = state["tracks"][0]
    assert [sample["timestamp_seconds"] for sample in track["trajectory"]] == [2, 3]
    assert manager.diagnostics["duplicate_or_out_of_order_samples"] == 1
    assert manager.diagnostics["trajectory_samples_truncated"] == 1


def test_missing_and_terminated_tracks_keep_last_observation_and_suppress_prediction():
    manager = SpatialTrackStateManager(MotionConfig(max_prediction_age_seconds=1.0))
    manager.update([detection(x=0)], 1)
    manager.update([detection(x=1)], 2)
    missing = manager.update([], 2.5, prediction_enabled=True)["tracks"][0]
    assert missing["status"] == "missing"
    assert missing["last_observed"]["timestamp_seconds"] == 2
    assert missing["prediction"]["status"] == "valid"
    terminated = manager.update([], 3.1, prediction_enabled=True)["tracks"][0]
    assert terminated["status"] == "terminated"
    assert terminated["prediction"]["status"] == "unavailable"


def test_reset_clears_trajectory_state():
    manager = SpatialTrackStateManager()
    manager.update([detection(x=0)], 1)
    manager.reset()
    assert manager.snapshot()["tracks"] == []
    assert manager.diagnostics == {}
