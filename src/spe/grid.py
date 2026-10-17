"""OpenCV grid rendering in image space and in the calibrated reference plane.

The image-space grid operates in source pixels only. The calibrated grid
projects reference-plane lines back into image coordinates through the inverse
homography so the overlay is perspective-correct.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import cv2
import numpy as np

from .exceptions import SPEValidationError
from .geometry import inverse_homography, transform_points, validate_homography


@dataclass(frozen=True)
class GridConfig:
    """Configuration for a regular image-space grid."""

    rows: int = 8
    columns: int = 12
    line_thickness: int = 1
    show_coordinates: bool = True
    line_color: tuple[int, int, int] = (91, 243, 168)


def _validate_config(config: GridConfig) -> None:
    if config.rows < 1 or config.columns < 1:
        raise SPEValidationError("Rows and columns must be at least 1.")
    if config.line_thickness < 1 or config.line_thickness > 12:
        raise SPEValidationError("Line thickness must be between 1 and 12.")
    if len(config.line_color) != 3 or any(not 0 <= value <= 255 for value in config.line_color):
        raise SPEValidationError("Line color must contain three values from 0 to 255.")


def generate_grid(image: np.ndarray, config: GridConfig | None = None) -> tuple[np.ndarray, dict]:
    """Draw a regular image-space grid on a copy of *image*."""
    if not isinstance(image, np.ndarray) or image.ndim not in (2, 3) or image.size == 0:
        raise SPEValidationError("A non-empty OpenCV image is required.")
    config = config or GridConfig()
    _validate_config(config)
    height, width = image.shape[:2]
    result = image.copy()
    color = tuple(int(value) for value in config.line_color)

    for column in range(config.columns + 1):
        x = min(round(column * width / config.columns), width - 1)
        cv2.line(result, (x, 0), (x, height - 1), color, config.line_thickness, cv2.LINE_AA)
    for row in range(config.rows + 1):
        y = min(round(row * height / config.rows), height - 1)
        cv2.line(result, (0, y), (width - 1, y), color, config.line_thickness, cv2.LINE_AA)

    if config.show_coordinates:
        for row in range(config.rows):
            for column in range(config.columns):
                x = round(column * width / config.columns) + 5
                y = round(row * height / config.rows) + 17
                cv2.putText(
                    result,
                    f"({column},{row})",
                    (min(x, width - 60), min(y, height - 5)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.38,
                    color,
                    1,
                    cv2.LINE_AA,
                )

    metadata = {
        "source": {"type": "image", "width": width, "height": height},
        "grid": {
            "rows": config.rows,
            "columns": config.columns,
            "cell_width": width / config.columns,
            "cell_height": height / config.rows,
            "coordinate_system": "image",
            "coordinate_convention": "top-left grid-cell coordinate (column, row)",
            "show_coordinates": config.show_coordinates,
            "line_thickness": config.line_thickness,
        },
        "status": "grid generated",
    }
    return result, metadata


def _sample_line(start: tuple[float, float], end: tuple[float, float], samples: int = 64) -> list:
    return np.linspace(start, end, samples, dtype=np.float32).tolist()


def generate_calibrated_grid(
    image: np.ndarray,
    homography: object,
    rows: int = 4,
    columns: int = 6,
    reference_width: float = 1000,
    reference_height: float = 600,
    source_points: Sequence[Sequence[float]] | None = None,
    show_grid: bool = True,
    show_roi: bool = True,
    line_color: tuple[int, int, int] = (91, 243, 168),
    roi_color: tuple[int, int, int] = (48, 59, 255),
    overlay_only: bool = False,
) -> tuple[np.ndarray, dict]:
    """Draw reference-plane grid lines projected back into image coordinates."""
    if not isinstance(image, np.ndarray) or image.ndim not in (2, 3) or image.size == 0:
        raise SPEValidationError("A non-empty OpenCV image is required.")
    if not isinstance(rows, int) or not isinstance(columns, int) or rows < 1 or columns < 1:
        raise SPEValidationError("Rows and columns must be positive integers.")
    if (
        not np.isfinite(reference_width)
        or not np.isfinite(reference_height)
        or reference_width <= 0
        or reference_height <= 0
    ):
        raise SPEValidationError("Reference dimensions must be positive finite numbers.")
    if len(line_color) != 3 or len(roi_color) != 3:
        raise SPEValidationError("Grid and ROI colors must contain three channels.")

    matrix = validate_homography(homography)
    height, width = image.shape[:2]
    result = np.zeros((*image.shape[:2], 4), dtype=np.uint8) if overlay_only else image.copy()
    inverse = inverse_homography(matrix)

    def draw_reference_line(points: list, color: tuple[int, int, int]) -> None:
        projected = np.asarray(transform_points(points, inverse), dtype=np.float32).reshape(
            -1, 1, 2
        )
        draw_color = (*color, 255) if overlay_only else color
        cv2.polylines(
            result, [np.round(projected).astype(np.int32)], False, draw_color, 2, cv2.LINE_AA
        )

    if show_grid:
        for row in range(rows + 1):
            y = row * reference_height / rows
            draw_reference_line(_sample_line((0, y), (reference_width, y)), line_color)
        for column in range(columns + 1):
            x = column * reference_width / columns
            draw_reference_line(_sample_line((x, 0), (x, reference_height)), line_color)

        if source_points is not None:
            boundary = np.asarray(source_points, dtype=np.float32).reshape(-1, 1, 2)
            if boundary.shape != (4, 1, 2) or not np.isfinite(boundary).all():
                raise SPEValidationError("Source points must contain four finite coordinate pairs.")
            draw_color = (*line_color, 255) if overlay_only else line_color
            cv2.polylines(
                result, [np.round(boundary).astype(np.int32)], True, draw_color, 2, cv2.LINE_AA
            )

    if show_roi:
        roi = source_points
        if roi is None:
            roi = transform_points(
                [
                    [0.0, 0.0],
                    [reference_width, 0.0],
                    [reference_width, reference_height],
                    [0.0, reference_height],
                ],
                inverse,
            )
        polygon = np.round(np.asarray(roi, dtype=np.float32)).astype(np.int32).reshape(-1, 1, 2)
        draw_color = (*roi_color, 255) if overlay_only else roi_color
        cv2.polylines(result, [polygon], True, draw_color, 3, cv2.LINE_AA)

    metadata = {
        "coordinate_system": "calibrated_reference_plane",
        "grid": {
            "rows": rows,
            "columns": columns,
            "cell_width": reference_width / columns,
            "cell_height": reference_height / rows,
            "width": reference_width,
            "height": reference_height,
            "show_grid": show_grid,
            "show_roi": show_roi,
            "overlay_only": overlay_only,
        },
        "source": {"width": width, "height": height},
        "status": "calibrated grid generated",
    }
    return result, metadata


__all__ = ["GridConfig", "generate_calibrated_grid", "generate_grid"]
