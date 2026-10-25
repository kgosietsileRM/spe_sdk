"""Request handling and preset resolution for the template demo."""

from __future__ import annotations

import contextlib
import json
import time
from pathlib import Path
from typing import Any

import core
import cv2
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
PRESET_DIR = BASE_DIR / "presets"
UPLOAD_DIR = BASE_DIR / "outputs" / "uploads"
REPORT_DIR = BASE_DIR / "outputs" / "reports"
FRAME_DIR = BASE_DIR / "outputs" / "frames"


def latest(directory: Path, pattern: str) -> Path | None:
    """Return the newest file matching a glob, if any."""
    files = sorted(directory.glob(pattern))
    return files[-1] if files else None


def latest_report_path() -> Path | None:
    return latest(REPORT_DIR, "report-*.json")


def latest_frame_path() -> Path | None:
    return latest(FRAME_DIR, "frame-*.jpg")


def load_presets() -> dict[str, dict[str, Any]]:
    """Load JSON output presets keyed by file stem."""
    presets: dict[str, dict[str, Any]] = {}
    for path in sorted(PRESET_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        presets[path.stem] = data
    return presets


def preset_points(preset: dict[str, Any], width: int, height: int) -> list[list[float]]:
    """Scale a preset's fractional calibration points to source pixels."""
    points: list[list[float]] = []
    for fraction_x, fraction_y in preset["points_fraction"]:
        x = min(int(float(fraction_x) * width), width - 1)
        y = min(int(float(fraction_y) * height), height - 1)
        points.append([float(max(0, x)), float(max(0, y))])
    return points


def save_upload(upload: FileStorage) -> Path:
    """Persist an uploaded media file and return its path."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    original = secure_filename(upload.filename or "upload.mp4") or "upload.mp4"
    target = UPLOAD_DIR / original
    counter = 1
    while target.exists():
        target = UPLOAD_DIR / f"{Path(original).stem}-{counter}{Path(original).suffix}"
        counter += 1
    upload.save(target)
    return target


def analyze_request(
    *,
    source: str,
    preset_name: str,
    upload: FileStorage | None = None,
    mode: str = "local",
    frames: int = 60,
    fps: float = 5.0,
    url: str = "http://127.0.0.1:5000",
    model: str = "model-a",
    confidence: float = 0.4,
) -> dict[str, Any]:
    """Run the requested analysis and return the JSON report."""
    presets = load_presets()
    if preset_name not in presets:
        raise ValueError(f"Unknown template preset: {preset_name}")
    preset = presets[preset_name]
    links = core.load_links()

    if upload is not None and upload.filename:
        path = save_upload(upload)
    else:
        path = core.resolve_media(source, links)

    info = core.probe(path)
    points = preset_points(preset, info.width, info.height)
    result = core.analyze(
        path,
        mode=mode,
        max_frames=max(1, min(frames, 2000)),
        sample_fps=max(0.1, min(fps, 30.0)),
        rows=int(preset["rows"]),
        columns=int(preset["columns"]),
        url=url,
        model=model,
        confidence=confidence,
        points=points,
    )
    token = f"{time.time_ns():020d}"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    core.save_report(result.report, REPORT_DIR / f"report-{token}.json")
    if result.last_frame is not None:
        FRAME_DIR.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(FRAME_DIR / f"frame-{token}.jpg"), result.last_frame)
        for old_frame in sorted(FRAME_DIR.glob("frame-*.jpg"))[:-5]:
            with contextlib.suppress(OSError):
                old_frame.unlink()
    for old_report in sorted(REPORT_DIR.glob("report-*.json"))[:-5]:
        with contextlib.suppress(OSError):
            old_report.unlink()
    return result.report
