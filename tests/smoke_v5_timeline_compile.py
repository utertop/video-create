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
from video_engine.timeline import (
    build_timeline_from_blueprint,
    move_clip,
    update_bgm_cue_volume,
    update_clip_content,
    update_clip_duration,
    update_clip_enabled,
)
from video_engine.timeline_compile import compile_from_timeline


def mock_library() -> Dict[str, Any]:
    return {
        "schema_version": "5.5",
        "document_type": "media_library",
        "assets": [
            _asset("asset_image_01", "image", "D:/mock/image_01.jpg"),
            _asset("asset_image_02", "image", "D:/mock/image_02.jpg"),
            _asset("asset_image_03", "image", "D:/mock/image_03.jpg"),
            _asset("asset_audio_01", "audio", "D:/mock/music.mp3", duration=42.0),
        ],
    }


def _asset(asset_id: str, kind: str, path: str, duration: float | None = None) -> Dict[str, Any]:
    media = {"orientation": "landscape"}
    if duration is not None:
        media["duration_seconds"] = duration
    return {
        "asset_id": asset_id,
        "type": kind,
        "status": "ready",
        "absolute_path": path,
        "relative_path": Path(path).name,
        "media": media,
    }


def mock_blueprint() -> Dict[str, Any]:
    return {
        "schema_version": "5.5",
        "document_type": "story_blueprint",
        "title": "Timeline Compile Smoke",
        "subtitle": "Before Edit",
        "metadata": {
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
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
                "section_cues": [{"section_id": "section_city", "phase": "intro", "energy": "medium"}],
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
                    {"asset_id": "asset_image_02", "enabled": True, "keep_audio": False},
                    {"asset_id": "asset_image_03", "enabled": True, "keep_audio": False},
                ],
                "children": [],
            }
        ],
    }


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def edited_timeline(base_timeline: Dict[str, Any]) -> Dict[str, Any]:
    timeline = base_timeline
    title_clip_id = next(clip_id for clip_id, clip in timeline["clip_index"].items() if clip["kind"] == "title_card")
    image_1 = _clip_for_asset(timeline, "asset_image_01")
    image_2 = _clip_for_asset(timeline, "asset_image_02")
    image_3 = _clip_for_asset(timeline, "asset_image_03")
    audio_clip_id = next(clip_id for clip_id, clip in timeline["clip_index"].items() if clip["kind"] == "audio_bgm")

    timeline = update_clip_enabled(timeline, image_1, False)
    timeline = update_clip_content(timeline, title_clip_id, {"title_text": "Edited Timeline Title"})
    timeline = update_clip_duration(timeline, image_2, 4.5)
    timeline = move_clip(timeline, image_3, 0)
    timeline = update_bgm_cue_volume(timeline, audio_clip_id, 0.42)
    return timeline


def _clip_for_asset(timeline: Dict[str, Any], asset_id: str) -> str:
    for clip_id, clip in timeline["clip_index"].items():
        source = clip.get("source_ref") or {}
        if source.get("asset_id") == asset_id:
            return clip_id
    raise AssertionError(f"missing clip for asset {asset_id}")


def assert_compiled_from_timeline(plan: Dict[str, Any]) -> None:
    assert plan["document_type"] == "render_plan"
    segments = plan["segments"]
    asset_order = [seg.get("asset_id") for seg in segments if seg.get("asset_id")]

    assert "asset_image_01" not in asset_order
    assert asset_order.index("asset_image_03") < asset_order.index("asset_image_02")
    assert any(seg.get("text") == "Edited Timeline Title" for seg in segments)

    image_2 = next(seg for seg in segments if seg.get("asset_id") == "asset_image_02")
    assert image_2["duration"] == 4.5
    assert round(plan["total_duration"], 3) == round(sum(float(seg["duration"]) for seg in segments), 3)
    assert (plan["render_settings"]["audio"] or {})["bgm_volume"] == 0.42

    metadata = plan["metadata"]
    assert metadata["generated_from"] == "timeline"
    assert metadata["timeline_compile_elapsed_ms"] >= 0
    assert metadata["recompute_summary"]["skipped_disabled_clips"] == 1
    assert metadata["recompute_summary"]["dirty"] is True


def test_timeline_compile_module_cli_and_worker() -> None:
    root = Path("tests/tmp_vcs_timeline_compile")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    library = mock_library()
    blueprint = mock_blueprint()
    base_render_plan = engine.Compiler(blueprint, library).compile()
    timeline = edited_timeline(build_timeline_from_blueprint(blueprint, base_render_plan, media_library=library))

    compiled = compile_from_timeline(
        timeline,
        base_render_plan,
        timeline_path="timeline.json",
        source_render_plan_path="render_plan.json",
    )
    assert_compiled_from_timeline(compiled)

    base_plan_path = root / "render_plan.json"
    timeline_path = root / "timeline.json"
    cli_output_path = root / "render_plan_from_timeline.json"
    worker_output_path = root / "render_plan_from_timeline_worker.json"
    write_json(base_plan_path, base_render_plan)
    write_json(timeline_path, timeline)

    engine.command_timeline_compile(
        Namespace(
            timeline=str(timeline_path),
            base_render_plan=str(base_plan_path),
            output=str(cli_output_path),
        )
    )
    assert_compiled_from_timeline(json.loads(cli_output_path.read_text(encoding="utf-8")))

    result = worker.run_task(
        {
            "type": "timeline-compile",
            "id": "timeline-compile-smoke",
            "timeline_path": str(timeline_path),
            "base_render_plan_path": str(base_plan_path),
            "output_path": str(worker_output_path),
        }
    )
    assert result["ok"] is True
    assert result["output_path"] == str(worker_output_path)
    assert_compiled_from_timeline(result["document"])


if __name__ == "__main__":
    test_timeline_compile_module_cli_and_worker()
    print("V5 timeline compile smoke test passed")
