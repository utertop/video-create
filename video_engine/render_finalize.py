"""Final output validation and finalize helpers for V5 rendering."""

from __future__ import annotations

import shutil
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, Optional, Tuple

from video_engine import render_ffmpeg as render_ffmpeg_helpers
from video_engine.render_cache import _v56_atomic_replace


EmitEvent = Callable[..., None]
ValidateVideo = Callable[..., Tuple[bool, str, Optional[float]]]
VideoHasAudioStream = Callable[[Path], bool]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def _default_close_clip(_clip: Any) -> None:
    return None


def _default_video_has_audio_stream(_path: Path) -> bool:
    return False


def validate_video(
    path: Path,
    min_size: int = 1024,
    *,
    has_moviepy: bool = False,
    video_file_clip_cls: Any = None,
    close_clip_fn: Callable[[Any], None] = _default_close_clip,
) -> Tuple[bool, str, Optional[float]]:
    if not path.exists():
        return False, "video file does not exist", None
    if path.stat().st_size < min_size:
        return False, f"video file is too small: {path.stat().st_size} bytes", None

    if not has_moviepy or video_file_clip_cls is None:
        return True, "MoviePy unavailable; size check passed", None

    clip = None
    try:
        clip = video_file_clip_cls(str(path))
        duration = float(clip.duration or 0.0)
        if duration <= 0:
            return False, "video duration is invalid", duration
        return True, "validation passed", duration
    except Exception as exc:
        return False, f"video validation failed: {exc}", None
    finally:
        if clip is not None:
            close_clip_fn(clip)


def apply_final_bgm_mix(
    input_video: Path,
    output_video: Path,
    audio_settings: Dict[str, Any],
    duration: Optional[float],
    prepared_bgm_path: Optional[Path] = None,
    prepared_bgm_is_bed: bool = False,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    video_has_audio_stream_fn: VideoHasAudioStream = _default_video_has_audio_stream,
) -> bool:
    return render_ffmpeg_helpers._v56_apply_final_bgm_mix(
        input_video,
        output_video,
        audio_settings,
        duration,
        prepared_bgm_path=prepared_bgm_path,
        prepared_bgm_is_bed=prepared_bgm_is_bed,
        emit_event_fn=emit_event_fn,
        video_has_audio_stream_fn=video_has_audio_stream_fn,
    )


def safe_apply_final_bgm_mix(
    apply_final_bgm_mix_fn: Callable[..., bool],
    *args: Any,
    **kwargs: Any,
) -> Tuple[bool, Optional[Exception]]:
    try:
        return bool(apply_final_bgm_mix_fn(*args, **kwargs)), None
    except Exception as exc:
        return False, exc


def finalize_output_from_visual_base(
    renderer: Any,
    visual_base_path: Path,
    output_path: Path,
    duration: float,
    *,
    apply_final_bgm_mix_fn: Callable[..., bool],
    validate_video_fn: ValidateVideo,
    atomic_replace_fn: Callable[[Path, Path], None] = _v56_atomic_replace,
) -> float:
    mixed_output = output_path.with_suffix(".audio.tmp.mp4")
    finalize_started = perf_counter()
    try:
        if mixed_output.exists():
            mixed_output.unlink()
    except Exception:
        pass

    final_duration = float(duration or 0.0)
    finalize_summary = {
        "audio_mix_attempted": False,
        "audio_mix_applied": False,
        "copy_through_used": False,
        "audio_mix_seconds": 0.0,
        "copy_through_seconds": 0.0,
        "total_finalize_seconds": 0.0,
    }
    audio_mix_started = perf_counter()
    if apply_final_bgm_mix_fn(
        visual_base_path,
        mixed_output,
        renderer.audio_settings,
        final_duration,
        prepared_bgm_path=renderer._prepare_music_bed(final_duration) or renderer._prepare_music_path(),
        prepared_bgm_is_bed=True,
    ):
        finalize_summary["audio_mix_attempted"] = True
        finalize_summary["audio_mix_applied"] = True
        finalize_summary["audio_mix_seconds"] = round(perf_counter() - audio_mix_started, 4)
        ok, reason, validated_duration = validate_video_fn(mixed_output, min_size=512)
        if not ok:
            raise RuntimeError(f"visual base validation failed: {reason}")
        atomic_replace_fn(mixed_output, output_path)
        finalize_summary["total_finalize_seconds"] = round(perf_counter() - finalize_started, 4)
        renderer.last_visual_finalize_summary = finalize_summary
        return float(validated_duration or final_duration)

    finalize_summary["audio_mix_attempted"] = True
    finalize_summary["audio_mix_seconds"] = round(perf_counter() - audio_mix_started, 4)
    copy_started = perf_counter()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    shutil.copy2(visual_base_path, output_path)
    finalize_summary["copy_through_used"] = True
    finalize_summary["copy_through_seconds"] = round(perf_counter() - copy_started, 4)
    ok, reason, validated_duration = validate_video_fn(output_path, min_size=512)
    if not ok:
        raise RuntimeError(f"visual base final validation failed: {reason}")
    finalize_summary["total_finalize_seconds"] = round(perf_counter() - finalize_started, 4)
    renderer.last_visual_finalize_summary = finalize_summary
    return float(validated_duration or final_duration)
