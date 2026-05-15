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


def make_audio(path: Path, duration: float, frequency: int = 440) -> None:
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


def test_scan_audio_and_auto_select_bgm() -> None:
    root = Path("tests/tmp_vcs_audio_auto")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    shots_dir = root / "chapter_a"
    shots_dir.mkdir()
    image_path = shots_dir / "shot.jpg"
    bgm_path = root / "travel_bgm_theme.m4a"
    sfx_path = root / "click_sfx.m4a"

    make_image(image_path, (48, 118, 84))
    make_audio(bgm_path, duration=18.0, frequency=440)
    make_audio(sfx_path, duration=4.0, frequency=880)

    library = engine.Scanner(str(root), recursive=True).scan()
    assert library["summary"]["audio_count"] == 2

    audio_assets = [asset for asset in library["assets"] if asset["type"] == "audio"]
    assert len(audio_assets) == 2
    assert any(asset["media"].get("duration_seconds") for asset in audio_assets)

    selected = engine.select_auto_music_asset(library["assets"])
    assert selected is not None
    assert selected["absolute_path"] == str(bgm_path.resolve())

    blueprint = engine.Planner(library).plan()
    blueprint["metadata"] = {
      **(blueprint.get("metadata") or {}),
      "audio": {
          "music_mode": "auto",
          "bgm_volume": 0.28,
          "source_audio_volume": 1.0,
          "keep_source_audio": True,
          "auto_ducking": True,
          "fade_in_seconds": 0.2,
          "fade_out_seconds": 0.2,
      },
    }
    render_plan = engine.Compiler(blueprint, library).compile()
    render_audio = render_plan["render_settings"]["audio"]
    assert render_audio["music_mode"] == "auto"
    assert render_audio["music_path"] == str(bgm_path.resolve())
    assert render_audio["music_source"] == "library"

    output = root / "auto_bgm_preview.mp4"
    preview_plan = {
        "document_type": "render_plan",
        "render_settings": {
            "fps": 12,
            "aspect_ratio": "16:9",
            "quality": "draft",
            "audio": render_audio,
        },
        "total_duration": 2.0,
        "segments": [
            {
                "segment_id": "seg_00001",
                "type": "image",
                "source_path": str(image_path),
                "duration": 2.0,
                "start_time": 0.0,
                "end_time": 2.0,
                "text": "Auto BGM",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
        ],
    }
    renderer = engine.Renderer(
        preview_plan,
        str(output),
        {
            "preview": True,
            "preview_height": 360,
            "fps": 12,
            "quality": "draft",
            "audio": {"music_mode": "auto"},
        },
    )
    prepared_music = renderer._prepare_music_path()
    assert prepared_music is not None
    assert prepared_music.exists()
    assert prepared_music.parent == root / ".video_create_project" / "audio_cache" / "normalized"
    prepared_mtime = prepared_music.stat().st_mtime_ns
    prepared_again = engine.prepare_cached_audio_for_mix(bgm_path.resolve(), root / ".video_create_project" / "audio_cache")
    assert prepared_again == prepared_music
    assert prepared_again.stat().st_mtime_ns == prepared_mtime
    renderer.render()
    ok, reason, duration = engine._v56_validate_video(output, min_size=512)
    assert ok, reason
    assert duration and 1.8 <= duration <= 2.3
    assert engine.video_has_audio_stream(output)


if __name__ == "__main__":
    test_scan_audio_and_auto_select_bgm()
    print("V5 audio auto-select smoke test passed")
