"""Video fit, motion, and overlay cache helpers for the V5 renderer."""

from __future__ import annotations

import gc
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from video_engine.render_routes import _v56_is_video_overlay_fitted_safe


EmitEvent = Callable[..., None]
QualityToCrf = Callable[[Any], str]
SelectVideoEncoder = Callable[[Dict[str, Any]], Tuple[str, List[str]]]
VideoHasAudioStream = Callable[[Path], bool]
ValidateVideo = Callable[..., Tuple[bool, str, Optional[float]]]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def _default_quality_to_crf(_quality: Any) -> str:
    return "23"


def _default_select_video_encoder(_params: Dict[str, Any]) -> Tuple[str, List[str]]:
    return "libx264", ["-preset", "veryfast"]


def _default_video_has_audio_stream(_path: Path) -> bool:
    return False


def _default_validate_video(path: Path, min_size: int = 1024) -> Tuple[bool, str, Optional[float]]:
    if path.exists() and path.stat().st_size >= min_size:
        return True, "validation passed", None
    return False, "video file missing or too small", None


def _default_close_clip(clip: Any) -> None:
    close = getattr(clip, "close", None)
    if callable(close):
        close()


def video_segment_cache_summary(renderer: Any) -> Dict[str, int]:
    return dict(getattr(renderer, "video_segment_cache_stats", {}) or {})


def emit_video_segment_cache_summary(renderer: Any, *, emit_event_fn: EmitEvent = _noop_emit_event) -> None:
    video_cache = video_segment_cache_summary(renderer)
    if int(video_cache.get("eligible") or 0) <= 0:
        return
    emit_event_fn(
        "log",
        message=(
            "Video segment cache summary: "
            f"eligible={video_cache.get('eligible')}, "
            f"hit={video_cache.get('hit')}, "
            f"created={video_cache.get('created')}, "
            f"fallback={video_cache.get('fallback')}, "
            f"motion_hit={video_cache.get('motion_hit')}, "
            f"saved_live_fits={video_cache.get('saved_live_fits')}, "
            f"saved_render_seconds={video_cache.get('saved_render_seconds')}"
        ),
    )
    emit_event_fn("video_cache", **video_cache)


def ffmpeg_video_motion_cache_spec(motion_config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    motion_type = str((motion_config or {}).get("type") or "none")
    if motion_type in {"none", "still_hold"}:
        return None
    if motion_type == "gentle_push":
        return {"type": motion_type, "mode": "progressive_zoom", "amount": 0.018}
    if motion_type == "slow_push":
        return {"type": motion_type, "mode": "progressive_zoom", "amount": 0.015}
    if motion_type == "micro_zoom":
        return {"type": motion_type, "mode": "progressive_zoom", "amount": 0.024}
    if motion_type == "subtle_ken_burns":
        return {"type": motion_type, "mode": "progressive_zoom", "amount": 0.012}
    return None


def can_use_ffmpeg_fitted_video(renderer: Any, seg: Dict[str, Any]) -> bool:
    if not renderer.prefer_ffmpeg_segments:
        return False
    if seg.get("type") != "video":
        return False

    transition = seg.get("transition_config") or {}
    transition_type = str(transition.get("type") or seg.get("transition") or "none")
    transition_duration = float(transition.get("duration") or 0.0)
    if transition_type not in {
        "none",
        "cut",
        "soft_crossfade",
        "fade_through_dark",
        "fade_through_white",
        "quick_zoom",
        "flash_cut",
    }:
        return False
    if transition_type in {"none", "cut"}:
        if transition_duration > 0.05:
            return False
    elif transition_duration > 0.8:
        return False

    motion_type = str((seg.get("motion_config") or {}).get("type") or "none")
    if motion_type not in {"none", "still_hold"} and renderer._ffmpeg_video_motion_cache_spec(seg.get("motion_config")) is None:
        return False
    return _v56_is_video_overlay_fitted_safe(seg)


def ffmpeg_fit_video_segment(
    renderer: Any,
    source: Path,
    duration: float,
    keep_audio: bool = True,
    force_audio_track: bool = False,
    track_stats: bool = True,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    select_video_encoder_fn: SelectVideoEncoder = _default_select_video_encoder,
    video_has_audio_stream_fn: VideoHasAudioStream = _default_video_has_audio_stream,
) -> Optional[Path]:
    fps = int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30)
    audio_mode = "source" if keep_audio else "silent" if force_audio_track else "none"
    extra = f"fit_v3|duration={round(float(duration or 0), 3)}|audio={audio_mode}|fps={fps}"
    out = renderer._cache_path("fitted_videos", source, ".mp4", extra)
    if out.exists() and out.stat().st_size > 1024:
        if track_stats:
            renderer.video_segment_cache_stats["hit"] += 1
            renderer.video_segment_cache_stats["saved_live_fits"] += 1
            renderer.video_segment_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
            emit_event_fn("log", message=f"Video segment cache hit: {out.name}")
        return out

    render_source = renderer._normalize_video_display_geometry(source)
    segment_duration = max(float(duration or 0.1), 0.1)
    prepared_source_audio = renderer._prepare_source_audio_path(source) if keep_audio else None
    use_cached_source_audio = prepared_source_audio is not None and prepared_source_audio.exists()
    fallback_source_audio = bool(keep_audio and video_has_audio_stream_fn(render_source))
    use_source_audio = bool(use_cached_source_audio or fallback_source_audio)
    needs_audio_track = bool(keep_audio or force_audio_track)
    source_volume = float(renderer.audio_settings.get("source_audio_volume", 1.0))
    tw, th = renderer.target_size
    vf = (
        f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
        f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps},format=yuv420p"
    )

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        selected_encoder, encoder_args = select_video_encoder_fn(renderer.params)

        def build_cmd(video_encoder: str, video_encoder_args: List[str]) -> List[str]:
            cmd = [ffmpeg, "-y", "-i", str(render_source)]
            if use_cached_source_audio:
                cmd += ["-i", str(prepared_source_audio)]
            elif needs_audio_track and not use_source_audio:
                cmd += [
                    "-f",
                    "lavfi",
                    "-t",
                    str(segment_duration),
                    "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=48000",
                ]
            cmd += ["-t", str(segment_duration), "-vf", vf, "-map", "0:v:0"]
            if needs_audio_track:
                if use_cached_source_audio:
                    audio_map = "1:a:0"
                elif use_source_audio:
                    audio_map = "0:a:0"
                else:
                    audio_map = "1:a:0"
                cmd += ["-map", audio_map]
                audio_filters = []
                if abs(source_volume - 1.0) > 0.001 and (use_source_audio or use_cached_source_audio):
                    audio_filters.append(f"volume={source_volume:.4f}")
                audio_filters.extend(["aresample=48000", "apad"])
                cmd += [
                    "-af",
                    ",".join(audio_filters),
                    "-ac",
                    "2",
                    "-ar",
                    "48000",
                    "-shortest",
                    "-c:a",
                    "aac",
                    "-b:a",
                    "160k",
                ]
            else:
                cmd += ["-an"]
            cmd += ["-c:v", video_encoder]
            cmd += video_encoder_args
            if video_encoder == "libx264":
                cmd += ["-crf", quality_to_crf_fn(renderer.params.get("python_quality") or renderer.params.get("quality") or "standard")]
            else:
                cmd += ["-b:v", "8M"]
            cmd += ["-movflags", "+faststart", str(out)]
            return cmd

        completed = subprocess.run(build_cmd(selected_encoder, encoder_args), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0 and selected_encoder != "libx264":
            emit_event_fn("log", message=f"Selected encoder {selected_encoder} failed, falling back to libx264: {completed.stderr[-600:]}")
            completed = subprocess.run(
                build_cmd("libx264", ["-preset", "veryfast"]),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        if completed.returncode == 0 and out.exists() and out.stat().st_size > 1024:
            if track_stats:
                renderer.video_segment_cache_stats["created"] += 1
                emit_event_fn("log", message=f"Video segment cache created: {out.name}")
            return out
        if track_stats:
            renderer.video_segment_cache_stats["fallback"] += 1
            emit_event_fn("log", message=f"FFmpeg fitted segment failed, falling back to MoviePy: {source.name}: {completed.stderr[-600:]}")
    except Exception as exc:
        if track_stats:
            renderer.video_segment_cache_stats["fallback"] += 1
            emit_event_fn("log", message=f"FFmpeg fitted segment raised, falling back to MoviePy: {source.name}: {exc}")

    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass
    return None


def ffmpeg_fit_motion_video_segment(
    renderer: Any,
    source: Path,
    duration: float,
    motion_spec: Dict[str, Any],
    keep_audio: bool = True,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    select_video_encoder_fn: SelectVideoEncoder = _default_select_video_encoder,
    video_has_audio_stream_fn: VideoHasAudioStream = _default_video_has_audio_stream,
) -> Optional[Path]:
    fps = int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30)
    audio_mode = "source" if keep_audio else "none"
    motion_key = json.dumps(motion_spec or {}, ensure_ascii=False, sort_keys=True)
    out = renderer._cache_path(
        "motion_fitted_videos",
        source,
        ".mp4",
        f"motion_fit_v1|duration={round(float(duration or 0), 3)}|audio={audio_mode}|fps={fps}|motion={motion_key}",
    )
    if out.exists() and out.stat().st_size > 1024:
        renderer.video_segment_cache_stats["hit"] += 1
        renderer.video_segment_cache_stats["motion_hit"] += 1
        renderer.video_segment_cache_stats["saved_live_fits"] += 1
        renderer.video_segment_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
        emit_event_fn("log", message=f"Video motion cache hit: {out.name}")
        return out

    base = renderer._ffmpeg_fit_video_segment(source, duration, keep_audio=keep_audio, track_stats=False)
    if not base or not base.exists():
        renderer.video_segment_cache_stats["fallback"] += 1
        renderer.video_segment_cache_stats["motion_fallback"] += 1
        emit_event_fn("log", message=f"FFmpeg motion fit fallback to MoviePy: {source.name}: base fit unavailable")
        return None

    tw, th = renderer.target_size
    segment_duration = max(float(duration or 0.1), 0.1)
    amount = float(motion_spec.get("amount") or 0.0)
    frame_budget = max(int(round(segment_duration * fps)), 1)
    zoom_expr = f"(1+{amount:.6f}*on/{frame_budget})"
    vf = (
        f"zoompan=z='{zoom_expr}':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d=1:s={tw}x{th}:fps={fps},"
        f"setsar=1,format=yuv420p"
    )

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        selected_encoder, encoder_args = select_video_encoder_fn(renderer.params)
        has_audio = bool(keep_audio and video_has_audio_stream_fn(base))

        def build_cmd(video_encoder: str, video_encoder_args: List[str]) -> List[str]:
            cmd = [ffmpeg, "-y", "-i", str(base), "-t", str(segment_duration), "-vf", vf, "-map", "0:v:0"]
            if has_audio:
                cmd += ["-map", "0:a:0", "-c:a", "copy", "-shortest"]
            else:
                cmd += ["-an"]
            cmd += ["-c:v", video_encoder]
            cmd += video_encoder_args
            if video_encoder == "libx264":
                cmd += ["-crf", quality_to_crf_fn(renderer.params.get("python_quality") or renderer.params.get("quality") or "standard")]
            else:
                cmd += ["-b:v", "8M"]
            cmd += ["-movflags", "+faststart", str(out)]
            return cmd

        completed = subprocess.run(build_cmd(selected_encoder, encoder_args), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0 and selected_encoder != "libx264":
            emit_event_fn("log", message=f"FFmpeg video motion {selected_encoder} fallback to libx264: {completed.stderr[-600:]}")
            completed = subprocess.run(
                build_cmd("libx264", ["-preset", "veryfast"]),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        if completed.returncode == 0 and out.exists() and out.stat().st_size > 1024:
            renderer.video_segment_cache_stats["created"] += 1
            renderer.video_segment_cache_stats["motion_created"] += 1
            emit_event_fn("log", message=f"Video motion cache created: {out.name}")
            return out
        renderer.video_segment_cache_stats["fallback"] += 1
        renderer.video_segment_cache_stats["motion_fallback"] += 1
        emit_event_fn("log", message=f"FFmpeg motion fit failed, falling back to MoviePy: {source.name}: {completed.stderr[-600:]}")
    except Exception as exc:
        renderer.video_segment_cache_stats["fallback"] += 1
        renderer.video_segment_cache_stats["motion_fallback"] += 1
        emit_event_fn("log", message=f"FFmpeg motion fit raised, falling back to MoviePy: {source.name}: {exc}")

    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass
    return None


def prerender_safe_video_overlay_segment(
    renderer: Any,
    fitted_source: Path,
    seg: Dict[str, Any],
    duration: float,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    validate_video_fn: ValidateVideo = _default_validate_video,
    close_clip_fn: Callable[[Any], None] = _default_close_clip,
    video_file_clip_cls: Any,
) -> Optional[Path]:
    overlay_spec = renderer._image_overlay_cache_spec(seg, duration)
    if overlay_spec is None:
        return fitted_source

    overlay_key = json.dumps(overlay_spec, ensure_ascii=False, sort_keys=True)
    out = renderer._cache_path(
        "overlay_fitted_videos",
        fitted_source,
        ".mp4",
        f"overlay_fit_v1|duration={round(float(duration or 0.0), 3)}|overlay={overlay_key}",
    )
    if out.exists() and out.stat().st_size > 1024:
        emit_event_fn("log", message=f"Video overlay cache hit: {out.name}")
        return out

    clip = None
    final = None
    try:
        clip = video_file_clip_cls(str(fitted_source)).set_duration(duration)
        final = renderer._apply_overlay_title(clip, seg)
        has_audio = getattr(final, "audio", None) is not None
        final.write_videofile(
            str(out),
            fps=int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30),
            codec="libx264",
            audio=has_audio,
            audio_codec="aac" if has_audio else None,
            preset="veryfast",
            threads=1,
            verbose=False,
            logger=None,
            ffmpeg_params=[
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-crf",
                quality_to_crf_fn(renderer.params.get("python_quality") or renderer.params.get("quality") or "standard"),
            ],
        )
        ok, _reason, _duration = validate_video_fn(out, min_size=512)
        if ok:
            emit_event_fn("log", message=f"Video overlay cache created: {out.name}")
            return out
    except Exception as exc:
        emit_event_fn("log", message=f"Video overlay prerender fallback: {exc}")
    finally:
        if final is not None:
            close_clip_fn(final)
        if clip is not None:
            close_clip_fn(clip)
        try:
            gc.collect()
        except Exception:
            pass

    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass
    return None
