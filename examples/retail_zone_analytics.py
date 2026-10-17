"""Retail floor analytics: per-zone occupancy and dwell from camera frames.

This example simulates a short burst of frames from an overhead store camera.
Each shopper detection is spatialized onto a calibrated 1000 x 600 floor plan
and assigned to a grid zone, then the script reports per-zone occupancy, unique
visitors, dwell time, and an ASCII floor map. Everything runs in-process with no
server required.

Run from the project root::

    python examples/retail_zone_analytics.py
"""

from __future__ import annotations

from collections import defaultdict

from spe import SpatialEngine, row_label

SOURCE_WIDTH = 1280
SOURCE_HEIGHT = 720
# Four image points (TL, TR, BR, BL) outlining the camera's visible floor.
SOURCE_POINTS = [[180, 120], [1090, 150], [1180, 640], [90, 660]]

GRID_ROWS = 4
GRID_COLUMNS = 6
FPS = 2.0


def shopper(identifier: str, foot_x: float, foot_y: float) -> dict:
    """Build a person detection whose feet are at ``(foot_x, foot_y)``."""
    width, height = 64.0, 170.0
    return {
        "id": identifier,
        "class_name": "person",
        "confidence": 0.9,
        "bbox": {
            "x": foot_x - width / 2,
            "y": foot_y - height,
            "width": width,
            "height": height,
        },
    }


# Shoppers move through the aisle; six frames sampled at 2 fps.
FRAMES: list[list[dict]] = [
    [shopper("shopper-1", 620, 420), shopper("shopper-2", 330, 520)],
    [
        shopper("shopper-1", 660, 410),
        shopper("shopper-2", 370, 505),
        shopper("shopper-3", 980, 430),
    ],
    [
        shopper("shopper-1", 720, 390),
        shopper("shopper-2", 410, 500),
        shopper("shopper-3", 1010, 440),
    ],
    [shopper("shopper-1", 790, 380), shopper("shopper-3", 1015, 445)],
    [shopper("shopper-1", 860, 385), shopper("shopper-4", 540, 330)],
    [shopper("shopper-1", 940, 400), shopper("shopper-4", 560, 340)],
]


def main() -> None:
    engine = SpatialEngine(
        grid_rows=GRID_ROWS,
        grid_columns=GRID_COLUMNS,
        source_dimensions={"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
    )
    engine.calibrate(SOURCE_POINTS, SOURCE_WIDTH, SOURCE_HEIGHT)

    occupancy: dict[str, int] = defaultdict(int)
    visitors: dict[str, set[str]] = defaultdict(set)
    dwell: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for frame in FRAMES:
        result = engine.spatialize_result({"detections": frame})
        for detection in result["detections"]:
            spatial = detection["spatial"]
            if spatial["status"] != "valid":
                continue
            zone = spatial["zone"]
            occupancy[zone] += 1
            visitors[zone].add(detection["id"])
            dwell[detection["id"]][zone] += 1

    print(f"sampled {len(FRAMES)} frames at {FPS:g} fps\n")
    print(f"{'zone':<6}{'visits':>8}{'visitors':>10}{'dwell(s)':>10}")
    print("-" * 34)
    for zone in sorted(occupancy):
        print(
            f"{zone:<6}{occupancy[zone]:>8}{len(visitors[zone]):>10}{occupancy[zone] / FPS:>10.1f}"
        )

    print("\nfloor map (person-frames per zone):")
    for row in range(GRID_ROWS):
        cells = []
        for column in range(GRID_COLUMNS):
            zone = f"{row_label(row)}{column + 1}"
            count = occupancy.get(zone, 0)
            cells.append(f"{zone}:{count:>2}" if count else f"{zone}: .")
        print("  " + "  ".join(cells))

    print("\ntracked dwell per shopper:")
    for identifier in sorted(dwell):
        track = dwell[identifier]
        total = sum(track.values()) / FPS
        path = " -> ".join(f"{zone}({frames / FPS:.1f}s)" for zone, frames in track.items())
        print(f"  {identifier}: {total:.1f}s total, {path}")


if __name__ == "__main__":
    main()
