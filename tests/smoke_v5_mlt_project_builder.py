import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import render_backends as backends


def test_build_mlt_project_writes_project_and_manifest() -> None:
    root = Path("tests/tmp_vcs_mlt_project_builder")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    image_path = root / "素材封面.jpg"
    video_path = root / "片段01.mp4"
    image_path.write_bytes(b"fake-image")
    video_path.write_bytes(b"fake-video")

    plan = {
        "render_settings": {"fps": 12, "aspect_ratio": "16:9"},
        "segments": [
            {
                "segment_id": "seg_001",
                "type": "image",
                "source_path": str(image_path.resolve()),
                "duration": 2.0,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "overlay_text": "杭州西湖",
                "overlay_subtitle": "傍晚风景",
                "overlay_duration": 1.8,
                "overlay_title_style": {"motion": "postcard_drift", "position": "lower_left"},
            },
            {
                "segment_id": "seg_002",
                "type": "video",
                "source_path": str(video_path.resolve()),
                "duration": 3.0,
                "transition": "soft_crossfade",
                "transition_config": {"type": "soft_crossfade", "duration": 0.4},
            },
        ],
    }

    result = backends.build_mlt_project(
        plan,
        {"engine": "mlt_experimental"},
        str((root / "output.mp4").resolve()),
    )

    assert result["supported"] is True
    assert Path(result["project_path"]).exists()
    assert Path(result["asset_manifest_path"]).exists()
    assert result["route_counts"]["segments"] == 2
    assert result["route_counts"]["crossfade_transitions"] == 1
    assert result["route_counts"]["text_overlays"] == 1

    project_text = Path(result["project_path"]).read_text(encoding="utf-8")
    assert "杭州西湖" in project_text
    assert "素材封面.jpg" in project_text
    assert "soft_crossfade" in project_text or "crossfade" in project_text

    manifest = json.loads(Path(result["asset_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["supported"] is True
    assert manifest["route_counts"]["video_segments"] == 1
    assert manifest["transitions"][0]["style"] == "crossfade"


def test_build_mlt_project_returns_structured_rejection() -> None:
    root = Path("tests/tmp_vcs_mlt_project_builder_reject")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    plan = {
        "render_settings": {"fps": 12, "aspect_ratio": "16:9"},
        "segments": [
            {
                "segment_id": "seg_bad",
                "type": "audio",
                "source_path": str((root / "voice.m4a").resolve()),
                "duration": 3.0,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
            }
        ],
    }

    result = backends.build_mlt_project(
        plan,
        {"engine": "mlt_experimental"},
        str((root / "output.mp4").resolve()),
    )

    assert result["supported"] is False
    assert result["rejection_reasons"] == [backends.MLT_BACKEND_REASON_UNSUPPORTED_SEGMENT_TYPE]
    assert Path(result["project_path"]).exists()
    manifest = json.loads(Path(result["asset_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["supported"] is False
    assert manifest["rejection_reasons"] == [backends.MLT_BACKEND_REASON_UNSUPPORTED_SEGMENT_TYPE]


if __name__ == "__main__":
    test_build_mlt_project_writes_project_and_manifest()
    test_build_mlt_project_returns_structured_rejection()
