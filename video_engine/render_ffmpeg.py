"""FFmpeg-oriented render helpers for the V5 stable renderer."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


EmitEvent = Callable[..., None]
QualityToCrf = Callable[[Any], str]
SelectVideoEncoder = Callable[[Dict[str, Any]], Tuple[str, List[str]]]
ValidateVideo = Callable[[Path], Tuple[bool, str, Optional[float]]]
VideoHasAudioStream = Callable[[Path], bool]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def _default_quality_to_crf(quality: Any) -> str:
    q = str(quality or "high").lower()
    return {"low": "28", "medium": "24", "high": "20", "ultra": "18"}.get(q, "20")


def _default_select_video_encoder(params: Dict[str, Any]) -> Tuple[str, List[str]]:
    encoder = str(params.get("ffmpeg_video_encoder") or params.get("video_encoder") or "libx264")
    if encoder in {"h264_nvenc", "h264_qsv", "h264_amf"}:
        return encoder, ["-preset", "p4"]
    return "libx264", ["-preset", "veryfast"]


def _default_validate_video(path: Path) -> Tuple[bool, str, Optional[float]]:
    if path.exists() and path.stat().st_size > 1024:
        return True, "校验通过", None
    return False, "视频文件不存在或大小异常", None


def _default_video_has_audio_stream(_path: Path) -> bool:
    return False


def _write_concat_list(concat_list: Path, chunks: List[Path]) -> None:
    with concat_list.open("w", encoding="utf-8", newline="\n") as f:
        for chunk in chunks:
            escaped = chunk.resolve().as_posix().replace("'", r"'\''")
            f.write(f"file '{escaped}'\n")


def _concat_copy(
    rendered_segments: List[Path],
    tmp_chunk: Path,
    message: str,
    fail_message: str,
    validate_fail_message: str,
    raised_message: str,
    percent: int,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    validate_video_fn: ValidateVideo = _default_validate_video,
) -> bool:
    concat_list = tmp_chunk.with_suffix(".concat.txt")
    try:
        _write_concat_list(concat_list, rendered_segments)

        import imageio_ffmpeg

        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(tmp_chunk),
        ]
        emit_event_fn("phase", phase="render", message=message, percent=percent)
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            emit_event_fn("log", message=f"{fail_message}: {completed.stderr[-800:]}")
            return False
        ok, reason, _duration = validate_video_fn(tmp_chunk)
        if not ok:
            emit_event_fn("log", message=f"{validate_fail_message}: {reason}")
            return False
        return True
    except Exception as exc:
        emit_event_fn("log", message=f"{raised_message}: {exc}")
        return False
    finally:
        try:
            if concat_list.exists():
                concat_list.unlink()
        except Exception:
            pass


def _v56_concat_chunks_ffmpeg(
    chunks: List[Path],
    tmp_output: Path,
    project_dir: Path,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
) -> bool:
    if not chunks:
        raise RuntimeError("没有可拼接的 chunk 文件")

    concat_list = project_dir / "concat_list.txt"
    resolved_output = tmp_output.resolve()
    _write_concat_list(concat_list, chunks)

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list.resolve()),
            "-c",
            "copy",
            str(resolved_output),
        ]
        emit_event_fn("phase", phase="concat", message="使用 FFmpeg 快速拼接分段视频", percent=96)
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0 and resolved_output.exists() and resolved_output.stat().st_size > 1024:
            return True
        emit_event_fn("log", message=f"FFmpeg concat copy 失败，准备回退 MoviePy: {completed.stderr[-800:]}")
        return False
    except Exception as exc:
        emit_event_fn("log", message=f"FFmpeg concat 不可用，准备回退 MoviePy: {exc}")
        return False


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
    if not chunks:
        raise RuntimeError("missing chunks for ffmpeg reencode concat")

    concat_list = project_dir / "concat_reencode_list.txt"
    resolved_output = tmp_output.resolve()
    _write_concat_list(concat_list, chunks)

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        selected_encoder, encoder_args = select_video_encoder_fn(params)
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list.resolve()),
            "-r",
            str(int(fps or 30)),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-c:v",
            selected_encoder,
        ]
        cmd += encoder_args
        if selected_encoder == "libx264":
            cmd += ["-crf", quality_to_crf_fn(params.get("quality") or params.get("python_quality") or "high")]
        else:
            cmd += ["-b:v", "8M"]
        cmd += [
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(resolved_output),
        ]
        emit_event_fn("phase", phase="concat", message="使用 FFmpeg 重编码合并分段视频", percent=96)
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0 and resolved_output.exists() and resolved_output.stat().st_size > 1024:
            return True
        emit_event_fn("log", message=f"FFmpeg concat reencode failed, fallback to MoviePy: {completed.stderr[-800:]}")
        return False
    except Exception as exc:
        emit_event_fn("log", message=f"FFmpeg concat reencode raised, fallback to MoviePy: {exc}")
        return False
    finally:
        try:
            if concat_list.exists():
                concat_list.unlink()
        except Exception:
            pass


def _v56_concat_chunks_moviepy(
    chunks: List[Path],
    tmp_output: Path,
    fps: int,
    params: Dict[str, Any],
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    close_clip_fn: Callable[[Any], None],
    video_file_clip_cls: Any,
    concatenate_videoclips_fn: Callable[..., Any],
    logger_factory: Callable[[int, int], Any],
) -> None:
    emit_event_fn("phase", phase="concat", message="使用 MoviePy 回退拼接分段视频", percent=96)
    clips = []
    final = None
    try:
        for chunk in chunks:
            clips.append(video_file_clip_cls(str(chunk)))
        final = concatenate_videoclips_fn(clips, method="compose")
        crf = quality_to_crf_fn(params.get("quality") or params.get("python_quality") or "high")
        final.write_videofile(
            str(tmp_output),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            ffmpeg_params=["-crf", crf, "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=logger_factory(96, 3),
        )
    finally:
        if final is not None:
            close_clip_fn(final)
        for clip in clips:
            close_clip_fn(clip)


def _v56_apply_final_bgm_mix(
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
    music_mode = str(audio_settings.get("music_mode") or "off")
    music_path = audio_settings.get("music_path")
    if music_mode == "off" or not music_path:
        return False

    bgm_path = prepared_bgm_path or Path(str(music_path))
    if not bgm_path.exists():
        emit_event_fn("log", message=f"BGM 文件不存在，稳定模式已跳过背景音乐: {bgm_path}")
        return False

    video_duration = max(0.1, float(duration or 0.0))
    bgm_volume = float(audio_settings.get("bgm_volume", 0.28))
    if bgm_volume <= 0:
        return False

    keep_source = bool(audio_settings.get("keep_source_audio", True))
    source_has_audio = keep_source and video_has_audio_stream_fn(input_video)
    if bool(audio_settings.get("auto_ducking", True)) and source_has_audio:
        bgm_volume = min(bgm_volume, float(audio_settings.get("duck_bgm_volume", 0.16)))

    fade_in = min(float(audio_settings.get("fade_in_seconds", 0.0)), video_duration / 2.0)
    fade_out = min(float(audio_settings.get("fade_out_seconds", 0.0)), video_duration / 2.0)

    bgm_filters = [f"volume={bgm_volume:.4f}"]
    if fade_in > 0:
        bgm_filters.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        fade_start = max(0.0, video_duration - fade_out)
        bgm_filters.append(f"afade=t=out:st={fade_start:.3f}:d={fade_out:.3f}")
    bgm_filters.extend([
        "aresample=48000",
        f"atrim=0:{video_duration:.3f}",
        "asetpts=N/SR/TB",
    ])

    if source_has_audio:
        filter_complex = (
            f"[1:a]{','.join(bgm_filters)}[bgm];"
            "[0:a:0]aresample=48000[src];"
            "[src][bgm]amix=inputs=2:duration=first:dropout_transition=0[mix]"
        )
    else:
        filter_complex = f"[1:a]{','.join(bgm_filters)}[mix]"

    try:
        import imageio_ffmpeg

        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-i",
            str(input_video),
        ]
        if not prepared_bgm_is_bed:
            cmd.extend(["-stream_loop", "-1"])
        cmd.extend([
            "-i",
            str(bgm_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[mix]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_video),
        ])
        emit_event_fn("phase", phase="audio", message="稳定模式：使用 FFmpeg 流式混合背景音乐", percent=97)
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0 and output_video.exists() and output_video.stat().st_size > 1024:
            return True
        emit_event_fn("log", message=f"稳定模式 BGM 混音失败，保留无 BGM 结果: {completed.stderr[-800:]}")
    except Exception as exc:
        emit_event_fn("log", message=f"稳定模式 BGM 混音异常，保留无 BGM 结果: {exc}")

    try:
        if output_video.exists():
            output_video.unlink()
    except Exception:
        pass
    return False


def _v56_try_write_ffmpeg_direct_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    validate_video_fn: ValidateVideo = _default_validate_video,
) -> bool:
    segments = chunk.get("segments") or []
    if not segments:
        return False
    if str(chunk.get("runtime_chunk_route") or "") not in {"", "ffmpeg_direct_chunk"}:
        return False

    sources: List[Path] = []
    for seg in segments:
        source_path = seg.get("source_path")
        if not source_path:
            return False
        source = Path(source_path)
        seg_route = str(seg.get("runtime_render_route") or seg.get("render_route") or "")
        if seg_route and seg_route != "direct_chunk_candidate":
            return False
        if not source.exists() or not renderer._can_use_ffmpeg_direct_chunk_segment(seg):
            return False
        sources.append(source)

    if hasattr(renderer, "_segment_keep_audio"):
        keep_audio_flags = [bool(renderer._segment_keep_audio(seg)) for seg in segments]
    else:
        keep_audio_flags = [bool(seg.get("keep_audio", True)) for seg in segments]
    needs_audio_track = any(keep_audio_flags)
    fitted_segments: List[Path] = []
    for seg, source, keep_audio in zip(segments, sources, keep_audio_flags):
        fitted = renderer._ffmpeg_fit_video_segment(
            source,
            float(seg.get("duration") or 0.1),
            keep_audio=keep_audio,
            force_audio_track=needs_audio_track,
        )
        if not fitted or not fitted.exists():
            return False
        fitted_segments.append(fitted)

    return _concat_copy(
        fitted_segments,
        tmp_chunk,
        f"使用 FFmpeg 直出轻量分段 {chunk['index'] + 1}",
        "FFmpeg chunk 直出失败，回退 MoviePy",
        "FFmpeg chunk 直出校验失败，回退 MoviePy",
        "FFmpeg chunk 直出异常，回退 MoviePy",
        min(94, 10 + chunk["index"]),
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
    segments = chunk.get("segments") or []
    if not segments:
        return False
    if str(chunk.get("runtime_chunk_route") or "") not in {"", "ffmpeg_image_chunk"}:
        return False

    if image_cls is None or image_ops is None:
        from PIL import Image, ImageOps

        image_cls = Image
        image_ops = ImageOps

    rendered_segments: List[Path] = []
    for seg in segments:
        source_path = seg.get("source_path")
        if not source_path:
            return False
        source = Path(str(source_path))
        if not source.exists() or not renderer._can_use_ffmpeg_image_chunk_segment(seg):
            return False
        render_source = renderer._get_proxy_source(source, is_video=False)
        fixed = renderer._cache_path("fixed_images", render_source, ".jpg", "exif_rgb_v1")
        if not fixed.exists():
            with image_cls.open(render_source) as img:
                img = image_ops.exif_transpose(img).convert("RGB")
                img.save(fixed, quality=95)
        duration = float(seg.get("duration") or 0.1)
        overlay_spec = renderer._image_overlay_cache_spec(seg, duration)
        if overlay_spec:
            prerendered = renderer._prerender_image_segment(
                render_source,
                fixed,
                duration,
                seg.get("motion_config"),
                overlay_spec=overlay_spec,
            )
        else:
            prerendered = renderer._ffmpeg_prerender_image_segment(
                render_source,
                fixed,
                duration,
                seg.get("motion_config"),
            )
        if not prerendered or not prerendered.exists():
            return False
        rendered_segments.append(prerendered)

    return _concat_copy(
        rendered_segments,
        tmp_chunk,
        f"FFmpeg image chunk {chunk['index'] + 1}",
        "FFmpeg image chunk fallback to MoviePy",
        "FFmpeg image chunk validation fallback to MoviePy",
        "FFmpeg image chunk raised, fallback to MoviePy",
        min(94, 10 + chunk["index"]),
        emit_event_fn=emit_event_fn,
        validate_video_fn=validate_video_fn,
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
    segments = chunk.get("segments") or []
    if not segments:
        return False
    if str(chunk.get("runtime_chunk_route") or "") not in {"", "ffmpeg_fitted_video_chunk"}:
        return False

    rendered_segments: List[Path] = []
    for seg in segments:
        source_path = seg.get("source_path")
        if not source_path:
            return False
        source = Path(str(source_path))
        if not source.exists() or not renderer._can_use_ffmpeg_fitted_video(seg):
            return False
        duration = float(seg.get("duration") or 0.1)
        keep_audio = renderer._segment_keep_audio(seg) if hasattr(renderer, "_segment_keep_audio") else bool(seg.get("keep_audio", True))
        motion_spec = renderer._ffmpeg_video_motion_cache_spec(seg.get("motion_config"))
        if motion_spec is not None:
            base = renderer._ffmpeg_fit_motion_video_segment(source, duration, motion_spec, keep_audio=keep_audio)
        else:
            base = renderer._ffmpeg_fit_video_segment(source, duration, keep_audio=keep_audio)
        if not base or not base.exists():
            return False
        prepared = renderer._prerender_safe_video_overlay_segment(base, seg, duration)
        if not prepared or not prepared.exists():
            return False
        rendered_segments.append(prepared)

    return _concat_copy(
        rendered_segments,
        tmp_chunk,
        f"使用 FFmpeg 拼接轻量视频分段 {chunk['index'] + 1}",
        "FFmpeg 轻量视频分段拼接失败，回退 MoviePy",
        "FFmpeg 轻量视频分段校验失败，回退 MoviePy",
        "FFmpeg 轻量视频分段异常，回退 MoviePy",
        min(94, 10 + chunk["index"]),
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
    segments = chunk.get("segments") or []
    if not segments:
        return False
    if str(chunk.get("runtime_chunk_route") or "") not in {"", "ffmpeg_card_chunk"}:
        return False

    rendered_segments: List[Path] = []
    for seg in segments:
        if not renderer._can_use_ffmpeg_card_chunk_segment(seg):
            return False
        prerendered = renderer._prerender_card_segment(seg, float(seg.get("duration") or 0.1))
        if not prerendered or not prerendered.exists():
            return False
        rendered_segments.append(prerendered)

    return _concat_copy(
        rendered_segments,
        tmp_chunk,
        f"FFmpeg card chunk {chunk['index'] + 1}",
        "FFmpeg card chunk fallback to MoviePy",
        "FFmpeg card chunk validation fallback to MoviePy",
        "FFmpeg card chunk raised, fallback to MoviePy",
        min(94, 10 + chunk["index"]),
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
    """Ensure chunk files all expose an AAC track so FFmpeg concat keeps audio streams."""
    if not video_path.exists() or video_has_audio_stream_fn(video_path):
        return True

    audio_tmp = video_path.with_suffix(".audio-track.tmp.mp4")
    video_duration = max(0.1, float(duration or 0.0))
    try:
        import imageio_ffmpeg

        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-i",
            str(video_path),
            "-f",
            "lavfi",
            "-t",
            f"{video_duration:.3f}",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=48000",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(audio_tmp),
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0 and audio_tmp.exists() and audio_tmp.stat().st_size > 1024:
            os.replace(str(audio_tmp), str(video_path))
            return video_has_audio_stream_fn(video_path)
        emit_event_fn("log", message=f"Stable chunk silent audio mux failed: {completed.stderr[-800:]}")
    except Exception as exc:
        emit_event_fn("log", message=f"Stable chunk silent audio mux raised: {exc}")
    finally:
        try:
            if audio_tmp.exists():
                audio_tmp.unlink()
        except Exception:
            pass
    return False
