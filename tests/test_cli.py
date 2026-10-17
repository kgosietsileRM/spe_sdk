"""Tests for the ``spe`` command-line interface."""

from __future__ import annotations

import json

import pytest

from spe import calculate_calibration
from spe.cli import main
from tests.conftest import RECTANGLE, SOURCE_HEIGHT, SOURCE_WIDTH


def test_cli_health(base_url, capsys):
    assert main(["--url", base_url, "health"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"


def test_cli_state(base_url, capsys):
    assert main(["--url", base_url, "state"]) == 0
    assert json.loads(capsys.readouterr().out)["state"]["calibrated"] is True


def test_cli_models(base_url, capsys):
    assert main(["--url", base_url, "models"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["id"] == "model-a"


def test_cli_calibrate(capsys):
    code = main(
        [
            "calibrate",
            "--size",
            "1000x600",
            "--points",
            "120,80",
            "880,110",
            "940,520",
            "60,540",
            "--rows",
            "4",
            "--columns",
            "6",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "calibrated"
    assert payload["calibrated_grid"]["rows"] == 4


def test_cli_inspect(tmp_path, capsys):
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    calibration_file = tmp_path / "calibration.json"
    calibration_file.write_text(json.dumps(record), encoding="utf-8")

    code = main(
        [
            "inspect",
            "--x",
            "500",
            "--y",
            "300",
            "--calibration",
            str(calibration_file),
            "--size",
            "1000x600",
        ]
    )
    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "valid"


def test_cli_reports_errors(capsys, tmp_path):
    code = main(
        [
            "inspect",
            "--x",
            "1",
            "--y",
            "1",
            "--calibration",
            str(tmp_path / "missing.json"),
        ]
    )
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_cli_version(capsys):
    with pytest.raises(SystemExit):
        main(["--version"])
    assert "spe-sdk" in capsys.readouterr().out


def test_cli_rejects_bad_points():
    with pytest.raises(SystemExit):
        main(["calibrate", "--size", "1000x600", "--points", "a", "b", "c", "d"])


def test_cli_rejects_bad_size():
    with pytest.raises(SystemExit):
        main(["calibrate", "--size", "nonsense", "--points", "1,1", "2,2", "3,3", "4,4"])
