"""Image and card prerender cache helpers for the V5 renderer."""

from __future__ import annotations

import gc
import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from video_engine.constants import STABLE_RENDER_DEFAULTS
from video_engine.render_routes import _should_auto_use_stable_renderer


EmitEvent = Callable[..., None]
QualityToCrf = Callable[[Any], str]
SelectVideoEncoder = Callable[[Dict[str, Any]], Tuple[str, List[str]]]
ValidateVideo = Callable[..., Tuple[bool, str, Optional[float]]]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def _default_quality_to_crf(_quality: Any) -> str:
    return "23"


def _default_select_video_encoder(_params: Dict[str, Any]) -> Tuple[str, List[str]]:
    return "libx264", ["-preset", "veryfast"]


def _default_validate_video(path: Path, min_size: int = 1024) -> Tuple[bool, str, Optional[float]]:
    if path.exists() and path.stat().st_size >= min_size:
        return True, "validation passed", None
    return False, "video file missing or too small", None


def _default_close_clip(clip: Any) -> None:
    close = getattr(clip, "close", None)
    if callable(close):
        close()


def should_prerender_image_segment(renderer: Any, duration: float, motion_config: Optional[Dict[str, Any]] = None) -> bool:
    performance_mode = str(renderer.params.get("performance_mode") or renderer.plan.get("render_settings", {}).get("performance_mode") or "").lower()
    render_mode = str(renderer.params.get("render_mode") or renderer.plan.get("render_settings", {}).get("render_mode") or "").lower()
    total_duration = float(renderer.plan.get("total_duration") or 0.0)
    segments = list(renderer.plan.get("segments", []) or [])
    segment_count = len(segments)
    motion_type = str((motion_config or {}).get("type") or "none")
    if motion_type not in {"none", "still_hold", "gentle_push", "slow_push", "ken_burns", "subtle_ken_burns", "punch_zoom", "micro_zoom"}:
        return False
    large_project = (
        performance_mode == "stable"
        or render_mode == "long_stable"
        or _should_auto_use_stable_renderer(total_duration, segments, renderer.params)
    )
    medium_project = (
        performance_mode in {"balanced", "quality"}
        and (
            total_duration >= float(STABLE_RENDER_DEFAULTS["image_heavy_seconds"])
            or segment_count >= int(STABLE_RENDER_DEFAULTS["image_heavy_segments"])
        )
    )
    return (large_project or medium_project) and float(duration or 0.0) > 0.1


def ffmpeg_image_motion_cache_spec(motion_config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    motion_type = str((motion_config or {}).get("type") or "none")
    if motion_type in {"none", "still_hold"}:
        return {"type": motion_type, "amount": 0.0}
    if motion_type == "gentle_push":
        return {"type": motion_type, "amount": 0.018}
    if motion_type == "slow_push":
        return {"type": motion_type, "amount": 0.015}
    if motion_type == "subtle_ken_burns":
        return {"type": motion_type, "amount": 0.012}
    if motion_type == "micro_zoom":
        return {"type": motion_type, "amount": 0.025}
    return None


def prerender_image_segment(
    renderer: Any,
    source: Path,
    fixed: Path,
    duration: float,
    motion_config: Optional[Dict[str, Any]] = None,
    overlay_spec: Optional[Dict[str, Any]] = None,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    validate_video_fn: ValidateVideo = _default_validate_video,
    close_clip_fn: Callable[[Any], None] = _default_close_clip,
) -> Optional[Path]:
    fps = int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30)
    motion_key = json.dumps(motion_config or {}, ensure_ascii=False, sort_keys=True)
    overlay_key = json.dumps(overlay_spec or {}, ensure_ascii=False, sort_keys=True)
    has_overlay = bool((overlay_spec or {}).get("text"))
    out = renderer._cache_path(
        "photo_segments",
        source,
        ".mp4",
        f"photo_seg_v4|duration={round(float(duration or 0.0), 3)}|fps={fps}|motion={motion_key}|overlay={overlay_key}",
    )
    if out.exists() and out.stat().st_size > 1024:
        renderer.photo_segment_cache_stats["hit"] += 1
        renderer.photo_segment_cache_stats["saved_live_composes"] += 1
        renderer.photo_segment_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
        if has_overlay:
            renderer.photo_segment_cache_stats["overlay_hit"] += 1
        emit_event_fn("log", message=f"Photo segment cache hit: {out.name}")
        return out

    clip = None
    try:
        clip = renderer._build_image_segment_clip(fixed, duration, motion_config, overlay_spec=overlay_spec)
        clip.write_videofile(
            str(out),
            fps=fps,
            codec="libx264",
            audio=False,
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
            renderer.photo_segment_cache_stats["created"] += 1
            if has_overlay:
                renderer.photo_segment_cache_stats["overlay_created"] += 1
            emit_event_fn("log", message=f"Photo segment cache created: {out.name}")
            return out
    except Exception as exc:
        renderer.photo_segment_cache_stats["fallback"] += 1
        emit_event_fn("log", message=f"Photo segment prerender fallback to live compose: {source.name}: {exc}")
    finally:
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


def ffmpeg_prerender_image_segment(
    renderer: Any,
    source: Path,
    fixed: Path,
    duration: float,
    motion_config: Optional[Dict[str, Any]] = None,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    select_video_encoder_fn: SelectVideoEncoder = _default_select_video_encoder,
    image_cls: Any = None,
) -> Optional[Path]:
    motion_spec = renderer._ffmpeg_image_motion_cache_spec(motion_config)
    if motion_spec is None:
        return None

    fps = int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30)
    motion_key = json.dumps(motion_spec, ensure_ascii=False, sort_keys=True)
    out = renderer._cache_path(
        "photo_segments_ffmpeg",
        source,
        ".mp4",
        f"photo_seg_ffmpeg_v1|duration={round(float(duration or 0.0), 3)}|fps={fps}|motion={motion_key}",
    )
    if out.exists() and out.stat().st_size > 1024:
        emit_event_fn("log", message=f"FFmpeg image segment cache hit: {out.name}")
        return out

    bg_path = renderer._blur_bg(fixed)
    segment_duration = max(float(duration or 0.1), 0.1)
    tw, th = renderer.target_size

    if image_cls is None:
        from PIL import Image

        image_cls = Image

    try:
        with image_cls.open(fixed) as img:
            iw, ih = img.size
    except Exception:
        return None

    base_scale = min(float(tw) / float(max(1, iw)), float(th) / float(max(1, ih)))
    base_w = max(2, int(round((iw * base_scale) / 2.0)) * 2)
    base_h = max(2, int(round((ih * base_scale) / 2.0)) * 2)
    amount = float(motion_spec.get("amount") or 0.0)

    fg_filter = f"[1:v]scale={base_w}:{base_h}[fg]"
    if amount > 0:
        zoom_expr = f"(1+{amount:.6f}*t/{segment_duration:.6f})"
        fg_filter = (
            "[1:v]"
            f"scale='max(2,trunc({base_w}*{zoom_expr}/2)*2)':"
            f"'max(2,trunc({base_h}*{zoom_expr}/2)*2)':eval=frame"
            "[fg]"
        )
    filter_complex = ";".join(
        [
            f"[0:v]scale={tw}:{th},setsar=1[bg]",
            fg_filter,
            "[bg][fg]overlay=(W-w)/2:(H-h)/2:eval=frame,format=yuv420p[outv]",
        ]
    )

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        selected_encoder, encoder_args = select_video_encoder_fn(renderer.params)

        def build_cmd(video_encoder: str, video_encoder_args: List[str]) -> List[str]:
            cmd = [
                ffmpeg,
                "-y",
                "-loop",
                "1",
                "-framerate",
                str(fps),
                "-t",
                f"{segment_duration:.6f}",
                "-i",
                str(bg_path),
                "-loop",
                "1",
                "-framerate",
                str(fps),
                "-t",
                f"{segment_duration:.6f}",
                "-i",
                str(fixed),
                "-filter_complex",
                filter_complex,
                "-map",
                "[outv]",
                "-r",
                str(fps),
                "-an",
                "-c:v",
                video_encoder,
            ]
            cmd += video_encoder_args
            if video_encoder == "libx264":
                cmd += ["-crf", quality_to_crf_fn(renderer.params.get("python_quality") or renderer.params.get("quality") or "standard")]
            else:
                cmd += ["-b:v", "8M"]
            cmd += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
            return cmd

        completed = subprocess.run(build_cmd(selected_encoder, encoder_args), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0 and selected_encoder != "libx264":
            emit_event_fn("log", message=f"FFmpeg image segment {selected_encoder} fallback to libx264: {completed.stderr[-600:]}")
            completed = subprocess.run(
                build_cmd("libx264", ["-preset", "veryfast"]),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        if completed.returncode == 0 and out.exists() and out.stat().st_size > 1024:
            emit_event_fn("log", message=f"FFmpeg image segment cache created: {out.name}")
            return out
        emit_event_fn("log", message=f"FFmpeg image segment fallback to MoviePy: {source.name}: {completed.stderr[-600:]}")
    except Exception as exc:
        emit_event_fn("log", message=f"FFmpeg image segment raised, fallback to MoviePy: {source.name}: {exc}")

    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass
    return None


def photo_segment_cache_summary(renderer: Any) -> Dict[str, int]:
    return dict(getattr(renderer, "photo_segment_cache_stats", {}) or {})


def emit_photo_segment_cache_summary(renderer: Any, *, emit_event_fn: EmitEvent = _noop_emit_event) -> None:
    photo_cache = photo_segment_cache_summary(renderer)
    if int(photo_cache.get("eligible") or 0) <= 0:
        return
    emit_event_fn(
        "log",
        message=(
            "Photo segment cache summary: "
            f"eligible={photo_cache.get('eligible')}, "
            f"hit={photo_cache.get('hit')}, "
            f"created={photo_cache.get('created')}, "
            f"fallback={photo_cache.get('fallback')}, "
            f"overlay_hit={photo_cache.get('overlay_hit')}, "
            f"saved_live_composes={photo_cache.get('saved_live_composes')}, "
            f"saved_render_seconds={photo_cache.get('saved_render_seconds')}"
        ),
    )
    emit_event_fn("photo_cache", **photo_cache)


def should_prerender_card_segment(_renderer: Any, seg: Dict[str, Any], duration: float) -> bool:
    return str(seg.get("type") or "") in {"title", "chapter", "end"} and float(duration or 0.0) > 0.1


def card_segment_cache_path(renderer: Any, seg: Dict[str, Any], duration: float) -> Path:
    stype = str(seg.get("type") or "")
    if stype == "title":
        background_source = renderer.params.get("title_background_path") or renderer.first_visual_source
        background_position = "first"
        background_source_2 = None
        background_position_2 = "first"
        blend_sources = False
        title_style = renderer.params.get("title_style") or seg.get("title_style")
        main = True
    elif stype == "end":
        background_source = renderer.params.get("end_background_path") or renderer.last_visual_source
        background_position = "last"
        background_source_2 = None
        background_position_2 = "first"
        blend_sources = False
        title_style = renderer.params.get("end_title_style") or seg.get("title_style")
        main = False
    else:
        background_source = seg.get("background_source_path")
        background_position = seg.get("background_source_position") or "first"
        background_source_2 = seg.get("background_source_path_2")
        background_position_2 = seg.get("background_source_position_2") or "first"
        blend_sources = bool((seg.get("background_mode") or "bridge_blur") == "bridge_blur")
        title_style = seg.get("title_style")
        main = False

    fps = int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30)
    key_payload = {
        "version": "card_seg_v1",
        "segment_id": seg.get("segment_id"),
        "segment_type": stype,
        "duration": round(float(duration or 0.0), 3),
        "text": seg.get("text"),
        "subtitle": seg.get("subtitle"),
        "title_style": title_style or {},
        "main": main,
        "background_mode": seg.get("background_mode"),
        "background_position": background_position,
        "background_position_2": background_position_2,
        "blend_sources": blend_sources,
        "fps": fps,
        "target_size": list(renderer.target_size),
        "source_1": renderer._cache_identity_for_source(background_source, "source_1"),
        "source_2": renderer._cache_identity_for_source(background_source_2, "source_2"),
    }
    return renderer._cache_bucket_path(
        "card_segments",
        ".mp4",
        json.dumps(key_payload, ensure_ascii=False, sort_keys=True),
    )


def prerender_card_segment(
    renderer: Any,
    seg: Dict[str, Any],
    duration: float,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    quality_to_crf_fn: QualityToCrf = _default_quality_to_crf,
    validate_video_fn: ValidateVideo = _default_validate_video,
    close_clip_fn: Callable[[Any], None] = _default_close_clip,
) -> Optional[Path]:
    stype = str(seg.get("type") or "")
    out = renderer._card_segment_cache_path(seg, duration)
    if out.exists() and out.stat().st_size > 1024:
        renderer.card_segment_cache_stats["hit"] += 1
        renderer.card_segment_cache_stats["saved_live_composes"] += 1
        renderer.card_segment_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
        emit_event_fn("log", message=f"Card segment cache hit: {out.name}")
        return out

    clip = None
    fps = int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30)
    try:
        clip = renderer._build_card_segment_clip(seg, duration)
        clip.write_videofile(
            str(out),
            fps=fps,
            codec="libx264",
            audio=False,
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
            renderer.card_segment_cache_stats["created"] += 1
            emit_event_fn("log", message=f"Card segment cache created: {out.name}")
            return out
    except Exception as exc:
        renderer.card_segment_cache_stats["fallback"] += 1
        emit_event_fn("log", message=f"Card segment prerender fallback to live compose: {seg.get('segment_id') or stype}: {exc}")
    finally:
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


def cached_card_segment(
    renderer: Any,
    seg: Dict[str, Any],
    duration: float,
    *,
    video_file_clip_cls: Any,
) -> Any:
    if not renderer._should_prerender_card_segment(seg, duration):
        return renderer._build_card_segment_clip(seg, duration)
    renderer.card_segment_cache_stats["eligible"] += 1
    cached = renderer._prerender_card_segment(seg, duration)
    if cached is not None and cached.exists():
        return video_file_clip_cls(str(cached))
    return renderer._build_card_segment_clip(seg, duration)


def card_segment_cache_summary(renderer: Any) -> Dict[str, int]:
    return dict(getattr(renderer, "card_segment_cache_stats", {}) or {})


def emit_card_segment_cache_summary(renderer: Any, *, emit_event_fn: EmitEvent = _noop_emit_event) -> None:
    card_cache = card_segment_cache_summary(renderer)
    if int(card_cache.get("eligible") or 0) <= 0:
        return
    emit_event_fn(
        "log",
        message=(
            "Card segment cache summary: "
            f"eligible={card_cache.get('eligible')}, "
            f"hit={card_cache.get('hit')}, "
            f"created={card_cache.get('created')}, "
            f"fallback={card_cache.get('fallback')}, "
            f"saved_live_composes={card_cache.get('saved_live_composes')}, "
            f"saved_render_seconds={card_cache.get('saved_render_seconds')}"
        ),
    )
    emit_event_fn("card_cache", **card_cache)
