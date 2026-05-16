from __future__ import annotations

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


def make_audio(path: Path, duration: float, frequency: int) -> None:
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


def test_music_bed_and_playlist_render() -> None:
    root = Path("tests/tmp_vcs_music_playlist")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    image_path = root / "shot.jpg"
    first_bgm = root / "bgm_a.m4a"
    second_bgm = root / "bgm_b.m4a"
    output = root / "playlist_mix.mp4"

    make_image(image_path, (72, 128, 92))
    make_audio(first_bgm, duration=4.0, frequency=440)
    make_audio(second_bgm, duration=5.0, frequency=550)

    cached_a = engine.prepare_cached_audio_for_mix(first_bgm, root / ".video_create_project" / "audio_cache")
    cached_b = engine.prepare_cached_audio_for_mix(second_bgm, root / ".video_create_project" / "audio_cache")

    bed = engine.build_music_bed_for_duration(
        [cached_a, cached_b],
        duration=11.0,
        cache_root=root / ".video_create_project" / "audio_cache",
        fit_strategy="auto",
        fade_in=0.2,
        fade_out=0.2,
    )
    assert bed is not None and bed.exists()
    metadata = engine.probe_audio_file(bed)
    assert metadata["duration_seconds"] and 10.5 <= float(metadata["duration_seconds"]) <= 11.5

    plan = {
        "document_type": "render_plan",
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "quality": "draft",
            "audio": {
                "music_mode": "manual",
                "music_path": str(first_bgm),
                "music_playlist_mode": "manual_playlist",
                "music_playlist_paths": [str(first_bgm), str(second_bgm)],
                "music_fit_strategy": "auto",
                "bgm_volume": 0.28,
                "source_audio_volume": 1.0,
                "keep_source_audio": True,
                "auto_ducking": True,
                "fade_in_seconds": 0.2,
                "fade_out_seconds": 0.2,
            },
        },
        "total_duration": 8.0,
        "segments": [
            {
                "segment_id": "seg_00001",
                "type": "image",
                "source_path": str(image_path),
                "duration": 8.0,
                "start_time": 0.0,
                "end_time": 8.0,
                "text": "Playlist Test",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
        ],
    }

    renderer = engine.Renderer(
        plan,
        str(output),
        {
            "preview": True,
            "preview_height": 360,
            "fps": 12,
            "quality": "draft",
            "audio": plan["render_settings"]["audio"],
        },
    )
    prepared_bed = renderer._prepare_music_bed(8.0)
    assert prepared_bed is not None and prepared_bed.exists()
    renderer.render()

    ok, reason, duration = engine._v56_validate_video(output, min_size=512)
    assert ok, reason
    assert duration and 7.6 <= duration <= 8.4
    assert engine.video_has_audio_stream(output)
    report_path = root / ".video_create_project" / "build_report.json"
    assert report_path.exists()
    report = engine.read_json(str(report_path))
    assert report["render_mode"] == "v5_standard"
    assert report["proxy_media"]["eligible"] >= 1
    assert report["diagnostics"]["audio_mix"]["music_mode"] == "manual"


def test_audio_loudness_normalized_cache_is_distinct() -> None:
    root = Path("tests/tmp_vcs_audio_loudness_cache")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    bgm = root / "bgm.m4a"
    cache_root = root / ".video_create_project" / "audio_cache"
    make_audio(bgm, duration=1.0, frequency=440)

    plain = engine.prepare_cached_audio_for_mix(bgm, cache_root)
    normalized = engine.prepare_cached_audio_for_mix(
        bgm,
        cache_root,
        normalize_audio=True,
        target_lufs=-18.0,
    )
    normalized_again = engine.prepare_cached_audio_for_mix(
        bgm,
        cache_root,
        normalize_audio=True,
        target_lufs=-18.0,
    )

    assert plain.exists()
    assert normalized.exists()
    assert normalized != plain
    assert normalized_again == normalized


if __name__ == "__main__":
    test_music_bed_and_playlist_render()
    test_audio_loudness_normalized_cache_is_distinct()
    print("V5 music playlist smoke test passed")
