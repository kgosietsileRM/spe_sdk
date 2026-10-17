"""Tests for point inspection, grid cells, zones, and spatialization."""

from __future__ import annotations

import pytest

from spe import (
    SPEValidationError,
    generate_zones,
    image_to_spatial,
    inspect_point,
    point_in_roi,
    row_label,
    spatial_point_to_grid_cell,
    spatialize_detection,
    zone_for_cell,
)
from spe import zones as zones_module
from tests.conftest import RECTANGLE, SOURCE_HEIGHT, SOURCE_WIDTH

CALIBRATION = None  # populated by the module-scoped fixture below


@pytest.fixture(scope="module")
def calibration():
    from spe import calculate_calibration

    return calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)


def test_point_in_roi_membership(calibration):
    assert point_in_roi([500, 300], RECTANGLE) is True
    assert point_in_roi([10, 10], RECTANGLE) is False


def test_image_to_spatial_maps_center(calibration):
    mapped = image_to_spatial([500, 300], calibration)
    assert mapped["coordinate_system"] == "calibrated_reference_plane"
    assert mapped["units"] == "normalized"
    assert 0 <= mapped["x"] <= 1000
    assert 0 <= mapped["y"] <= 600


def test_spatial_point_to_grid_cell_boundaries():
    assert spatial_point_to_grid_cell([0, 0], 4, 6, 1000, 600) == {
        "row": 0,
        "column": 0,
        "coordinate": [0, 0],
    }
    assert spatial_point_to_grid_cell([1000, 600], 4, 6, 1000, 600) == {
        "row": 3,
        "column": 5,
        "coordinate": [5, 3],
    }
    assert spatial_point_to_grid_cell([-50, 10], 4, 6, 1000, 600) is None


def test_row_labels_and_zones():
    assert [row_label(i) for i in range(3)] == ["A", "B", "C"]
    assert row_label(25) == "Z"
    assert row_label(26) == "AA"
    zones = generate_zones(2, 2)
    assert [zone["id"] for zone in zones] == ["A1", "A2", "B1", "B2"]
    assert zone_for_cell({"row": 1, "column": 1}, 2, 2) == "B2"
    assert zone_for_cell(None, 2, 2) is None


def test_inspect_point_valid(calibration):
    state = {
        "source_dimensions": {"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
        "calibration": calibration,
        "grid": {"rows": 3, "columns": 3},
    }
    result = inspect_point([500, 300], state)
    assert result["status"] == "valid"
    assert result["roi"]["inside"] is True
    assert result["grid_cell"] is not None
    assert result["reference"]["coordinate_system"] == "calibrated_reference_plane"


def test_inspect_point_outside_roi(calibration):
    state = {
        "source_dimensions": {"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
        "calibration": calibration,
        "grid": {"rows": 3, "columns": 3},
    }
    result = inspect_point([5, 5], state)
    assert result["status"] == "outside_roi"


def test_inspect_point_outside_image(calibration):
    state = {
        "source_dimensions": {"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
        "calibration": calibration,
    }
    assert inspect_point([5000, 5000], state) == {
        "status": "invalid",
        "reason": "point_outside_image",
    }


def test_inspect_point_without_calibration():
    state = {"source_dimensions": {"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT}}
    assert inspect_point([100, 100], state) == {
        "status": "invalid",
        "reason": "calibration_unavailable",
    }


def test_spatialize_detection_valid(calibration):
    detection = {"bbox": {"x": 480, "y": 280, "width": 40, "height": 40}}
    spatial = spatialize_detection(detection, calibration, grid={"rows": 3, "columns": 3})
    assert spatial["status"] == "valid"
    assert spatial["zone"] is not None
    assert spatial["position"]["units"] == "normalized"


def test_spatialize_detection_outside_roi(calibration):
    detection = {"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}}
    spatial = spatialize_detection(detection, calibration)
    assert spatial["status"] == "outside_roi"
    assert spatial["in_roi"] is False


def test_spatialize_detection_without_calibration():
    detection = {"bbox": {"x": 0, "y": 0, "width": 10, "height": 10}}
    assert spatialize_detection(detection, None)["reason"] == "calibration_unavailable"


def test_parameter_validation_errors():
    with pytest.raises(SPEValidationError):
        generate_zones(0, 3)
    with pytest.raises(SPEValidationError):
        spatial_point_to_grid_cell([0, 0], 0, 3, 1000, 600)
    with pytest.raises(SPEValidationError):
        point_in_roi([0, 0], [[0, 0], [1, 1]])
    assert zones_module.generate_zones(1, 1) == [{"id": "A1", "row": 0, "column": 0}]


def test_point_validation_errors():
    with pytest.raises(SPEValidationError):
        point_in_roi("not-a-point", RECTANGLE)
    with pytest.raises(SPEValidationError):
        point_in_roi([1, 2, 3], RECTANGLE)
    with pytest.raises(SPEValidationError):
        point_in_roi([True, 0], RECTANGLE)
    with pytest.raises(SPEValidationError):
        point_in_roi([float("inf"), 0], RECTANGLE)
    with pytest.raises(SPEValidationError):
        point_in_roi([0, 0], "not-a-polygon")


def test_spatial_point_to_grid_cell_rejects_bad_dimensions():
    with pytest.raises(SPEValidationError):
        spatial_point_to_grid_cell([0, 0], 3, 3, 0, 600)


def test_image_to_spatial_requires_homography(calibration):
    with pytest.raises(SPEValidationError):
        image_to_spatial([1, 2], {})
    with pytest.raises(SPEValidationError):
        image_to_spatial([1, 2], {"homography": calibration["homography"], "reference_plane": {}})


def test_image_to_spatial_rejects_bad_units(calibration):
    broken = dict(calibration)
    broken["reference_plane"] = dict(calibration["reference_plane"], units="  ")
    with pytest.raises(SPEValidationError):
        image_to_spatial([500, 300], broken)


def test_inspect_point_requires_valid_state():
    with pytest.raises(SPEValidationError):
        inspect_point([1, 2], "not-a-state")
    with pytest.raises(SPEValidationError):
        inspect_point([1, 2], {"source_dimensions": {}})
    with pytest.raises(SPEValidationError):
        inspect_point([1, 2], {"source_dimensions": {"width": 10.5, "height": 10}})
    with pytest.raises(SPEValidationError):
        inspect_point([1, 2], {"source_dimensions": {"width": 0, "height": 10}})


def test_point_rejects_non_iterable():
    with pytest.raises(SPEValidationError):
        point_in_roi(123, RECTANGLE)


def test_spatialize_detection_invalid_roi(calibration):
    detection = {"bbox": {"x": 480, "y": 280, "width": 40, "height": 40}}
    spatial = spatialize_detection(detection, calibration, roi={"points": [[0, 0], [1, 1]]})
    assert spatial["reason"] == "invalid_roi"


def test_spatialize_detection_spatialization_error(calibration):
    broken = dict(calibration)
    broken["reference_plane"] = {"width": float("nan"), "height": 600, "units": "normalized"}
    detection = {"bbox": {"x": 480, "y": 280, "width": 40, "height": 40}}
    spatial = spatialize_detection(detection, broken)
    assert spatial["reason"] == "spatialization_error"


def test_spatialize_detection_invalid_bbox(calibration):
    spatial = spatialize_detection({"bbox": {"x": "bad"}}, calibration)
    assert spatial["reason"] == "invalid_bbox"


def test_spatialize_detection_without_roi(calibration):
    detection = {"bbox": {"x": 480, "y": 280, "width": 40, "height": 40}}
    without_points = {k: v for k, v in calibration.items() if k != "source_points"}
    spatial = spatialize_detection(detection, without_points)
    assert spatial["reason"] == "roi_unavailable"


def test_spatialize_detection_result_enriches_each(fixture_calibration):
    result = {
        "detections": [
            {"bbox": {"x": 480, "y": 280, "width": 40, "height": 40}},
            {"bbox": {"x": 0, "y": 0, "width": 5, "height": 5}},
        ]
    }
    from spe import spatialize_detection_result

    enriched = spatialize_detection_result(result, fixture_calibration)
    assert len(enriched["detections"]) == 2
    assert enriched["detections"][0]["spatial"]["status"] == "valid"
    assert enriched["detections"][1]["spatial"]["status"] == "outside_roi"


@pytest.fixture
def fixture_calibration(calibration):
    return calibration
