from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def make_image(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (960, 540), color)
    image.save(path, quality=92)


def make_bgm(path: Path, frequency: int, duration: float = 3.0) -> None:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def test_standard_render_reuses_visual_base_when_only_bgm_changes() -> None:
    root = Path("tests/tmp_vcs_audio_visual_cache_standard")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    first = root / "first.jpg"
    second = root / "second.jpg"
    bgm_a = root / "bgm_a.m4a"
    bgm_b = root / "bgm_b.m4a"
    output_a = root / "mix_a.mp4"
    output_b = root / "mix_b.mp4"
    make_image(first, (72, 118, 84))
    make_image(second, (148, 94, 66))
    make_bgm(bgm_a, 440, duration=3.0)
    make_bgm(bgm_b, 660, duration=3.0)

    plan = {
        "document_type": "render_plan",
        "render_settings": {"fps": 12, "aspect_ratio": "16:9", "quality": "draft"},
        "total_duration": 2.0,
        "segments": [
            {
                "segment_id": "seg_00001",
                "type": "image",
                "source_path": str(first),
                "duration": 1.0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": None,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_00002",
                "type": "image",
                "source_path": str(second),
                "duration": 1.0,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": None,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
        ],
    }

    params_a = {
        "preview": True,
        "preview_height": 360,
        "fps": 12,
        "quality": "draft",
        "audio": {
            "music_mode": "manual",
            "music_path": str(bgm_a),
            "music_source": "manual",
            "bgm_volume": 0.22,
            "source_audio_volume": 1.0,
            "keep_source_audio": True,
            "auto_ducking": True,
            "fade_in_seconds": 0.0,
            "fade_out_seconds": 0.0,
        },
    }
    params_b = {
        "preview": True,
        "preview_height": 360,
        "fps": 12,
        "quality": "draft",
        "audio": {
            "music_mode": "manual",
            "music_path": str(bgm_b),
            "music_source": "manual",
            "bgm_volume": 0.35,
            "source_audio_volume": 1.0,
            "keep_source_audio": True,
            "auto_ducking": False,
            "fade_in_seconds": 0.2,
            "fade_out_seconds": 0.2,
        },
    }

    renderer_a = engine.Renderer(plan, str(output_a), params_a)
    renderer_a.render()
    cache_dir = root / ".video_create_project" / "render_cache" / "final_video_bases"
    cached = list(cache_dir.glob("*.mp4"))
    assert len(cached) == 1, "expected exactly one cached visual base video"
    cache_path = cached[0]
    first_mtime = cache_path.stat().st_mtime_ns
    assert renderer_a.visual_base_cache_stats["created"] == 1
    assert renderer_a.visual_base_cache_stats["hit"] == 0
    assert engine.video_has_audio_stream(output_a)

    renderer_b = engine.Renderer(plan, str(output_b), params_b)
    renderer_b.render()
    cached_again = list(cache_dir.glob("*.mp4"))
    assert len(cached_again) == 1
    assert cached_again[0].stat().st_mtime_ns == first_mtime
    assert renderer_b.visual_base_cache_stats["created"] == 0
    assert renderer_b.visual_base_cache_stats["hit"] == 1
    assert engine.video_has_audio_stream(output_b)


def test_stable_chunk_cache_key_ignores_bgm_only_changes() -> None:
    root = Path("tests/tmp_vcs_audio_visual_cache_stable")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    image_path = root / "photo.jpg"
    make_image(image_path, (84, 108, 152))

    segment = {
        "segment_id": "seg_00001",
        "type": "image",
        "source_path": str(image_path),
        "duration": 1.2,
        "start_time": 0.0,
        "end_time": 1.2,
        "text": None,
        "subtitle": None,
        "transition_config": {"type": "cut", "duration": 0},
        "motion_config": {"type": "none"},
        "runtime_render_route": "photo_prerender",
    }

    params_a = {
        "fps": 12,
        "quality": "draft",
        "audio": {
            "music_mode": "manual",
            "music_path": str(root / "bgm_a.m4a"),
            "bgm_volume": 0.2,
            "auto_ducking": True,
            "keep_source_audio": True,
            "source_audio_volume": 1.0,
            "normalize_audio": False,
            "target_lufs": -16.0,
        },
    }
    params_b = {
        "fps": 12,
        "quality": "draft",
        "audio": {
            "music_mode": "manual",
            "music_path": str(root / "bgm_b.m4a"),
            "bgm_volume": 0.45,
            "auto_ducking": False,
            "keep_source_audio": True,
            "source_audio_volume": 1.0,
            "normalize_audio": False,
            "target_lufs": -16.0,
        },
    }
    params_c = {
        "fps": 12,
        "quality": "draft",
        "audio": {
            "music_mode": "manual",
            "music_path": str(root / "bgm_b.m4a"),
            "bgm_volume": 0.45,
            "auto_ducking": False,
            "keep_source_audio": True,
            "source_audio_volume": 0.5,
            "normalize_audio": False,
            "target_lufs": -16.0,
        },
    }

    key_a = engine._v56_segment_cache_key(segment, params_a)
    key_b = engine._v56_segment_cache_key(segment, params_b)
    key_c = engine._v56_segment_cache_key(segment, params_c)

    assert key_a == key_b, "BGM-only changes should not invalidate stable chunk cache keys"
    assert key_a != key_c, "source audio gain changes must still invalidate stable chunk cache keys"


if __name__ == "__main__":
    test_standard_render_reuses_visual_base_when_only_bgm_changes()
    test_stable_chunk_cache_key_ignores_bgm_only_changes()
    print("V5 audio visual cache smoke test passed")
