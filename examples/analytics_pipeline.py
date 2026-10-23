"""Track objects across frames and summarize zone, motion, and line events.

Run with ``python examples/analytics_pipeline.py``. The script uses synthetic
detections only, so it needs no model, video file, or running server.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from spe import (
    InferenceContext,
    LineCrossingCounter,
    ModelAgnosticTracker,
    ObservationBatchWriter,
    SpatialEngine,
    SpatialTrackStateManager,
    ZoneOccupancyTracker,
    create_observation,
    resolve_inference_context,
    summarize_tracks,
)

CALIBRATION_POINTS = [[120, 80], [880, 110], [940, 520], [60, 540]]
SOURCE_WIDTH, SOURCE_HEIGHT = 1000, 600


def detection(bbox: dict[str, float], class_name: str = "person") -> dict[str, Any]:
    return {"class_name": class_name, "confidence": 0.9, "bbox": bbox}


def main() -> None:
    engine = SpatialEngine(grid_rows=3, grid_columns=3)
    engine.calibrate(CALIBRATION_POINTS, SOURCE_WIDTH, SOURCE_HEIGHT)
    context = resolve_inference_context(
        InferenceContext.region_of_interest(CALIBRATION_POINTS), SOURCE_WIDTH, SOURCE_HEIGHT
    )
    print("inference scope:", context["scope"])

    tracker = ModelAgnosticTracker()
    motion = SpatialTrackStateManager()
    occupancy = ZoneOccupancyTracker()
    gate = LineCrossingCounter([500, 0], [500, SOURCE_HEIGHT], name="centre-gate")

    frames = [
        (0.0, [detection({"x": 200, "y": 300, "width": 60, "height": 120})]),
        (1.0, [detection({"x": 420, "y": 300, "width": 60, "height": 120})]),
        (2.0, [detection({"x": 640, "y": 300, "width": 60, "height": 120})]),
    ]

    observations = []
    tracked_frames = []
    motion_state: dict[str, Any] = {}
    for timestamp, detections in frames:
        tracked = tracker.update(detections, timestamp)["detections"]
        spatial = engine.spatialize_result({"detections": tracked})["detections"]
        motion_state = motion.update(spatial, timestamp)
        tracked_frames.append({"timestamp": timestamp, "detections": spatial})
        occupancy.update(spatial, timestamp)
        gate.update(spatial)
        observations.append(
            create_observation(
                {"detections": spatial},
                analysis_id="analytics-demo",
                source_id="synthetic",
                timestamp=timestamp,
                frame_index=int(timestamp),
            )
        )

    summaries = summarize_tracks(tracked_frames)
    print("track summary:", summaries[0])
    print("motion tracks:", len(motion_state["tracks"]))

    zones = occupancy.snapshot()["zones"]
    print("zones:", {zone: stats["entries"] for zone, stats in zones.items()})
    print("gate crossings:", gate.snapshot()["total"])

    with tempfile.TemporaryDirectory() as directory:
        with ObservationBatchWriter(
            "analytics-demo", "synthetic", {"id": "demo"}, root=Path(directory)
        ) as writer:
            for observation in observations:
                writer.append(observation)
        print("observations written:", len(observations))


if __name__ == "__main__":
    main()
