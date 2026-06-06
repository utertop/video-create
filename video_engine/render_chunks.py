"""Stable render chunk writing and concat helpers."""

from __future__ import annotations

import gc
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from video_engine import render_ffmpeg as render_ffmpeg_helpers
from video_engine.render_cache import _v56_atomic_replace


EmitEvent = Callable[..., None]
QualityToCrf = Callable[[Any], str]
SelectVideoEncoder = Callable[[Dict[str, Any]], Tuple[str, List[str]]]
ValidateVideo = Callable[[Path], Tuple[bool, str, Optional[float]]]
VideoHasAudioStream = Callable[[Path], bool]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def _default_quality_to_crf(_quality: Any) -> str:
    return "23"


def _default_select_video_encoder(_params: Dict[str, Any]) -> Tuple[str, List[str]]:
    return "libx264", ["-preset", "veryfast"]


def _default_validate_video(path: Path) -> Tuple[bool, str, Optional[float]]:
    if path.exists() and path.stat().st_size >= 1024:
        return True, "validation passed", None
    return False, "video file missing or too small", None


def _default_video_has_audio_stream(_path: Path) -> bool:
    return False


def _default_close_clip(_clip: Any) -> None:
    return None


def _v56_concat_chunks_ffmpeg(
    chunks: List[Path],
    tmp_output: Path,
    project_dir: Path,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
) -> bool:
    return render_ffmpeg_helpers._v56_concat_chunks_ffmpeg(
        chunks,
        tmp_output,
        project_dir,
        emit_event_fn=emit_event_fn,
    )


def _v56_concat_chunks_ffmpeg_reencode(
    chunks: List[Path],
    tmp_output: Path,
    project_dir: Path,
    fps: int,
    params: Dict[str, Any],
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    select_video_encoder_fn: SelectVideoEncoder = _default_select_video_encoder,
) -> bool:
    return render_ffmpeg_helpers._v56_concat_chunks_ffmpeg_reencode(
        chunks,
        tmp_output,
        project_dir,
        fps,
        params,
        emit_event_fn=emit_event_fn,
        quality_to_crf_fn=quality_to_crf_fn,
        select_video_encoder_fn=select_video_encoder_fn,
    )


def _v56_concat_chunks_moviepy(
    chunks: List[Path],
    tmp_output: Path,
    fps: int,
    params: Dict[str, Any],
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    close_clip_fn: Callable[[Any], None] = _default_close_clip,
    video_file_clip_cls: Any = None,
    concatenate_videoclips_fn: Any = None,
    logger_factory: Any = None,
) -> None:
    return render_ffmpeg_helpers._v56_concat_chunks_moviepy(
        chunks,
        tmp_output,
        fps,
        params,
        emit_event_fn=emit_event_fn,
        quality_to_crf_fn=quality_to_crf_fn,
        close_clip_fn=close_clip_fn,
        video_file_clip_cls=video_file_clip_cls,
        concatenate_videoclips_fn=concatenate_videoclips_fn,
        logger_factory=logger_factory,
    )


def _v56_try_write_ffmpeg_direct_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    validate_video_fn: ValidateVideo = _default_validate_video,
) -> bool:
    return render_ffmpeg_helpers._v56_try_write_ffmpeg_direct_chunk(
        renderer,
        chunk,
        tmp_chunk,
        params,
        emit_event_fn=emit_event_fn,
        validate_video_fn=validate_video_fn,
    )


def _v56_try_write_ffmpeg_image_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    validate_video_fn: ValidateVideo = _default_validate_video,
    image_cls: Any = None,
    image_ops: Any = None,
) -> bool:
    return render_ffmpeg_helpers._v56_try_write_ffmpeg_image_chunk(
        renderer,
        chunk,
        tmp_chunk,
        params,
        emit_event_fn=emit_event_fn,
        validate_video_fn=validate_video_fn,
        image_cls=image_cls,
        image_ops=image_ops,
    )


def _v56_try_write_ffmpeg_fitted_video_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    validate_video_fn: ValidateVideo = _default_validate_video,
) -> bool:
    return render_ffmpeg_helpers._v56_try_write_ffmpeg_fitted_video_chunk(
        renderer,
        chunk,
        tmp_chunk,
        params,
        emit_event_fn=emit_event_fn,
        validate_video_fn=validate_video_fn,
    )


def _v56_try_write_ffmpeg_card_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    validate_video_fn: ValidateVideo = _default_validate_video,
) -> bool:
    return render_ffmpeg_helpers._v56_try_write_ffmpeg_card_chunk(
        renderer,
        chunk,
        tmp_chunk,
        params,
        emit_event_fn=emit_event_fn,
        validate_video_fn=validate_video_fn,
    )


def _v56_ensure_silent_audio_track(
    video_path: Path,
    duration: Optional[float] = None,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    video_has_audio_stream_fn: VideoHasAudioStream = _default_video_has_audio_stream,
) -> bool:
    return render_ffmpeg_helpers._v56_ensure_silent_audio_track(
        video_path,
        duration,
        emit_event_fn=emit_event_fn,
        video_has_audio_stream_fn=video_has_audio_stream_fn,
    )


def _v56_write_chunk_video(
    renderer: Any,
    chunk: Dict[str, Any],
    chunk_path: Path,
    fps: int,
    params: Dict[str, Any],
    ensure_audio_track: bool = False,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    validate_video_fn: ValidateVideo = _default_validate_video,
    ensure_silent_audio_track_fn: Callable[[Path, Optional[float]], bool] = _v56_ensure_silent_audio_track,
    try_write_ffmpeg_direct_chunk_fn: Callable[..., bool] = _v56_try_write_ffmpeg_direct_chunk,
    try_write_ffmpeg_fitted_video_chunk_fn: Callable[..., bool] = _v56_try_write_ffmpeg_fitted_video_chunk,
    try_write_ffmpeg_card_chunk_fn: Callable[..., bool] = _v56_try_write_ffmpeg_card_chunk,
    try_write_ffmpeg_image_chunk_fn: Callable[..., bool] = _v56_try_write_ffmpeg_image_chunk,
    close_clip_fn: Callable[[Any], None] = _default_close_clip,
    logger_factory: Any = None,
) -> None:
    clips = []
    rendered_segments = []
    combined = None
    tmp_chunk = chunk_path.with_suffix(".rendering.tmp.mp4")

    def _finalize_fast_chunk() -> None:
        if ensure_audio_track:
            ok, _reason, duration = validate_video_fn(tmp_chunk)
            if ok and not ensure_silent_audio_track_fn(tmp_chunk, duration):
                raise RuntimeError("failed to ensure audio-ready stable chunk")
        _v56_atomic_replace(tmp_chunk, chunk_path)

    try:
        chunk_route = str(chunk.get("runtime_chunk_route") or "")
        if chunk_route == "ffmpeg_direct_chunk" and try_write_ffmpeg_direct_chunk_fn(renderer, chunk, tmp_chunk, params):
            _finalize_fast_chunk()
            return
        if chunk_route == "ffmpeg_fitted_video_chunk" and try_write_ffmpeg_fitted_video_chunk_fn(renderer, chunk, tmp_chunk, params):
            _finalize_fast_chunk()
            return
        if chunk_route == "ffmpeg_card_chunk" and try_write_ffmpeg_card_chunk_fn(renderer, chunk, tmp_chunk, params):
            _finalize_fast_chunk()
            return
        if chunk_route == "ffmpeg_image_chunk" and try_write_ffmpeg_image_chunk_fn(renderer, chunk, tmp_chunk, params):
            _finalize_fast_chunk()
            return

        for seg in chunk["segments"]:
            emit_event_fn(
                "phase",
                phase="render",
                message=f"Rendering chunk {chunk['index'] + 1}: {seg.get('type')} {seg.get('text') or ''}",
                percent=min(94, 10 + chunk["index"]),
            )
            clip = renderer._segment(seg)
            if clip is not None:
                clips.append(clip)
                rendered_segments.append(seg)

        if not clips:
            raise RuntimeError(f"chunk_{chunk['index']:03d} has no renderable clip")

        combined = renderer._compose_timeline(clips, rendered_segments)
        crf = quality_to_crf_fn(params.get("quality") or params.get("python_quality") or "high")
        combined.write_videofile(
            str(tmp_chunk),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            ffmpeg_params=["-crf", crf, "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=logger_factory(base_percent=20, span_percent=70) if logger_factory else None,
        )

        ok, reason, duration = validate_video_fn(tmp_chunk)
        if not ok:
            raise RuntimeError(f"chunk validation failed: {reason}")

        if ensure_audio_track and not ensure_silent_audio_track_fn(tmp_chunk, duration):
            raise RuntimeError("failed to ensure audio-ready stable chunk")

        _v56_atomic_replace(tmp_chunk, chunk_path)
    finally:
        if combined is not None:
            close_clip_fn(combined)
        for clip in clips:
            close_clip_fn(clip)
        if tmp_chunk.exists():
            try:
                tmp_chunk.unlink()
            except Exception:
                pass
        try:
            gc.collect()
        except Exception:
            pass
