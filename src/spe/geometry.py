"""Local geometry core: projective homography and four-point calibration.

This module is self-contained and depends only on OpenCV and NumPy. It mirrors
the coordinate contract used by the Spatial Intelligence Engine application:

* image coordinates use pixels with the origin at the top-left;
* the calibrated reference plane is a normalized ``1000 x 600`` plane by default;
* calibration point order is ``top_left, top_right, bottom_right, bottom_left``.
"""

from __future__ import annotations

from collections.abc import Sequence

import cv2
import numpy as np

from .exceptions import SPEValidationError

REFERENCE_WIDTH = 1000
REFERENCE_HEIGHT = 600
POINT_ORDER: tuple[str, ...] = ("top_left", "top_right", "bottom_right", "bottom_left")

PointLike = Sequence[float] | Sequence[Sequence[float]] | np.ndarray


def _as_points(
    points: PointLike,
    name: str,
    exact_count: int | None = None,
) -> np.ndarray:
    """Coerce *points* into a finite ``(N, 2)`` float32 array or raise."""
    try:
        values = np.asarray(points, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise SPEValidationError(f"{name} must contain numeric coordinate pairs.") from error
    if values.ndim == 1 and values.shape[0] == 2:
        values = values.reshape(1, 2)
    if values.ndim != 2 or values.shape[1] != 2:
        raise SPEValidationError(f"{name} must contain coordinate pairs.")
    if exact_count is not None and values.shape[0] != exact_count:
        raise SPEValidationError(f"{name} must contain exactly {exact_count} coordinate pairs.")
    if values.shape[0] == 0:
        raise SPEValidationError(f"{name} must contain at least one coordinate pair.")
    if not np.isfinite(values).all():
        raise SPEValidationError(f"{name} must contain only finite coordinates.")
    return values.astype(np.float32)


def _cross_2d(first: np.ndarray, second: np.ndarray) -> float:
    return float(first[0] * second[1] - first[1] * second[0])


def calculate_homography(
    source_points: PointLike,
    destination_points: PointLike,
) -> tuple[np.ndarray, np.ndarray]:
    """Calculate a validated source-to-destination homography with OpenCV.

    Returns the ``3 x 3`` matrix and the per-point inlier mask.
    """
    source = _as_points(source_points, "Source points", 4)
    destination = _as_points(destination_points, "Destination points", 4)
    matrix, mask = cv2.findHomography(source, destination, method=0)
    if matrix is None or matrix.shape != (3, 3) or not np.isfinite(matrix).all():
        raise SPEValidationError("OpenCV homography calculation failed.")
    inliers = mask.reshape(-1).astype(np.int8) if mask is not None else np.ones(4, dtype=np.int8)
    return matrix.astype(np.float64), inliers


def validate_homography(homography: object) -> np.ndarray:
    """Return a finite, invertible ``3 x 3`` homography matrix or raise."""
    try:
        values = np.asarray(homography, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise SPEValidationError("Homography must be a numeric 3x3 matrix.") from error
    if values.shape != (3, 3) or not np.isfinite(values).all():
        raise SPEValidationError("Homography must be a finite 3x3 matrix.")
    if abs(float(np.linalg.det(values))) < 1e-12:
        raise SPEValidationError("Homography matrix is not invertible.")
    return values


def transform_points(points: PointLike, homography: object) -> list[list[float]]:
    """Transform one or more points with an OpenCV homography."""
    values = _as_points(points, "Points")
    matrix = validate_homography(homography)
    transformed = cv2.perspectiveTransform(values.reshape(-1, 1, 2), matrix).reshape(-1, 2)
    if not np.isfinite(transformed).all():
        raise SPEValidationError("Homography produced non-finite coordinates.")
    return transformed.astype(float).tolist()


def inverse_homography(homography: object) -> np.ndarray:
    """Return the inverse transform as a normalized floating-point matrix."""
    matrix = validate_homography(homography)
    inverse = np.linalg.inv(matrix)
    inverse /= inverse[2, 2]
    return inverse


def reprojection_error(
    source_points: PointLike,
    destination_points: PointLike,
    homography: object,
) -> float:
    """Return the mean Euclidean destination-space reprojection error."""
    expected = _as_points(destination_points, "Destination points", 4)
    actual = np.asarray(transform_points(source_points, homography), dtype=np.float64)
    return float(np.mean(np.linalg.norm(actual - expected, axis=1)))


def warp_image(image: np.ndarray, homography: object, width: int, height: int) -> np.ndarray:
    """Warp an image into the calibrated reference plane."""
    if not isinstance(image, np.ndarray) or image.ndim not in (2, 3) or image.size == 0:
        raise SPEValidationError("A non-empty OpenCV image is required.")
    if not isinstance(width, int) or not isinstance(height, int) or width < 2 or height < 2:
        raise SPEValidationError("Warp dimensions must be integers greater than 1.")
    return cv2.warpPerspective(
        image,
        validate_homography(homography),
        (width, height),
        flags=cv2.INTER_LINEAR,
    )


def validate_source_points(points: PointLike, width: int, height: int) -> np.ndarray:
    """Validate ``TL, TR, BR, BL`` image points and return float32 coordinates."""
    if not isinstance(width, int) or not isinstance(height, int) or width < 2 or height < 2:
        raise SPEValidationError("Source width and height must be integers greater than 1.")
    try:
        values = np.asarray(points, dtype=np.float64)
    except (TypeError, ValueError) as error:
        raise SPEValidationError("Source points must be numeric coordinate pairs.") from error
    if values.shape != (4, 2) or not np.isfinite(values).all():
        raise SPEValidationError("Exactly four finite coordinate pairs are required.")
    if (values < 0).any() or (values[:, 0] > width - 1).any() or (values[:, 1] > height - 1).any():
        raise SPEValidationError("All source points must be inside the source frame.")
    distances = np.linalg.norm(values[:, None] - values[None, :], axis=2)
    if np.min(distances + np.eye(4) * 1e9) < 1e-6:
        raise SPEValidationError("Source points must not be duplicates.")
    crosses = [
        _cross_2d(
            values[(index + 1) % 4] - values[index],
            values[(index + 2) % 4] - values[(index + 1) % 4],
        )
        for index in range(4)
    ]
    area = abs(sum(_cross_2d(values[index], values[(index + 1) % 4]) for index in range(4)) / 2)
    if area < 1.0 or not (
        all(value > 0 for value in crosses) or all(value < 0 for value in crosses)
    ):
        raise SPEValidationError(
            "Calibration points must form a non-degenerate quadrilateral in TL, TR, BR, BL order."
        )
    return values.astype(np.float32)


def calculate_calibration(
    points: PointLike,
    width: int,
    height: int,
    reference_width: float = REFERENCE_WIDTH,
    reference_height: float = REFERENCE_HEIGHT,
    units: str = "normalized",
) -> dict:
    """Validate four points and return an image-to-plane calibration record."""
    source = validate_source_points(points, width, height)
    if (
        not np.isfinite(reference_width)
        or not np.isfinite(reference_height)
        or reference_width <= 0
        or reference_height <= 0
    ):
        raise SPEValidationError("Reference dimensions must be positive finite numbers.")
    if not isinstance(units, str) or not units.strip():
        raise SPEValidationError("Reference units must be a non-empty string.")

    destination = np.array(
        [[0, 0], [reference_width, 0], [reference_width, reference_height], [0, reference_height]],
        dtype=np.float32,
    )
    homography, mask = calculate_homography(source, destination)
    inverse = inverse_homography(homography)
    error = reprojection_error(source, destination, homography)
    source_area = abs(
        sum(_cross_2d(source[index], source[(index + 1) % 4]) for index in range(4)) / 2
    )
    return {
        "status": "calibrated",
        "method": "manual_four_point",
        "coordinate_system": "calibrated_reference_plane",
        "point_order": list(POINT_ORDER),
        "source_points": source.astype(int).tolist(),
        "destination_points": destination.astype(int).tolist(),
        "reference_plane": {
            "width": float(reference_width),
            "height": float(reference_height),
            "units": units,
        },
        "roi": {"status": "active", "type": "calibrated_planar_region"},
        "homography": homography.tolist(),
        "inverse_homography": inverse.tolist(),
        "reprojection_error": error,
        "source_roi": {
            "area_px": float(source_area),
            "area_percent": float(source_area / (width * height) * 100),
        },
        "transformation": {"direction": "image_to_calibrated_reference_plane", "reusable": True},
        "inlier_mask": mask.reshape(-1).astype(int).tolist() if mask is not None else [],
    }


__all__ = [
    "POINT_ORDER",
    "REFERENCE_HEIGHT",
    "REFERENCE_WIDTH",
    "calculate_calibration",
    "calculate_homography",
    "inverse_homography",
    "reprojection_error",
    "transform_points",
    "validate_homography",
    "validate_source_points",
    "warp_image",
]
