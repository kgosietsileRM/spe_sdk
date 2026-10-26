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
    assert "spe-engine" in capsys.readouterr().out


def test_cli_rejects_bad_points():
    with pytest.raises(SystemExit):
        main(["calibrate", "--size", "1000x600", "--points", "a", "b", "c", "d"])


def test_cli_rejects_bad_size():
    with pytest.raises(SystemExit):
        main(["calibrate", "--size", "nonsense", "--points", "1,1", "2,2", "3,3", "4,4"])


def test_cli_models_descriptors(base_url, capsys):
    assert main(["--url", base_url, "models", "--descriptors"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["id"] == "model-a"
    assert payload[0]["provider"] == "ultralytics"


def test_cli_compact_output(base_url, capsys):
    assert main(["--url", base_url, "--compact", "health"]) == 0
    assert capsys.readouterr().out.strip() == '{"status":"ok"}'


def test_cli_spatialize(tmp_path, capsys):
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    calibration_file = tmp_path / "calibration.json"
    calibration_file.write_text(json.dumps(record), encoding="utf-8")
    detections_file = tmp_path / "detections.json"
    detections_file.write_text(
        json.dumps({"detections": [{"bbox": {"x": 480, "y": 280, "width": 40, "height": 40}}]}),
        encoding="utf-8",
    )

    code = main(
        [
            "spatialize",
            "--calibration",
            str(calibration_file),
            "--detections",
            str(detections_file),
            "--rows",
            "4",
            "--columns",
            "6",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload[0]["status"] == "valid"
    assert payload[0]["zone"] is not None


def test_cli_spatialize_rejects_bad_detections(tmp_path, capsys):
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    calibration_file = tmp_path / "calibration.json"
    calibration_file.write_text(json.dumps(record), encoding="utf-8")
    detections_file = tmp_path / "detections.json"
    detections_file.write_text('"nope"', encoding="utf-8")

    code = main(
        [
            "spatialize",
            "--calibration",
            str(calibration_file),
            "--detections",
            str(detections_file),
        ]
    )
    assert code == 1
    assert "error:" in capsys.readouterr().err


def test_cli_track(tmp_path, capsys):
    frames_file = tmp_path / "frames.json"
    frames_file.write_text(
        json.dumps(
            [
                {
                    "timestamp": 0,
                    "detections": [{"bbox": {"x": 10, "y": 10, "width": 20, "height": 20}}],
                },
                {
                    "timestamp": 1,
                    "detections": [{"bbox": {"x": 12, "y": 12, "width": 20, "height": 20}}],
                },
            ]
        ),
        encoding="utf-8",
    )
    code = main(["track", "--frames", str(frames_file)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["frames"]) == 2
    assert payload["frames"][-1]["detections"][0]["track_id"] == "track-1"


def test_cli_track_rejects_non_list(tmp_path, capsys):
    frames_file = tmp_path / "frames.json"
    frames_file.write_text("{}", encoding="utf-8")
    assert main(["track", "--frames", str(frames_file)]) == 1
    assert "error:" in capsys.readouterr().err


def test_cli_render_grid(tmp_path, capsys, sample_image):
    import cv2

    source = tmp_path / "source.png"
    assert cv2.imwrite(str(source), sample_image)
    output = tmp_path / "grid.png"
    code = main(
        [
            "render-grid",
            "--image",
            str(source),
            "--output",
            str(output),
            "--rows",
            "4",
            "--columns",
            "5",
        ]
    )
    assert code == 0
    assert output.is_file()
    assert json.loads(capsys.readouterr().out)["grid"]["rows"] == 4


def test_cli_render_calibrated_grid(tmp_path, capsys, sample_image):
    import cv2

    source = tmp_path / "source.png"
    assert cv2.imwrite(str(source), sample_image)
    record = calculate_calibration(RECTANGLE, SOURCE_WIDTH, SOURCE_HEIGHT)
    calibration_file = tmp_path / "calibration.json"
    calibration_file.write_text(json.dumps(record), encoding="utf-8")
    output = tmp_path / "calibrated.png"
    code = main(
        [
            "render-grid",
            "--image",
            str(source),
            "--output",
            str(output),
            "--calibration",
            str(calibration_file),
        ]
    )
    assert code == 0
    assert output.is_file()


def test_cli_render_grid_rejects_missing_image(tmp_path, capsys):
    code = main(
        [
            "render-grid",
            "--image",
            str(tmp_path / "missing.png"),
            "--output",
            str(tmp_path / "out.png"),
        ]
    )
    assert code == 1
    assert "Unable to read image" in capsys.readouterr().err
