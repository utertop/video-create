import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple

import imageio_ffmpeg

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
    assert [group["runtime_chunk_route"] for group in chunk_groups] == [
        "ffmpeg_image_chunk",
        "ffmpeg_direct_chunk",
        "ffmpeg_fitted_video_chunk",
    ]
    assert chunk_groups[2]["runtime_chunk_route_reason"] == "all_segments_ffmpeg_fitted_video_safe"

    direct_only_groups = engine._v56_build_chunk_groups([plan["segments"][1]], 30, {"performance_mode": "balanced"})
    assert direct_only_groups[0]["runtime_chunk_route"] == "ffmpeg_direct_chunk"
    assert direct_only_groups[0]["runtime_chunk_route_reason"] == "all_segments_direct_chunk_safe"

    image_only_groups = engine._v56_build_chunk_groups([plan["segments"][0]], 30, {"performance_mode": "balanced"})
    assert image_only_groups[0]["runtime_chunk_route"] == "ffmpeg_image_chunk"
    assert image_only_groups[0]["runtime_chunk_route_reason"] == "all_segments_ffmpeg_image_chunk_safe"

    motion_only_groups = engine._v56_build_chunk_groups([plan["segments"][2]], 30, {"performance_mode": "balanced"})
    assert motion_only_groups[0]["runtime_chunk_route"] == "ffmpeg_fitted_video_chunk"
    assert motion_only_groups[0]["runtime_chunk_route_reason"] == "all_segments_ffmpeg_fitted_video_safe"


def test_render_backend_selector_prefers_stable_for_long_video_exports() -> None:
    plan = {
        "total_duration": 720.0,
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "performance_mode": "balanced",
            "render_mode": "auto",
        },
        "segments": [{"segment_id": f"seg_{idx:03d}", "type": "image", "duration": 8.0} for idx in range(60)],
    }

    decision = engine._v56_resolve_render_backend(plan, {"performance_mode": "balanced", "render_mode": "auto"})

    assert decision["backend_name"] == "ffmpeg_stable_backend"
    assert decision["backend_family"] == "long_video_stable"
    assert decision["reason"] == "stable_renderer_selected"
    assert "legacy_moviepy_backend" in (decision.get("fallback_chain") or [])


def test_render_backend_selector_returns_formal_decision_type() -> None:
    plan = {
        "total_duration": 720.0,
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "performance_mode": "balanced",
            "render_mode": "auto",
        },
        "segments": [{"segment_id": f"seg_{idx:03d}", "type": "image", "duration": 8.0} for idx in range(60)],
    }

    decision = engine._v56_resolve_render_backend_decision(plan, {"performance_mode": "balanced", "render_mode": "auto"})

    assert isinstance(decision, engine.BackendDecision)
    assert decision.backend_name == "ffmpeg_stable_backend"
    assert decision.backend_family == "long_video_stable"
    assert decision.reason == "stable_renderer_selected"
    assert decision.to_dict()["backend_name"] == "ffmpeg_stable_backend"


def test_backend_execution_result_defaults_to_selected_backend() -> None:
    decision = engine.BackendDecision(
        backend_name="ffmpeg_stable_backend",
        backend_family="long_video_stable",
        backend_mode="final_render",
        reason="stable_renderer_selected",
        fallback_chain=["ffmpeg_stable_backend", "legacy_moviepy_backend"],
        capability_flags=["stable", "chunked", "ffmpeg", "fallback_moviepy"],
    )

    execution = engine.BackendExecutionResult.from_decision(decision)
    payload = engine._v56_backend_report_payload(execution)

    assert isinstance(execution, engine.BackendExecutionResult)
    assert execution.selected_backend_name == "ffmpeg_stable_backend"
    assert execution.actual_backend_name == "ffmpeg_stable_backend"
    assert execution.fallback_applied is False
    assert payload["selected_backend"] == "ffmpeg_stable_backend"
    assert payload["actual_backend_name"] == "ffmpeg_stable_backend"
    assert payload["fallback_used"] is None
    assert payload["fallback_applied"] is False


def test_render_diagnostics_expose_route_observability() -> None:
    plan = {
        "total_duration": 8.0,
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "performance_mode": "balanced",
            "render_mode": "standard",
        },
        "segments": [
            {
                "segment_id": "seg_diag_img",
                "type": "image",
                "duration": 4.0,
                "start_time": 0.0,
                "end_time": 4.0,
                "motion_config": {"type": "gentle_push"},
            },
            {
                "segment_id": "seg_diag_vid",
                "type": "video",
                "duration": 1.0,
                "start_time": 4.0,
                "end_time": 5.0,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
                "keep_audio": False,
            },
        ],
    }
    renderer = engine.Renderer(
        plan,
        "tests/tmp_vcs_render_diag/output.mp4",
        {"fps": 12, "quality": "draft", "render_mode": "standard", "performance_mode": "balanced"},
    )
    diagnostics = engine._v56_render_diagnostics(renderer, [], [], False, {"total_render_seconds": 1.23})

    assert diagnostics["strategy_version"] == "render_diagnostics_v2"
    assert diagnostics["routing"]["segments"]["route_counts"]["image_live_compose"] == 1
    assert diagnostics["routing"]["segments"]["route_counts"]["direct_chunk_candidate"] == 1
    assert diagnostics["timings"]["total_render_seconds"] == 1.23


def test_render_backend_selector_keeps_preview_on_legacy_backend() -> None:
    plan = {
        "total_duration": 12.0,
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "performance_mode": "balanced",
            "render_mode": "auto",
        },
        "segments": [{"segment_id": "seg_preview", "type": "image", "duration": 2.0}],
    }

    decision = engine._v56_resolve_render_backend(plan, {"preview": True, "fps": 12})

    assert decision["backend_name"] == "legacy_moviepy_backend"
    assert decision["backend_mode"] == "preview"
    assert decision["reason"] == "preview_render_uses_standard_renderer"


def test_standard_visual_chunk_groups_prefer_ffmpeg_for_safe_image_units() -> None:
    root = Path("tests/tmp_vcs_standard_visual_ffmpeg_image_chunk")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    first = root / "first.jpg"
    second = root / "second.jpg"
    engine.Image.new("RGB", (960, 540), (82, 116, 164)).save(first, quality=92)
    engine.Image.new("RGB", (960, 540), (148, 92, 74)).save(second, quality=92)

    plan = {
        "total_duration": 4.0,
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
            "render_mode": "standard",
        },
        "segments": [
            {
                "segment_id": "seg_img_1",
                "type": "image",
                "source_path": str(first),
                "duration": 2.0,
                "start_time": 0.0,
                "end_time": 2.0,
                "text": None,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "gentle_push"},
            },
            {
                "segment_id": "seg_img_2",
                "type": "image",
                "source_path": str(second),
                "duration": 2.0,
                "start_time": 2.0,
                "end_time": 4.0,
                "text": None,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "slow_push"},
            },
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(root / "output.mp4"),
        {"fps": 12, "quality": "draft", "render_mode": "standard", "performance_mode": "balanced"},
    )
    groups = renderer._build_standard_visual_chunk_groups()

    assert groups
    assert groups[0]["runtime_chunk_route"] == "ffmpeg_image_chunk"
    assert groups[0]["runtime_chunk_route_reason"] == "all_segments_ffmpeg_image_chunk_safe"


def test_standard_visual_chunk_groups_prefer_ffmpeg_for_safe_image_overlay_units() -> None:
    root = Path("tests/tmp_vcs_standard_visual_ffmpeg_image_overlay_chunk")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    first = root / "first.jpg"
    second = root / "second.jpg"
    engine.Image.new("RGB", (960, 540), (96, 126, 176)).save(first, quality=92)
    engine.Image.new("RGB", (960, 540), (160, 104, 84)).save(second, quality=92)

    plan = {
        "total_duration": 4.0,
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
            "render_mode": "standard",
        },
        "segments": [
            {
                "segment_id": "seg_img_overlay_1",
                "type": "image",
                "source_path": str(first),
                "duration": 2.0,
                "start_time": 0.0,
                "end_time": 2.0,
                "text": None,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "gentle_push"},
                "overlay_text": "Tokyo Walk",
                "overlay_subtitle": "Golden hour",
                "overlay_duration": 1.6,
                "overlay_title_style": {"preset": "minimal_editorial", "motion": "editorial_fade", "position": "lower_left"},
            },
            {
                "segment_id": "seg_img_overlay_2",
                "type": "image",
                "source_path": str(second),
                "duration": 2.0,
                "start_time": 2.0,
                "end_time": 4.0,
                "text": None,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "slow_push"},
                "overlay_text": "Neon Street",
                "overlay_subtitle": None,
                "overlay_duration": 1.4,
                "overlay_title_style": {"preset": "minimal_editorial", "motion": "editorial_fade", "position": "lower_left"},
            },
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(root / "output.mp4"),
        {"fps": 12, "quality": "draft", "render_mode": "standard", "performance_mode": "balanced"},
    )
    groups = renderer._build_standard_visual_chunk_groups()

    assert groups
    assert groups[0]["runtime_chunk_route"] == "ffmpeg_image_chunk"
    assert groups[0]["runtime_chunk_route_reason"] == "all_segments_ffmpeg_image_chunk_safe"


def test_standard_visual_chunk_groups_prefer_ffmpeg_for_static_card_units() -> None:
    root = Path("tests/tmp_vcs_standard_visual_ffmpeg_card_chunk")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    background = root / "bg.jpg"
    engine.Image.new("RGB", (960, 540), (78, 110, 150)).save(background, quality=92)

    plan = {
        "total_duration": 2.4,
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
            "render_mode": "standard",
        },
        "segments": [
            {
                "segment_id": "seg_title_1",
                "type": "title",
                "duration": 1.2,
                "text": "Static Title",
                "subtitle": "Card unit",
                "start_time": 0.0,
                "end_time": 1.2,
                "transition_config": {"type": "cut", "duration": 0},
                "title_style": {"preset": "cinematic_bold", "motion": "static_hold"},
            },
            {
                "segment_id": "seg_end_1",
                "type": "end",
                "duration": 1.2,
                "text": "Static End",
                "subtitle": "Card unit",
                "start_time": 1.2,
                "end_time": 2.4,
                "transition_config": {"type": "cut", "duration": 0},
                "title_style": {"preset": "cinematic_bold", "motion": "static_hold"},
            },
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(root / "output.mp4"),
        {
            "fps": 12,
            "quality": "draft",
            "render_mode": "standard",
            "performance_mode": "balanced",
            "title_background_path": str(background),
            "end_background_path": str(background),
            "title_style": {"preset": "cinematic_bold", "motion": "static_hold"},
            "end_title_style": {"preset": "cinematic_bold", "motion": "static_hold"},
        },
    )
    groups = renderer._build_standard_visual_chunk_groups()

    assert groups
    assert groups[0]["runtime_chunk_route"] == "ffmpeg_card_chunk"
    assert groups[0]["runtime_chunk_route_reason"] == "all_segments_ffmpeg_card_chunk_safe"


def test_standard_visual_chunk_groups_prefer_ffmpeg_for_safe_video_fit_units() -> None:
    root = Path("tests/tmp_vcs_standard_visual_ffmpeg_video_chunk")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    first = root / "first.mp4"
    second = root / "second.mp4"
    subprocess.check_call(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=12:duration=1.0",
            "-pix_fmt",
            "yuv420p",
            str(first),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.check_call(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=12:duration=1.0",
            "-pix_fmt",
            "yuv420p",
            str(second),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    plan = {
        "total_duration": 2.0,
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
            "render_mode": "standard",
        },
        "segments": [
            {
                "segment_id": "seg_vid_fit_1",
                "type": "video",
                "source_path": str(first),
                "duration": 1.0,
                "start_time": 0.0,
                "end_time": 1.0,
                "transition_config": {"type": "soft_crossfade", "duration": 0.3},
                "motion_config": {"type": "micro_zoom"},
                "keep_audio": False,
            },
            {
                "segment_id": "seg_vid_fit_2",
                "type": "video",
                "source_path": str(second),
                "duration": 1.0,
                "start_time": 1.0,
                "end_time": 2.0,
                "transition_config": {"type": "soft_crossfade", "duration": 0.3},
                "motion_config": {"type": "subtle_ken_burns"},
                "keep_audio": False,
                "overlay_text": "Safe Overlay",
                "overlay_subtitle": "Video fit",
                "overlay_duration": 1.0,
                "overlay_title_style": {"preset": "minimal_editorial", "motion": "editorial_fade", "position": "lower_left"},
            },
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(root / "output.mp4"),
        {"fps": 12, "quality": "draft", "render_mode": "standard", "performance_mode": "balanced", "edit_strategy": "fast_assembly"},
    )
    groups = renderer._build_standard_visual_chunk_groups()

    assert groups
    assert groups[0]["runtime_chunk_route"] == "ffmpeg_fitted_video_chunk"
    assert groups[0]["runtime_chunk_route_reason"] == "all_segments_ffmpeg_fitted_video_safe"


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


def test_proxy_media_manifest_is_preferred_for_preview() -> None:
    root = Path("tests/tmp_vcs_proxy_manifest")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "image_01.jpg"
    engine.Image.new("RGB", (1280, 720), (92, 138, 188)).save(source, quality=92)
    library = engine.Scanner(str(root), recursive=True).scan()
    manifest = library.get("proxy_media_manifest") or {}
    asset_entry = (manifest.get("assets") or {}).get(str(source.resolve()))
    profile = ((asset_entry or {}).get("profiles") or {}).get("preview_540p") or {}
    proxy_path = Path(str(profile.get("path") or ""))

    assert profile.get("status") == "ready"
    assert proxy_path.is_file()

    plan = {"render_settings": {"fps": 12, "aspect_ratio": "16:9"}, "segments": []}
    renderer = engine.Renderer(
        plan,
        str(root / "output.mp4"),
        {
            "preview": True,
            "preview_height": 360,
            "fps": 12,
            "quality": "draft",
            "proxy_media_manifest": manifest,
        },
    )

    resolved = renderer._get_proxy_source(source, is_video=False)
    stats = renderer._proxy_media_summary()

    assert resolved == proxy_path
    assert stats["eligible"] == 1
    assert stats["manifest_hit"] == 1
    assert stats["created"] == 0
    assert stats["fallback"] == 0


def test_stable_render_failure_report_preserves_resume_metadata() -> None:
    root = Path("tests/tmp_vcs_stable_failure_recovery")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    first = root / "first.jpg"
    second = root / "second.jpg"
    engine.Image.new("RGB", (960, 540), (84, 112, 166)).save(first, quality=92)
    engine.Image.new("RGB", (960, 540), (152, 94, 70)).save(second, quality=92)

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "long_stable",
            "performance_mode": "stable",
            "render_mode": "long_stable",
        },
        "total_duration": 2.0,
        "segments": [
            {
                "segment_id": "seg_fail_0001",
                "type": "image",
                "source_path": str(first),
                "duration": 1.0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": None,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "gentle_push"},
            },
            {
                "segment_id": "seg_fail_0002",
                "type": "image",
                "source_path": str(second),
                "duration": 1.0,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": None,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "slow_push"},
            },
        ],
    }
    output = root / "output.mp4"
    params = {"fps": 12, "quality": "draft", "render_mode": "long_stable", "performance_mode": "stable"}

    original = engine._v56_write_chunk_video

    def failing_once(renderer, chunk, chunk_path, fps, render_params, ensure_audio_track=False):
        raise RuntimeError("forced chunk failure for observability")

    engine._v56_write_chunk_video = failing_once
    try:
        try:
            engine.V56StableRenderer(plan, str(output), params).render()
            raise AssertionError("expected stable renderer to fail")
        except RuntimeError as exc:
            assert "forced chunk failure" in str(exc)
    finally:
        engine._v56_write_chunk_video = original

    report = engine.read_json(str(root / ".video_create_project" / "build_report.json"))
    manifest = engine.read_json(str(root / ".video_create_project" / "chunks" / output.stem / "chunk_manifest.json"))

    assert report["status"] == "failed"
    assert report["failed_stage"] == "chunk_render"
    assert report["failure"]["retryable"] is True
    assert report["recovery"]["resumable"] is True
    assert report["recovery"]["failed_chunk"] == "chunk_000.mp4"
    assert manifest["last_failed_chunk"] == "chunk_000.mp4"
    assert manifest["chunks"]["chunk_000.mp4"]["failure"]["code"] == "chunk_render_failed"
    assert manifest["chunks"]["chunk_000.mp4"]["attempt_count"] == 1


def _stable_failure_plan(root: Path) -> Tuple[Dict, Path, Dict]:
    first = root / "first.jpg"
    second = root / "second.jpg"
    engine.Image.new("RGB", (960, 540), (84, 112, 166)).save(first, quality=92)
    engine.Image.new("RGB", (960, 540), (152, 94, 70)).save(second, quality=92)
    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "long_stable",
            "performance_mode": "stable",
            "render_mode": "long_stable",
        },
        "total_duration": 2.0,
        "segments": [
            {
                "segment_id": "seg_fail_0001",
                "type": "image",
                "source_path": str(first),
                "duration": 1.0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": None,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "gentle_push"},
            },
            {
                "segment_id": "seg_fail_0002",
                "type": "image",
                "source_path": str(second),
                "duration": 1.0,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": None,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "slow_push"},
            },
        ],
    }
    output = root / "output.mp4"
    params = {"fps": 12, "quality": "draft", "render_mode": "long_stable", "performance_mode": "stable"}
    return plan, output, params


def test_stable_render_concat_failure_report_is_written() -> None:
    root = Path("tests/tmp_vcs_stable_concat_failure")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    plan, output, params = _stable_failure_plan(root)

    original_copy = engine._v56_concat_chunks_ffmpeg
    original_reencode = engine._v56_concat_chunks_ffmpeg_reencode
    original_moviepy = engine._v56_concat_chunks_moviepy

    engine._v56_concat_chunks_ffmpeg = lambda *args, **kwargs: False
    engine._v56_concat_chunks_ffmpeg_reencode = lambda *args, **kwargs: False

    def fail_moviepy(*args, **kwargs):
        raise RuntimeError("forced concat failure for recovery")

    engine._v56_concat_chunks_moviepy = fail_moviepy
    try:
        try:
            engine.V56StableRenderer(plan, str(output), params).render()
            raise AssertionError("expected concat failure")
        except RuntimeError as exc:
            assert "forced concat failure" in str(exc)
    finally:
        engine._v56_concat_chunks_ffmpeg = original_copy
        engine._v56_concat_chunks_ffmpeg_reencode = original_reencode
        engine._v56_concat_chunks_moviepy = original_moviepy

    report = engine.read_json(str(root / ".video_create_project" / "build_report.json"))
    assert report["failed_stage"] == "concat"
    assert report["failure"]["code"] == "concat_failed"
    assert report["recovery"]["resumable"] is True


def test_stable_render_audio_mix_failure_report_is_written() -> None:
    root = Path("tests/tmp_vcs_stable_audio_failure")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    plan, output, params = _stable_failure_plan(root)

    original_safe_mix = engine._v56_safe_apply_final_bgm_mix
    engine._v56_safe_apply_final_bgm_mix = lambda *args, **kwargs: (False, RuntimeError("forced audio mix failure"))
    try:
        try:
            engine.V56StableRenderer(plan, str(output), params).render()
            raise AssertionError("expected audio mix failure")
        except RuntimeError as exc:
            assert "forced audio mix failure" in str(exc)
    finally:
        engine._v56_safe_apply_final_bgm_mix = original_safe_mix

    report = engine.read_json(str(root / ".video_create_project" / "build_report.json"))
    assert report["failed_stage"] == "audio_mix"
    assert report["failure"]["code"] == "audio_mix_failed"
    assert report["recovery"]["resumable"] is True


def test_stable_render_output_validate_failure_report_is_written() -> None:
    root = Path("tests/tmp_vcs_stable_output_validate_failure")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    plan, output, params = _stable_failure_plan(root)

    original_validate = engine._v56_validate_video
    original_safe_mix = engine._v56_safe_apply_final_bgm_mix

    def patched_validate(path, *args, **kwargs):
        candidate = Path(path)
        if candidate == output.with_suffix(".rendering.tmp.mp4"):
            return False, "forced final validation failure", 0.0
        return original_validate(path, *args, **kwargs)

    engine._v56_validate_video = patched_validate
    engine._v56_safe_apply_final_bgm_mix = lambda *args, **kwargs: (False, None)
    try:
        try:
            engine.V56StableRenderer(plan, str(output), params).render()
            raise AssertionError("expected output validation failure")
        except RuntimeError as exc:
            assert "forced final validation failure" in str(exc)
    finally:
        engine._v56_validate_video = original_validate
        engine._v56_safe_apply_final_bgm_mix = original_safe_mix

    report = engine.read_json(str(root / ".video_create_project" / "build_report.json"))
    assert report["failed_stage"] == "output_validate"
    assert report["failure"]["code"] == "output_validation_failed"
    assert report["recovery"]["resumable"] is True


if __name__ == "__main__":
    test_compile_emits_render_scheduler_hints()
    test_renderer_applies_runtime_render_routes()
    test_render_backend_selector_prefers_stable_for_long_video_exports()
    test_render_backend_selector_returns_formal_decision_type()
    test_backend_execution_result_defaults_to_selected_backend()
    test_render_diagnostics_expose_route_observability()
    test_render_backend_selector_keeps_preview_on_legacy_backend()
    test_stable_chunk_cache_key_tracks_source_file_changes()
    test_proxy_media_cache_is_opt_in_and_reportable()
    test_proxy_media_manifest_is_preferred_for_preview()
    test_stable_render_failure_report_preserves_resume_metadata()
    print("V5 render scheduler smoke test passed")
