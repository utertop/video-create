from __future__ import annotations

from typing import Any, Dict, List, Optional

from .constants import STABLE_RENDER_DEFAULTS


_V56_SAFE_OVERLAY_MOTIONS = {
    "fade_slide_up",
    "editorial_fade",
    "fade_only",
    "static_hold",
    "lower_third_slide",
    "cinematic_reveal",
    "postcard_drift",
}

_V56_SAFE_CARD_MOTIONS = set(_V56_SAFE_OVERLAY_MOTIONS)


def _visual_segment_mix(segments: List[Dict[str, Any]]) -> Dict[str, int]:
    visual_segments = [seg for seg in segments if str(seg.get("type") or "") in {"image", "video"}]
    image_count = sum(1 for seg in visual_segments if str(seg.get("type") or "") == "image")
    video_count = sum(1 for seg in visual_segments if str(seg.get("type") or "") == "video")
    return {
        "visual_count": len(visual_segments),
        "image_count": image_count,
        "video_count": video_count,
    }


def _is_image_heavy_visual_mix(segments: List[Dict[str, Any]], min_visual_count: int = 12) -> bool:
    mix = _visual_segment_mix(segments)
    visual_count = int(mix["visual_count"])
    if visual_count < min_visual_count:
        return False
    image_ratio = float(mix["image_count"]) / float(max(1, visual_count))
    return image_ratio >= float(STABLE_RENDER_DEFAULTS["image_heavy_ratio"])


def _should_auto_use_stable_renderer(
    total_duration: float,
    segments: List[Dict[str, Any]],
    params: Dict[str, Any],
) -> bool:
    segment_count = len(segments)
    stable_threshold_seconds = float(params.get("stable_threshold_seconds", STABLE_RENDER_DEFAULTS["seconds"]))
    stable_threshold_segments = int(params.get("stable_threshold_segments", STABLE_RENDER_DEFAULTS["segments"]))
    image_heavy_seconds = float(
        params.get("stable_image_heavy_threshold_seconds", STABLE_RENDER_DEFAULTS["image_heavy_seconds"])
    )
    image_heavy_segments = int(
        params.get("stable_image_heavy_threshold_segments", STABLE_RENDER_DEFAULTS["image_heavy_segments"])
    )
    if _is_image_heavy_visual_mix(segments) and (
        total_duration >= image_heavy_seconds or segment_count >= image_heavy_segments
    ):
        return True
    return total_duration >= stable_threshold_seconds or segment_count >= stable_threshold_segments


def _v56_image_overlay_cache_spec(seg: Dict[str, Any], duration: float) -> Optional[Dict[str, Any]]:
    text = seg.get("overlay_text")
    if not text:
        return None
    subtitle = seg.get("overlay_subtitle")
    overlay_duration = min(float(seg.get("overlay_duration") or 1.8), float(duration or 1.8))
    style = dict(seg.get("overlay_title_style") or {})
    motion = str(style.get("motion") or "fade_slide_up")
    position = str(style.get("position") or "lower_left")
    if motion not in _V56_SAFE_OVERLAY_MOTIONS:
        return None
    if position not in {"lower_left", "lower_center", "center"}:
        return None
    if len(str(text)) > 42 or len(str(subtitle or "")) > 64:
        return None
    if overlay_duration > min(3.2, float(duration or 0.0)):
        return None
    return {
        "text": str(text),
        "subtitle": str(subtitle) if subtitle else None,
        "duration": round(overlay_duration, 3),
        "style": style,
    }


def _v56_is_ffmpeg_image_chunk_candidate(
    seg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> bool:
    params = params or {}
    if bool(params.get("preview")):
        return False
    if str(seg.get("type") or "") != "image":
        return False
    if not seg.get("source_path"):
        return False
    transition = seg.get("transition_config") or {}
    transition_type = str(transition.get("type") or seg.get("transition") or "none")
    transition_duration = float(transition.get("duration") or 0.0)
    if transition_type not in {"none", "cut"} or transition_duration > 0.05:
        return False
    motion_type = str((seg.get("motion_config") or {}).get("type") or "none")
    if motion_type not in {"none", "still_hold", "gentle_push", "slow_push", "subtle_ken_burns", "micro_zoom"}:
        return False
    if seg.get("overlay_text"):
        return _v56_image_overlay_cache_spec(seg, float(seg.get("duration") or 0.0)) is not None
    return True


def _v56_prefer_ffmpeg_segments(params: Optional[Dict[str, Any]] = None) -> bool:
    params = params or {}
    performance_mode = str(params.get("performance_mode") or "").lower()
    edit_strategy = str(params.get("edit_strategy") or "").lower()
    engine = str(params.get("engine") or "").lower()
    render_mode = str(params.get("render_mode") or "").lower()
    return (
        performance_mode == "stable"
        or edit_strategy in {"fast_assembly", "long_stable"}
        or render_mode == "long_stable"
        or engine == "ffmpeg_concat"
    )


def _v56_video_motion_fit_supported(seg: Dict[str, Any]) -> bool:
    motion_type = str((seg.get("motion_config") or {}).get("type") or "none")
    return motion_type in {"gentle_push", "slow_push", "micro_zoom", "subtle_ken_burns"}


def _v56_is_video_overlay_fitted_safe(seg: Dict[str, Any]) -> bool:
    text = seg.get("overlay_text")
    if not text:
        return True
    subtitle = seg.get("overlay_subtitle")
    overlay_duration = float(seg.get("overlay_duration") or 1.8)
    style = dict(seg.get("overlay_title_style") or {})
    motion = str(style.get("motion") or "fade_slide_up")
    position = str(style.get("position") or "lower_left")
    if motion not in _V56_SAFE_OVERLAY_MOTIONS:
        return False
    if position not in {"lower_left", "lower_center", "center"}:
        return False
    if len(str(text)) > 42 or len(str(subtitle or "")) > 64:
        return False
    return overlay_duration <= 3.2


def _v56_is_ffmpeg_direct_chunk_candidate(
    seg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> bool:
    params = params or {}
    if bool(params.get("preview")) or not _v56_prefer_ffmpeg_segments(params):
        return False
    if seg.get("type") != "video" or seg.get("overlay_text") or not seg.get("source_path"):
        return False
    transition = seg.get("transition_config") or {}
    transition_type = str(transition.get("type") or seg.get("transition") or "none")
    transition_duration = float(transition.get("duration") or 0.0)
    if transition_type not in {"none", "cut"} or transition_duration > 0.05:
        return False
    motion_type = str((seg.get("motion_config") or {}).get("type") or "none")
    return motion_type in {"none", "still_hold"}


def _v56_is_ffmpeg_fitted_video_chunk_candidate(
    seg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> bool:
    params = params or {}
    if bool(params.get("preview")) or not _v56_prefer_ffmpeg_segments(params):
        return False
    if seg.get("type") != "video" or not seg.get("source_path"):
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
    if motion_type not in {"none", "still_hold"} and not _v56_video_motion_fit_supported(seg):
        return False
    return _v56_is_video_overlay_fitted_safe(seg)


def _v56_resolved_card_style(seg: Dict[str, Any], params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    params = params or {}
    stype = str(seg.get("type") or "")
    if stype == "title":
        style = params.get("title_style") or seg.get("title_style") or {}
        return dict(style)
    if stype == "end":
        style = params.get("end_title_style") or seg.get("title_style") or {}
        return dict(style)
    return dict(seg.get("title_style") or {})


def _v56_is_ffmpeg_card_chunk_candidate(
    seg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> bool:
    params = params or {}
    if bool(params.get("preview")):
        return False
    if str(seg.get("type") or "") not in {"title", "chapter", "end"}:
        return False
    transition = seg.get("transition_config") or {}
    transition_type = str(transition.get("type") or seg.get("transition") or "none")
    transition_duration = float(transition.get("duration") or 0.0)
    if transition_type not in {"none", "cut"} or transition_duration > 0.05:
        return False
    motion = str(_v56_resolved_card_style(seg, params).get("motion") or "fade_slide_up")
    return motion in _V56_SAFE_CARD_MOTIONS


def _v56_is_ffmpeg_fitted_video_chunk_route(route: str) -> bool:
    return str(route or "") in {"video_fit", "video_motion_fit"}


def _v56_chunk_route_family(
    seg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> str:
    route = str(seg.get("runtime_render_route") or seg.get("render_route") or "moviepy_required")
    if route == "moviepy_required":
        route = _v56_segment_route_for_chunk_planning(seg, params)
    if route == "direct_chunk_candidate":
        return "direct"
    if _v56_is_ffmpeg_fitted_video_chunk_route(route):
        return "video"
    if _v56_is_ffmpeg_card_chunk_candidate(seg, params):
        return "card"
    if _v56_is_ffmpeg_image_chunk_candidate(seg, params):
        return "image"
    return "timeline"


def _v56_segment_route_for_chunk_planning(
    seg: Dict[str, Any],
    params: Optional[Dict[str, Any]] = None,
) -> str:
    route = str(seg.get("runtime_render_route") or seg.get("render_route") or "")
    if route:
        return route
    if _v56_is_ffmpeg_direct_chunk_candidate(seg, params):
        return "direct_chunk_candidate"
    if _v56_is_ffmpeg_fitted_video_chunk_candidate(seg, params):
        motion_type = str((seg.get("motion_config") or {}).get("type") or "none")
        return "video_motion_fit" if motion_type not in {"none", "still_hold"} else "video_fit"
    if _v56_is_ffmpeg_image_chunk_candidate(seg, params):
        return "ffmpeg_image_chunk_candidate"
    if _v56_is_ffmpeg_card_chunk_candidate(seg, params):
        return "ffmpeg_card_chunk_candidate"
    return "moviepy_required"
