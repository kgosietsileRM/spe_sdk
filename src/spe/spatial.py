"""Reusable point and detection spatialization primitives.

These functions translate source-pixel coordinates into calibrated reference
coordinates, resolve grid cells and zones, and inspect a single point using the
canonical spatial state contract shared with the engine API.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any, cast

import cv2
import numpy as np

from .exceptions import SPEValidationError
from .geometry import transform_points, validate_homography
from .zones import zone_for_cell


def _finite_number(value: Any, name: str) -> float:
    if isinstance(value, bool):
        raise SPEValidationError(f"{name} must be numeric.")
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise SPEValidationError(f"{name} must be numeric.") from error
    if not math.isfinite(number):
        raise SPEValidationError(f"{name} must be finite.")
    return number


def _point(point: Any, name: str = "Point") -> tuple[float, float]:
    if isinstance(point, (str, bytes)):
        raise SPEValidationError(f"{name} must contain two numeric coordinates.")
    try:
        values = list(point)
    except TypeError as error:
        raise SPEValidationError(f"{name} must contain two numeric coordinates.") from error
    if len(values) != 2:
        raise SPEValidationError(f"{name} must contain two numeric coordinates.")
    return _finite_number(values[0], f"{name} x"), _finite_number(values[1], f"{name} y")


def point_in_roi(image_point: Sequence[float], source_points: Sequence[Sequence[float]]) -> bool:
    """Return whether an image point is inside or on the calibrated ROI."""
    point = _point(image_point, "Image point")
    try:
        polygon = np.asarray(source_points, dtype=np.float32)
    except (TypeError, ValueError) as error:
        raise SPEValidationError("ROI points must contain numeric coordinate pairs.") from error
    if polygon.shape != (4, 2) or not np.isfinite(polygon).all():
        raise SPEValidationError("ROI must contain four finite coordinate pairs.")
    return cv2.pointPolygonTest(polygon, point, False) >= 0


def image_to_spatial(image_point: Sequence[float], calibration: Mapping[str, Any]) -> dict:
    """Map one native image point through an existing calibration record."""
    point = _point(image_point, "Image point")
    if not isinstance(calibration, Mapping) or not calibration.get("homography"):
        raise SPEValidationError("A calibrated homography is required.")
    matrix = validate_homography(calibration["homography"])
    mapped = transform_points([point], matrix)[0]
    reference = calibration.get("reference_plane") or {}
    width = _finite_number(reference.get("width"), "Reference width")
    height = _finite_number(reference.get("height"), "Reference height")
    units = reference.get("units", "normalized")
    if not isinstance(units, str) or not units.strip():
        raise SPEValidationError("Reference units must be a non-empty string.")
    return {
        "x": mapped[0],
        "y": mapped[1],
        "coordinate_system": "calibrated_reference_plane",
        "units": units,
        "width": width,
        "height": height,
    }


def spatial_point_to_grid_cell(
    spatial_point: Sequence[float],
    rows: int,
    columns: int,
    width: float,
    height: float,
) -> dict | None:
    """Return a calibrated grid cell, including safe maximum boundaries."""
    x, y = _point(spatial_point, "Spatial point")
    if not isinstance(rows, int) or not isinstance(columns, int) or rows < 1 or columns < 1:
        raise SPEValidationError("Grid rows and columns must be positive integers.")
    width = _finite_number(width, "Grid width")
    height = _finite_number(height, "Grid height")
    if width <= 0 or height <= 0:
        raise SPEValidationError("Grid width and height must be positive.")
    epsilon = 1e-9
    if x < -epsilon or y < -epsilon or x > width + epsilon or y > height + epsilon:
        return None
    x = min(max(x, 0.0), width)
    y = min(max(y, 0.0), height)
    column = min(columns - 1, math.floor(x / (width / columns)))
    row = min(rows - 1, math.floor(y / (height / rows)))
    return {"row": row, "column": column, "coordinate": [column, row]}


def inspect_point(image_point: Sequence[float], spatial_state: Mapping[str, Any]) -> dict:
    """Inspect a native image point using the canonical spatial state contract."""
    point = _point(image_point, "Image point")
    if not isinstance(spatial_state, Mapping):
        raise SPEValidationError("Spatial state must be an object.")
    source = spatial_state.get("source_dimensions") or spatial_state.get("source") or {}
    try:
        raw_width = _finite_number(source["width"], "Source width")
        raw_height = _finite_number(source["height"], "Source height")
    except (KeyError, TypeError, ValueError) as error:
        raise SPEValidationError("Valid source image dimensions are required.") from error
    if not raw_width.is_integer() or not raw_height.is_integer():
        raise SPEValidationError("Source image dimensions must be integers.")
    image_width = int(raw_width)
    image_height = int(raw_height)
    if image_width < 1 or image_height < 1:
        raise SPEValidationError("Source image dimensions must be positive.")
    if point[0] < 0 or point[1] < 0 or point[0] > image_width - 1 or point[1] > image_height - 1:
        return {"status": "invalid", "reason": "point_outside_image"}

    calibration = spatial_state.get("calibration")
    if not isinstance(calibration, Mapping) or not calibration.get("homography"):
        return {"status": "invalid", "reason": "calibration_unavailable"}
    source_points = cast("Sequence[Sequence[float]]", calibration.get("source_points"))
    inside = point_in_roi(point, source_points)
    result: dict[str, Any] = {
        "status": "valid" if inside else "outside_roi",
        "image": {"x": point[0], "y": point[1], "coordinate_system": "image_pixels", "units": "px"},
        "roi": {"inside": inside, "coordinate_system": "image_pixels"},
        "reference": None,
        "physical": {"available": False, "coordinate_system": "physical_reference_plane"},
        "grid_cell": None,
    }
    if not inside:
        return result

    reference = image_to_spatial(point, calibration)
    result["reference"] = {key: reference[key] for key in ("x", "y", "coordinate_system", "units")}
    plane = calibration["reference_plane"]
    units = reference["units"]
    if units != "normalized":
        result["physical"] = {
            "available": True,
            "x": reference["x"],
            "y": reference["y"],
            "coordinate_system": "physical_reference_plane",
            "units": units,
        }
    grid = spatial_state.get("grid") or {}
    rows = grid.get("rows", 4)
    columns = grid.get("columns", 6)
    result["grid_cell"] = spatial_point_to_grid_cell(
        (reference["x"], reference["y"]), rows, columns, plane["width"], plane["height"]
    )
    return result


def spatialize_detection(
    detection: Mapping[str, Any],
    calibration: Mapping[str, Any] | None,
    roi: Mapping[str, Any] | None = None,
    grid: Mapping[str, Any] | None = None,
) -> dict:
    """Add calibrated spatial data without changing source-pixel detection fields."""
    bbox = detection.get("bbox") or {}
    try:
        ground: dict[str, Any] = {
            "x": float(bbox["x"]) + float(bbox["width"]) / 2,
            "y": float(bbox["y"]) + float(bbox["height"]),
            "coordinate_system": "source_pixels",
            "units": "px",
        }
    except (KeyError, TypeError, ValueError):
        return {"status": "unavailable", "reason": "invalid_bbox"}
    spatial: dict[str, Any] = {
        "status": "unavailable",
        "ground_point": ground,
        "position": None,
        "grid_cell": None,
        "zone": None,
        "in_roi": None,
        "coordinate_system": "calibrated_reference_plane",
        "units": None,
    }
    if not isinstance(calibration, Mapping) or not calibration.get("homography"):
        spatial["reason"] = "calibration_unavailable"
        return spatial
    points = (roi or {}).get("points") or calibration.get("source_points")
    if not points:
        spatial["reason"] = "roi_unavailable"
        return spatial
    try:
        inside = point_in_roi([ground["x"], ground["y"]], points)
    except SPEValidationError:
        spatial["reason"] = "invalid_roi"
        return spatial
    spatial["in_roi"] = inside
    if not inside:
        spatial["status"] = "outside_roi"
        return spatial
    try:
        position = image_to_spatial([ground["x"], ground["y"]], dict(calibration))
        reference = calibration.get("reference_plane") or {}
        configured = calibration.get("calibrated_grid") or grid or {}
        rows = int(configured.get("rows", 3))
        columns = int(configured.get("columns", 3))
        cell = spatial_point_to_grid_cell(
            (position["x"], position["y"]),
            rows,
            columns,
            float(reference["width"]),
            float(reference["height"]),
        )
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        spatial["reason"] = "spatialization_error"
        return spatial
    spatial.update(
        {
            "status": "valid",
            "position": {
                "x": position["x"],
                "y": position["y"],
                "coordinate_system": position["coordinate_system"],
                "units": position["units"],
            },
            "grid_cell": cell,
        }
    )
    if cell:
        spatial["zone"] = zone_for_cell(cell, rows, columns)
    spatial["units"] = position["units"]
    return spatial


def spatialize_detection_result(
    result: Mapping[str, Any],
    calibration: Mapping[str, Any] | None,
    roi: Mapping[str, Any] | None = None,
    grid: Mapping[str, Any] | None = None,
) -> dict:
    """Enrich a normalized detection result with calibrated spatial data."""
    enriched = {**result, "detections": []}
    for detection in result.get("detections") or []:
        item = {**detection}
        item["spatial"] = spatialize_detection(detection, calibration, roi, grid)
        enriched["detections"].append(item)
    return enriched


is_point_in_spatial_roi = point_in_roi
point_to_grid_cell = spatial_point_to_grid_cell

__all__ = [
    "image_to_spatial",
    "inspect_point",
    "is_point_in_spatial_roi",
    "point_in_roi",
    "point_to_grid_cell",
    "spatial_point_to_grid_cell",
    "spatialize_detection",
    "spatialize_detection_result",
]
