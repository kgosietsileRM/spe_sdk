"""Tests for provider-neutral tracking."""

from __future__ import annotations

from spe import ModelAgnosticTracker, TrackingConfig


def detection(x, y=10, width=20, height=20, class_id=1):
    return {
        "id": f"det-{x}-{y}",
        "class_id": class_id,
        "class_name": "car",
        "confidence": 0.8,
        "bbox": {"x": x, "y": y, "width": width, "height": height},
        "coordinate_system": "source_pixels",
    }


def test_consecutive_detections_and_short_gap_keep_identity():
    tracker = ModelAgnosticTracker()
    first = tracker.update([detection(10)], 0.0)["detections"][0]["track_id"]
    tracker.update([], 0.5)
    returned = tracker.update([detection(12)], 1.0)["detections"][0]["track_id"]
    assert returned == first


def test_long_gap_terminates_and_new_detection_gets_new_id():
    tracker = ModelAgnosticTracker(TrackingConfig(max_missing_seconds=1.0))
    first = tracker.update([detection(10)], 0.0)["detections"][0]["track_id"]
    tracker.update([], 2.0)
    second = tracker.update([detection(10)], 2.1)["detections"][0]["track_id"]
    assert second != first
    assert tracker.diagnostics["tracks_terminated"] == 1


def test_assignment_is_one_to_one_and_class_mismatch_is_rejected():
    tracker = ModelAgnosticTracker()
    tracker.update([detection(10), detection(100, class_id=2)], 0.0)
    result = tracker.update([detection(12), detection(13), detection(100, class_id=3)], 1.0)[
        "detections"
    ]
    assert len({item["track_id"] for item in result[:2]}) == 2
    assert result[2]["track_id"] not in {item["track_id"] for item in result[:2]}


def test_duplicate_and_out_of_order_observations_do_not_mutate_tracker():
    tracker = ModelAgnosticTracker()
    tracker.update([detection(10)], 1.0)
    before = tracker.snapshot()
    tracker.update([detection(100)], 1.0)
    tracker.update([detection(100)], 0.5)
    assert tracker.snapshot()["active_tracks"] == before["active_tracks"]
    assert tracker.diagnostics["duplicate_observations_rejected"] == 1
    assert tracker.diagnostics["out_of_order_rejected"] == 1


def test_invalid_geometry_is_safe_and_calibration_is_not_required():
    tracker = ModelAgnosticTracker()
    result = tracker.update([{"bbox": {"x": 0, "y": 0, "width": 0, "height": 2}}], 0.0)
    assert result["detections"][0].get("track_id") is None
    assert tracker.diagnostics["invalid_detections"] == 1


def test_reset_clears_identity_state():
    tracker = ModelAgnosticTracker()
    tracker.update([detection(10)], 0.0)
    tracker.reset()
    assert tracker.snapshot()["active_tracks"] == 0
    assert tracker.diagnostics == {}
