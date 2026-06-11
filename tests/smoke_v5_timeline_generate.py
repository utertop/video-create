from __future__ import annotations

import json
import shutil
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine
import video_engine_worker as worker
from video_engine.timeline import build_timeline_from_blueprint


def mock_library() -> Dict[str, Any]:
    return {
        "schema_version": "5.5",
        "document_type": "media_library",
        "assets": [
            {
                "asset_id": "asset_image_01",
                "type": "image",
                "status": "ready",
                "absolute_path": "D:/mock/image_01.jpg",
                "relative_path": "image_01.jpg",
                "media": {"orientation": "landscape"},
            },
            {
                "asset_id": "asset_video_01",
                "type": "video",
                "status": "ready",
                "absolute_path": "D:/mock/video_01.mp4",
                "relative_path": "video_01.mp4",
                "media": {"orientation": "landscape", "duration_seconds": 2.5},
            },
            {
                "asset_id": "asset_audio_01",
                "type": "audio",
                "status": "ready",
                "absolute_path": "D:/mock/music.mp3",
                "relative_path": "music.mp3",
                "media": {"duration_seconds": 30.0},
            },
        ],
    }


def mock_blueprint() -> Dict[str, Any]:
    return {
        "schema_version": "5.5",
        "document_type": "story_blueprint",
        "title": "Timeline Generate Smoke",
        "subtitle": "Schema V1",
        "metadata": {
            "edit_strategy": "fast_assembly",
            "performance_mode": "stable",
            "audio": {
                "music_mode": "manual",
                "music_path": "D:/mock/music.mp3",
                "bgm_volume": 0.25,
                "source_audio_volume": 1.0,
                "keep_source_audio": True,
                "auto_ducking": True,
                "fade_in_seconds": 1.0,
                "fade_out_seconds": 2.0,
            },
            "audio_blueprint": {
                "version": 1,
                "mode": "apply",
                "section_cues": [
                    {
                        "section_id": "section_city",
                        "phase": "intro",
                        "energy": "medium",
                        "reason": "smoke cue",
                    }
                ],
            },
        },
        "sections": [
            {
                "section_id": "section_city",
                "section_type": "city",
                "title": "City",
                "subtitle": None,
                "enabled": True,
                "asset_refs": [
                    {"asset_id": "asset_image_01", "enabled": True, "keep_audio": False},
                    {"asset_id": "asset_video_01", "enabled": True, "keep_audio": True},
                ],
                "children": [],
            }
        ],
    }


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def assert_timeline_generated(timeline: Dict[str, Any]) -> None:
    assert timeline["document_type"] == "timeline"
    assert timeline["timeline_version"] == "v1"
    tracks = timeline["tracks"]
    assert {track["kind"] for track in tracks} >= {"video", "audio", "title"}
    clip_index = timeline["clip_index"]
    assert clip_index
    assert any(clip["kind"] == "image_asset" for clip in clip_index.values())
    assert any(clip["kind"] == "video_asset" for clip in clip_index.values())
    assert any(clip["kind"] in {"title_card", "chapter_card"} for clip in clip_index.values())
    assert any(clip["kind"] == "audio_bgm" for clip in clip_index.values())
    assert timeline["performance_policy"]["final"]["uses_original_source"] is True
    assert timeline["performance_policy"]["final"]["allow_proxy"] is False
    assert timeline["performance_policy"]["preview"]["cache_namespace"] == "preview"
    assert timeline["performance_policy"]["final"]["cache_namespace"] == "final"

    for clip_id, clip in clip_index.items():
        assert clip["clip_id"] == clip_id
        assert round(clip["timeline_start"] + clip["timeline_duration"], 3) == round(clip["timeline_end"], 3)
        assert clip["enabled"] is True


def test_timeline_generate_module_cli_and_worker() -> None:
    root = Path("tests/tmp_vcs_timeline_generate")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    library = mock_library()
    blueprint = mock_blueprint()
    render_plan = engine.Compiler(blueprint, library).compile()

    timeline = build_timeline_from_blueprint(
        blueprint,
        render_plan,
        media_library=library,
        media_library_path="media_library.json",
        story_blueprint_path="story_blueprint.json",
        render_plan_path="render_plan.json",
        project_dir=str(root / ".video_create_project"),
    )
    assert_timeline_generated(timeline)

    first_visual_id = next(
        clip_id
        for clip_id, clip in timeline["clip_index"].items()
        if clip["kind"] in {"image_asset", "video_asset"}
    )
    preserved_id = "clip_custom_preserved_id"
    timeline["clip_index"][preserved_id] = timeline["clip_index"].pop(first_visual_id)
    timeline["clip_index"][preserved_id]["clip_id"] = preserved_id

    regenerated = build_timeline_from_blueprint(
        blueprint,
        render_plan,
        media_library=library,
        existing_timeline=timeline,
        project_dir=str(root / ".video_create_project"),
    )
    assert preserved_id in regenerated["clip_index"]

    library_path = root / "media_library.json"
    blueprint_path = root / "story_blueprint.json"
    render_plan_path = root / "render_plan.json"
    timeline_path = root / "timeline.json"
    worker_timeline_path = root / "timeline_worker.json"
    write_json(library_path, library)
    write_json(blueprint_path, blueprint)
    write_json(render_plan_path, render_plan)

    engine.command_timeline_generate(
        Namespace(
            render_plan=str(render_plan_path),
            output=str(timeline_path),
            blueprint=str(blueprint_path),
            library=str(library_path),
            existing_timeline=None,
            project_dir=str(root / ".video_create_project"),
        )
    )
    assert_timeline_generated(json.loads(timeline_path.read_text(encoding="utf-8")))

    result = worker.run_task(
        {
            "type": "timeline-generate",
            "id": "timeline-generate-smoke",
            "render_plan_path": str(render_plan_path),
            "blueprint_path": str(blueprint_path),
            "library_path": str(library_path),
            "output_path": str(worker_timeline_path),
            "project_dir": str(root / ".video_create_project"),
        }
    )
    assert result["ok"] is True
    assert result["output_path"] == str(worker_timeline_path)
    assert_timeline_generated(result["document"])


if __name__ == "__main__":
    test_timeline_generate_module_cli_and_worker()
    print("V5 timeline generate smoke test passed")
