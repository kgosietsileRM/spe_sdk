"""Smoke checks for the stand-alone examples and their isolated installs."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
STANDALONE_DEMOS = ("cli", "powershell", "template", "web")


def demo_python_files() -> list[Path]:
    return sorted(path for demo in STANDALONE_DEMOS for path in (EXAMPLES_DIR / demo).glob("*.py"))


def test_standalone_demo_scripts_parse() -> None:
    scripts = demo_python_files()
    assert scripts, "no stand-alone demo scripts found"
    for path in scripts:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


@pytest.mark.parametrize("demo", STANDALONE_DEMOS)
def test_demo_venv_installs_published_sdk(demo: str) -> None:
    folder = EXAMPLES_DIR / demo
    requirements = (folder / "requirements.txt").read_text(encoding="utf-8")
    bootstrap = (folder / "bootstrap.ps1").read_text(encoding="utf-8")

    assert "spe-engine==0.2.1" in requirements
    assert "-r $requirements" in bootstrap
    assert "spe_engine-*.whl" not in bootstrap
