"""Tests for the typed value objects (BoundingBox, Detection, Calibration, ...)."""

from __future__ import annotations

import pytest

from spe import (
    BoundingBox,
    Calibration,
    Detection,
    GridCell,
    ReferencePlane,
    SPEValidationError,
    Zone,
    calculate_calibration,
)
from tests.conftest import RECTANGLE, SOURCE_HEIGHT, SOURCE_WIDTH


def test_bounding_box_round_trip():
    box = BoundingBox.from_dict({"x": 1, "y": 2, "width": 3, "height": 4})
    assert box.to_dict() == {"x": 1.0, "y": 2.0, "width": 3.0, "height": 4.0}
    assert box.center == {"x": 2.5, "y": 4.0}


def test_reference_plane_defaults_and_override():
    assert ReferencePlane.from_dict(None).units == "normalized"
    plane = ReferencePlane.from_dict({"width": 2.0, "height": 1.0, "units": "m"})
    assert plane.to_dict() == {"width": 2.0, "height": 1.0, "units": "m"}


def test_detection_round_trip_includes_identifiers():
    detection = Detection(
        "person",
        BoundingBox(0, 0, 10, 10),
        confidence=0.5,
        id="det-1",
        class_id=3,
        track_id="track-9",
    )
    payload = detection.to_dict()
    assert payload["id"] == "det-1"
    assert payload["class_id"] == 3
    assert payload["track_id"] == "track-9"
    restored = Detection.from_dict(payload)
    assert restored.class_name == "person"
    assert restored.coordinate_system == "source_pixels"


def test_detection_to_dict_without_optional_ids():
    payload = Detection("person", BoundingBox(0, 0, 10, 10)).to_dict()
    assert "class_id" not in payload
    assert "track_id" not in payload
    assert payload["class_name"] == "person"


def test_detection_from_dict_uses_label_fallback():
    restored = Detection.from_dict(
        {"label": "car", "bbox": {"x": 0, "y": 0, "width": 1, "height": 1}}
    )
    assert restored.class_name == "car"


def test_detection_rejects_bad_coordinate_system():
    with pytest.raises(SPEValidationError):
        Detection("person", BoundingBox(0, 0, 10, 10), coordinate_system="reference_pixels")


def test_detection_requires_class_name():
    with pytest.raises(SPEValidationError):
        Detection("   ", BoundingBox(0, 0, 10, 10))


def test_grid_cell_and_zone_mappings():
    assert GridCell(row=1, column=2).to_dict() == {"row": 1, "column": 2, "coordinate": [2, 1]}
    assert Zone.from_dict({"id": "B2", "row": 1, "column": 1}).to_dict() == {
        "id": "B2",
        "row": 1,
        "column": 1,
    }


def test_calibration_from_points_and_queries():
    calibration = Calibration.from_points(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT, rows=4, columns=6)
    assert calibration.rows == 4 and calibration.columns == 6
    assert calibration.status == "calibrated"
    forward = calibration.image_to_reference([[500, 300]])
    backward = calibration.reference_to_image(forward)
    assert backward[0][0] == pytest.approx(500, abs=1e-3)
    assert calibration.cell_for(forward[0]) is not None
    assert calibration.zone_for(forward[0]) is not None


def test_calibration_to_dict_can_omit_grid():
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    calibration = Calibration.from_record(record, rows=3, columns=3)
    assert "calibrated_grid" not in calibration.to_dict(include_grid=False)
    assert calibration.to_dict()["calibrated_grid"] == {"rows": 3, "columns": 3}


def test_calibration_without_homography_raises():
    calibration = Calibration(source_points=[], homography=None, inverse_homography=None)
    with pytest.raises(SPEValidationError):
        calibration.image_to_reference([[0, 0]])
    with pytest.raises(SPEValidationError):
        calibration.reference_to_image([[0, 0]])
