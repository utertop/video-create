import sys
from pathlib import Path
import shutil

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


def test_stable_chunk_cache_key_tracks_source_file_changes() -> None:
    root = Path("tests/tmp_vcs_smart_invalidation")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "clip.mp4"
    source.write_bytes(b"old source")
    seg = {
        "segment_id": "seg_cache_key",
        "type": "video",
        "source_path": str(source),
        "duration": 1.0,
        "transition_config": {"type": "cut", "duration": 0},
        "motion_config": {"type": "none"},
        "keep_audio": False,
    }
    params = {"fps": 12, "quality": "draft"}

    first = engine._v56_segment_cache_key(seg, params)
    source.write_bytes(b"new source with different bytes")
    second = engine._v56_segment_cache_key(seg, params)

    assert first != second, "stable chunk cache key must invalidate when source file content changes"


def test_proxy_media_cache_is_opt_in_and_reportable() -> None:
    root = Path("tests/tmp_vcs_proxy_media")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "image_01.jpg"
    engine.Image.new("RGB", (320, 180), (64, 120, 180)).save(source, quality=90)
    plan = {"render_settings": {"fps": 12, "aspect_ratio": "16:9"}, "segments": []}
    renderer = engine.Renderer(
        plan,
        str(root / "output.mp4"),
        {"fps": 12, "quality": "draft", "proxy_media": True},
    )

    proxy_a = renderer._get_proxy_source(source, is_video=False)
    proxy_b = renderer._get_proxy_source(source, is_video=False)
    stats = renderer._proxy_media_summary()

    assert proxy_a == proxy_b
    assert proxy_a.exists()
    assert proxy_a.parent == root / ".video_create_project" / "proxies"
    assert stats["eligible"] == 2
    assert stats["created"] == 1
    assert stats["hit"] == 1
    assert stats["fallback"] == 0


if __name__ == "__main__":
    test_compile_emits_render_scheduler_hints()
    test_renderer_applies_runtime_render_routes()
    test_stable_chunk_cache_key_tracks_source_file_changes()
    test_proxy_media_cache_is_opt_in_and_reportable()
    print("V5 render scheduler smoke test passed")
