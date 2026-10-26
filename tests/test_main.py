"""Tests for ``python -m spe`` entry point."""

from __future__ import annotations

import runpy
import sys
import warnings

import pytest


def test_main_module_reports_version(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["spe", "--version"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("spe.__main__", run_name="__main__")
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.strip()


def test_cli_module_entry_point(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["spe", "--version"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        with pytest.raises(SystemExit) as exit_info:
            runpy.run_module("spe.cli", run_name="__main__")
    assert exit_info.value.code == 0
    assert "spe-engine" in capsys.readouterr().out
