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


def test_standard_visual_chunk_cache_reuses_unchanged_chunk_groups() -> None:
    root = Path("tests/tmp_vcs_audio_visual_chunk_reuse")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    colors = [
        (66, 102, 144),
        (92, 126, 78),
        (148, 96, 72),
        (104, 84, 152),
    ]
    sources = []
    for idx, color in enumerate(colors, 1):
        path = root / f"img_{idx}.jpg"
        make_image(path, color)
        sources.append(path)

    def make_plan(third_text: str) -> dict:
        segments = []
        cursor = 0.0
        for idx, source in enumerate(sources, 1):
            duration = 1.0
            segments.append(
                {
                    "segment_id": f"seg_{idx:05d}",
                    "type": "image",
                    "source_path": str(source),
                    "duration": duration,
                    "start_time": cursor,
                    "end_time": cursor + duration,
                    "text": third_text if idx == 3 else f"Segment {idx}",
                    "subtitle": None,
                    "transition_config": {"type": "cut", "duration": 0},
                    "motion_config": {"type": "none"},
                }
            )
            cursor += duration
        return {
            "document_type": "render_plan",
            "render_settings": {"fps": 12, "aspect_ratio": "16:9", "quality": "draft"},
            "total_duration": cursor,
            "segments": segments,
        }

    params = {
        "preview": True,
        "preview_height": 360,
        "fps": 12,
        "quality": "draft",
        "visual_base_chunk_cache": True,
        "visual_base_chunk_max_segments": 2,
        "visual_base_chunk_seconds": 30,
        "audio": {
            "music_mode": "off",
            "keep_source_audio": True,
            "source_audio_volume": 1.0,
        },
    }

    plan_a = make_plan("Chunk B before")
    output_a = root / "render_a.mp4"
    renderer_a = engine.Renderer(plan_a, str(output_a), params)
    groups_a = renderer_a._build_standard_visual_chunk_groups()
    assert len(groups_a) == 2
    renderer_a.render()
    chunk_dir = root / ".video_create_project" / "render_cache" / "visual_base_chunks"
    first_chunk_a = chunk_dir / f"{groups_a[0]['cache_key']}.mp4"
    second_chunk_a = chunk_dir / f"{groups_a[1]['cache_key']}.mp4"
    assert first_chunk_a.is_file()
    assert second_chunk_a.is_file()
    first_chunk_mtime = first_chunk_a.stat().st_mtime_ns
    second_chunk_mtime = second_chunk_a.stat().st_mtime_ns
    assert renderer_a.visual_base_cache_stats["chunk_created"] == 2

    plan_b = make_plan("Chunk B after")
    output_b = root / "render_b.mp4"
    renderer_b = engine.Renderer(plan_b, str(output_b), params)
    groups_b = renderer_b._build_standard_visual_chunk_groups()
    assert len(groups_b) == 2
    assert groups_b[0]["cache_key"] == groups_a[0]["cache_key"]
    assert groups_b[1]["cache_key"] != groups_a[1]["cache_key"]
    renderer_b.render()
    first_chunk_b = chunk_dir / f"{groups_b[0]['cache_key']}.mp4"
    second_chunk_b = chunk_dir / f"{groups_b[1]['cache_key']}.mp4"
    assert first_chunk_b.stat().st_mtime_ns == first_chunk_mtime
    assert second_chunk_b.is_file()
    assert second_chunk_b.stat().st_mtime_ns != second_chunk_mtime
    assert renderer_b.visual_base_cache_stats["chunk_hit"] >= 1
    assert renderer_b.visual_base_cache_stats["chunk_created"] >= 1


def test_transition_aware_visual_chunk_reuse_keeps_unaffected_neighbors() -> None:
    root = Path("tests/tmp_vcs_audio_visual_transition_units")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    colors = [
        (74, 110, 152),
        (92, 138, 84),
        (152, 98, 76),
        (110, 88, 166),
    ]
    sources = []
    for idx, color in enumerate(colors, 1):
        path = root / f"transition_{idx}.jpg"
        make_image(path, color)
        sources.append(path)

    def make_plan(third_text: str) -> dict:
        cursor = 0.0
        segments = []
        for idx, source in enumerate(sources, 1):
            duration = 1.0
            transition_config = {"type": "cut", "duration": 0}
            transition = "cut"
            if idx == 3:
                transition_config = {"type": "soft_crossfade", "duration": 0.32}
                transition = "soft_crossfade"
            segments.append(
                {
                    "segment_id": f"seg_transition_{idx:05d}",
                    "type": "image",
                    "source_path": str(source),
                    "duration": duration,
                    "start_time": cursor,
                    "end_time": cursor + duration,
                    "text": third_text if idx == 3 else f"Transition {idx}",
                    "subtitle": None,
                    "transition": transition,
                    "transition_config": transition_config,
                    "motion_config": {"type": "none"},
                }
            )
            cursor += duration
        return {
            "document_type": "render_plan",
            "render_settings": {"fps": 12, "aspect_ratio": "16:9", "quality": "draft"},
            "total_duration": cursor,
            "segments": segments,
        }

    params = {
        "preview": True,
        "preview_height": 360,
        "fps": 12,
        "quality": "draft",
        "visual_base_chunk_cache": True,
        "visual_base_chunk_max_segments": 2,
        "visual_base_chunk_seconds": 30,
        "audio": {
            "music_mode": "off",
            "keep_source_audio": True,
            "source_audio_volume": 1.0,
        },
    }

    plan_a = make_plan("Crossfade before")
    renderer_a = engine.Renderer(plan_a, str(root / "transition_a.mp4"), params)
    groups_a = renderer_a._build_standard_visual_chunk_groups()
    assert [len(group["segments"]) for group in groups_a] == [1, 2, 1]
    renderer_a.render()
    chunk_dir = root / ".video_create_project" / "render_cache" / "visual_base_chunks"
    chunk_paths_a = [chunk_dir / f"{group['cache_key']}.mp4" for group in groups_a]
    mtimes_a = [path.stat().st_mtime_ns for path in chunk_paths_a]

    plan_b = make_plan("Crossfade after")
    renderer_b = engine.Renderer(plan_b, str(root / "transition_b.mp4"), params)
    groups_b = renderer_b._build_standard_visual_chunk_groups()
    assert [len(group["segments"]) for group in groups_b] == [1, 2, 1]
    assert groups_b[0]["cache_key"] == groups_a[0]["cache_key"]
    assert groups_b[1]["cache_key"] != groups_a[1]["cache_key"]
    assert groups_b[2]["cache_key"] == groups_a[2]["cache_key"]
    renderer_b.render()
    chunk_paths_b = [chunk_dir / f"{group['cache_key']}.mp4" for group in groups_b]
    assert chunk_paths_b[0].stat().st_mtime_ns == mtimes_a[0]
    assert chunk_paths_b[2].stat().st_mtime_ns == mtimes_a[2]
    assert chunk_paths_b[1].stat().st_mtime_ns != mtimes_a[1]
    assert renderer_b.visual_base_cache_stats["chunk_hit"] >= 2
    assert renderer_b.visual_base_cache_stats["chunk_created"] >= 1


def test_fade_through_dark_expands_transition_unit_forward() -> None:
    root = Path("tests/tmp_vcs_audio_visual_fade_radius")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    sources = []
    for idx, color in enumerate(((72, 108, 152), (96, 140, 86), (154, 96, 70), (112, 86, 164)), 1):
        path = root / f"fade_{idx}.jpg"
        make_image(path, color)
        sources.append(path)

    plan = {
        "document_type": "render_plan",
        "render_settings": {"fps": 12, "aspect_ratio": "16:9", "quality": "draft"},
        "total_duration": 4.0,
        "segments": [
            {
                "segment_id": "seg_fade_00001",
                "type": "image",
                "source_path": str(sources[0]),
                "duration": 1.0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": "Fade 1",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_fade_00002",
                "type": "image",
                "source_path": str(sources[1]),
                "duration": 1.0,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": "Fade 2",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_fade_00003",
                "type": "image",
                "source_path": str(sources[2]),
                "duration": 1.0,
                "start_time": 2.0,
                "end_time": 3.0,
                "text": "Fade 3",
                "transition": "fade_through_dark",
                "transition_config": {"type": "fade_through_dark", "duration": 0.34},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_fade_00004",
                "type": "image",
                "source_path": str(sources[3]),
                "duration": 1.0,
                "start_time": 3.0,
                "end_time": 4.0,
                "text": "Fade 4",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
        ],
    }
    params = {
        "preview": True,
        "preview_height": 360,
        "fps": 12,
        "quality": "draft",
        "visual_base_chunk_cache": True,
        "visual_base_chunk_max_segments": 2,
        "visual_base_chunk_seconds": 30,
        "audio": {"music_mode": "off"},
    }

    renderer = engine.Renderer(plan, str(root / "fade.mp4"), params)
    units = renderer._build_standard_visual_transition_units()
    assert [len(unit) for unit in units] == [1, 3], "fade_through_dark should pull the following segment into the same local invalidation unit"


def test_quick_zoom_stays_local_to_previous_and_current() -> None:
    root = Path("tests/tmp_vcs_audio_visual_quick_zoom_radius")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    sources = []
    for idx, color in enumerate(((68, 112, 150), (98, 142, 82), (150, 94, 72), (114, 90, 162)), 1):
        path = root / f"zoom_{idx}.jpg"
        make_image(path, color)
        sources.append(path)

    plan = {
        "document_type": "render_plan",
        "render_settings": {"fps": 12, "aspect_ratio": "16:9", "quality": "draft"},
        "total_duration": 4.0,
        "segments": [
            {
                "segment_id": "seg_zoom_00001",
                "type": "image",
                "source_path": str(sources[0]),
                "duration": 1.0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": "Zoom 1",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_zoom_00002",
                "type": "image",
                "source_path": str(sources[1]),
                "duration": 1.0,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": "Zoom 2",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_zoom_00003",
                "type": "image",
                "source_path": str(sources[2]),
                "duration": 1.0,
                "start_time": 2.0,
                "end_time": 3.0,
                "text": "Zoom 3",
                "transition": "quick_zoom",
                "transition_config": {"type": "quick_zoom", "duration": 0.18},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_zoom_00004",
                "type": "image",
                "source_path": str(sources[3]),
                "duration": 1.0,
                "start_time": 3.0,
                "end_time": 4.0,
                "text": "Zoom 4",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
        ],
    }
    params = {
        "preview": True,
        "preview_height": 360,
        "fps": 12,
        "quality": "draft",
        "visual_base_chunk_cache": True,
        "visual_base_chunk_max_segments": 2,
        "visual_base_chunk_seconds": 30,
        "audio": {"music_mode": "off"},
    }

    renderer = engine.Renderer(plan, str(root / "zoom.mp4"), params)
    units = renderer._build_standard_visual_transition_units()
    assert [len(unit) for unit in units] == [1, 2, 1], "quick_zoom should stay local to the previous/current pair"


def test_fade_through_white_expands_transition_unit_forward() -> None:
    root = Path("tests/tmp_vcs_audio_visual_white_radius")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    sources = []
    for idx, color in enumerate(((78, 118, 146), (104, 146, 88), (160, 102, 76), (118, 94, 170)), 1):
        path = root / f"white_{idx}.jpg"
        make_image(path, color)
        sources.append(path)

    plan = {
        "document_type": "render_plan",
        "render_settings": {"fps": 12, "aspect_ratio": "16:9", "quality": "draft"},
        "total_duration": 4.0,
        "segments": [
            {
                "segment_id": "seg_white_00001",
                "type": "image",
                "source_path": str(sources[0]),
                "duration": 1.0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": "White 1",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_white_00002",
                "type": "image",
                "source_path": str(sources[1]),
                "duration": 1.0,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": "White 2",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_white_00003",
                "type": "image",
                "source_path": str(sources[2]),
                "duration": 1.0,
                "start_time": 2.0,
                "end_time": 3.0,
                "text": "White 3",
                "transition": "fade_through_white",
                "transition_config": {"type": "fade_through_white", "duration": 0.46},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_white_00004",
                "type": "image",
                "source_path": str(sources[3]),
                "duration": 1.0,
                "start_time": 3.0,
                "end_time": 4.0,
                "text": "White 4",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
        ],
    }
    params = {
        "preview": True,
        "preview_height": 360,
        "fps": 12,
        "quality": "draft",
        "visual_base_chunk_cache": True,
        "visual_base_chunk_max_segments": 2,
        "visual_base_chunk_seconds": 30,
        "audio": {"music_mode": "off"},
    }

    renderer = engine.Renderer(plan, str(root / "white.mp4"), params)
    units = renderer._build_standard_visual_transition_units()
    assert [len(unit) for unit in units] == [1, 3], "fade_through_white should pull the following segment into the same local invalidation unit"


def test_flash_cut_stays_local_to_previous_and_current() -> None:
    root = Path("tests/tmp_vcs_audio_visual_flash_cut_radius")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    sources = []
    for idx, color in enumerate(((70, 116, 152), (100, 146, 84), (152, 98, 74), (120, 92, 166)), 1):
        path = root / f"flash_{idx}.jpg"
        make_image(path, color)
        sources.append(path)

    plan = {
        "document_type": "render_plan",
        "render_settings": {"fps": 12, "aspect_ratio": "16:9", "quality": "draft"},
        "total_duration": 4.0,
        "segments": [
            {
                "segment_id": "seg_flash_00001",
                "type": "image",
                "source_path": str(sources[0]),
                "duration": 1.0,
                "start_time": 0.0,
                "end_time": 1.0,
                "text": "Flash 1",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_flash_00002",
                "type": "image",
                "source_path": str(sources[1]),
                "duration": 1.0,
                "start_time": 1.0,
                "end_time": 2.0,
                "text": "Flash 2",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_flash_00003",
                "type": "image",
                "source_path": str(sources[2]),
                "duration": 1.0,
                "start_time": 2.0,
                "end_time": 3.0,
                "text": "Flash 3",
                "transition": "flash_cut",
                "transition_config": {"type": "flash_cut", "duration": 0.16},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_flash_00004",
                "type": "image",
                "source_path": str(sources[3]),
                "duration": 1.0,
                "start_time": 3.0,
                "end_time": 4.0,
                "text": "Flash 4",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
        ],
    }
    params = {
        "preview": True,
        "preview_height": 360,
        "fps": 12,
        "quality": "draft",
        "visual_base_chunk_cache": True,
        "visual_base_chunk_max_segments": 2,
        "visual_base_chunk_seconds": 30,
        "audio": {"music_mode": "off"},
    }

    renderer = engine.Renderer(plan, str(root / "flash.mp4"), params)
    units = renderer._build_standard_visual_transition_units()
    assert [len(unit) for unit in units] == [1, 2, 1], "flash_cut should stay local to the previous/current pair"


if __name__ == "__main__":
    test_standard_render_reuses_visual_base_when_only_bgm_changes()
    test_stable_chunk_cache_key_ignores_bgm_only_changes()
    test_standard_visual_chunk_cache_reuses_unchanged_chunk_groups()
    test_transition_aware_visual_chunk_reuse_keeps_unaffected_neighbors()
    test_fade_through_dark_expands_transition_unit_forward()
    test_fade_through_white_expands_transition_unit_forward()
    test_quick_zoom_stays_local_to_previous_and_current()
    test_flash_cut_stays_local_to_previous_and_current()
    print("V5 audio visual cache smoke test passed")
