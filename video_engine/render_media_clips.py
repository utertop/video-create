"""Image/video clip composition helpers for the V5 renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from video_engine.constants import IMAGE_EXTS, VIDEO_EXTS


EmitEvent = Callable[..., None]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def find_visual_source(renderer: Any, direction: str) -> Optional[str]:
    """Find first/last image or video source from render_plan for title/end backgrounds."""
    segments = renderer.plan.get("segments", [])
    ordered = segments if direction == "first" else list(reversed(segments))
    for seg in ordered:
        if seg.get("type") in {"image", "video"} and seg.get("source_path"):
            return str(seg.get("source_path"))
    return None


def source_frame_for_background(
    renderer: Any,
    source_path: Optional[str],
    position: str,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    image_cls: Any = None,
    image_ops: Any = None,
    video_file_clip_cls: Any = None,
) -> Optional[Path]:
    if not source_path:
        return None

    source = Path(str(source_path))
    if not source.exists():
        emit_event_fn("log", message=f"Preview background source missing, using fallback: {source}")
        return None

    suffix = source.suffix.lower()
    out = renderer._cache_path("text_frames", source, ".jpg", f"text_bg|position={position}")
    if out.exists():
        return out

    try:
        if suffix in IMAGE_EXTS:
            with image_cls.open(source) as img:
                img = image_ops.exif_transpose(img).convert("RGB")
                img.save(out, quality=94)
            return out

        if suffix in VIDEO_EXTS:
            render_source = renderer._normalize_video_display_geometry(source)
            clip = video_file_clip_cls(str(render_source))
            try:
                duration = float(clip.duration or 0)
                if position == "last":
                    t = max(0.0, duration - 0.08) if duration else 0.0
                elif position == "middle":
                    t = max(0.0, duration / 2.0) if duration else 0.0
                else:
                    t = 0.05 if duration > 0.1 else 0.0
                clip.save_frame(str(out), t=t)
                return out
            finally:
                clip.close()
    except Exception as exc:
        emit_event_fn("log", message=f"Fixed image cache failed for {source.name}: {exc}")

    return None


def image_clip(
    renderer: Any,
    source: Path,
    duration: float,
    motion_config: Optional[Dict[str, Any]] = None,
    overlay_spec: Optional[Dict[str, Any]] = None,
    *,
    image_cls: Any = None,
    image_ops: Any = None,
    video_file_clip_cls: Any = None,
) -> Any:
    source = renderer._get_proxy_source(source, is_video=False)
    fixed = renderer._cache_path("fixed_images", source, ".jpg", "exif_rgb_v1")
    if not fixed.exists():
        with image_cls.open(source) as img:
            img = image_ops.exif_transpose(img).convert("RGB")
            img.save(fixed, quality=95)

    if renderer._should_prerender_image_segment(duration, motion_config):
        renderer.photo_segment_cache_stats["eligible"] += 1
        if overlay_spec:
            renderer.photo_segment_cache_stats["overlay_eligible"] += 1
        prerendered = renderer._prerender_image_segment(source, fixed, duration, motion_config, overlay_spec=overlay_spec)
        if prerendered is not None and prerendered.exists():
            return video_file_clip_cls(str(prerendered)).set_duration(duration)

    return renderer._build_image_segment_clip(fixed, duration, motion_config, overlay_spec=overlay_spec)


def video_clip(
    renderer: Any,
    source: Path,
    duration: float,
    keep_audio: bool = True,
    motion_config: Optional[Dict[str, Any]] = None,
    prefer_ffmpeg: bool = False,
    *,
    audio_file_clip_cls: Any = None,
    color_clip_cls: Any = None,
    composite_video_clip_cls: Any = None,
    image_clip_cls: Any = None,
    video_file_clip_cls: Any = None,
) -> Any:
    source = renderer._get_proxy_source(source, is_video=True)
    if prefer_ffmpeg:
        renderer.video_segment_cache_stats["eligible"] += 1
        motion_spec = renderer._ffmpeg_video_motion_cache_spec(motion_config)
        if motion_spec is not None:
            renderer.video_segment_cache_stats["motion_eligible"] += 1
            motion_fitted = renderer._ffmpeg_fit_motion_video_segment(
                source,
                duration,
                motion_spec,
                keep_audio=keep_audio,
            )
            if motion_fitted:
                return video_file_clip_cls(str(motion_fitted))
        else:
            fitted = renderer._ffmpeg_fit_video_segment(source, duration, keep_audio=keep_audio)
            if fitted:
                return video_file_clip_cls(str(fitted))

    render_source = renderer._normalize_video_display_geometry(source)
    raw = video_file_clip_cls(str(render_source))
    if raw.duration and raw.duration > duration:
        raw = raw.subclip(0, duration)
    raw = raw.set_duration(min(duration, raw.duration or duration))

    frame_path: Optional[Path] = renderer._cache_path("video_frames", source, ".jpg", "middle_frame_v1")
    try:
        if not frame_path.exists():
            raw.save_frame(str(frame_path), t=min(1.0, (raw.duration or 1.0) / 2))
    except Exception:
        frame_path = None

    final = compose_with_blur_bg(
        renderer,
        raw,
        raw.duration or duration,
        source_image=frame_path,
        motion_config=motion_config,
        color_clip_cls=color_clip_cls,
        composite_video_clip_cls=composite_video_clip_cls,
        image_cls=getattr(renderer.renderer, "image_cls", None),
        image_filter_mod=getattr(renderer.renderer, "image_filter_mod", None),
        image_clip_cls=image_clip_cls,
    )
    prepared_source_audio = renderer._prepare_source_audio_path(source) if keep_audio else None
    if keep_audio and prepared_source_audio is not None:
        source_volume = float(renderer.audio_settings.get("source_audio_volume", 1.0))
        if source_volume > 0:
            source_audio = audio_file_clip_cls(str(prepared_source_audio))
            source_audio_duration = float(getattr(source_audio, "duration", None) or 0.0)
            if source_audio_duration > 0:
                source_audio = source_audio.subclip(0, min(source_audio_duration, raw.duration or duration))
            if abs(source_volume - 1.0) > 0.001:
                source_audio = source_audio.volumex(source_volume)
            final = final.set_audio(source_audio)
    elif keep_audio and raw.audio is not None:
        source_volume = float(renderer.audio_settings.get("source_audio_volume", 1.0))
        if source_volume > 0:
            source_audio = raw.audio
            if abs(source_volume - 1.0) > 0.001:
                source_audio = source_audio.volumex(source_volume)
            final = final.set_audio(source_audio)
    return final


def compose_with_blur_bg(
    renderer: Any,
    clip: Any,
    duration: float,
    source_image: Optional[Path],
    motion_config: Optional[Dict[str, Any]] = None,
    *,
    color_clip_cls: Any = None,
    composite_video_clip_cls: Any = None,
    image_cls: Any = None,
    image_filter_mod: Any = None,
    image_clip_cls: Any = None,
) -> Any:
    tw, th = renderer.target_size
    scale = min(tw / clip.w, th / clip.h)
    fg = clip.resize((max(1, int(clip.w * scale)), max(1, int(clip.h * scale))))
    fg = apply_visual_motion(renderer, fg, duration, motion_config)

    if source_image and Path(source_image).exists():
        bg_path = blur_bg(
            renderer,
            Path(source_image),
            image_cls=image_cls,
            image_filter_mod=image_filter_mod,
        )
        bg = image_clip_cls(str(bg_path)).set_duration(duration)
    else:
        bg = color_clip_cls(renderer.target_size, color=(0, 0, 0)).set_duration(duration)

    return composite_video_clip_cls(
        [bg, fg.set_position("center")],
        size=renderer.target_size,
    ).set_duration(duration)


def apply_visual_motion(renderer: Any, clip: Any, duration: float, motion_config: Optional[Dict[str, Any]]) -> Any:
    motion_type = str((motion_config or {}).get("type") or "none")
    if motion_type in {"none", "still_hold"}:
        return clip

    duration = max(float(duration or 0.1), 0.1)

    if motion_type in {"gentle_push", "slow_push"}:
        amount = 0.018 if motion_type == "gentle_push" else 0.015
        return resize_clip_safe(clip, lambda t: 1.0 + amount * min(max(t / duration, 0.0), 1.0))

    if motion_type in {"ken_burns", "subtle_ken_burns"}:
        amount = 0.022 if motion_type == "ken_burns" else 0.012
        return resize_clip_safe(clip, lambda t: 1.0 + amount * min(max(t / duration, 0.0), 1.0))

    if motion_type in {"punch_zoom", "micro_zoom"}:
        amount = 0.035 if motion_type == "punch_zoom" else 0.025
        return resize_clip_safe(
            clip,
            lambda t: 1.0 + amount * max(0.0, 1.0 - min(max(t / 0.42, 0.0), 1.0)),
        )

    return clip


def resize_clip_safe(clip: Any, scale_fn: Any) -> Any:
    try:
        return clip.resize(scale_fn)
    except Exception:
        return clip


def blur_bg(
    renderer: Any,
    source_image: Path,
    *,
    image_cls: Any = None,
    image_filter_mod: Any = None,
) -> Path:
    out = renderer._cache_path("blur_backgrounds", source_image, ".jpg", "blur30_dark28_v1")
    if out.exists():
        return out

    tw, th = renderer.target_size
    img = None
    bg = None
    try:
        with image_cls.open(source_image) as raw_img:
            img = raw_img.convert("RGB")
        scale = max(tw / img.width, th / img.height)
        bg = img.resize((int(img.width * scale), int(img.height * scale)), image_cls.Resampling.LANCZOS)

        left = max(0, (bg.width - tw) // 2)
        top = max(0, (bg.height - th) // 2)
        bg = bg.crop((left, top, left + tw, top + th)).filter(image_filter_mod.GaussianBlur(30))
        bg = image_cls.blend(bg, image_cls.new("RGB", bg.size, (0, 0, 0)), 0.28)
        bg.save(out, quality=90)
        return out
    finally:
        for image in (bg, img):
            try:
                if image is not None:
                    image.close()
            except Exception:
                pass


def add_watermark(
    video: Any,
    text: str,
    *,
    np_module: Any = None,
    image_cls: Any = None,
    image_draw_mod: Any = None,
    image_clip_cls: Any = None,
    composite_video_clip_cls: Any = None,
    load_font_fn: Callable[[int], Any],
    text_size_fn: Callable[[Any, str, Any], Tuple[int, int]],
    draw_text_with_emoji_fn: Callable[..., None],
) -> Any:
    font = load_font_fn(30)
    temp = image_cls.new("RGBA", (1, 1), (0, 0, 0, 0))
    draw = image_draw_mod.Draw(temp)
    tw, th = text_size_fn(draw, text, font)

    img = image_cls.new("RGBA", (tw + 32, th + 24), (0, 0, 0, 0))
    draw = image_draw_mod.Draw(img)
    draw_text_with_emoji_fn(draw, (16, 10), text, font=font, fill=(255, 255, 255, 150))

    wm = image_clip_cls(np_module.array(img)).set_duration(video.duration).set_position(("right", "bottom"))
    return composite_video_clip_cls([video, wm], size=video.size)
