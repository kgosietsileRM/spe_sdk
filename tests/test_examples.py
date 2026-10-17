"""Smoke tests that every example parses and the local ones actually run."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"

# Examples that need a running SPE engine server or a video file are only
# syntax-checked; the rest are executed end to end.
SERVER_EXAMPLES = {
    "http_client.py",
    "async_client.py",
    "http_analysis_session.py",
    "stream_video.py",
}
LOCAL_EXAMPLES = sorted(
    path for path in EXAMPLES_DIR.glob("*.py") if path.name not in SERVER_EXAMPLES
)


def test_all_examples_parse() -> None:
    examples = sorted(EXAMPLES_DIR.glob("*.py"))
    assert examples, "no example scripts found"
    for path in examples:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize("example", LOCAL_EXAMPLES, ids=lambda path: path.name)
def test_local_example_runs(example: Path, tmp_path: Path) -> None:
    args = [sys.executable, str(example)]
    if example.name == "annotated_overlay.py":
        args += ["--output", str(tmp_path / "overlay.png")]

    completed = subprocess.run(
        args,
        cwd=EXAMPLES_DIR.parent,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
