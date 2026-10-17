"""Traffic lane analytics with a metric reference plane.

Calibrates a road segment to a metric reference plane (30 m x 8 m) split into
three lanes, then estimates each vehicle's lane and speed from two frames
sampled a known interval apart. Runs in-process with no server required.

Run from the project root::

    python examples/traffic_lane_speed.py
"""

from __future__ import annotations

from spe import ReferencePlane, SpatialEngine

SOURCE_WIDTH = 1280
SOURCE_HEIGHT = 720
SOURCE_POINTS = [[260, 260], [1040, 260], [1240, 700], [40, 700]]

LANES = 3
ROAD_WIDTH_M = 30.0
ROAD_LENGTH_M = 8.0
FRAME_INTERVAL_S = 0.5


def vehicle(identifier: str, foot_x: float, foot_y: float) -> dict:
    """Build a car detection whose wheels touch ``(foot_x, foot_y)``."""
    width, height = 150.0, 110.0
    return {
        "id": identifier,
        "class_name": "car",
        "confidence": 0.88,
        "bbox": {
            "x": foot_x - width / 2,
            "y": foot_y - height,
            "width": width,
            "height": height,
        },
    }


FRAME_A = [vehicle("car-1", 420, 420), vehicle("car-2", 780, 380)]
FRAME_B = [vehicle("car-1", 520, 420), vehicle("car-2", 860, 380)]


def _positions(
    engine: SpatialEngine, frame: list[dict]
) -> dict[str, tuple[float, float, str | None]]:
    """Map each detection to ``(x_metres, y_metres, lane)`` on the road plane."""
    positions: dict[str, tuple[float, float, str | None]] = {}
    for detection in frame:
        bbox = detection["bbox"]
        foot = [
            bbox["x"] + bbox["width"] / 2,
            bbox["y"] + bbox["height"],
        ]
        x_metres, y_metres = engine.image_to_reference(foot)[0]
        lane = engine.zone_for_image_point(foot)
        positions[detection["id"]] = (x_metres, y_metres, lane)
    return positions


def main() -> None:
    plane = ReferencePlane(width=ROAD_WIDTH_M, height=ROAD_LENGTH_M, units="meters")
    engine = SpatialEngine(grid_rows=1, grid_columns=LANES)
    engine.calibrate(
        SOURCE_POINTS,
        SOURCE_WIDTH,
        SOURCE_HEIGHT,
        reference_plane=plane,
        rows=1,
        columns=LANES,
    )

    frame_a = _positions(engine, FRAME_A)
    frame_b = _positions(engine, FRAME_B)

    print(
        f"road plane {ROAD_WIDTH_M:g} m x {ROAD_LENGTH_M:g} m, "
        f"{LANES} lanes, interval {FRAME_INTERVAL_S:g}s\n"
    )
    print(f"{'vehicle':<9}{'lane':>6}{'moved(m)':>10}{'speed(km/h)':>13}")
    print("-" * 38)
    for identifier, (x_a, y_a, lane) in frame_a.items():
        x_b, y_b, _ = frame_b[identifier]
        distance = ((x_b - x_a) ** 2 + (y_b - y_a) ** 2) ** 0.5
        speed = distance / FRAME_INTERVAL_S * 3.6
        print(f"{identifier:<9}{lane or '-':>6}{distance:>10.1f}{speed:>13.1f}")

    state = engine.spatial_state()
    print(f"\nreference units: {state['calibration']['reference_plane']['units']}")
    print(f"zones: {', '.join(zone.id for zone in engine.zones())}")


if __name__ == "__main__":
    main()
