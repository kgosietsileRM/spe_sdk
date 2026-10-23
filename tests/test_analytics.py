"""Tests for the tracking and motion analytics helpers."""

from __future__ import annotations

import pytest

from spe import (
    LineCrossingCounter,
    SPEValidationError,
    ZoneOccupancyTracker,
    summarize_tracks,
)


def _detection(track_id, zone, x=0.0, y=0.0):
    return {
        "track_id": track_id,
        "class_name": "person",
        "spatial": {"status": "valid", "zone": zone, "position": {"x": x, "y": y}},
    }


def test_zone_occupancy_tracks_entries_and_dwell():
    tracker = ZoneOccupancyTracker()
    tracker.update([_detection("t1", "A1", 1, 1)], timestamp=0.0)
    snapshot = tracker.update([_detection("t1", "A1", 2, 2)], timestamp=2.0)
    assert snapshot["zones"]["A1"] == {
        "occupancy": 1,
        "entries": 1,
        "dwell_seconds": 2.0,
        "tracks": ["t1"],
    }

    snapshot = tracker.update([_detection("t1", "B2", 5, 5)], timestamp=3.0)
    assert snapshot["zones"]["B2"]["entries"] == 1
    assert snapshot["zones"]["B2"]["dwell_seconds"] == 0.0
    snapshot = tracker.update([_detection("t1", "B2", 6, 6)], timestamp=5.0)
    assert snapshot["zones"]["A1"]["dwell_seconds"] == 2.0
    assert snapshot["zones"]["B2"]["dwell_seconds"] == 2.0
    assert snapshot["active_tracks"] == 1


def test_zone_occupancy_multiple_tracks_and_missing_fields():
    tracker = ZoneOccupancyTracker()
    snapshot = tracker.update(
        [
            _detection("t1", "A1"),
            _detection("t2", "A1"),
            {"track_id": "t3", "class_name": "person"},
            {"class_name": "person", "spatial": {"status": "valid", "zone": "A1"}},
        ],
        timestamp=1.0,
    )
    assert snapshot["zones"]["A1"]["occupancy"] == 2
    assert snapshot["active_tracks"] == 2
    tracker.reset()
    assert tracker.snapshot() == {"timestamp": None, "active_tracks": 0, "zones": {}}


def test_summarize_tracks_distance_speed_and_zones():
    frames = [
        {"timestamp": 0, "detections": [_detection("t1", "A1", 0, 0)]},
        {"timestamp": 1, "detections": [_detection("t1", "A1", 3, 4)]},
        {"timestamp": 2, "detections": [_detection("t1", "B2", 6, 8)]},
    ]
    summaries = summarize_tracks(frames)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary["track_id"] == "t1"
    assert summary["duration"] == 2.0
    assert summary["distance"] == pytest.approx(10.0)
    assert summary["average_speed"] == pytest.approx(5.0)
    assert summary["zones"] == ["A1", "B2"]
    assert summary["start_position"] == [0.0, 0.0]
    assert summary["end_position"] == [6.0, 8.0]
    assert summary["distance_units"] == "source_pixels"


def test_summarize_tracks_reads_foot_point_and_bbox_and_id_fallback():
    frames = [
        {"timestamp": None, "detections": [{"id": "x", "foot_point": {"x": 1, "y": 2}}]},
        {
            "timestamp": None,
            "detections": [{"id": "x", "bbox": {"x": 0, "y": 0, "width": 2, "height": 4}}],
        },
    ]
    summaries = summarize_tracks(frames)
    assert summaries[0]["track_id"] == "x"
    assert summaries[0]["start_position"] == [1.0, 2.0]
    assert summaries[0]["end_position"] == [1.0, 4.0]
    assert summaries[0]["distance"] == pytest.approx(2.0)
    assert summaries[0]["average_speed"] == 0.0
    assert summarize_tracks([{"detections": [{"bbox": {}}]}]) == []


def test_summarize_tracks_rejects_bad_timestamp():
    with pytest.raises(SPEValidationError, match="Timestamps"):
        summarize_tracks([{"timestamp": "soon", "detections": []}])


def test_line_crossing_counts_both_directions():
    counter = LineCrossingCounter([0, 0], [0, 10], name="gate")
    counter.update([_detection("t1", "A1", -1, 5)])
    payload = counter.update([_detection("t1", "A1", 1, 5)])
    assert payload["negative"] == 1
    assert payload["total"] == 1
    payload = counter.update([_detection("t1", "A1", -1, 5)])
    assert payload["positive"] == 1
    assert payload["total"] == 2
    assert payload["name"] == "gate"
    assert len(payload["events"]) == 2


def test_line_crossing_ignores_same_side_border_and_missing_identity():
    counter = LineCrossingCounter([0, 0], [0, 10])
    counter.update([_detection("t1", "A1", -1, 5)])
    assert counter.update([_detection("t1", "A1", -2, 5)])["total"] == 0
    assert counter.update([_detection("t1", "A1", 0, 5)])["total"] == 0
    assert counter.update([_detection("t1", "A1", 2, 5)])["total"] == 1
    counter.update([{"spatial": {"status": "valid", "position": {"x": 5, "y": 5}}}])
    assert counter.snapshot()["total"] == 1


def test_line_crossing_limits_events_and_resets():
    counter = LineCrossingCounter([0, 0], [0, 10], max_events=1)
    counter.update([_detection("t1", "A1", -1, 5)])
    counter.update([_detection("t1", "A1", 1, 5)])
    counter.update([_detection("t1", "A1", -1, 5)])
    assert counter.snapshot()["total"] == 2
    assert len(counter.snapshot()["events"]) == 1
    counter.reset()
    assert counter.snapshot()["total"] == 0
    assert counter.snapshot()["events"] == []


def test_line_crossing_validation():
    with pytest.raises(SPEValidationError, match="differ"):
        LineCrossingCounter([0, 0], [0, 0])
    with pytest.raises(SPEValidationError, match="two coordinates"):
        LineCrossingCounter([0, 0, 0], [0, 1])
