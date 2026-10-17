"""Stream a video frame-by-frame into the SPE detection endpoint.

This example reads a local video with OpenCV, encodes each frame as JPEG, and
posts it to ``POST /api/analysis/detect-frame`` at a bounded rate. Start the
engine first (from its repository root)::

    python app.py

Then run::

    python examples/stream_video.py path/to/clip.mp4 --fps 5

Press ``Ctrl+C`` to stop early.
"""

from __future__ import annotations

import argparse
import time

import cv2

from spe import SPEClient

BASE_URL = "http://127.0.0.1:5000"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", help="Path to a local video file.")
    parser.add_argument("--url", default=BASE_URL, help="Base URL of the SPE server.")
    parser.add_argument("--model", default="model-a", help="Model id to run.")
    parser.add_argument("--fps", type=float, default=5.0, help="Frames per second to sample.")
    parser.add_argument("--confidence", type=float, default=0.4, help="Detection threshold.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    capture = cv2.VideoCapture(args.video)
    if not capture.isOpened():
        raise SystemExit(f"Could not open video: {args.video}")

    interval = 1.0 / args.fps if args.fps > 0 else 0.0
    frame_index = 0
    sent = 0
    try:
        with SPEClient(args.url) as client:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break
                frame_index += 1
                parsed, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                if not parsed:
                    continue
                result = client.detect_frame(
                    buffer.tobytes(),
                    filename=f"frame-{frame_index:06d}.jpg",
                    model_id=args.model,
                    confidence=args.confidence,
                    frame_index=frame_index,
                    timestamp=time.time(),
                )
                sent += 1
                for detection in result.get("detections", []):
                    spatial = detection.get("spatial")
                    zone = spatial.get("zone") if isinstance(spatial, dict) else None
                    print(f"frame {frame_index}: {detection['class_name']} zone={zone}")
                if interval:
                    time.sleep(interval)
    except KeyboardInterrupt:
        print("\ninterrupted")
    finally:
        capture.release()

    print(f"sent {sent} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
