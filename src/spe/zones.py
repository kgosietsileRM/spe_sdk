"""Deterministic semantic zones derived from calibrated grid dimensions.

Zones are stable, human-readable identifiers (``A1``, ``B3``, ... ) produced by
combining a spreadsheet-style row label with a one-based column number.
"""

from __future__ import annotations

from .exceptions import SPEValidationError


def row_label(index: int) -> str:
    """Return a spreadsheet-style row label: ``A..Z, AA, AB, ...``."""
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        raise SPEValidationError("Zone row must be a non-negative integer.")
    value = index + 1
    label = ""
    while value:
        value, remainder = divmod(value - 1, 26)
        label = chr(65 + remainder) + label
    return label


def generate_zones(rows: int, columns: int) -> list[dict]:
    """Return every zone for a ``rows x columns`` grid in row-major order."""
    if not isinstance(rows, int) or not isinstance(columns, int) or rows < 1 or columns < 1:
        raise SPEValidationError("Calibrated grid rows and columns must be positive integers.")
    return [
        {"id": f"{row_label(row)}{column + 1}", "row": row, "column": column}
        for row in range(rows)
        for column in range(columns)
    ]


def zone_for_cell(cell: dict | None, rows: int, columns: int) -> str | None:
    """Return the zone id for a grid cell dict, or ``None`` when unknown."""
    if not cell:
        return None
    zones = generate_zones(rows, columns)
    row = cell.get("row")
    column = cell.get("column")
    return next(
        (zone["id"] for zone in zones if zone["row"] == row and zone["column"] == column),
        None,
    )


__all__ = ["generate_zones", "row_label", "zone_for_cell"]
