from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def make_image(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (1280, 720), color)
    image.save(path, quality=92)


def test_card_segment_cache_reuse() -> None:
    root = Path("tests/tmp_vcs_card_segment_cache")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source_a = root / "first.jpg"
    source_b = root / "last.jpg"
    output = root / "card_output.mp4"
    make_image(source_a, (88, 126, 164))
    make_image(source_b, (146, 92, 76))

    plan = {
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "quality": "draft",
        },
        "total_duration": 12.0,
        "segments": [
            {
                "segment_id": "seg_title_0001",
                "type": "title",
                "duration": 1.2,
                "text": "Cache Warmup",
                "subtitle": "Opening card",
                "start_time": 0.0,
                "end_time": 1.2,
                "title_style": {"preset": "cinematic_bold", "motion": "fade_slide_up"},
            },
            {
                "segment_id": "seg_image_0001",
                "type": "image",
                "source_path": str(source_a),
                "duration": 1.0,
                "text": None,
                "subtitle": None,
                "start_time": 1.2,
                "end_time": 2.2,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_chapter_0001",
                "type": "chapter",
                "duration": 1.3,
                "text": "Chapter One",
                "subtitle": "Bridge blur card",
                "start_time": 2.2,
                "end_time": 3.5,
                "background_mode": "bridge_blur",
                "background_source_path": str(source_a),
                "background_source_position": "last",
                "background_source_path_2": str(source_b),
                "background_source_position_2": "first",
                "title_style": {"preset": "film_subtitle", "motion": "fade_slide_up"},
            },
            {
                "segment_id": "seg_image_0002",
                "type": "image",
                "source_path": str(source_b),
                "duration": 1.0,
                "text": None,
                "subtitle": None,
                "start_time": 3.5,
                "end_time": 4.5,
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_end_0001",
                "type": "end",
                "duration": 1.1,
                "text": "Thanks for watching",
                "subtitle": "Ending card",
                "start_time": 4.5,
                "end_time": 5.6,
                "title_style": {"preset": "cinematic_bold", "motion": "fade_slide_up"},
            },
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(output),
        {
            "fps": 12,
            "quality": "draft",
        },
    )

    card_segments = [plan["segments"][0], plan["segments"][2], plan["segments"][4]]
    first_clips = [renderer._segment(seg) for seg in card_segments]
    cache_dir = root / ".video_create_project" / "render_cache" / "card_segments"
    cached = sorted(cache_dir.glob("*.mp4"))
    assert len(cached) == 3, "expected cached title/chapter/end card segments"
    first_mtimes = {path.name: path.stat().st_mtime_ns for path in cached}
    assert renderer.card_segment_cache_stats["eligible"] == 3
    assert renderer.card_segment_cache_stats["created"] == 3
    assert renderer.card_segment_cache_stats["hit"] == 0
    for clip in first_clips:
        engine.close_clip(clip)

    second_clips = [renderer._segment(seg) for seg in card_segments]
    cached_again = sorted(cache_dir.glob("*.mp4"))
    assert len(cached_again) == 3
    for path in cached_again:
        assert path.stat().st_mtime_ns == first_mtimes[path.name]
    assert renderer.card_segment_cache_stats["eligible"] == 6
    assert renderer.card_segment_cache_stats["created"] == 3
    assert renderer.card_segment_cache_stats["hit"] == 3
    assert renderer.card_segment_cache_stats["saved_live_composes"] == 3
    assert renderer.card_segment_cache_stats["saved_render_seconds"] == 3
    for clip in second_clips:
        engine.close_clip(clip)


if __name__ == "__main__":
    test_card_segment_cache_reuse()
    print("V5 card segment cache smoke test passed")
