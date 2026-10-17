"""High-level, stateful local facade for the Spatial Intelligence Engine.

``SpatialEngine`` bundles a calibration, an optional calibrated grid and source
dimensions, then exposes ergonomic operations for calibration, coordinate
inspection, grid rendering and detection spatialization. It runs entirely in
process with no server required.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from .exceptions import SPEEngineError, SPEValidationError
from .geometry import calculate_calibration
from .grid import GridConfig, generate_calibrated_grid, generate_grid
from .models import Calibration, GridCell, ReferencePlane, Zone
from .spatial import (
    image_to_spatial,
    inspect_point,
    spatialize_detection,
    spatialize_detection_result,
)
from .zones import generate_zones


class SpatialEngine:
    """A stateful local engine for calibrated spatial queries."""

    def __init__(
        self,
        *,
        calibration: Calibration | Mapping[str, Any] | None = None,
        grid_rows: int = 3,
        grid_columns: int = 3,
        source_dimensions: Mapping[str, Any] | None = None,
    ) -> None:
        self.grid_rows = int(grid_rows)
        self.grid_columns = int(grid_columns)
        self.source_dimensions = dict(source_dimensions) if source_dimensions else None
        self.calibration: Calibration | None = None
        if calibration is not None:
            self.calibration = (
                calibration
                if isinstance(calibration, Calibration)
                else Calibration.from_dict(calibration)
            )
            self.grid_rows = self.calibration.rows
            self.grid_columns = self.calibration.columns

    # -- calibration -------------------------------------------------------
    def calibrate(
        self,
        source_points: Sequence[Sequence[float]],
        source_width: int,
        source_height: int,
        *,
        reference_plane: ReferencePlane | None = None,
        rows: int | None = None,
        columns: int | None = None,
    ) -> Calibration:
        """Validate four points and install a reusable calibration."""
        plane = reference_plane or ReferencePlane()
        resolved_rows = int(rows) if rows is not None else self.grid_rows
        resolved_columns = int(columns) if columns is not None else self.grid_columns
        if resolved_rows < 1 or resolved_columns < 1:
            raise SPEValidationError("Calibrated grid rows and columns must be positive integers.")
        record = calculate_calibration(
            source_points,
            int(source_width),
            int(source_height),
            reference_width=plane.width,
            reference_height=plane.height,
            units=plane.units,
        )
        record["calibrated_grid_rows"] = resolved_rows
        record["calibrated_grid_columns"] = resolved_columns
        self.grid_rows = resolved_rows
        self.grid_columns = resolved_columns
        self.source_dimensions = {"width": int(source_width), "height": int(source_height)}
        self.calibration = Calibration.from_record(
            record, rows=resolved_rows, columns=resolved_columns
        )
        return self.calibration

    def load_calibration(self, data: Calibration | Mapping[str, Any]) -> Calibration:
        """Install a previously serialized calibration."""
        self.calibration = data if isinstance(data, Calibration) else Calibration.from_dict(data)
        self.grid_rows = self.calibration.rows
        self.grid_columns = self.calibration.columns
        return self.calibration

    def clear_calibration(self) -> None:
        self.calibration = None

    @property
    def is_calibrated(self) -> bool:
        return self.calibration is not None and bool(self.calibration.homography)

    def _require_calibration(self) -> Calibration:
        if not self.is_calibrated:
            raise SPEEngineError("The engine is not calibrated.")
        return self.calibration  # type: ignore[return-value]

    # -- transforms --------------------------------------------------------
    def image_to_reference(self, points: Sequence[Sequence[float]]) -> list[list[float]]:
        """Map image-space points into the calibrated reference plane."""
        return self._require_calibration().image_to_reference(points)

    def reference_to_image(self, points: Sequence[Sequence[float]]) -> list[list[float]]:
        """Map reference-plane points back into image space."""
        return self._require_calibration().reference_to_image(points)

    def cell_for_reference_point(self, reference_point: Sequence[float]) -> GridCell | None:
        """Return the grid cell containing a reference-plane point."""
        return self._require_calibration().cell_for(reference_point)

    def zone_for_reference_point(self, reference_point: Sequence[float]) -> str | None:
        """Return the semantic zone id for a reference-plane point."""
        return self._require_calibration().zone_for(reference_point)

    def zone_for_image_point(self, image_point: Sequence[float]) -> str | None:
        """Return the semantic zone id for an image-space point."""
        mapped = image_to_spatial(image_point, self._require_calibration().to_dict())
        return self._require_calibration().zone_for([mapped["x"], mapped["y"]])

    def cell_for_image_point(self, image_point: Sequence[float]) -> GridCell | None:
        """Return the grid cell for an image-space point."""
        mapped = image_to_spatial(image_point, self._require_calibration().to_dict())
        return self._require_calibration().cell_for([mapped["x"], mapped["y"]])

    def zones(self) -> list[Zone]:
        """Return every zone for the configured calibrated grid."""
        return [Zone.from_dict(zone) for zone in generate_zones(self.grid_rows, self.grid_columns)]

    # -- inspection --------------------------------------------------------
    def spatial_state(self) -> dict[str, Any]:
        """Return the canonical state contract consumed by :func:`inspect_point`."""
        calibration = self._require_calibration().to_dict()
        state: dict[str, Any] = {
            "calibration": calibration,
            "grid": {"rows": self.grid_rows, "columns": self.grid_columns},
        }
        if self.source_dimensions:
            state["source_dimensions"] = dict(self.source_dimensions)
        return state

    def inspect(self, image_point: Sequence[float]) -> dict[str, Any]:
        """Inspect a single image-space point against the installed state."""
        return inspect_point(image_point, self.spatial_state())

    # -- spatialization ----------------------------------------------------
    def spatialize_detection(self, detection: Mapping[str, Any]) -> dict[str, Any]:
        """Add calibrated spatial data to one detection mapping."""
        calibration = self._require_calibration().to_dict()
        grid = {"rows": self.grid_rows, "columns": self.grid_columns}
        return spatialize_detection(detection, calibration, grid=grid)

    def spatialize_result(self, result: Mapping[str, Any]) -> dict[str, Any]:
        """Add calibrated spatial data to a normalized detection result."""
        calibration = self._require_calibration().to_dict()
        grid = {"rows": self.grid_rows, "columns": self.grid_columns}
        return spatialize_detection_result(result, calibration, grid=grid)

    def spatialize(self, detections: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
        """Spatialize a sequence of detection mappings."""
        return [self.spatialize_detection(detection) for detection in detections]

    # -- rendering ---------------------------------------------------------
    def render_grid(
        self,
        image: np.ndarray,
        *,
        rows: int = 8,
        columns: int = 12,
        line_thickness: int = 1,
        line_color: tuple[int, int, int] = (91, 243, 168),
        show_coordinates: bool = True,
    ) -> tuple[np.ndarray, dict]:
        """Draw an image-space grid on a copy of *image*."""
        config = GridConfig(
            rows=rows,
            columns=columns,
            line_thickness=line_thickness,
            line_color=line_color,
            show_coordinates=show_coordinates,
        )
        return generate_grid(image, config)

    def render_calibrated_grid(
        self,
        image: np.ndarray,
        *,
        show_grid: bool = True,
        show_roi: bool = True,
        line_color: tuple[int, int, int] = (91, 243, 168),
        roi_color: tuple[int, int, int] = (48, 59, 255),
        overlay_only: bool = False,
    ) -> tuple[np.ndarray, dict]:
        """Render the calibrated grid, projected back into image space."""
        calibration = self._require_calibration()
        return generate_calibrated_grid(
            image,
            calibration.require_homography(),
            rows=calibration.rows,
            columns=calibration.columns,
            reference_width=calibration.reference_plane.width,
            reference_height=calibration.reference_plane.height,
            source_points=calibration.source_points,
            show_grid=show_grid,
            show_roi=show_roi,
            line_color=line_color,
            roi_color=roi_color,
            overlay_only=overlay_only,
        )

    # -- persistence -------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "grid_rows": self.grid_rows,
            "grid_columns": self.grid_columns,
            "source_dimensions": self.source_dimensions,
            "calibration": self.calibration.to_dict() if self.calibration else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SpatialEngine:
        calibration = data.get("calibration")
        engine = cls(
            grid_rows=int(data.get("grid_rows", 3)),
            grid_columns=int(data.get("grid_columns", 3)),
            source_dimensions=data.get("source_dimensions"),
        )
        if calibration:
            engine.calibration = Calibration.from_dict(calibration)
            engine.grid_rows = int(data.get("grid_rows", engine.calibration.rows))
            engine.grid_columns = int(data.get("grid_columns", engine.calibration.columns))
        return engine


__all__ = ["SpatialEngine"]
