"""Tests for the high-level SpatialEngine facade and value objects."""

from __future__ import annotations

import pytest

from spe import (
    BoundingBox,
    Calibration,
    Detection,
    GridCell,
    ReferencePlane,
    SpatialEngine,
    SPEEngineError,
    SPEValidationError,
)
from tests.conftest import RECTANGLE, SOURCE_HEIGHT, SOURCE_WIDTH


def test_calibrate_and_query(engine):
    assert engine.is_calibrated
    assert isinstance(engine.calibration, Calibration)
    mapped = engine.image_to_reference([500, 300])
    assert len(mapped) == 1
    zone = engine.zone_for_image_point([500, 300])
    assert zone is not None
    assert engine.cell_for_image_point([500, 300]) is not None


def test_inspect_uses_source_dimensions(engine):
    result = engine.inspect([500, 300])
    assert result["status"] == "valid"


def test_zones_count(engine):
    assert len(engine.zones()) == 9


def test_render_grid(engine, sample_image):
    rendered, metadata = engine.render_grid(sample_image, rows=4, columns=5)
    assert rendered.shape == sample_image.shape
    assert metadata["grid"]["rows"] == 4
    assert metadata["grid"]["columns"] == 5


def test_render_calibrated_grid(engine, sample_image):
    rendered, metadata = engine.render_calibrated_grid(sample_image)
    assert rendered.shape == sample_image.shape
    assert metadata["coordinate_system"] == "calibrated_reference_plane"


def test_render_calibrated_grid_overlay_only(engine, sample_image):
    rendered, _ = engine.render_calibrated_grid(sample_image, overlay_only=True)
    assert rendered.shape == (SOURCE_HEIGHT, SOURCE_WIDTH, 4)


def test_explicit_reference_plane_units():
    engine = SpatialEngine()
    calibration = engine.calibrate(
        RECTANGLE,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        reference_plane=ReferencePlane(width=2.0, height=1.2, units="m"),
    )
    assert calibration.reference_plane.units == "m"
    result = engine.inspect([500, 300])
    assert result["physical"]["available"] is True
    assert result["physical"]["units"] == "m"


def test_spatialize_result(engine):
    result = {
        "model": {"id": "model-a"},
        "detections": [
            {
                "id": "d1",
                "class_name": "person",
                "bbox": {"x": 470, "y": 270, "width": 40, "height": 40},
            }
        ],
    }
    enriched = engine.spatialize_result(result)
    assert enriched["detections"][0]["spatial"]["status"] == "valid"


def test_uncalibrated_engine_raises():
    engine = SpatialEngine()
    assert engine.is_calibrated is False
    with pytest.raises(SPEEngineError):
        engine.inspect([10, 10])


def test_serialization_round_trip(engine):
    payload = engine.to_dict()
    restored = SpatialEngine.from_dict(payload)
    assert restored.is_calibrated
    assert restored.grid_rows == engine.grid_rows
    assert restored.inspect([500, 300])["status"] == "valid"


def test_bounding_box_geometry():
    box = BoundingBox(10, 20, 40, 60)
    assert box.center == {"x": 30, "y": 50}
    assert box.foot_point == {"x": 30, "y": 80}
    with pytest.raises(SPEValidationError):
        BoundingBox(-1, 0, 10, 10)


def test_detection_validation_and_dict():
    detection = Detection("person", BoundingBox(0, 0, 10, 10), confidence=0.9, track_id="track-1")
    payload = detection.to_dict()
    assert payload["class_name"] == "person"
    assert payload["track_id"] == "track-1"
    with pytest.raises(SPEValidationError):
        Detection("person", BoundingBox(0, 0, 10, 10), confidence=1.5)


def test_grid_cell_coordinate_order():
    cell = GridCell(row=2, column=5)
    assert cell.coordinate == [5, 2]
    assert GridCell.from_dict({"row": 1, "column": 3}).coordinate == [3, 1]


def test_load_and_clear_calibration(engine):
    payload = engine.calibration.to_dict()
    other = SpatialEngine()
    loaded = other.load_calibration(payload)
    assert isinstance(loaded, Calibration)
    assert other.is_calibrated
    other.clear_calibration()
    assert other.is_calibrated is False


def test_reference_space_queries(engine):
    reference = engine.image_to_reference([500, 300])[0]
    assert engine.reference_to_image(reference)[0][0] == pytest.approx(500, abs=1e-3)
    assert engine.cell_for_reference_point(reference) is not None
    assert engine.zone_for_reference_point(reference) is not None


def test_spatial_state_without_source_dimensions():
    engine = SpatialEngine()
    engine.calibrate(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    engine.source_dimensions = None
    assert "source_dimensions" not in engine.spatial_state()


def test_spatialize_one_and_many(engine):
    detection = {"bbox": {"x": 480, "y": 280, "width": 40, "height": 40}}
    single = engine.spatialize_detection(detection)
    assert single["status"] == "valid"
    batch = engine.spatialize([detection, detection])
    assert len(batch) == 2


def test_calibrate_rejects_bad_grid(engine):
    engine.grid_rows = 0
    with pytest.raises(SPEValidationError):
        engine.calibrate(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)


def test_from_dict_without_calibration():
    engine = SpatialEngine.from_dict({"grid_rows": 2, "grid_columns": 2})
    assert engine.is_calibrated is False
    assert engine.grid_rows == 2


def test_zone_polygons_are_projected_into_image_space(engine):
    polygons = engine.zone_polygons()
    assert len(polygons) == 9
    assert set(polygons) == {zone.id for zone in engine.zones()}
    for polygon in polygons.values():
        assert len(polygon) == 4
        for x, y in polygon:
            assert -1 <= x <= SOURCE_WIDTH + 1
            assert -1 <= y <= SOURCE_HEIGHT + 1


def test_detections_in_zone_filters_and_validates(engine):
    polygon = engine.zone_polygons()["A1"]
    center_x = sum(point[0] for point in polygon) / 4
    center_y = sum(point[1] for point in polygon) / 4
    detection = {
        "class_name": "person",
        "bbox": {"x": center_x - 5, "y": center_y - 10, "width": 10, "height": 10},
    }
    found = engine.detections_in_zone([detection], "A1")
    assert len(found) == 1
    assert found[0]["zone"] == "A1"
    assert engine.detections_in_zone([detection], "C3") == []
    with pytest.raises(SPEValidationError, match="Unknown zone"):
        engine.detections_in_zone([detection], "Z9")


def test_zone_polygons_require_calibration():
    with pytest.raises(SPEEngineError):
        SpatialEngine().zone_polygons()
