"""Batch-analyze every selected media key and emit JSON + CSV summaries."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

import core
import cv2

FIELDS = (
    "source",
    "mode",
    "frames",
    "duration_seconds",
    "active_tracks",
    "tracks",
    "lane_a_queue",
    "lane_b_queue",
    "lane_c_queue",
    "lane_a_crossings",
    "lane_b_crossings",
    "lane_c_crossings",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", nargs="+", default=["video"])
    parser.add_argument("--mode", choices=("local", "server"), default="local")
    parser.add_argument("--url", default="http://127.0.0.1:5000")
    parser.add_argument("--model", default="model-a")
    parser.add_argument("--confidence", type=float, default=0.4)
    parser.add_argument("--frames", type=int, default=60)
    parser.add_argument("--fps", type=float, default=5.0)
    parser.add_argument("--rows", type=int, default=core.DEFAULT_ROWS)
    parser.add_argument("--columns", type=int, default=core.DEFAULT_COLUMNS)
    parser.add_argument("--out", type=Path, default=Path("outputs"))
    return parser.parse_args()


def row_for(report: dict[str, Any]) -> dict[str, Any]:
    lanes = report["lanes"]
    return {
        "source": Path(report["source"]["path"]).name,
        "mode": report["mode"],
        "frames": report["sampled_frames"],
        "duration_seconds": report["duration_seconds"],
        "active_tracks": report["occupancy"]["active_tracks"],
        "tracks": len(report["tracks"]),
        **{
            f"lane_{letter.lower()}_{field}": lanes.get(letter, {}).get(field, 0)
            for letter in ("A", "B", "C")
            for field in ("queue", "crossings")
        },
    }


def main() -> int:
    args = parse_args()
    links = core.load_links()
    args.out.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    failures = 0

    for key in args.sources:
        if key not in links:
            print(f"skip {key}: not present in assets/link.json")
            failures += 1
            continue
        try:
            path = core.resolve_media(key, links)
            report_path = args.out / f"{key}.json"
            overlay_path = args.out / f"{key}.jpg"

            def save_frame(
                _index: int,
                annotated: Any,
                _spatial: list[dict[str, Any]],
                _occupancy: dict[str, Any],
                _lanes: dict[str, Any],
                overlay: Path = overlay_path,
            ) -> None:
                cv2.imwrite(str(overlay), annotated)

            print(f"analyzing {key} ({path.name})...")
            result = core.analyze(
                path,
                mode=args.mode,
                max_frames=args.frames,
                sample_fps=args.fps,
                rows=args.rows,
                columns=args.columns,
                url=args.url,
                model=args.model,
                confidence=args.confidence,
                on_frame=save_frame,
            )
            core.save_report(result.report, report_path)
            summaries.append({"key": key, "report": result.report, "ok": True})
            rows.append(row_for(result.report))
            print(
                f"  {result.report['sampled_frames']} frames, "
                f"{result.report['occupancy']['active_tracks']} active tracks -> {report_path}"
            )
        except Exception as error:
            failures += 1
            print(f"  failed: {error}")
            summaries.append({"key": key, "ok": False, "error": str(error)})

    summary_path = args.out / "summary.json"
    summary_path.write_text(
        json.dumps(summaries, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if rows:
        with (args.out / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    print(f"wrote {summary_path}")
    if rows:
        print(f"wrote {args.out / 'summary.csv'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
