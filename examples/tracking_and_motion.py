"""Track people across frames and estimate motion on a calibrated plane.

Combines the local :class:`SpatialEngine` (calibration and spatialization), the
:class:`ModelAgnosticTracker` (stable identities), and the
:class:`SpatialTrackStateManager` (trajectory, velocity, and prediction). Runs
fully in-process with no server or model required.

Run from the project root::

    python examples/tracking_and_motion.py
"""

from __future__ import annotations

from spe import ModelAgnosticTracker, SpatialEngine, SpatialTrackStateManager

SOURCE_WIDTH = 1280
SOURCE_HEIGHT = 720
SOURCE_POINTS = [[180, 120], [1090, 150], [1180, 640], [90, 660]]
GRID_ROWS = 4
GRID_COLUMNS = 6
FPS = 5.0


def person(identifier: str, foot_x: float, foot_y: float) -> dict:
    """Build a person detection whose feet are at ``(foot_x, foot_y)``."""
    width, height = 64.0, 170.0
    return {
        "id": identifier,
        "class_id": 0,
        "class_name": "person",
        "confidence": 0.9,
        "bbox": {
            "x": foot_x - width / 2,
            "y": foot_y - height,
            "width": width,
            "height": height,
        },
        "coordinate_system": "source_pixels",
    }


# One shopper walks steadily right; another mostly stands still.
FRAMES = [
    [person("a", 400, 500), person("b", 800, 420)],
    [person("a", 460, 500), person("b", 800, 420)],
    [person("a", 520, 495), person("b", 805, 422)],
    [person("a", 580, 490), person("b", 810, 424)],
    [person("a", 640, 485), person("b", 815, 426)],
]


def main() -> None:
    engine = SpatialEngine(
        grid_rows=GRID_ROWS,
        grid_columns=GRID_COLUMNS,
        source_dimensions={"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
    )
    engine.calibrate(SOURCE_POINTS, SOURCE_WIDTH, SOURCE_HEIGHT)

    tracker = ModelAgnosticTracker()
    motion = SpatialTrackStateManager()

    print(f"{'t(s)':>4}  {'track':<8}{'zone':>5}{'speed':>9}{'predicted (x, y)':>20}")
    print("-" * 48)
    for index, frame in enumerate(FRAMES):
        timestamp = index / FPS
        spatialized = engine.spatialize_result({"detections": frame})["detections"]
        tracked = tracker.update(spatialized, timestamp)["detections"]
        state = motion.update(tracked, timestamp, prediction_enabled=True)
        tracks = {track["track_id"]: track for track in state["tracks"]}

        for detection in tracked:
            track_id = detection.get("track_id")
            spatial = detection["spatial"]
            track = tracks.get(track_id, {})
            velocity = track.get("motion", {}).get("velocity", {})
            prediction = track.get("prediction", {})
            speed = f"{velocity['speed']:.1f}" if velocity.get("status") == "valid" else "-"
            predicted = (
                f"({prediction['x']:.0f}, {prediction['y']:.0f})"
                if prediction.get("status") == "valid"
                else "-"
            )
            zone = spatial.get("zone") or "-"
            print(f"{timestamp:>4.1f}  {track_id!s:<8}{zone:>5}{speed:>9}{predicted:>20}")

    print("\ntracker diagnostics:", tracker.snapshot())
    print("speed units: normalized reference-plane units per second")


if __name__ == "__main__":
    main()
