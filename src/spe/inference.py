"""Source-space inference context for model providers.

The engine can restrict detection to the whole source frame or to a
four-point ROI. ``InferenceContext`` is the typed form of that contract and
:func:`resolve_inference_context` validates it against the frame dimensions,
mirroring the server's own checks.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .exceptions import SPEValidationError

_SCOPES = frozenset({"whole_source", "roi"})


def _point(value: Sequence[float]) -> tuple[float, float]:
    if len(value) != 2:
        raise SPEValidationError("Each ROI point must contain exactly two coordinates.")
    x, y = float(value[0]), float(value[1])
    if not math.isfinite(x) or not math.isfinite(y):
        raise SPEValidationError("ROI points must be finite numbers.")
    return x, y


def _polygon_area(points: Sequence[tuple[float, float]]) -> float:
    total = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


@dataclass(frozen=True)
class InferenceContext:
    """A validated source-space inference scope."""

    scope: str = "whole_source"
    roi: tuple[tuple[float, float], ...] | None = None

    def __post_init__(self) -> None:
        if self.scope not in _SCOPES:
            raise SPEValidationError("Inference scope must be whole_source or roi.")
        if self.scope == "roi":
            if self.roi is None or len(self.roi) != 4:
                raise SPEValidationError("ROI inference requires exactly four points.")
        elif self.roi is not None:
            raise SPEValidationError("Whole-source inference does not accept an ROI.")

    @classmethod
    def whole_source(cls) -> InferenceContext:
        """Return the default whole-frame context."""
        return cls(scope="whole_source")

    @classmethod
    def region_of_interest(cls, points: Sequence[Sequence[float]]) -> InferenceContext:
        """Return a four-point ROI context (TL, TR, BR, BL)."""
        if len(points) != 4:
            raise SPEValidationError("ROI inference requires exactly four points.")
        return cls(scope="roi", roi=tuple(_point(point) for point in points))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> InferenceContext:
        """Build a context from the engine's JSON shape."""
        data = data or {}
        scope = str(data.get("scope", "whole_source"))
        if scope not in _SCOPES:
            raise SPEValidationError("Inference scope must be whole_source or roi.")
        if scope == "whole_source":
            return cls.whole_source()
        points = (data.get("roi") or {}).get("points") or data.get("points")
        if not points:
            raise SPEValidationError("ROI inference requires a 'roi.points' list.")
        return cls.region_of_interest(points)

    def to_dict(self) -> dict[str, Any]:
        """Return the engine-compatible inference context payload."""
        if self.scope == "whole_source":
            return {"scope": "whole_source", "coordinate_system": "source_pixels"}
        return {
            "scope": "roi",
            "coordinate_system": "source_pixels",
            "roi": {"points": [[x, y] for x, y in self.roi or ()]},
        }


def resolve_inference_context(
    context: Mapping[str, Any] | InferenceContext | None,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Validate and normalize an inference context for a ``width x height`` frame.

    Args:
        context: A mapping, an :class:`InferenceContext`, or ``None`` for the
            whole source.
        width: Frame width in pixels.
        height: Frame height in pixels.

    Raises:
        SPEValidationError: If the scope is unsupported or the ROI is not four
            finite, in-frame, non-degenerate points.
    """
    width = int(width)
    height = int(height)
    if width < 1 or height < 1:
        raise SPEValidationError("Frame dimensions must be positive integers.")
    resolved = (
        context if isinstance(context, InferenceContext) else InferenceContext.from_dict(context)
    )
    payload = resolved.to_dict()
    if resolved.scope == "whole_source":
        return payload
    points = resolved.roi or ()
    if any(x < 0 or y < 0 or x >= width or y >= height for x, y in points):
        raise SPEValidationError("ROI inference requires four points inside the frame.")
    if _polygon_area(list(points)) < 1:
        raise SPEValidationError("ROI points must enclose a non-degenerate area.")
    return payload


__all__ = ["InferenceContext", "resolve_inference_context"]
