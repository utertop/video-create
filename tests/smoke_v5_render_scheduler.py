import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def test_compile_emits_render_scheduler_hints() -> None:
    library = {
        "assets": [
            {
                "asset_id": "asset_video_01",
                "type": "video",
                "status": "ok",
                "absolute_path": "D:/mock/video_01.mp4",
                "media": {"orientation": "landscape"},
            },
            {
                "asset_id": "asset_image_01",
                "type": "image",
                "status": "ok",
                "absolute_path": "D:/mock/image_01.jpg",
                "media": {"orientation": "landscape"},
            },
        ]
    }
    blueprint = {
        "title": "Scheduler Smoke",
        "subtitle": None,
        "metadata": {
            "edit_strategy": "fast_assembly",
            "transition_profile": "fast_assembly",
            "rhythm_profile": "fast_assembly",
            "performance_mode": "stable",
        },
        "sections": [
            {
                "section_id": "section_city",
                "section_type": "city",
                "title": "City",
                "subtitle": None,
                "enabled": True,
                "asset_refs": [
                    {"asset_id": "asset_video_01", "enabled": True},
                    {"asset_id": "asset_image_01", "enabled": True},
                ],
                "children": [],
            }
        ],
    }

    plan = engine.Compiler(blueprint, library).compile()
    scheduler = plan.get("render_scheduler") or {}
    counts = scheduler.get("route_counts") or {}
    segments = plan.get("segments") or []

    assert scheduler.get("strategy_version") == "segment_rules_v1"
    assert sum(counts.values()) == len(segments)
    assert any(seg.get("render_route") for seg in segments)
    assert "photo_prerender" in counts or "direct_chunk_candidate" in counts or "video_fit" in counts


def test_renderer_applies_runtime_render_routes() -> None:
    root = Path("tests/tmp_vcs_render_scheduler")
    root.mkdir(parents=True, exist_ok=True)
    plan = {
        "total_duration": 320.0,
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
            "render_mode": "standard",
        },
        "segments": [
            {
                "segment_id": "seg_img",
                "type": "image",
                "source_path": str(root / "image_01.jpg"),
                "duration": 4.0,
                "text": None,
                "subtitle": None,
                "start_time": 0.0,
                "end_time": 4.0,
                "motion_config": {"type": "gentle_push"},
            },
            {
                "segment_id": "seg_vid_chunk",
                "type": "video",
                "source_path": str(root / "video_01.mp4"),
                "duration": 0.8,
                "text": None,
                "subtitle": None,
                "start_time": 4.0,
                "end_time": 4.8,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
                "keep_audio": False,
            },
            {
                "segment_id": "seg_vid_motion",
                "type": "video",
                "source_path": str(root / "video_02.mp4"),
                "duration": 1.2,
                "text": None,
                "subtitle": None,
                "start_time": 4.8,
                "end_time": 6.0,
                "transition": "soft_crossfade",
                "transition_config": {"type": "soft_crossfade", "duration": 0.32},
                "motion_config": {"type": "gentle_push"},
                "keep_audio": False,
            },
        ],
    }
    renderer = engine.Renderer(
        plan,
        str(root / "output.mp4"),
        {"fps": 12, "quality": "draft", "edit_strategy": "fast_assembly", "performance_mode": "balanced"},
    )
    routes = {seg["segment_id"]: seg.get("runtime_render_route") for seg in plan["segments"]}
    counts = renderer.render_scheduler_summary.get("route_counts") or {}

    assert routes["seg_img"] == "photo_prerender"
    assert routes["seg_vid_chunk"] == "direct_chunk_candidate"
    assert routes["seg_vid_motion"] == "video_motion_fit"
    assert counts.get("photo_prerender") == 1
    assert counts.get("direct_chunk_candidate") == 1
    assert counts.get("video_motion_fit") == 1

    chunk_groups = engine._v56_build_chunk_groups(plan["segments"], 30, {"performance_mode": "balanced"})
    assert chunk_groups[0]["runtime_chunk_route"] == "moviepy_chunk"
    assert chunk_groups[0]["runtime_chunk_route_reason"] == "contains_timeline_or_image_segments"

    direct_only_groups = engine._v56_build_chunk_groups([plan["segments"][1]], 30, {"performance_mode": "balanced"})
    assert direct_only_groups[0]["runtime_chunk_route"] == "ffmpeg_direct_chunk"
    assert direct_only_groups[0]["runtime_chunk_route_reason"] == "all_segments_direct_chunk_safe"


if __name__ == "__main__":
    test_compile_emits_render_scheduler_hints()
    test_renderer_applies_runtime_render_routes()
    print("V5 render scheduler smoke test passed")
