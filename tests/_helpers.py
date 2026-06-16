from __future__ import annotations

import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Sequence

import imageio_ffmpeg
from PIL import Image


def reset_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


@contextmanager
def temporary_attr(target: Any, name: str, value: Any) -> Iterator[None]:
    original = getattr(target, name)
    setattr(target, name, value)
    try:
        yield
    finally:
        setattr(target, name, original)


def select_encoder_with_hardware(engine: Any, encoders: list[str], params: Dict[str, Any]) -> tuple[str, list[str]]:
    with temporary_attr(engine, "detect_ffmpeg_hardware_encoders", lambda: encoders):
        return engine.select_ffmpeg_video_encoder(params)


def make_image(path: Path, color: tuple[int, int, int], size: tuple[int, int] = (960, 540), quality: int = 92) -> Path:
    Image.new("RGB", size, color).save(path, quality=quality)
    return path


def make_images(root: Path, prefix: str, colors: Sequence[tuple[int, int, int]]) -> list[Path]:
    sources: list[Path] = []
    for idx, color in enumerate(colors, 1):
        path = root / f"{prefix}_{idx}.jpg"
        make_image(path, color)
        sources.append(path)
    return sources


def make_bgm(path: Path, frequency: int, duration: float = 3.0) -> Path:
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
    return path


def make_video(path: Path, duration: float = 1.0, with_audio: bool = False) -> Path:
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    args = [
        ffmpeg,
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"testsrc=size=640x360:rate=12:duration={duration}",
    ]
    if with_audio:
        args.extend([
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:sample_rate=48000:duration={duration}",
            "-shortest",
        ])
    args.extend(["-pix_fmt", "yuv420p", "-c:v", "libx264"])
    if with_audio:
        args.extend(["-c:a", "aac", "-b:a", "128k"])
    args.append(str(path))
    subprocess.check_call(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return path


def make_video_with_audio(path: Path, duration: float = 1.0) -> Path:
    return make_video(path, duration=duration, with_audio=True)


def assert_valid_video(engine: Any, path: Path, min_size: int = 512) -> float:
    ok, reason, duration = engine._v56_validate_video(path, min_size=min_size)
    assert ok, reason
    return duration


def read_build_report(engine: Any, root: Path) -> Dict[str, Any]:
    return engine.read_json(str(root / ".video_create_project" / "build_report.json"))


def render_settings(**overrides: Any) -> Dict[str, Any]:
    settings: Dict[str, Any] = {"fps": 12, "aspect_ratio": "16:9"}
    settings.update(overrides)
    return settings


def stable_render_settings(**overrides: Any) -> Dict[str, Any]:
    settings = render_settings(
        edit_strategy="long_stable",
        performance_mode="stable",
        render_mode="long_stable",
    )
    settings.update(overrides)
    return settings


def draft_params(**overrides: Any) -> Dict[str, Any]:
    params: Dict[str, Any] = {"fps": 12, "quality": "draft"}
    params.update(overrides)
    return params


def cut_transition() -> Dict[str, Any]:
    return {"type": "cut", "duration": 0}


def image_segment(
    segment_id: str,
    source_path: Path | str,
    start_time: float,
    duration: float,
    **overrides: Any,
) -> Dict[str, Any]:
    segment: Dict[str, Any] = {
        "segment_id": segment_id,
        "type": "image",
        "source_path": str(source_path),
        "duration": duration,
        "start_time": start_time,
        "end_time": start_time + duration,
        "text": None,
        "transition_config": cut_transition(),
        "motion_config": {"type": "none"},
    }
    segment.update(overrides)
    return segment


def video_segment(
    segment_id: str,
    source_path: Path | str,
    start_time: float,
    duration: float,
    **overrides: Any,
) -> Dict[str, Any]:
    segment = image_segment(segment_id, source_path, start_time, duration, **overrides)
    segment["type"] = "video"
    segment.setdefault("subtitle", None)
    segment.setdefault("transition", "cut")
    segment.setdefault("keep_audio", False)
    return segment


def render_plan(
    segments: Iterable[Dict[str, Any]],
    *,
    settings: Dict[str, Any] | None = None,
    total_duration: float | None = None,
    document_type: str | None = None,
) -> Dict[str, Any]:
    segment_list = list(segments)
    plan: Dict[str, Any] = {
        "render_settings": settings or render_settings(),
        "segments": segment_list,
    }
    if document_type:
        plan["document_type"] = document_type
    if total_duration is not None:
        plan["total_duration"] = total_duration
    return plan


def long_image_plan(
    *,
    total_duration: float = 720.0,
    segment_count: int = 60,
    segment_duration: float = 8.0,
    **settings_overrides: Any,
) -> Dict[str, Any]:
    return render_plan(
        [{"segment_id": f"seg_{idx:03d}", "type": "image", "duration": segment_duration} for idx in range(segment_count)],
        settings=render_settings(
            performance_mode="balanced",
            render_mode="auto",
            **settings_overrides,
        ),
        total_duration=total_duration,
    )


def manual_audio_params(
    music_path: Path | str,
    *,
    bgm_volume: float,
    source_audio_volume: float = 1.0,
    keep_source_audio: bool = True,
    auto_ducking: bool = True,
    fade_in_seconds: float = 0.0,
    fade_out_seconds: float = 0.0,
) -> Dict[str, Any]:
    return draft_params(
        preview=True,
        preview_height=360,
        audio={
            "music_mode": "manual",
            "music_path": str(music_path),
            "music_source": "manual",
            "bgm_volume": bgm_volume,
            "source_audio_volume": source_audio_volume,
            "keep_source_audio": keep_source_audio,
            "auto_ducking": auto_ducking,
            "fade_in_seconds": fade_in_seconds,
            "fade_out_seconds": fade_out_seconds,
        },
    )


def visual_chunk_cache_params(**overrides: Any) -> Dict[str, Any]:
    params = draft_params(
        preview=True,
        preview_height=360,
        visual_base_chunk_cache=True,
        visual_base_chunk_max_segments=2,
        visual_base_chunk_seconds=30,
        audio={"music_mode": "off"},
    )
    params.update(overrides)
    return params


def four_image_transition_plan(root: Path, prefix: str, transitions: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    colors = [(86, 112, 150), (120, 92, 148), (148, 104, 80), (82, 132, 104)]
    sources = make_images(root, prefix, colors)
    segments = []
    for idx, source in enumerate(sources, 1):
        transition_config = transitions[idx - 1]
        overrides: Dict[str, Any] = {"transition_config": transition_config}
        if transition_config.get("type") != "cut":
            overrides["transition"] = transition_config.get("type")
        segments.append(image_segment(f"seg_{prefix}_{idx:05d}", source, float(idx - 1), 1.0, **overrides))
    return render_plan(segments, settings=render_settings(quality="draft"))


def stable_failure_plan(root: Path) -> tuple[Dict[str, Any], Path, Dict[str, Any]]:
    first = make_image(root / "first.jpg", (84, 112, 166))
    second = make_image(root / "second.jpg", (152, 94, 70))
    plan = render_plan(
        [
            image_segment("seg_fail_0001", first, 0.0, 1.0, motion_config={"type": "gentle_push"}, transition="cut"),
            image_segment("seg_fail_0002", second, 1.0, 1.0, motion_config={"type": "slow_push"}, transition="cut"),
        ],
        settings=stable_render_settings(),
        total_duration=2.0,
    )
    return plan, root / "output.mp4", draft_params(render_mode="long_stable", performance_mode="stable")
