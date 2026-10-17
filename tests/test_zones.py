"""Focused tests for deterministic zone generation."""

from __future__ import annotations

import pytest

from spe import SPEValidationError, generate_zones, row_label, zone_for_cell


def test_row_label_sequences():
    assert row_label(0) == "A"
    assert row_label(25) == "Z"
    assert row_label(26) == "AA"
    assert row_label(51) == "AZ"
    assert row_label(52) == "BA"


def test_row_label_rejects_invalid():
    with pytest.raises(SPEValidationError):
        row_label(-1)
    with pytest.raises(SPEValidationError):
        row_label(True)


def test_generate_zones_row_major():
    zones = generate_zones(2, 3)
    assert [zone["id"] for zone in zones] == ["A1", "A2", "A3", "B1", "B2", "B3"]
    assert zones[0] == {"id": "A1", "row": 0, "column": 0}


def test_generate_zones_validates_dimensions():
    with pytest.raises(SPEValidationError):
        generate_zones(0, 3)
    with pytest.raises(SPEValidationError):
        generate_zones(3, -1)


def test_zone_for_cell_lookup():
    assert zone_for_cell({"row": 1, "column": 2}, 3, 3) == "B3"
    assert zone_for_cell(None, 3, 3) is None
    assert zone_for_cell({"row": 9, "column": 9}, 3, 3) is None
