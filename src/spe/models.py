"""Typed value objects for the SPE SDK.

These dataclasses are lightweight wrappers over the engine's JSON contracts.
They provide attribute access, round-trip ``to_dict``/``from_dict`` conversion,
and a few convenience transforms, while remaining plain-data friendly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .exceptions import SPEValidationError
from .geometry import (
    POINT_ORDER,
    REFERENCE_HEIGHT,
    REFERENCE_WIDTH,
    calculate_calibration,
    transform_points,
)
from .spatial import spatial_point_to_grid_cell
from .zones import zone_for_cell


@dataclass(frozen=True)
class BoundingBox:
    """An axis-aligned box in source-pixel coordinates."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise SPEValidationError("Bounding box must be positive and non-negative.")

    @property
    def center(self) -> dict[str, float]:
        return {"x": self.x + self.width / 2, "y": self.y + self.height / 2}

    @property
    def foot_point(self) -> dict[str, float]:
        return {"x": self.x + self.width / 2, "y": self.y + self.height}

    def to_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> BoundingBox:
        return cls(
            x=float(data["x"]),
            y=float(data["y"]),
            width=float(data["width"]),
            height=float(data["height"]),
        )


@dataclass(frozen=True)
class Detection:
    """A single perception observation in source-pixel coordinates."""

    class_name: str
    bbox: BoundingBox
    confidence: float = 0.0
    id: str | None = None
    class_id: int | None = None
    track_id: str | None = None
    coordinate_system: str = "source_pixels"

    def __post_init__(self) -> None:
        if not str(self.class_name).strip():
            raise SPEValidationError("Detection class name is required.")
        if not 0 <= float(self.confidence) <= 1:
            raise SPEValidationError("Detection confidence must be between 0 and 1.")
        if self.coordinate_system != "source_pixels":
            raise SPEValidationError("Model detections must use 'source_pixels' coordinates.")

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "class_name": self.class_name,
            "confidence": self.confidence,
            "bbox": self.bbox.to_dict(),
            "center": self.bbox.center,
            "foot_point": self.bbox.foot_point,
            "coordinate_system": self.coordinate_system,
        }
        if self.id is not None:
            payload["id"] = self.id
        if self.class_id is not None:
            payload["class_id"] = self.class_id
        if self.track_id is not None:
            payload["track_id"] = self.track_id
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Detection:
        return cls(
            class_name=str(data.get("class_name") or data.get("label") or ""),
            bbox=BoundingBox.from_dict(data["bbox"]),
            confidence=float(data.get("confidence", 0.0)),
            id=data.get("id"),
            class_id=data.get("class_id"),
            track_id=data.get("track_id"),
            coordinate_system=data.get("coordinate_system", "source_pixels"),
        )


@dataclass
class ReferencePlane:
    """The normalized (or physical) calibration target plane."""

    width: float = REFERENCE_WIDTH
    height: float = REFERENCE_HEIGHT
    units: str = "normalized"

    def to_dict(self) -> dict[str, Any]:
        return {"width": float(self.width), "height": float(self.height), "units": self.units}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ReferencePlane:
        data = data or {}
        return cls(
            width=float(data.get("width", REFERENCE_WIDTH)),
            height=float(data.get("height", REFERENCE_HEIGHT)),
            units=str(data.get("units", "normalized")),
        )


@dataclass(frozen=True)
class GridCell:
    """A calibrated grid cell (zero-based row/column, ``(column, row)`` coordinate)."""

    row: int
    column: int

    @property
    def coordinate(self) -> list[int]:
        return [self.column, self.row]

    def to_dict(self) -> dict[str, Any]:
        return {"row": self.row, "column": self.column, "coordinate": self.coordinate}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GridCell:
        return cls(row=int(data["row"]), column=int(data["column"]))


@dataclass(frozen=True)
class Zone:
    """A semantic zone identifier derived from a grid cell."""

    id: str
    row: int
    column: int

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "row": self.row, "column": self.column}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Zone:
        return cls(id=str(data["id"]), row=int(data["row"]), column=int(data["column"]))


@dataclass
class Calibration:
    """A four-point planar calibration and its reusable transforms."""

    source_points: list[list[float]]
    homography: list[list[float]] | None
    inverse_homography: list[list[float]] | None
    reference_plane: ReferencePlane = field(default_factory=ReferencePlane)
    rows: int = 3
    columns: int = 3
    status: str = "calibrated"
    method: str = "manual_four_point"
    coordinate_system: str = "calibrated_reference_plane"
    point_order: Sequence[str] = POINT_ORDER
    destination_points: list[list[float]] = field(default_factory=list)
    reprojection_error: float = 0.0
    source_roi: dict[str, Any] = field(default_factory=dict)
    inlier_mask: list[int] = field(default_factory=list)
    transformation: dict[str, Any] = field(default_factory=dict)

    # -- constructors ------------------------------------------------------
    @classmethod
    def from_points(
        cls,
        source_points: Sequence[Sequence[float]],
        source_width: int,
        source_height: int,
        reference_plane: ReferencePlane | None = None,
        rows: int = 3,
        columns: int = 3,
    ) -> Calibration:
        plane = reference_plane or ReferencePlane()
        record = calculate_calibration(
            source_points,
            int(source_width),
            int(source_height),
            reference_width=plane.width,
            reference_height=plane.height,
            units=plane.units,
        )
        return cls.from_record(record, rows=rows, columns=columns)

    @classmethod
    def from_record(
        cls, record: Mapping[str, Any], rows: int | None = None, columns: int | None = None
    ) -> Calibration:
        plane = ReferencePlane.from_dict(record.get("reference_plane"))
        resolved_rows = (
            rows
            if rows is not None
            else int(record.get("calibrated_grid_rows", record.get("rows", 3)))
        )
        resolved_columns = (
            columns
            if columns is not None
            else int(record.get("calibrated_grid_columns", record.get("columns", 3)))
        )
        return cls(
            source_points=[list(point) for point in record.get("source_points", [])],
            homography=record.get("homography"),
            inverse_homography=record.get("inverse_homography"),
            reference_plane=plane,
            rows=resolved_rows,
            columns=resolved_columns,
            status=record.get("status", "calibrated"),
            method=record.get("method", "manual_four_point"),
            coordinate_system=record.get("coordinate_system", "calibrated_reference_plane"),
            point_order=record.get("point_order", POINT_ORDER),
            destination_points=[list(point) for point in record.get("destination_points", [])],
            reprojection_error=float(record.get("reprojection_error", 0.0)),
            source_roi=dict(record.get("source_roi", {})),
            inlier_mask=list(record.get("inlier_mask", [])),
            transformation=dict(record.get("transformation", {})),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Calibration:
        return cls.from_record(data)

    # -- serialization -----------------------------------------------------
    def to_dict(self, *, include_grid: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": self.status,
            "method": self.method,
            "coordinate_system": self.coordinate_system,
            "point_order": list(self.point_order),
            "source_points": [list(point) for point in self.source_points],
            "destination_points": [list(point) for point in self.destination_points],
            "reference_plane": self.reference_plane.to_dict(),
            "homography": self.homography,
            "inverse_homography": self.inverse_homography,
            "reprojection_error": self.reprojection_error,
            "source_roi": self.source_roi,
            "inlier_mask": self.inlier_mask,
            "transformation": self.transformation,
        }
        if include_grid:
            payload["calibrated_grid"] = {"rows": self.rows, "columns": self.columns}
        return payload

    # -- transforms --------------------------------------------------------
    def _require_matrix(self, name: str, matrix: list[list[float]] | None) -> list[list[float]]:
        if not matrix:
            raise SPEValidationError(
                f"Calibration has no {name}; it must be calculated or loaded before use."
            )
        return matrix

    def require_homography(self) -> list[list[float]]:
        """Return the source→reference homography or raise if absent."""
        return self._require_matrix("homography", self.homography)

    def require_inverse_homography(self) -> list[list[float]]:
        """Return the reference→source homography or raise if absent."""
        return self._require_matrix("inverse_homography", self.inverse_homography)

    def image_to_reference(self, points: Sequence[Sequence[float]]) -> list[list[float]]:
        """Map image-space points into the calibrated reference plane."""
        return transform_points(points, self.require_homography())

    def reference_to_image(self, points: Sequence[Sequence[float]]) -> list[list[float]]:
        """Map reference-plane points back into image space."""
        return transform_points(points, self.require_inverse_homography())

    def cell_for(self, reference_point: Sequence[float]) -> GridCell | None:
        """Return the grid cell containing a reference-plane point."""
        cell = spatial_point_to_grid_cell(
            reference_point,
            self.rows,
            self.columns,
            self.reference_plane.width,
            self.reference_plane.height,
        )
        return GridCell.from_dict(cell) if cell else None

    def zone_for(self, reference_point: Sequence[float]) -> str | None:
        """Return the semantic zone id for a reference-plane point."""
        cell = self.cell_for(reference_point)
        return zone_for_cell(cell.to_dict() if cell else None, self.rows, self.columns)


__all__ = [
    "BoundingBox",
    "Calibration",
    "Detection",
    "GridCell",
    "ReferencePlane",
    "Zone",
]
