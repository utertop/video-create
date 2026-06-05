from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .constants import ENGINE_VERSION
from .render_routes import (
    _v56_chunk_route_family,
    _v56_is_ffmpeg_card_chunk_candidate,
    _v56_is_ffmpeg_fitted_video_chunk_route,
    _v56_is_ffmpeg_image_chunk_candidate,
)

_emit_event: Callable[..., None] = lambda _event_type, **_payload: None


def set_render_cache_event_emitter(callback: Callable[..., None]) -> None:
    global _emit_event
    _emit_event = callback


def emit_event(event_type: str, **payload: Any) -> None:
    _emit_event(event_type, **payload)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _v56_stable_json_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def _v56_source_fingerprint(path_value: Any) -> Optional[Dict[str, Any]]:
    if not path_value:
        return None
    path = Path(str(path_value))
    payload: Dict[str, Any] = {
        "path": str(path.resolve()) if path.exists() else str(path),
        "exists": path.exists(),
    }
    if path.exists():
        try:
            stat = path.stat()
            payload.update({
                "size": int(stat.st_size),
                "mtime_ns": int(stat.st_mtime_ns),
            })
        except Exception as exc:
            payload["stat_error"] = str(exc)
    return payload


def _v56_segment_source_fingerprints(seg: Dict[str, Any]) -> Dict[str, Any]:
    paths = {
        "source_path": seg.get("source_path"),
        "background_source_path": seg.get("background_source_path"),
        "background_source_path_2": seg.get("background_source_path_2"),
    }
    return {
        name: fingerprint
        for name, value in paths.items()
        for fingerprint in [_v56_source_fingerprint(value)]
        if fingerprint is not None
    }


def _v56_chunk_visual_audio_payload(params: Dict[str, Any]) -> Dict[str, Any]:
    audio = params.get("audio")
    if not isinstance(audio, dict):
        audio = {}
    return {
        "keep_source_audio": bool(audio.get("keep_source_audio", True)),
        "source_audio_volume": audio.get("source_audio_volume"),
        "normalize_audio": bool(audio.get("normalize_audio", False)),
        "target_lufs": audio.get("target_lufs"),
    }


def _v56_segment_cache_key(seg: Dict[str, Any], params: Dict[str, Any]) -> str:
    stable = {
        "engine_version": ENGINE_VERSION,
        "segment_id": seg.get("segment_id"),
        "type": seg.get("type"),
        "source_path": seg.get("source_path"),
        "asset_id": seg.get("asset_id"),
        "duration": seg.get("duration"),
        "text": seg.get("text"),
        "subtitle": seg.get("subtitle"),
        "background_mode": seg.get("background_mode"),
        "background_source_path": seg.get("background_source_path"),
        "background_source_path_2": seg.get("background_source_path_2"),
        "source_fingerprints": _v56_segment_source_fingerprints(seg),
        "overlay_text": seg.get("overlay_text"),
        "title_style": seg.get("title_style"),
        "overlay_title_style": seg.get("overlay_title_style"),
        "params_title_style": params.get("title_style") if seg.get("type") == "title" else None,
        "params_end_title_style": params.get("end_title_style") if seg.get("type") == "end" else None,
        "transition_config": seg.get("transition_config"),
        "motion_config": seg.get("motion_config"),
        "rhythm_config": seg.get("rhythm_config"),
        "keep_audio": seg.get("keep_audio"),
        "audio_visual": _v56_chunk_visual_audio_payload(params),
        "aspect_ratio": params.get("aspect_ratio"),
        "fps": params.get("fps"),
        "quality": params.get("quality"),
        "python_quality": params.get("python_quality"),
    }
    return _v56_stable_json_hash(stable)


def _v56_build_chunk_groups(
    segments: List[Dict[str, Any]],
    chunk_seconds: float,
    params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    params = params or {}
    chunk_seconds = max(float(chunk_seconds or 120), 30.0)

    groups: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_duration = 0.0
    current_keys: List[str] = []

    def chunk_route_payload(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        routes = [str(seg.get("runtime_render_route") or seg.get("render_route") or "moviepy_required") for seg in items]
        route_counts: Dict[str, int] = {}
        for route in routes:
            route_counts[route] = route_counts.get(route, 0) + 1
        if items and all(route == "direct_chunk_candidate" for route in routes):
            return {
                "runtime_chunk_route": "ffmpeg_direct_chunk",
                "runtime_chunk_route_reason": "all_segments_direct_chunk_safe",
                "runtime_chunk_route_tags": ["ffmpeg", "chunk", "direct"],
                "runtime_chunk_route_counts": route_counts,
            }
        if items and all(_v56_is_ffmpeg_fitted_video_chunk_route(route) for route in routes):
            return {
                "runtime_chunk_route": "ffmpeg_fitted_video_chunk",
                "runtime_chunk_route_reason": "all_segments_ffmpeg_fitted_video_safe",
                "runtime_chunk_route_tags": ["ffmpeg", "chunk", "video_fit"],
                "runtime_chunk_route_counts": route_counts,
            }
        if items and all(_v56_is_ffmpeg_card_chunk_candidate(seg, params) for seg in items):
            return {
                "runtime_chunk_route": "ffmpeg_card_chunk",
                "runtime_chunk_route_reason": "all_segments_ffmpeg_card_chunk_safe",
                "runtime_chunk_route_tags": ["ffmpeg", "chunk", "card"],
                "runtime_chunk_route_counts": route_counts,
            }
        if items and all(_v56_is_ffmpeg_image_chunk_candidate(seg, params) for seg in items):
            return {
                "runtime_chunk_route": "ffmpeg_image_chunk",
                "runtime_chunk_route_reason": "all_segments_ffmpeg_image_chunk_safe",
                "runtime_chunk_route_tags": ["ffmpeg", "chunk", "image"],
                "runtime_chunk_route_counts": route_counts,
            }
        if any(route in {"moviepy_required", "image_live_compose", "photo_prerender"} for route in routes):
            reason = "contains_timeline_or_image_segments"
        elif any(route in {"video_fit", "video_motion_fit"} for route in routes):
            reason = "contains_video_timeline_segments"
        else:
            reason = "default_timeline_chunk"
        return {
            "runtime_chunk_route": "moviepy_chunk",
            "runtime_chunk_route_reason": reason,
            "runtime_chunk_route_tags": ["moviepy", "chunk", "timeline"],
            "runtime_chunk_route_counts": route_counts,
        }

    for seg in segments:
        duration = float(seg.get("duration") or 0.0)
        route_family = _v56_chunk_route_family(seg, params)

        if current:
            current_family = _v56_chunk_route_family(current[0], params)
            time_exceeded = current_duration + duration > chunk_seconds
            route_changed = current_family != route_family

            if time_exceeded or route_changed:
                groups.append({
                    "index": len(groups),
                    "segments": current,
                    "duration": round(current_duration, 3),
                    "cache_key": _v56_stable_json_hash(current_keys),
                    **chunk_route_payload(current),
                })
                current = []
                current_duration = 0.0
                current_keys = []

        current.append(seg)
        current_duration += duration
        current_keys.append(_v56_segment_cache_key(seg, params))

    if current:
        groups.append({
            "index": len(groups),
            "segments": current,
            "duration": round(current_duration, 3),
            "cache_key": _v56_stable_json_hash(current_keys),
            **chunk_route_payload(current),
        })

    return groups


def _v56_atomic_replace(tmp_path: Path, final_path: Path) -> None:
    ensure_parent(final_path)
    if final_path.exists():
        final_path.unlink()
    os.replace(str(tmp_path), str(final_path))


def _v56_write_build_report(report_path: Path, report: Dict[str, Any]) -> None:
    try:
        ensure_parent(report_path)
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        emit_event("log", message=f"写入 build_report.json 失败: {exc}")
