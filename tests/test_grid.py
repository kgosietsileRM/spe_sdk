"""Tests for the image-space and calibrated grid renderers."""

from __future__ import annotations

import numpy as np
import pytest

from spe import (
    GridConfig,
    SPEValidationError,
    calculate_calibration,
    generate_calibrated_grid,
    generate_grid,
)
from tests.conftest import RECTANGLE, SOURCE_HEIGHT, SOURCE_WIDTH


def test_generate_grid_default_config(sample_image):
    rendered, metadata = generate_grid(sample_image)
    assert rendered.shape == sample_image.shape
    assert metadata["status"] == "grid generated"
    assert metadata["grid"]["rows"] == 8
    assert metadata["grid"]["columns"] == 12
    assert metadata["grid"]["coordinate_system"] == "image"


def test_generate_grid_custom_config(sample_image):
    config = GridConfig(rows=4, columns=5, line_thickness=2, show_coordinates=False)
    rendered, metadata = generate_grid(sample_image, config)
    assert rendered.shape == sample_image.shape
    assert metadata["grid"]["show_coordinates"] is False


def test_generate_grid_rejects_bad_image():
    with pytest.raises(SPEValidationError):
        generate_grid(np.array([], dtype=np.uint8))


def test_generate_grid_rejects_bad_config(sample_image):
    with pytest.raises(SPEValidationError):
        generate_grid(sample_image, GridConfig(rows=0, columns=3))
    with pytest.raises(SPEValidationError):
        generate_grid(sample_image, GridConfig(line_thickness=99))
    with pytest.raises(SPEValidationError):
        generate_grid(sample_image, GridConfig(line_color=(300, 0, 0)))


@pytest.fixture
def homography() -> list[list[float]]:
    return calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)["homography"]


def test_generate_calibrated_grid(sample_image, homography):
    rendered, metadata = generate_calibrated_grid(sample_image, homography, rows=3, columns=4)
    assert rendered.shape == sample_image.shape
    assert metadata["coordinate_system"] == "calibrated_reference_plane"
    assert metadata["grid"]["rows"] == 3


def test_generate_calibrated_grid_overlay_only(sample_image, homography):
    rendered, _ = generate_calibrated_grid(sample_image, homography, overlay_only=True)
    assert rendered.shape == (SOURCE_HEIGHT, SOURCE_WIDTH, 4)


def test_generate_calibrated_grid_roi_without_source_points(sample_image, homography):
    rendered, _ = generate_calibrated_grid(sample_image, homography, show_roi=True)
    assert rendered.shape == sample_image.shape


def test_generate_calibrated_grid_rejects_bad_homography(sample_image):
    with pytest.raises(SPEValidationError):
        generate_calibrated_grid(sample_image, [[1, 0], [0, 1]])


def test_generate_calibrated_grid_rejects_bad_rows(sample_image, homography):
    with pytest.raises(SPEValidationError):
        generate_calibrated_grid(sample_image, homography, rows=0)


def test_generate_calibrated_grid_rejects_bad_image(homography):
    with pytest.raises(SPEValidationError):
        generate_calibrated_grid(np.array([], dtype=np.uint8), homography)


def test_generate_calibrated_grid_rejects_bad_reference(homography):
    with pytest.raises(SPEValidationError):
        generate_calibrated_grid(np.zeros((10, 10, 3), np.uint8), homography, reference_width=0)


def test_generate_calibrated_grid_rejects_bad_colors(sample_image, homography):
    with pytest.raises(SPEValidationError):
        generate_calibrated_grid(sample_image, homography, line_color=(1, 2))


def test_generate_calibrated_grid_rejects_bad_source_points(sample_image, homography):
    with pytest.raises(SPEValidationError):
        generate_calibrated_grid(sample_image, homography, source_points=[[0, 0], [1, 1]])


def test_generate_calibrated_grid_with_source_points(sample_image, homography):
    rendered, _ = generate_calibrated_grid(
        sample_image, homography, source_points=RECTANGLE, show_roi=True
    )
    assert rendered.shape == sample_image.shape


def test_generate_calibrated_grid_without_grid_or_roi(sample_image, homography):
    rendered, _ = generate_calibrated_grid(
        sample_image, homography, show_grid=False, show_roi=False
    )
    assert rendered.shape == sample_image.shape
