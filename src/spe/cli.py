"""Command-line interface for the SPE SDK.

Examples::

    spe health
    spe --url http://127.0.0.1:5000 models
    spe state
    spe inspect --x 400 --y 250 --calibration cal.json --width 1000 --height 600
    spe calibrate --image-size 1000x600 --points 120,80 880,110 940,520 60,540
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ._version import __version__
from .client import SPEClient
from .engine import SpatialEngine
from .exceptions import SPEError
from .tracking import ModelAgnosticTracker, TrackingConfig


def _parse_point(value: str) -> list[float]:
    try:
        x, y = value.replace(";", ",").split(",")
        return [float(x), float(y)]
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"Invalid point '{value}'. Use 'x,y'.") from error


def _parse_size(value: str) -> tuple[int, int]:
    try:
        width, height = value.lower().split("x")
        return int(width), int(height)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Size must be WIDTHxHEIGHT, e.g. 1000x600.") from error


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _detections(document: Any) -> list[Mapping[str, Any]]:
    if isinstance(document, dict):
        document = document.get("detections", [])
    if not isinstance(document, list):
        raise ValueError("Detections must be a list or an object with a 'detections' list.")
    result: list[Mapping[str, Any]] = []
    for item in document:
        result.append(dict(item))
    return result


def _client(args: argparse.Namespace) -> SPEClient:
    return SPEClient(args.url, api_key=args.api_key, timeout=args.timeout)


def _print(payload: Any, compact: bool = False) -> None:
    if compact:
        json.dump(payload, sys.stdout, separators=(",", ":"), default=str)
    else:
        json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spe", description="Spatial Intelligence Engine SDK CLI.")
    parser.add_argument("--version", action="version", version=f"spe-sdk {__version__}")
    parser.add_argument(
        "--url", default="http://127.0.0.1:5000", help="Base URL of a running SPE server."
    )
    parser.add_argument("--api-key", default=None, help="Optional API key for the server.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Request timeout in seconds.")
    parser.add_argument("--compact", action="store_true", help="Emit compact JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health", help="Check server health.")
    subparsers.add_parser("state", help="Fetch the master spatial state.")
    models = subparsers.add_parser("models", help="List registered perception models.")
    models.add_argument("--descriptors", action="store_true", help="Emit typed model descriptors.")

    inspect = subparsers.add_parser("inspect", help="Inspect a point against a calibration file.")
    inspect.add_argument("--x", type=float, required=True)
    inspect.add_argument("--y", type=float, required=True)
    inspect.add_argument("--calibration", required=True, help="Path to a calibration JSON file.")
    inspect.add_argument(
        "--size", type=_parse_size, default=(1000, 600), help="Source size WIDTHxHEIGHT."
    )
    inspect.add_argument("--rows", type=int, default=3)
    inspect.add_argument("--columns", type=int, default=3)

    calibrate = subparsers.add_parser(
        "calibrate", help="Calculate a calibration from four image points."
    )
    calibrate.add_argument(
        "--size", type=_parse_size, required=True, help="Source size WIDTHxHEIGHT."
    )
    calibrate.add_argument(
        "--points",
        nargs=4,
        required=True,
        type=_parse_point,
        metavar="X,Y",
        help="TL TR BR BL points.",
    )
    calibrate.add_argument("--rows", type=int, default=3)
    calibrate.add_argument("--columns", type=int, default=3)
    calibrate.add_argument("--reference", type=_parse_size, default=(1000, 600))
    calibrate.add_argument("--units", default="normalized")

    spatialize = subparsers.add_parser(
        "spatialize", help="Add calibrated spatial data to detections in a JSON file."
    )
    spatialize.add_argument("--calibration", required=True, help="Path to a calibration JSON file.")
    spatialize.add_argument("--detections", required=True, help="Path to detections JSON.")
    spatialize.add_argument("--rows", type=int, default=None)
    spatialize.add_argument("--columns", type=int, default=None)

    track = subparsers.add_parser("track", help="Run the model-agnostic tracker over JSON frames.")
    track.add_argument("--frames", required=True, help="Path to a JSON list of frames.")
    track.add_argument("--min-iou", type=float, default=0.01)
    track.add_argument("--max-distance-scale", type=float, default=2.5)
    track.add_argument("--max-missing", type=float, default=1.5)
    track.add_argument("--confirmation", type=int, default=2)

    render = subparsers.add_parser("render-grid", help="Render a grid onto an image file.")
    render.add_argument("--image", required=True, help="Input image path.")
    render.add_argument("--output", required=True, help="Output image path.")
    render.add_argument("--calibration", help="Optional calibration JSON for a calibrated grid.")
    render.add_argument("--rows", type=int, default=8)
    render.add_argument("--columns", type=int, default=12)
    render.add_argument("--thickness", type=int, default=1)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "health":
            with _client(args) as client:
                _print(client.health(), args.compact)
        elif args.command == "state":
            with _client(args) as client:
                _print(client.get_state(), args.compact)
        elif args.command == "models":
            with _client(args) as client:
                payload = (
                    [model.to_dict() for model in client.models()]
                    if args.descriptors
                    else client.list_models()
                )
                _print(payload, args.compact)
        elif args.command == "inspect":
            calibration = _load_json(args.calibration)
            engine = SpatialEngine(
                calibration=calibration,
                grid_rows=args.rows,
                grid_columns=args.columns,
                source_dimensions={"width": args.size[0], "height": args.size[1]},
            )
            _print(engine.inspect([args.x, args.y]), args.compact)
        elif args.command == "calibrate":
            from .models import ReferencePlane

            plane = ReferencePlane(
                width=args.reference[0], height=args.reference[1], units=args.units
            )
            engine = SpatialEngine(grid_rows=args.rows, grid_columns=args.columns)
            calibration = engine.calibrate(
                args.points, args.size[0], args.size[1], reference_plane=plane
            )
            _print(calibration.to_dict(), args.compact)
        elif args.command == "spatialize":
            calibration = _load_json(args.calibration)
            engine = SpatialEngine(calibration=calibration)
            if args.rows is not None:
                engine.grid_rows = int(args.rows)
            if args.columns is not None:
                engine.grid_columns = int(args.columns)
            _print(engine.spatialize(_detections(_load_json(args.detections))), args.compact)
        elif args.command == "track":
            frames = _load_json(args.frames)
            if not isinstance(frames, list):
                raise ValueError("Frames must be a JSON list of frame objects.")
            config = TrackingConfig(
                min_iou=args.min_iou,
                max_center_distance_scale=args.max_distance_scale,
                max_missing_seconds=args.max_missing,
                confirmation_observations=args.confirmation,
            )
            tracker = ModelAgnosticTracker(config)
            tracked = []
            for index, frame in enumerate(frames):
                detections = _detections(frame)
                timestamp = frame.get("timestamp") if isinstance(frame, dict) else None
                tracked.append(
                    tracker.update(detections, timestamp if timestamp is not None else index)
                )
            _print({"frames": tracked, "diagnostics": tracker.snapshot()}, args.compact)
        elif args.command == "render-grid":
            import cv2

            engine = SpatialEngine()
            image = cv2.imread(args.image, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError(f"Unable to read image: {args.image}")
            if args.calibration:
                engine.load_calibration(_load_json(args.calibration))
                rendered, metadata = engine.render_calibrated_grid(image)
            else:
                rendered, metadata = engine.render_grid(
                    image,
                    rows=args.rows,
                    columns=args.columns,
                    line_thickness=args.thickness,
                )
            if not cv2.imwrite(args.output, rendered):
                raise ValueError(f"Unable to write image: {args.output}")
            _print(metadata, args.compact)
    except (SPEError, OSError, ValueError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
