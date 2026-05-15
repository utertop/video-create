from __future__ import annotations

import shutil
import subprocess
import sys
import json
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def make_image(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (960, 540), color)
    image.save(path, quality=92)


def make_bgm(path: Path, duration: float = 3.0) -> None:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration}",
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


def test_manual_bgm_mix_adds_audio_stream() -> None:
    root = Path("tests/tmp_vcs_bgm_mix")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    first = root / "first.jpg"
    second = root / "second.jpg"
    bgm = root / "bgm.m4a"
    output = root / "with_bgm.mp4"
    make_image(first, (42, 112, 82))
    make_image(second, (156, 96, 58))
    make_bgm(bgm, duration=3.0)

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
                "text": "Music A",
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
                "text": "Music B",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
        ],
    }

    engine.Renderer(
        plan,
        str(output),
        {
            "preview": True,
            "preview_height": 360,
            "fps": 12,
            "quality": "draft",
            "audio": {
                "music_mode": "manual",
                "music_path": str(bgm),
                "music_source": "manual",
                "bgm_volume": 0.28,
                "source_audio_volume": 1.0,
                "keep_source_audio": True,
                "auto_ducking": True,
                "fade_in_seconds": 0.2,
                "fade_out_seconds": 0.2,
            },
        },
    ).render()

    ok, reason, duration = engine._v56_validate_video(output, min_size=512)
    assert ok, reason
    assert duration and 1.8 <= duration <= 2.3
    assert engine.video_has_audio_stream(output)

    stable_output = root / "stable_with_bgm.mp4"
    plan_path = root / "render_plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    engine.render_with_v56_stability(
        str(plan_path),
        str(stable_output),
        {
            "preview": True,
            "preview_height": 360,
            "fps": 12,
            "quality": "draft",
            "performance_mode": "stable",
            "chunk_seconds": 30,
            "cover": False,
            "audio": {
                "music_mode": "manual",
                "music_path": str(bgm),
                "music_source": "manual",
                "bgm_volume": 0.28,
                "source_audio_volume": 1.0,
                "keep_source_audio": True,
                "auto_ducking": True,
                "fade_in_seconds": 0.2,
                "fade_out_seconds": 0.2,
            },
        },
    )
    ok, reason, duration = engine._v56_validate_video(stable_output, min_size=512)
    assert ok, reason
    assert duration and 1.8 <= duration <= 2.3
    assert engine.video_has_audio_stream(stable_output)


if __name__ == "__main__":
    test_manual_bgm_mix_adds_audio_stream()
    print("V5 BGM mix smoke test passed")
