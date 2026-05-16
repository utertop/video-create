from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def make_image(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (1200, 800), color)
    image.save(path, quality=92)


def test_photo_segment_prerender_cache() -> None:
    root = Path("tests/tmp_vcs_photo_segment_cache")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "photo.jpg"
    output = root / "photo_output.mp4"
    make_image(source, (66, 120, 88))

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "quality": "draft",
            "performance_mode": "stable",
            "render_mode": "long_stable",
        },
        "total_duration": 720.0,
        "segments": [
            {
                "segment_id": "seg_photo_0001",
                "type": "image",
                "source_path": str(source),
                "duration": 2.0,
                "text": None,
                "subtitle": None,
                "start_time": 0.0,
                "end_time": 2.0,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "subtle_ken_burns"},
            }
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(output),
        {
            "fps": 12,
            "quality": "draft",
            "performance_mode": "stable",
            "render_mode": "long_stable",
        },
    )
    clip = renderer._image_clip(source, 2.0, {"type": "subtle_ken_burns"})
    cache_dir = root / ".video_create_project" / "render_cache" / "photo_segments"
    cached = list(cache_dir.glob("*.mp4"))
    assert cached, "expected prerendered photo segment cache"
    cached_path = cached[0]
    first_mtime = cached_path.stat().st_mtime_ns
    assert renderer.photo_segment_cache_stats["eligible"] == 1
    assert renderer.photo_segment_cache_stats["created"] == 1
    assert renderer.photo_segment_cache_stats["hit"] == 0
    assert renderer.photo_segment_cache_stats["saved_live_composes"] == 0
    assert renderer.photo_segment_cache_stats["saved_render_seconds"] == 0
    engine.close_clip(clip)

    clip_again = renderer._image_clip(source, 2.0, {"type": "subtle_ken_burns"})
    cached_again = list(cache_dir.glob("*.mp4"))
    assert len(cached_again) == 1
    assert cached_again[0].stat().st_mtime_ns == first_mtime
    assert renderer.photo_segment_cache_stats["eligible"] == 2
    assert renderer.photo_segment_cache_stats["created"] == 1
    assert renderer.photo_segment_cache_stats["hit"] == 1
    assert renderer.photo_segment_cache_stats["saved_live_composes"] == 1
    assert renderer.photo_segment_cache_stats["saved_render_seconds"] == 2
    engine.close_clip(clip_again)


def test_photo_segment_cache_balanced_medium_project() -> None:
    root = Path("tests/tmp_vcs_photo_segment_cache_balanced")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "photo.jpg"
    output = root / "photo_output.mp4"
    make_image(source, (110, 84, 132))

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "quality": "draft",
            "performance_mode": "balanced",
            "render_mode": "standard",
        },
        "total_duration": 300.0,
        "segments": [
            {
                "segment_id": "seg_photo_balanced_0001",
                "type": "image",
                "source_path": str(source),
                "duration": 2.0,
                "text": None,
                "subtitle": None,
                "start_time": 0.0,
                "end_time": 2.0,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "gentle_push"},
            }
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(output),
        {
            "fps": 12,
            "quality": "draft",
            "performance_mode": "balanced",
            "render_mode": "standard",
        },
    )
    clip = renderer._image_clip(source, 2.0, {"type": "gentle_push"})
    cache_dir = root / ".video_create_project" / "render_cache" / "photo_segments"
    cached = list(cache_dir.glob("*.mp4"))
    assert cached, "expected prerendered photo segment cache for balanced medium project"
    assert renderer.photo_segment_cache_stats["eligible"] == 1
    assert renderer.photo_segment_cache_stats["created"] == 1
    engine.close_clip(clip)


def test_photo_segment_cache_with_light_overlay() -> None:
    root = Path("tests/tmp_vcs_photo_segment_cache_overlay")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "photo.jpg"
    output = root / "photo_output.mp4"
    make_image(source, (92, 128, 154))

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "quality": "draft",
            "performance_mode": "stable",
            "render_mode": "long_stable",
        },
        "total_duration": 720.0,
        "segments": [
            {
                "segment_id": "seg_photo_overlay_0001",
                "type": "image",
                "source_path": str(source),
                "duration": 2.5,
                "text": None,
                "subtitle": None,
                "start_time": 0.0,
                "end_time": 2.5,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "gentle_push"},
                "overlay_text": "Tokyo Walk",
                "overlay_subtitle": "City lights",
                "overlay_duration": 1.6,
                "overlay_title_style": {
                    "preset": "travel_postcard",
                    "motion": "postcard_drift",
                    "position": "lower_left",
                },
            }
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(output),
        {
            "fps": 12,
            "quality": "draft",
            "performance_mode": "stable",
            "render_mode": "long_stable",
        },
    )
    seg = plan["segments"][0]
    overlay_spec = renderer._image_overlay_cache_spec(seg, 2.5)
    assert overlay_spec is not None, "expected lightweight overlay to be cache-eligible"
    clip = renderer._image_clip(source, 2.5, {"type": "gentle_push"}, overlay_spec=overlay_spec)
    cache_dir = root / ".video_create_project" / "render_cache" / "photo_segments"
    cached = list(cache_dir.glob("*.mp4"))
    assert cached, "expected prerendered overlay photo segment cache"
    assert renderer.photo_segment_cache_stats["overlay_eligible"] == 1
    assert renderer.photo_segment_cache_stats["overlay_created"] == 1
    engine.close_clip(clip)

    clip_again = renderer._image_clip(source, 2.5, {"type": "gentle_push"}, overlay_spec=overlay_spec)
    assert renderer.photo_segment_cache_stats["overlay_hit"] == 1
    assert renderer.photo_segment_cache_stats["saved_live_composes"] == 1
    assert renderer.photo_segment_cache_stats["saved_render_seconds"] == 2
    engine.close_clip(clip_again)


if __name__ == "__main__":
    test_photo_segment_prerender_cache()
    test_photo_segment_cache_balanced_medium_project()
    test_photo_segment_cache_with_light_overlay()
    print("V5 photo segment cache smoke test passed")
