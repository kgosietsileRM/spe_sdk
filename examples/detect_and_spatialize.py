"""Spatialize detections locally using the SPE SDK.

This example shows how to attach calibrated spatial data (reference position,
grid cell, and semantic zone) to provider-neutral detections, then inspect the
result. Run it from the project root::

    python examples/detect_and_spatialize.py
"""

from __future__ import annotations

from spe import SpatialEngine

SOURCE_WIDTH = 1280
SOURCE_HEIGHT = 720
SOURCE_POINTS = [[180, 120], [1090, 150], [1180, 640], [90, 660]]

DETECTIONS = [
    {
        "id": "det-001",
        "class_name": "person",
        "confidence": 0.91,
        "bbox": {"x": 560, "y": 300, "width": 70, "height": 180},
    },
    {
        "id": "det-002",
        "class_name": "forklift",
        "confidence": 0.78,
        "bbox": {"x": 820, "y": 360, "width": 160, "height": 120},
    },
    {
        "id": "det-003",
        "class_name": "box",
        "confidence": 0.64,
        "bbox": {"x": 40, "y": 40, "width": 30, "height": 30},
    },
]


def main() -> None:
    engine = SpatialEngine(
        grid_rows=4,
        grid_columns=6,
        source_dimensions={"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
    )
    engine.calibrate(SOURCE_POINTS, SOURCE_WIDTH, SOURCE_HEIGHT)

    result = engine.spatialize_result({"model": {"id": "model-a"}, "detections": DETECTIONS})

    for detection in result["detections"]:
        spatial = detection["spatial"]
        if spatial["status"] == "valid":
            position = spatial["position"]
            print(
                f"{detection['class_name']:<9} -> "
                f"reference=({position['x']:.1f}, {position['y']:.1f}) "
                f"cell={spatial['grid_cell']['coordinate']} zone={spatial['zone']}"
            )
        else:
            print(f"{detection['class_name']:<9} -> {spatial['status']} ({spatial.get('reason')})")


if __name__ == "__main__":
    main()
