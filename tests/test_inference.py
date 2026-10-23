"""Tests for source-space inference contexts."""

from __future__ import annotations

import pytest

from spe import InferenceContext, SPEValidationError, resolve_inference_context

SQUARE = [[100, 100], [300, 100], [300, 300], [100, 300]]


def test_whole_source_context_round_trip():
    context = InferenceContext.whole_source()
    assert context.to_dict() == {"scope": "whole_source", "coordinate_system": "source_pixels"}
    assert InferenceContext.from_dict(context.to_dict()) == context
    assert resolve_inference_context(None, 1000, 600)["scope"] == "whole_source"


def test_roi_context_round_trip_and_resolution():
    context = InferenceContext.region_of_interest(SQUARE)
    payload = context.to_dict()
    assert payload["scope"] == "roi"
    assert payload["roi"]["points"] == SQUARE
    assert InferenceContext.from_dict(payload) == context
    resolved = resolve_inference_context(context, 1000, 600)
    assert resolved["roi"]["points"] == SQUARE


def test_from_dict_accepts_points_without_roi_wrapper():
    context = InferenceContext.from_dict({"scope": "roi", "points": SQUARE})
    assert context.roi == tuple(tuple(point) for point in SQUARE)


@pytest.mark.parametrize(
    ("points", "message"),
    [
        ([[0, 0], [10, 0], [10, 10]], "four points"),
        ([[0, 0], [10, 0], [10, 10], [0, 10]], "inside the frame"),
        ([[0, 0], [10, 0], [10, 10], [0, -1]], "inside the frame"),
        ([[0, 0], [2, 0], [4, 0], [2, 0]], "non-degenerate"),
    ],
)
def test_roi_resolution_rejects_invalid_points(points, message):
    with pytest.raises(SPEValidationError, match=message):
        resolve_inference_context({"scope": "roi", "roi": {"points": points}}, 10, 10)


def test_resolution_rejects_invalid_scope_and_dimensions():
    with pytest.raises(SPEValidationError, match="scope"):
        resolve_inference_context({"scope": "everything"}, 100, 100)
    with pytest.raises(SPEValidationError, match="dimensions"):
        resolve_inference_context(None, 0, 100)


def test_roi_rejects_non_finite_and_malformed_points():
    with pytest.raises(SPEValidationError, match="finite"):
        resolve_inference_context(
            {"scope": "roi", "roi": {"points": [[0, 0], [1, 0], [1, 1], [0, float("nan")]]}},
            10,
            10,
        )
    with pytest.raises(SPEValidationError, match="two coordinates"):
        InferenceContext.region_of_interest([[0, 0, 0], [1, 0], [1, 1], [0, 1]])


def test_context_validation_errors():
    with pytest.raises(SPEValidationError, match="four points"):
        InferenceContext(scope="roi")
    with pytest.raises(SPEValidationError, match="four points"):
        InferenceContext(scope="roi", roi=((0.0, 0.0),))
    with pytest.raises(SPEValidationError, match="Whole-source"):
        InferenceContext(scope="whole_source", roi=((0.0, 0.0),))
    with pytest.raises(SPEValidationError, match=r"roi\.points"):
        InferenceContext.from_dict({"scope": "roi"})
