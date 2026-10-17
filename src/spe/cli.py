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
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ._version import __version__
from .client import SPEClient
from .engine import SpatialEngine
from .exceptions import SPEError


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


def _print(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, default=str)
    sys.stdout.write("\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="spe", description="Spatial Intelligence Engine SDK CLI.")
    parser.add_argument("--version", action="version", version=f"spe-sdk {__version__}")
    parser.add_argument(
        "--url", default="http://127.0.0.1:5000", help="Base URL of a running SPE server."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("health", help="Check server health.")
    subparsers.add_parser("state", help="Fetch the master spatial state.")
    subparsers.add_parser("models", help="List registered perception models.")

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

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "health":
            with SPEClient(args.url) as client:
                _print(client.health())
        elif args.command == "state":
            with SPEClient(args.url) as client:
                _print(client.get_state())
        elif args.command == "models":
            with SPEClient(args.url) as client:
                _print(client.list_models())
        elif args.command == "inspect":
            calibration = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
            engine = SpatialEngine(
                calibration=calibration,
                grid_rows=args.rows,
                grid_columns=args.columns,
                source_dimensions={"width": args.size[0], "height": args.size[1]},
            )
            _print(engine.inspect([args.x, args.y]))
        elif args.command == "calibrate":
            from .models import ReferencePlane

            plane = ReferencePlane(
                width=args.reference[0], height=args.reference[1], units=args.units
            )
            engine = SpatialEngine(grid_rows=args.rows, grid_columns=args.columns)
            calibration = engine.calibrate(
                args.points, args.size[0], args.size[1], reference_plane=plane
            )
            _print(calibration.to_dict())
    except (SPEError, OSError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
