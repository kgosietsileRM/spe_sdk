"""Render a calibrated grid overlay and annotate detections, then save a PNG.

Builds a synthetic camera frame, calibrates it, draws the perspective-correct
calibrated grid plus ROI, overlays bounding boxes with zone labels, and writes
the result to disk. Uses OpenCV only -- no server, no video source.

Run from the project root::

    python examples/annotated_overlay.py
    python examples/annotated_overlay.py --output C:\\temp\\overlay.png
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np

from spe import SpatialEngine

SOURCE_WIDTH = 1280
SOURCE_HEIGHT = 720
SOURCE_POINTS = [[180, 120], [1090, 150], [1180, 640], [90, 660]]
GRID_ROWS = 4
GRID_COLUMNS = 6
DEFAULT_OUTPUT = Path("examples/output/annotated_overlay.png")


def make_frame() -> np.ndarray:
    """Build a plain synthetic frame so the example needs no input image."""
    frame = np.full((SOURCE_HEIGHT, SOURCE_WIDTH, 3), 26, dtype=np.uint8)
    cv2.rectangle(frame, (0, 480), (SOURCE_WIDTH, SOURCE_HEIGHT), (40, 42, 46), -1)
    return frame


DETECTIONS = [
    {
        "id": "person-1",
        "class_name": "person",
        "confidence": 0.92,
        "bbox": {"x": 560, "y": 250, "width": 70, "height": 180},
    },
    {
        "id": "person-2",
        "class_name": "person",
        "confidence": 0.81,
        "bbox": {"x": 880, "y": 300, "width": 66, "height": 175},
    },
    {
        "id": "cart-1",
        "class_name": "cart",
        "confidence": 0.70,
        "bbox": {"x": 300, "y": 380, "width": 140, "height": 110},
    },
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Where to write the annotated PNG (default: %(default)s).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    engine = SpatialEngine(
        grid_rows=GRID_ROWS,
        grid_columns=GRID_COLUMNS,
        source_dimensions={"width": SOURCE_WIDTH, "height": SOURCE_HEIGHT},
    )
    engine.calibrate(SOURCE_POINTS, SOURCE_WIDTH, SOURCE_HEIGHT)

    image = make_frame()
    image, _ = engine.render_calibrated_grid(image, show_grid=True, show_roi=True)

    result = engine.spatialize_result({"detections": DETECTIONS})
    for detection in result["detections"]:
        bbox = detection["bbox"]
        spatial = detection["spatial"]
        top_left = (int(bbox["x"]), int(bbox["y"]))
        bottom_right = (int(bbox["x"] + bbox["width"]), int(bbox["y"] + bbox["height"]))
        valid = spatial["status"] == "valid"
        color = (120, 230, 120) if valid else (80, 80, 240)
        cv2.rectangle(image, top_left, bottom_right, color, 2)
        label = f"{detection['class_name']} {spatial.get('zone') or '-'}"
        cv2.putText(
            image,
            label,
            (top_left[0], top_left[1] - 8),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            1,
            cv2.LINE_AA,
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), image):
        raise SystemExit(f"could not write {args.output}")

    print(f"wrote {args.output} ({image.shape[1]}x{image.shape[0]})")
    print("zone labels:", [detection["spatial"].get("zone") for detection in result["detections"]])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
