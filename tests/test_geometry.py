"""Tests for the local geometry core."""

from __future__ import annotations

import numpy as np
import pytest

from spe import (
    REFERENCE_HEIGHT,
    REFERENCE_WIDTH,
    SPEValidationError,
    calculate_calibration,
    calculate_homography,
    inverse_homography,
    reprojection_error,
    transform_points,
    validate_homography,
    validate_source_points,
    warp_image,
)
from tests.conftest import RECTANGLE, SOURCE_HEIGHT, SOURCE_WIDTH

DESTINATION = [
    [0, 0],
    [REFERENCE_WIDTH, 0],
    [REFERENCE_WIDTH, REFERENCE_HEIGHT],
    [0, REFERENCE_HEIGHT],
]


def test_calculate_calibration_maps_corners():
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    mapped = transform_points(RECTANGLE, record["homography"])
    assert np.allclose(mapped, DESTINATION, atol=1.0)


def test_calibration_reports_metadata():
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT, units="cm")
    assert record["status"] == "calibrated"
    assert record["point_order"] == ["top_left", "top_right", "bottom_right", "bottom_left"]
    assert record["reference_plane"]["units"] == "cm"
    assert record["reprojection_error"] < 1e-6
    assert len(record["inlier_mask"]) == 4


def test_round_trip_is_stable():
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    forward = transform_points([[500, 300]], record["homography"])
    backward = transform_points(forward, record["inverse_homography"])
    assert np.allclose(backward, [[500, 300]], atol=1e-4)


def test_calculate_homography_returns_3x3_and_mask():
    matrix, mask = calculate_homography(RECTANGLE, DESTINATION)
    assert matrix.shape == (3, 3)
    assert mask.shape == (4,)


def test_inverse_homography_is_normalized():
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    inverse = inverse_homography(record["homography"])
    assert inverse.shape == (3, 3)
    assert inverse[2, 2] == pytest.approx(1.0)


def test_reprojection_error_is_small_for_exact_corners():
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    error = reprojection_error(RECTANGLE, DESTINATION, record["homography"])
    assert error < 1e-6


def test_validate_source_points_rejects_duplicates():
    with pytest.raises(SPEValidationError):
        validate_source_points([[0, 0], [0, 0], [100, 100], [0, 100]], SOURCE_WIDTH, SOURCE_HEIGHT)


def test_validate_source_points_rejects_degenerate_quad():
    with pytest.raises(SPEValidationError):
        validate_source_points([[0, 0], [100, 0], [200, 0], [300, 0]], SOURCE_WIDTH, SOURCE_HEIGHT)


def test_validate_source_points_rejects_out_of_bounds():
    with pytest.raises(SPEValidationError):
        validate_source_points(
            [[0, 0], [2000, 0], [2000, 600], [0, 600]], SOURCE_WIDTH, SOURCE_HEIGHT
        )


def test_validate_homography_rejects_singular_matrix():
    with pytest.raises(SPEValidationError):
        validate_homography([[1, 0, 0], [0, 1, 0], [0, 0, 0]])


def test_warp_image_produces_requested_size(sample_image):
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    warped = warp_image(sample_image, record["homography"], 200, 120)
    assert warped.shape[:2] == (120, 200)


def test_calculate_calibration_rejects_bad_units():
    with pytest.raises(SPEValidationError):
        calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT, units="  ")


def test_calculate_calibration_rejects_bad_reference_size():
    with pytest.raises(SPEValidationError):
        calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT, reference_width=0)


def test_validate_homography_rejects_non_numeric():
    with pytest.raises(SPEValidationError):
        validate_homography([["a", "b", "c"], ["d", "e", "f"], ["g", "h", "i"]])


def test_validate_homography_rejects_wrong_shape():
    with pytest.raises(SPEValidationError):
        validate_homography([[1, 0], [0, 1]])


def test_transform_points_rejects_bad_inputs():
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    homography = record["homography"]
    with pytest.raises(SPEValidationError):
        transform_points("not-points", homography)
    with pytest.raises(SPEValidationError):
        transform_points([1, 2, 3], homography)
    with pytest.raises(SPEValidationError):
        transform_points(np.zeros((0, 2)), homography)
    with pytest.raises(SPEValidationError):
        transform_points([[np.inf, 0]], homography)


def test_transform_points_rejects_non_finite_result(monkeypatch):
    import cv2

    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)

    def _nan(*_args, **_kwargs):
        return np.array([[[np.nan, 0.0]]], dtype=np.float32)

    monkeypatch.setattr(cv2, "perspectiveTransform", _nan)
    with pytest.raises(SPEValidationError):
        transform_points([[1.0, 0.0]], record["homography"])


def test_warp_image_rejects_bad_image_and_size():
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    with pytest.raises(SPEValidationError):
        warp_image(np.array([], dtype=np.uint8), record["homography"], 10, 10)
    with pytest.raises(SPEValidationError):
        warp_image(np.zeros((10, 10, 3), np.uint8), record["homography"], 1, 1)


def test_validate_source_points_rejects_bad_dimensions():
    with pytest.raises(SPEValidationError):
        validate_source_points(RECTANGLE, 1, 600)


def test_validate_source_points_rejects_non_numeric():
    with pytest.raises(SPEValidationError):
        validate_source_points([["a", 0], [1, 0], [1, 1], [0, 1]], SOURCE_WIDTH, SOURCE_HEIGHT)


def test_validate_source_points_rejects_wrong_count():
    with pytest.raises(SPEValidationError):
        validate_source_points([[0, 0], [1, 0], [1, 1]], SOURCE_WIDTH, SOURCE_HEIGHT)


def test_calculate_homography_requires_four_points():
    with pytest.raises(SPEValidationError):
        calculate_homography([[0, 0], [1, 0], [1, 1]], [[0, 0], [1, 0], [1, 1], [0, 1]])


def test_calculate_homography_failure(monkeypatch):
    import cv2

    monkeypatch.setattr(cv2, "findHomography", lambda *_args, **_kwargs: (None, None))
    with pytest.raises(SPEValidationError):
        calculate_homography(RECTANGLE, [[0, 0], [1, 0], [1, 1], [0, 1]])
