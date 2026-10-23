"""Tests for provider-neutral observation builders."""

from __future__ import annotations

import json

import pytest

from spe import create_image_observation, create_observation
from spe.exceptions import SPEValidationError


def _result():
    return {
        "model": {"id": "model-a", "provider": "ultralytics", "version": "YOLOv8n"},
        "detections": [
            {
                "id": "det-001",
                "class_id": 0,
                "class_name": "person",
                "confidence": 0.9,
                "bbox": {"x": 10, "y": 20, "width": 30, "height": 40},
                "center": {"x": 25, "y": 40},
                "coordinate_system": "source_pixels",
            }
        ],
    }


def test_observation_is_provider_neutral_and_timestamped():
    observation = create_observation(
        _result(), analysis_id="analysis-1", source_id="source-1", timestamp=2.5, frame_index=75
    )

    assert observation["analysis_id"] == "analysis-1"
    assert observation["source_id"] == "source-1"
    assert observation["timestamp"] == 2.5
    assert observation["timestamp_type"] == "media"
    assert observation["frame_index"] == 75
    assert observation["coordinate_system"] == "source_pixels"
    assert observation["perception"] == {
        "provider": "ultralytics",
        "model_id": "model-a",
        "model_version": "YOLOv8n",
    }
    assert observation["detections"][0]["detection_id"] == "det-001"
    assert "track_id" not in observation["detections"][0]


def test_observation_preserves_provider_track_identity():
    result = _result()
    result["detections"][0]["track_id"] = "track-7"

    observation = create_observation(
        result, analysis_id="analysis-1", source_id="source-1", timestamp=2.5, frame_index=75
    )

    assert observation["detections"][0]["track_id"] == "track-7"


def test_image_observation_wraps_static_context():
    observation = create_image_observation(_result(), source_id="src-1")

    assert observation["observation_type"] == "image"
    assert observation["source_id"] == "src-1"
    assert observation["model"]["id"] == "model-a"
    assert len(observation["detections"]) == 1


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"analysis_id": " ", "source_id": "src"}, "identifiers"),
        ({"analysis_id": "a", "source_id": " "}, "identifiers"),
    ],
)
def test_observation_rejects_missing_identifiers(kwargs, message):
    with pytest.raises(SPEValidationError, match=message):
        create_observation(_result(), timestamp=0.0, frame_index=0, **kwargs)


def test_observation_rejects_invalid_timestamp_and_frame_index():
    with pytest.raises(SPEValidationError, match="timestamp"):
        create_observation(_result(), analysis_id="a", source_id="s", timestamp=-1.0, frame_index=0)
    with pytest.raises(SPEValidationError, match="frame index"):
        create_observation(_result(), analysis_id="a", source_id="s", timestamp=0.0, frame_index=-1)


def test_image_observation_requires_source_id():
    with pytest.raises(SPEValidationError, match="source identifier"):
        create_image_observation(_result(), source_id=" ")


def _observation(index: int) -> dict:
    return {"observation_id": f"obs-{index}", "frame_index": index}


def test_batch_writer_flushes_and_writes_manifest(tmp_path):
    from spe import ObservationBatchWriter

    writer = ObservationBatchWriter(
        "run-1", "src-1", {"id": "model-a"}, root=tmp_path, batch_size=2, interval_ms=40.0
    )
    assert writer.append(_observation(0)) is None
    assert writer.flush() == writer.path
    assert writer.flush() is None
    writer.append(_observation(1))
    writer.append(_observation(2))
    writer.update_sampling(50.0, 20.0)
    writer.close()

    lines = writer.path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    manifest = json.loads(writer.manifest_path.read_text(encoding="utf-8"))
    assert manifest["observation_count"] == 3
    assert manifest["status"] == "complete"
    assert manifest["interval_ms"] == 50.0
    assert manifest["effective_fps"] == 20.0


def test_batch_writer_appends_and_context_manager(tmp_path):
    from spe import ObservationBatchWriter

    with ObservationBatchWriter("run-1", "src-1", {}, root=tmp_path) as writer:
        writer.append(_observation(0))
    with ObservationBatchWriter("run-1", "src-1", {}, root=tmp_path, batch_size=1) as writer:
        assert writer._count == 1
        writer.append(_observation(1))
    assert len(writer.path.read_text(encoding="utf-8").splitlines()) == 2


def test_batch_writer_validates_paths_and_arguments(tmp_path):
    from spe import ObservationBatchWriter

    with pytest.raises(SPEValidationError, match="analysis_id"):
        ObservationBatchWriter("../escape", "src", {}, root=tmp_path)
    with pytest.raises(SPEValidationError, match="source_id"):
        ObservationBatchWriter("run", "", {}, root=tmp_path)
    with pytest.raises(SPEValidationError, match="batch_size"):
        ObservationBatchWriter("run", "src", {}, root=tmp_path, batch_size=0)
    writer = ObservationBatchWriter("run", "src", {}, root=tmp_path)
    with pytest.raises(SPEValidationError, match="observation mapping"):
        writer.append({})
    with pytest.raises(SPEValidationError, match="Status"):
        writer.close("unknown")
