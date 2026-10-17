"""Warehouse bay occupancy from a calibrated camera.

Calibrates a warehouse floor to a 5 x 8 bay grid, maps detected pallets to
bays, and prints an occupancy map, the list of empty bays, and a fill ratio.
Runs in-process with no server required.

Run from the project root::

    python examples/warehouse_grid_inventory.py
"""

from __future__ import annotations

from collections import defaultdict

from spe import SpatialEngine, row_label

SOURCE_WIDTH = 1280
SOURCE_HEIGHT = 720
SOURCE_POINTS = [[180, 120], [1090, 150], [1180, 640], [90, 660]]
BAY_ROWS = 5
BAY_COLUMNS = 8


def pallet(identifier: str, foot_x: float, foot_y: float) -> dict:
    """Build a pallet detection whose base is at ``(foot_x, foot_y)``."""
    width, height = 120.0, 90.0
    return {
        "id": identifier,
        "class_name": "pallet",
        "confidence": 0.85,
        "bbox": {
            "x": foot_x - width / 2,
            "y": foot_y - height,
            "width": width,
            "height": height,
        },
    }


PALLETS = [
    pallet("plt-01", 300, 300),
    pallet("plt-02", 420, 300),
    pallet("plt-03", 300, 480),
    pallet("plt-04", 660, 320),
    pallet("plt-05", 900, 300),
    pallet("plt-06", 1000, 470),
    pallet("plt-07", 540, 520),
]


def main() -> None:
    engine = SpatialEngine(
        grid_rows=BAY_ROWS,
        grid_columns=BAY_COLUMNS,
        source_dimensions={"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
    )
    engine.calibrate(SOURCE_POINTS, SOURCE_WIDTH, SOURCE_HEIGHT)

    bays: dict[str, list[str]] = defaultdict(list)
    for detection in engine.spatialize_result({"detections": PALLETS})["detections"]:
        spatial = detection["spatial"]
        if spatial["status"] == "valid":
            bays[spatial["zone"]].append(detection["id"])

    all_zones = [
        f"{row_label(row)}{column + 1}" for row in range(BAY_ROWS) for column in range(BAY_COLUMNS)
    ]

    print(f"warehouse bays: {BAY_ROWS} rows x {BAY_COLUMNS} columns\n")
    print("     " + "".join(f"{column + 1:>4}" for column in range(BAY_COLUMNS)))
    for row in range(BAY_ROWS):
        cells = []
        for column in range(BAY_COLUMNS):
            zone = f"{row_label(row)}{column + 1}"
            cells.append(f"{'##' if bays.get(zone) else '..':>4}")
        print(f"  {row_label(row)}  " + "".join(cells))

    occupied = [zone for zone in all_zones if bays.get(zone)]
    empty = [zone for zone in all_zones if not bays.get(zone)]
    fill = len(occupied) / len(all_zones) * 100

    print(f"\noccupied bays ({len(occupied)}): {', '.join(occupied)}")
    print(f"empty bays ({len(empty)}): {', '.join(empty)}")
    print(f"fill ratio: {fill:.0f}%")
    for zone in occupied:
        print(f"  {zone}: {', '.join(bays[zone])}")


if __name__ == "__main__":
    main()
