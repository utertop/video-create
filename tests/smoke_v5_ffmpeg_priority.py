import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import imageio_ffmpeg

import video_engine_v5 as engine


def make_video(path: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.check_call(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=12:duration=1.0",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def make_video_with_audio(path: Path) -> None:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.check_call(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=12:duration=1.0",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=48000:duration=1.0",
            "-shortest",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def test_ffmpeg_priority_fits_simple_video_segments() -> None:
    root = Path("tests/tmp_vcs_ffmpeg_priority")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "source.mp4"
    output = root / "output.mp4"
    make_video(source)

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
        },
        "segments": [
            {
                "segment_id": "seg_00000",
                "type": "video",
                "source_path": str(source),
                "duration": 0.8,
                "text": None,
                "subtitle": None,
                "start_time": 0,
                "end_time": 0.8,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
                "rhythm_config": {"pace": "fast_review", "role": "footage"},
                "keep_audio": False,
            }
        ],
    }

    engine.Renderer(plan, str(output), {"fps": 12, "quality": "draft", "edit_strategy": "fast_assembly"}).render()
    ok, reason, _duration = engine._v56_validate_video(output, min_size=512)

    assert ok, reason
    fitted = list((root / ".video_create_project" / "render_cache" / "fitted_videos").glob("*.mp4"))
    assert fitted, "expected FFmpeg fitted video cache"


def test_ffmpeg_video_segment_cache_stats() -> None:
    root = Path("tests/tmp_vcs_ffmpeg_video_cache_stats")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "source.mp4"
    output = root / "output.mp4"
    make_video(source)

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
        },
        "segments": [
            {
                "segment_id": "seg_cache_00000",
                "type": "video",
                "source_path": str(source),
                "duration": 0.8,
                "text": None,
                "subtitle": None,
                "start_time": 0,
                "end_time": 0.8,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
                "rhythm_config": {"pace": "fast_review", "role": "footage"},
                "keep_audio": False,
            }
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(output),
        {"fps": 12, "quality": "draft", "edit_strategy": "fast_assembly", "performance_mode": "balanced"},
    )
    clip = renderer._video_clip(source, 0.8, keep_audio=False, motion_config={"type": "none"}, prefer_ffmpeg=True)
    assert renderer.video_segment_cache_stats["eligible"] == 1
    assert renderer.video_segment_cache_stats["created"] == 1
    assert renderer.video_segment_cache_stats["hit"] == 0
    engine.close_clip(clip)

    clip_again = renderer._video_clip(source, 0.8, keep_audio=False, motion_config={"type": "none"}, prefer_ffmpeg=True)
    assert renderer.video_segment_cache_stats["eligible"] == 2
    assert renderer.video_segment_cache_stats["created"] == 1
    assert renderer.video_segment_cache_stats["hit"] == 1
    assert renderer.video_segment_cache_stats["saved_live_fits"] == 1
    assert renderer.video_segment_cache_stats["saved_render_seconds"] == 1
    engine.close_clip(clip_again)


def test_ffmpeg_priority_writes_lightweight_chunk_directly() -> None:
    root = Path("tests/tmp_vcs_ffmpeg_direct_chunk")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source_a = root / "source_a.mp4"
    source_b = root / "source_b.mp4"
    chunk_path = root / "chunk_000.mp4"
    make_video(source_a)
    make_video(source_b)

    segments = []
    for idx, source in enumerate([source_a, source_b]):
        segments.append(
            {
                "segment_id": f"seg_{idx:05d}",
                "type": "video",
                "source_path": str(source),
                "duration": 0.6,
                "text": None,
                "subtitle": None,
                "start_time": idx * 0.6,
                "end_time": (idx + 1) * 0.6,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
                "rhythm_config": {"pace": "fast_review", "role": "footage"},
                "keep_audio": False,
            }
        )

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "stable",
        },
        "segments": segments,
    }
    params = {"fps": 12, "quality": "draft", "edit_strategy": "fast_assembly", "performance_mode": "stable"}
    renderer = engine.Renderer(plan, str(root / "output.mp4"), params)

    engine._v56_write_chunk_video(renderer, {"index": 0, "segments": segments}, chunk_path, 12, params)
    ok, reason, duration = engine._v56_validate_video(chunk_path, min_size=512)

    assert ok, reason
    assert duration and duration > 0.9
    fitted = list((root / ".video_create_project" / "render_cache" / "fitted_videos").glob("*.mp4"))
    assert len(fitted) == 2


def test_ffmpeg_direct_chunk_unifies_source_and_silent_audio() -> None:
    root = Path("tests/tmp_vcs_ffmpeg_direct_audio_chunk")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source_with_audio = root / "source_audio.mp4"
    source_silent = root / "source_silent.mp4"
    chunk_path = root / "chunk_000.mp4"
    make_video_with_audio(source_with_audio)
    make_video(source_silent)

    segments = []
    for idx, source in enumerate([source_with_audio, source_silent]):
        segments.append(
            {
                "segment_id": f"seg_audio_{idx:05d}",
                "type": "video",
                "source_path": str(source),
                "duration": 0.6,
                "text": None,
                "subtitle": None,
                "start_time": idx * 0.6,
                "end_time": (idx + 1) * 0.6,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
                "rhythm_config": {"pace": "fast_review", "role": "footage"},
                "keep_audio": True,
            }
        )

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "stable",
        },
        "segments": segments,
    }
    params = {"fps": 12, "quality": "draft", "edit_strategy": "fast_assembly", "performance_mode": "stable"}
    renderer = engine.Renderer(plan, str(root / "output.mp4"), params)

    engine._v56_write_chunk_video(renderer, {"index": 0, "segments": segments}, chunk_path, 12, params)
    ok, reason, duration = engine._v56_validate_video(chunk_path, min_size=512)

    assert ok, reason
    assert duration and duration > 0.9
    assert engine.video_has_audio_stream(chunk_path), "expected unified AAC audio track in direct FFmpeg chunk"
    prepared_audio = renderer._prepare_source_audio_path(source_with_audio)
    assert prepared_audio is not None
    assert prepared_audio.exists()
    assert prepared_audio.parent == root / ".video_create_project" / "audio_cache" / "normalized"
    prepared_mtime = prepared_audio.stat().st_mtime_ns
    prepared_again = renderer._prepare_source_audio_path(source_with_audio)
    assert prepared_again == prepared_audio
    assert prepared_again.stat().st_mtime_ns == prepared_mtime


def test_ffmpeg_concat_keeps_audio_chunks_out_of_moviepy() -> None:
    root = Path("tests/tmp_vcs_ffmpeg_concat_audio")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source_with_audio = root / "source_audio.mp4"
    source_silent = root / "source_silent.mp4"
    chunk_a = root / "chunk_a.mp4"
    chunk_b = root / "chunk_b.mp4"
    merged = root / "merged.mp4"
    make_video_with_audio(source_with_audio)
    make_video(source_silent)

    segments = [
        {
            "segment_id": "seg_audio_a",
            "type": "video",
            "source_path": str(source_with_audio),
            "duration": 0.8,
            "text": None,
            "subtitle": None,
            "start_time": 0.0,
            "end_time": 0.8,
            "transition": "cut",
            "transition_config": {"type": "cut", "duration": 0},
            "motion_config": {"type": "none"},
            "rhythm_config": {"pace": "fast_review", "role": "footage"},
            "keep_audio": True,
        },
        {
            "segment_id": "seg_audio_b",
            "type": "video",
            "source_path": str(source_silent),
            "duration": 0.8,
            "text": None,
            "subtitle": None,
            "start_time": 0.8,
            "end_time": 1.6,
            "transition": "cut",
            "transition_config": {"type": "cut", "duration": 0},
            "motion_config": {"type": "none"},
            "rhythm_config": {"pace": "fast_review", "role": "footage"},
            "keep_audio": True,
        },
    ]
    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "stable",
        },
        "segments": segments,
    }
    params = {"fps": 12, "quality": "draft", "edit_strategy": "fast_assembly", "performance_mode": "stable"}
    renderer = engine.Renderer(plan, str(root / "output.mp4"), params)

    engine._v56_write_chunk_video(renderer, {"index": 0, "segments": segments}, chunk_a, 12, params)
    engine._v56_write_chunk_video(renderer, {"index": 1, "segments": segments}, chunk_b, 12, params)
    concat_ok = engine._v56_concat_chunks_ffmpeg([chunk_a, chunk_b], merged, root)
    assert concat_ok, "expected FFmpeg concat copy to merge audio-ready chunks"
    ok, reason, duration = engine._v56_validate_video(merged, min_size=512)
    assert ok, reason
    assert duration and duration > 2.5
    assert engine.video_has_audio_stream(merged), "expected merged ffmpeg output to keep audio stream"


def test_ffmpeg_fitted_video_allows_lightweight_overlay_and_soft_transition() -> None:
    root = Path("tests/tmp_vcs_ffmpeg_overlay_fit")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "source.mp4"
    output = root / "output.mp4"
    make_video(source)

    segment = {
        "segment_id": "seg_overlay_fit",
        "type": "video",
        "source_path": str(source),
        "duration": 1.0,
        "text": None,
        "subtitle": None,
        "start_time": 0.0,
        "end_time": 1.0,
        "transition": "soft_crossfade",
        "transition_config": {"type": "soft_crossfade", "duration": 0.32},
        "motion_config": {"type": "none"},
        "rhythm_config": {"pace": "medium", "role": "footage"},
        "keep_audio": False,
        "overlay_text": "Tokyo Walk",
        "overlay_subtitle": "Golden hour",
        "overlay_duration": 1.8,
        "overlay_title_style": {"preset": "cinematic_bold", "motion": "editorial_fade", "position": "lower_left"},
    }
    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
        },
        "segments": [segment],
    }
    renderer = engine.Renderer(
        plan,
        str(output),
        {"fps": 12, "quality": "draft", "edit_strategy": "fast_assembly", "performance_mode": "balanced"},
    )

    assert renderer._can_use_ffmpeg_fitted_video(segment) is True
    assert renderer._can_use_ffmpeg_direct_chunk_segment(segment) is False

    clip = renderer._video_clip(source, 1.0, keep_audio=False, motion_config={"type": "none"}, prefer_ffmpeg=True)
    fitted = list((root / ".video_create_project" / "render_cache" / "fitted_videos").glob("*.mp4"))
    assert fitted, "expected lightweight overlay segment to still create FFmpeg fitted cache"
    engine.close_clip(clip)


def test_ffmpeg_fitted_video_rejects_unsafe_overlay_or_motion_for_safe_expansion() -> None:
    root = Path("tests/tmp_vcs_ffmpeg_overlay_reject")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "source.mp4"
    output = root / "output.mp4"
    make_video(source)

    base_plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
        },
        "segments": [],
    }
    renderer = engine.Renderer(
        base_plan,
        str(output),
        {"fps": 12, "quality": "draft", "edit_strategy": "fast_assembly", "performance_mode": "balanced"},
    )

    unsafe_overlay = {
        "segment_id": "seg_overlay_reject",
        "type": "video",
        "source_path": str(source),
        "duration": 1.0,
        "transition": "soft_crossfade",
        "transition_config": {"type": "soft_crossfade", "duration": 0.32},
        "motion_config": {"type": "none"},
        "overlay_text": "X" * 60,
        "overlay_subtitle": None,
        "overlay_duration": 1.8,
        "overlay_title_style": {"preset": "cinematic_bold", "motion": "editorial_fade", "position": "lower_left"},
        "keep_audio": False,
    }
    moving_segment = {
        "segment_id": "seg_motion_reject",
        "type": "video",
        "source_path": str(source),
        "duration": 1.0,
        "transition": "cut",
        "transition_config": {"type": "cut", "duration": 0},
        "motion_config": {"type": "ken_burns"},
        "keep_audio": False,
    }

    assert renderer._can_use_ffmpeg_fitted_video(unsafe_overlay) is False
    assert renderer._can_use_ffmpeg_fitted_video(moving_segment) is False


def test_ffmpeg_motion_cache_handles_simple_video_motion() -> None:
    root = Path("tests/tmp_vcs_ffmpeg_motion_cache")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "source.mp4"
    output = root / "output.mp4"
    make_video(source)

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "edit_strategy": "fast_assembly",
            "performance_mode": "balanced",
        },
        "segments": [
            {
                "segment_id": "seg_motion_cache_00000",
                "type": "video",
                "source_path": str(source),
                "duration": 0.9,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "gentle_push"},
                "keep_audio": False,
            }
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(output),
        {"fps": 12, "quality": "draft", "edit_strategy": "fast_assembly", "performance_mode": "balanced"},
    )
    segment = plan["segments"][0]
    assert renderer._can_use_ffmpeg_fitted_video(segment) is True
    assert renderer._can_use_ffmpeg_direct_chunk_segment(segment) is False

    clip = renderer._video_clip(source, 0.9, keep_audio=False, motion_config={"type": "gentle_push"}, prefer_ffmpeg=True)
    motion_cache = list((root / ".video_create_project" / "render_cache" / "motion_fitted_videos").glob("*.mp4"))
    assert motion_cache, "expected FFmpeg motion-fitted cache for simple video motion"
    assert renderer.video_segment_cache_stats["motion_eligible"] == 1
    assert renderer.video_segment_cache_stats["motion_created"] == 1
    engine.close_clip(clip)

    clip_again = renderer._video_clip(source, 0.9, keep_audio=False, motion_config={"type": "gentle_push"}, prefer_ffmpeg=True)
    assert renderer.video_segment_cache_stats["motion_hit"] == 1
    assert renderer.video_segment_cache_stats["saved_live_fits"] >= 1
    engine.close_clip(clip_again)


if __name__ == "__main__":
    test_ffmpeg_priority_fits_simple_video_segments()
    test_ffmpeg_video_segment_cache_stats()
    test_ffmpeg_priority_writes_lightweight_chunk_directly()
    test_ffmpeg_direct_chunk_unifies_source_and_silent_audio()
    test_ffmpeg_concat_keeps_audio_chunks_out_of_moviepy()
    test_ffmpeg_fitted_video_allows_lightweight_overlay_and_soft_transition()
    test_ffmpeg_fitted_video_rejects_unsafe_overlay_or_motion_for_safe_expansion()
    test_ffmpeg_motion_cache_handles_simple_video_motion()
    print("V5 FFmpeg priority smoke test passed")
