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

    @property
    def area(self) -> float:
        """Return the box area in squared source-pixel units."""
        return float(self.width * self.height)

    @property
    def x2(self) -> float:
        """Return the right edge coordinate."""
        return self.x + self.width

    @property
    def y2(self) -> float:
        """Return the bottom edge coordinate."""
        return self.y + self.height

    def as_xyxy(self) -> tuple[float, float, float, float]:
        """Return ``(x1, y1, x2, y2)`` bounds."""
        return (self.x, self.y, self.x2, self.y2)

    @classmethod
    def from_xyxy(cls, x1: float, y1: float, x2: float, y2: float) -> BoundingBox:
        """Build a box from top-left and bottom-right corners."""
        if float(x2) <= float(x1) or float(y2) <= float(y1):
            raise SPEValidationError("Bounding box x2/y2 must be greater than x1/y1.")
        return cls(
            x=float(x1), y=float(y1), width=float(x2) - float(x1), height=float(y2) - float(y1)
        )

    def intersection(self, other: BoundingBox) -> BoundingBox | None:
        """Return the overlapping box, or ``None`` when the boxes do not overlap."""
        left = max(self.x, other.x)
        top = max(self.y, other.y)
        right = min(self.x2, other.x2)
        bottom = min(self.y2, other.y2)
        if right <= left or bottom <= top:
            return None
        return BoundingBox(x=left, y=top, width=right - left, height=bottom - top)

    def iou(self, other: BoundingBox) -> float:
        """Return the intersection-over-union ratio in ``[0, 1]``."""
        overlap = self.intersection(other)
        intersection = overlap.area if overlap else 0.0
        union = self.area + other.area - intersection
        return intersection / union if union else 0.0

    def union(self, other: BoundingBox) -> BoundingBox:
        """Return the smallest box enclosing both boxes."""
        return BoundingBox.from_xyxy(
            min(self.x, other.x),
            min(self.y, other.y),
            max(self.x2, other.x2),
            max(self.y2, other.y2),
        )

    def contains(self, point: Mapping[str, Any] | Sequence[float], *, strict: bool = False) -> bool:
        """Return whether a point lies inside the box.

        Args:
            point: Mapping with ``x``/``y`` keys or a two-item ``(x, y)`` sequence.
            strict: When true, points on the border are excluded.
        """
        if isinstance(point, Mapping):
            x, y = float(point["x"]), float(point["y"])
        else:
            values = list(point)
            if len(values) != 2:
                raise SPEValidationError("Point must contain exactly two coordinates.")
            x, y = float(values[0]), float(values[1])
        if strict:
            return self.x < x < self.x2 and self.y < y < self.y2
        return self.x <= x <= self.x2 and self.y <= y <= self.y2

    def translate(self, dx: float, dy: float) -> BoundingBox:
        """Return a copy shifted by ``(dx, dy)`` pixels."""
        return BoundingBox(
            x=self.x + float(dx), y=self.y + float(dy), width=self.width, height=self.height
        )

    def scale(self, factor: float) -> BoundingBox:
        """Return a copy scaled about its center by ``factor``."""
        if float(factor) <= 0:
            raise SPEValidationError("Scale factor must be positive.")
        center = self.center
        width = self.width * float(factor)
        height = self.height * float(factor)
        return BoundingBox(
            x=center["x"] - width / 2,
            y=center["y"] - height / 2,
            width=width,
            height=height,
        )

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


@dataclass(frozen=True)
class ModelDescriptor:
    """Typed metadata for a registered perception model.

    Mirrors the engine's ``ModelDescriptor`` contract so callers can branch on
    capabilities (for example, whether a model supports temporal tracking)
    without inspecting raw JSON.
    """

    id: str
    name: str
    provider: str = ""
    version: str = ""
    description: str = ""
    capabilities: tuple[str, ...] = ("object_detection",)
    tracking_modes: tuple[str, ...] = ()
    status: str = "unavailable"
    reason: str | None = None

    def __post_init__(self) -> None:
        if not str(self.id).strip():
            raise SPEValidationError("Model id is required.")
        if not str(self.name).strip() or not str(self.provider).strip():
            raise SPEValidationError("Model name and provider are required.")
        if self.status not in {"registered", "available", "unavailable", "error"}:
            raise SPEValidationError(f"Unsupported model status: {self.status}")

    @property
    def supports_tracking(self) -> bool:
        """Return whether the model advertises any temporal tracking mode."""
        return bool(self.tracking_modes) or "tracking" in self.capabilities

    def supports(self, capability: str) -> bool:
        """Return whether *capability* is advertised by the model."""
        return capability in self.capabilities

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "provider": self.provider,
            "version": self.version,
            "description": self.description,
            "capabilities": list(self.capabilities),
            "tracking_modes": list(self.tracking_modes),
            "status": self.status,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModelDescriptor:
        return cls(
            id=str(data["id"]),
            name=str(data.get("name", data["id"])),
            provider=str(data.get("provider") or "unknown"),
            version=str(data.get("version", "")),
            description=str(data.get("description", "")),
            capabilities=tuple(
                str(item) for item in data.get("capabilities") or ("object_detection",)
            ),
            tracking_modes=tuple(str(item) for item in data.get("tracking_modes") or ()),
            status=str(data.get("status", "unavailable")),
            reason=data.get("reason"),
        )


__all__ = [
    "BoundingBox",
    "Calibration",
    "Detection",
    "GridCell",
    "ModelDescriptor",
    "ReferencePlane",
    "Zone",
]
