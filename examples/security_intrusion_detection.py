"""Restricted-area intrusion detection on a calibrated camera.

Defines a restricted polygon (for example a fenced loading bay) inside the
calibrated region and raises an alert whenever a person's ground point falls
inside it. Every detection is also mapped to its calibrated grid zone. Runs
in-process with no server required.

Run from the project root::

    python examples/security_intrusion_detection.py
"""

from __future__ import annotations

from spe import SpatialEngine, point_in_roi

SOURCE_WIDTH = 1280
SOURCE_HEIGHT = 720
SOURCE_POINTS = [[180, 120], [1090, 150], [1180, 640], [90, 660]]
# A fenced loading bay in the top-right of the calibrated region (TL, TR, BR, BL).
RESTRICTED_ZONE = [[780, 230], [1060, 250], [1080, 560], [800, 590]]

GRID_ROWS = 4
GRID_COLUMNS = 6


def person(identifier: str, foot_x: float, foot_y: float, confidence: float = 0.9) -> dict:
    """Build a person detection whose feet are at ``(foot_x, foot_y)``."""
    width, height = 62.0, 168.0
    return {
        "id": identifier,
        "class_name": "person",
        "confidence": confidence,
        "bbox": {
            "x": foot_x - width / 2,
            "y": foot_y - height,
            "width": width,
            "height": height,
        },
    }


FRAME = [
    person("staff-1", 300, 500),
    person("staff-2", 520, 430),
    person("visitor-1", 640, 360),
    person("intruder-1", 930, 430, confidence=0.72),
    person("intruder-2", 1000, 520, confidence=0.66),
]


def main() -> None:
    engine = SpatialEngine(
        grid_rows=GRID_ROWS,
        grid_columns=GRID_COLUMNS,
        source_dimensions={"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
    )
    engine.calibrate(SOURCE_POINTS, SOURCE_WIDTH, SOURCE_HEIGHT)

    result = engine.spatialize_result({"detections": FRAME})

    print("restricted-area monitor\n")
    alerts = 0
    for detection in result["detections"]:
        spatial = detection["spatial"]
        ground = spatial["ground_point"]
        inside = point_in_roi([ground["x"], ground["y"]], RESTRICTED_ZONE)
        zone = spatial["zone"] if spatial["status"] == "valid" else "-"
        if inside:
            alerts += 1
            print(
                f"  ALERT  {detection['id']:<11} zone={zone} "
                f"conf={detection['confidence']:.2f} "
                f"ground=({ground['x']:.0f}, {ground['y']:.0f})"
            )
        else:
            print(f"  ok     {detection['id']:<11} zone={zone}")

    print(f"\n{alerts} intrusion alert(s) in this frame")
    print(f"restricted area polygon: {RESTRICTED_ZONE}")


if __name__ == "__main__":
    main()
