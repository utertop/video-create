"""Render diagnostics and build-report helpers for the V5 renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from render_backends import build_backend_report_payload as backend_report_payload


SelectVideoEncoder = Callable[[Dict[str, Any]], Tuple[str, List[str]]]
ShouldUseHardwareEncoding = Callable[[Dict[str, Any]], bool]
VideoHasAudioStream = Callable[[Path], bool]


def _default_select_video_encoder(_params: Dict[str, Any]) -> Tuple[str, List[str]]:
    return "libx264", ["-preset", "veryfast"]


def _default_should_use_hardware_encoding(_params: Dict[str, Any]) -> bool:
    return False


def _default_video_has_audio_stream(_path: Path) -> bool:
    return False


def _v56_stable_should_force_chunk_audio_track(
    renderer: Any,
    segments: List[Dict[str, Any]],
    *,
    video_has_audio_stream_fn: VideoHasAudioStream = _default_video_has_audio_stream,
) -> bool:
    settings = getattr(renderer, "audio_settings", {}) or {}
    if not bool(settings.get("keep_source_audio", True)):
        return False
    try:
        if float(settings.get("source_audio_volume", 1.0)) <= 0:
            return False
    except Exception:
        return False

    for seg in segments:
        if seg.get("type") != "video" or not renderer._segment_keep_audio(seg):
            continue
        source_path = seg.get("source_path")
        if source_path and video_has_audio_stream_fn(Path(str(source_path))):
            return True
    return False


def _v56_collect_segment_route_details(segments: List[Dict[str, Any]], limit: int = 200) -> List[Dict[str, Any]]:
    details: List[Dict[str, Any]] = []
    for seg in segments[:limit]:
        static_route = seg.get("render_route")
        static_reason = seg.get("render_route_reason")
        static_tags = list(seg.get("render_route_tags") or [])
        runtime_route = seg.get("runtime_render_route") or static_route
        runtime_reason = seg.get("runtime_render_route_reason") or static_reason
        runtime_tags = list(seg.get("runtime_render_route_tags") or static_tags)
        details.append({
            "segment_id": seg.get("segment_id"),
            "type": seg.get("type"),
            "start_time": seg.get("start_time"),
            "end_time": seg.get("end_time"),
            "duration": seg.get("duration"),
            "route": runtime_route,
            "reason": runtime_reason,
            "tags": runtime_tags,
            "static_route": static_route,
            "static_reason": static_reason,
            "static_tags": static_tags,
            "runtime_route": runtime_route,
            "runtime_reason": runtime_reason,
            "runtime_tags": runtime_tags,
            "has_overlay": bool(seg.get("overlay_text") or seg.get("overlay_subtitle")),
            "transition": ((seg.get("transition_config") or {}).get("type") or seg.get("transition")),
            "motion": ((seg.get("motion_config") or {}).get("type") or "none"),
        })
    return details


def _v56_collect_chunk_route_details(
    groups: List[Dict[str, Any]],
    chunk_reports: List[Dict[str, Any]],
    limit: int = 200,
) -> List[Dict[str, Any]]:
    report_by_name = {str(item.get("name") or ""): item for item in chunk_reports}
    details: List[Dict[str, Any]] = []
    for group in groups[:limit]:
        chunk_name = f"chunk_{int(group.get('index') or 0):03d}.mp4"
        report = report_by_name.get(chunk_name, {})
        details.append({
            "name": chunk_name,
            "index": group.get("index"),
            "cache_key": group.get("cache_key"),
            "status": report.get("status"),
            "duration": report.get("duration"),
            "route": group.get("runtime_chunk_route"),
            "reason": group.get("runtime_chunk_route_reason"),
            "tags": list(group.get("runtime_chunk_route_tags") or []),
            "route_counts": dict(group.get("runtime_chunk_route_counts") or {}),
            "segment_count": len(group.get("segments") or []),
        })
    return details


def _v56_route_reason_summary(items: List[Dict[str, Any]], route_key: str, reason_key: str) -> Dict[str, Any]:
    route_counts: Dict[str, int] = {}
    reason_counts: Dict[str, int] = {}
    by_route: Dict[str, Dict[str, int]] = {}
    for item in items:
        route = str(item.get(route_key) or item.get("route") or "")
        reason = str(item.get(reason_key) or item.get("reason") or "")
        if route:
            route_counts[route] = route_counts.get(route, 0) + 1
        if reason:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        if route and reason:
            route_bucket = by_route.setdefault(route, {})
            route_bucket[reason] = route_bucket.get(reason, 0) + 1
    return {
        "route_counts": route_counts,
        "reason_counts": reason_counts,
        "reasons_by_route": by_route,
    }


def _v56_top_named_counts(counts: Dict[str, int], limit: int = 5) -> List[Dict[str, Any]]:
    ranked = sorted(
        ((str(name), int(count)) for name, count in (counts or {}).items() if count),
        key=lambda item: (-item[1], item[0]),
    )
    return [{"name": name, "count": count} for name, count in ranked[: max(1, int(limit or 5))]]


def _v56_timing_highlights(timings: Optional[Dict[str, Any]], limit: int = 3) -> Dict[str, Any]:
    timings = dict(timings or {})
    numeric_steps: List[Tuple[str, float]] = []
    for key, value in timings.items():
        if key == "total_render_seconds":
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)) and key.endswith("_seconds"):
            numeric_steps.append((key, round(float(value), 4)))
    numeric_steps.sort(key=lambda item: (-item[1], item[0]))
    accounted_seconds = round(sum(seconds for _, seconds in numeric_steps), 4)
    total_render_seconds = round(float(timings.get("total_render_seconds") or 0.0), 4)
    return {
        "top_steps": [
            {"name": name, "seconds": seconds}
            for name, seconds in numeric_steps[: max(1, int(limit or 3))]
        ],
        "measured_step_count": len(numeric_steps),
        "accounted_seconds": accounted_seconds,
        "total_render_seconds": total_render_seconds,
        "unaccounted_seconds": round(max(0.0, total_render_seconds - accounted_seconds), 4),
    }


def _v56_cache_efficiency_entry(
    stats: Optional[Dict[str, Any]],
    *,
    hit_keys: Tuple[str, ...] = ("hit",),
    created_keys: Tuple[str, ...] = ("created",),
    fallback_keys: Tuple[str, ...] = ("fallback",),
) -> Dict[str, Any]:
    raw = dict(stats or {})
    eligible = int(raw.get("eligible") or 0)
    hits = sum(int(raw.get(key) or 0) for key in hit_keys)
    created = sum(int(raw.get(key) or 0) for key in created_keys)
    fallback = sum(int(raw.get(key) or 0) for key in fallback_keys)
    payload: Dict[str, Any] = {
        "eligible": eligible,
        "hit_count": hits,
        "created_count": created,
        "fallback_count": fallback,
        "raw": raw,
    }
    if eligible > 0:
        payload["hit_rate"] = round(hits / float(eligible), 4)
        payload["created_rate"] = round(created / float(eligible), 4)
        payload["fallback_rate"] = round(fallback / float(eligible), 4)
    else:
        payload["hit_rate"] = None
        payload["created_rate"] = None
        payload["fallback_rate"] = None
    return payload


def _v56_fast_path_coverage(
    items: List[Dict[str, Any]],
    *,
    fast_routes: Tuple[str, ...],
    route_key: str = "route",
    reason_key: str = "reason",
    limit: int = 5,
) -> Dict[str, Any]:
    fast_route_set = set(str(route) for route in fast_routes)
    total = len(items)
    fast_path_count = 0
    slow_reason_counts: Dict[str, int] = {}
    slow_route_counts: Dict[str, int] = {}
    for item in items:
        route = str(item.get(route_key) or item.get("route") or "")
        if route in fast_route_set:
            fast_path_count += 1
            continue
        if route:
            slow_route_counts[route] = slow_route_counts.get(route, 0) + 1
        reason = str(item.get(reason_key) or item.get("reason") or "")
        if reason:
            slow_reason_counts[reason] = slow_reason_counts.get(reason, 0) + 1
    non_fast_path_count = max(0, total - fast_path_count)
    return {
        "total": total,
        "fast_path_count": fast_path_count,
        "non_fast_path_count": non_fast_path_count,
        "fast_path_rate": round(fast_path_count / float(total), 4) if total > 0 else None,
        "top_non_fast_path_routes": _v56_top_named_counts(slow_route_counts, limit=limit),
        "top_non_fast_path_reasons": _v56_top_named_counts(slow_reason_counts, limit=limit),
    }


def _v56_route_difference_summary(items: List[Dict[str, Any]], limit: int = 5) -> Dict[str, Any]:
    total = len(items)
    changed_count = 0
    change_counts: Dict[str, int] = {}
    runtime_reason_counts: Dict[str, int] = {}
    for item in items:
        static_route = str(item.get("static_route") or "")
        runtime_route = str(item.get("runtime_route") or item.get("route") or "")
        if not static_route or not runtime_route or static_route == runtime_route:
            continue
        changed_count += 1
        change_key = f"{static_route}->{runtime_route}"
        change_counts[change_key] = change_counts.get(change_key, 0) + 1
        runtime_reason = str(item.get("runtime_reason") or item.get("reason") or "")
        if runtime_reason:
            runtime_reason_counts[runtime_reason] = runtime_reason_counts.get(runtime_reason, 0) + 1
    return {
        "total": total,
        "changed_count": changed_count,
        "unchanged_count": max(0, total - changed_count),
        "changed_rate": round(changed_count / float(total), 4) if total > 0 else None,
        "top_changes": _v56_top_named_counts(change_counts, limit=limit),
        "top_runtime_reasons": _v56_top_named_counts(runtime_reason_counts, limit=limit),
    }


def _v56_backend_report_payload(
    decision: Optional[Any],
    fallback_used: Optional[str] = None,
    fallback_reason: Optional[str] = None,
) -> Dict[str, Any]:
    return backend_report_payload(decision, fallback_used=fallback_used, fallback_reason=fallback_reason)


def _v56_observability_summary(
    renderer: Any,
    *,
    segment_route_details: List[Dict[str, Any]],
    chunk_route_details: List[Dict[str, Any]],
    timings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    params = getattr(renderer, "params", {}) or {}
    render_settings = getattr(renderer, "plan", {}).get("render_settings", {}) or {}
    backend_payload = _v56_backend_report_payload(
        getattr(renderer, "backend_execution", None) or getattr(renderer, "backend_decision", None)
    )
    return {
        "backend_resolution": {
            **backend_payload,
            "render_mode": params.get("render_mode") or render_settings.get("render_mode") or "auto",
            "performance_mode": params.get("performance_mode") or render_settings.get("performance_mode"),
            "preview": bool(params.get("preview")),
        },
        "timing_highlights": _v56_timing_highlights(timings or getattr(renderer, "last_render_timings", {}) or {}),
        "cache_efficiency": {
            "visual_base_cache": _v56_cache_efficiency_entry(
                getattr(renderer, "visual_base_cache_stats", {}) or {},
                hit_keys=("hit", "chunk_hit"),
            ),
            "photo_segment_cache": _v56_cache_efficiency_entry(
                renderer._photo_segment_cache_summary() if hasattr(renderer, "_photo_segment_cache_summary") else {}
            ),
            "card_segment_cache": _v56_cache_efficiency_entry(
                renderer._card_segment_cache_summary() if hasattr(renderer, "_card_segment_cache_summary") else {}
            ),
            "video_segment_cache": _v56_cache_efficiency_entry(
                renderer._video_segment_cache_summary() if hasattr(renderer, "_video_segment_cache_summary") else {}
            ),
            "proxy_media": _v56_cache_efficiency_entry(
                renderer._proxy_media_summary() if hasattr(renderer, "_proxy_media_summary") else {},
                hit_keys=("hit", "manifest_hit"),
            ),
        },
        "fast_path_coverage": {
            "segments": _v56_fast_path_coverage(
                segment_route_details,
                fast_routes=("photo_prerender", "direct_chunk_candidate", "video_fit", "video_motion_fit"),
            ),
            "chunks": _v56_fast_path_coverage(
                chunk_route_details,
                fast_routes=("ffmpeg_direct_chunk", "ffmpeg_fitted_video_chunk", "ffmpeg_card_chunk", "ffmpeg_image_chunk"),
            ),
        },
        "route_differences": {
            "segments": _v56_route_difference_summary(segment_route_details),
        },
    }


def _v56_report_summary_fields(
    backend_payload: Dict[str, Any],
    diagnostics: Dict[str, Any],
    *,
    render_intent: str,
) -> Dict[str, Any]:
    observability = dict((diagnostics or {}).get("observability") or {})
    fast_path_coverage = dict(observability.get("fast_path_coverage") or {})
    segment_fast_path = dict(fast_path_coverage.get("segments") or {})
    chunk_fast_path = dict(fast_path_coverage.get("chunks") or {})
    route_differences = dict((observability.get("route_differences") or {}).get("segments") or {})
    return {
        "render_intent": render_intent,
        "actual_backend": backend_payload.get("actual_backend_name"),
        "backend_reason": backend_payload.get("reason"),
        "fallback_chain": list(backend_payload.get("fallback_chain") or []),
        "fallback_used": backend_payload.get("fallback_used"),
        "fallback_reason": backend_payload.get("fallback_reason"),
        "fallback_applied": bool(backend_payload.get("fallback_applied")),
        "segment_fast_path_rate": segment_fast_path.get("fast_path_rate"),
        "chunk_fast_path_rate": chunk_fast_path.get("fast_path_rate"),
        "segment_route_difference_count": int(route_differences.get("changed_count") or 0),
        "segment_route_difference_rate": route_differences.get("changed_rate"),
    }


def _v56_classify_render_failure(error: Any, stage: str) -> Dict[str, Any]:
    message = str(error or "")
    lowered = message.lower()
    code = f"{stage}_failed"
    if "concat" in lowered:
        code = "concat_failed"
    elif "audio" in lowered or "混合" in message:
        code = "audio_mix_failed"
    elif "validate" in lowered or "校验" in message:
        code = "output_validation_failed"
    elif "moviepy" in lowered and ("not installed" in lowered or "不可用" in message):
        code = "missing_moviepy_dependency"
    elif "ffmpeg" in lowered:
        code = "ffmpeg_failed"
    elif "unknown render backend" in lowered:
        code = "unknown_backend"

    retryable = stage in {"chunk_render", "concat", "audio_mix", "finalize", "output_validate"}
    if code in {"missing_moviepy_dependency", "unknown_backend"}:
        retryable = False

    return {
        "stage": stage,
        "code": code,
        "retryable": retryable,
        "message": message,
    }


def _v56_build_recovery_summary(
    manifest: Optional[Dict[str, Any]],
    *,
    chunk_reports: List[Dict[str, Any]],
    failed_chunk: Optional[str] = None,
    failure: Optional[Dict[str, Any]] = None,
    manifest_path: Optional[Path] = None,
    resumed_from_manifest: bool = False,
    reused_chunk_count: int = 0,
) -> Dict[str, Any]:
    manifest_chunks = ((manifest or {}).get("chunks") or {}) if isinstance(manifest, dict) else {}
    done_chunks = sum(1 for item in manifest_chunks.values() if item.get("status") == "done")
    failed_chunks = sum(1 for item in manifest_chunks.values() if item.get("status") == "failed")
    return {
        "resumable": True,
        "resumed_from_manifest": bool(resumed_from_manifest or failed_chunks or reused_chunk_count),
        "manifest_path": str(manifest_path) if manifest_path else None,
        "reused_chunk_count": reused_chunk_count,
        "completed_chunk_count": done_chunks,
        "failed_chunk_count": failed_chunks,
        "reported_chunk_count": len(chunk_reports),
        "failed_chunk": failed_chunk,
        "failure": dict(failure or {}),
    }


def _v56_render_diagnostics(
    renderer: Any,
    groups: List[Dict[str, Any]],
    chunk_reports: List[Dict[str, Any]],
    force_chunk_audio_track: bool,
    timings: Optional[Dict[str, Any]] = None,
    *,
    select_video_encoder_fn: SelectVideoEncoder = _default_select_video_encoder,
    should_default_to_hardware_encoding_fn: ShouldUseHardwareEncoding = _default_should_use_hardware_encoding,
) -> Dict[str, Any]:
    settings = getattr(renderer, "audio_settings", {}) or {}
    selected_encoder, encoder_args = select_video_encoder_fn(getattr(renderer, "params", {}) or {})
    cached = sum(1 for item in chunk_reports if item.get("status") == "cached")
    rendered = sum(1 for item in chunk_reports if item.get("status") == "rendered")
    segments = getattr(renderer, "plan", {}).get("segments", []) or []
    source_paths = []
    for seg in segments:
        source_path = seg.get("source_path")
        if source_path:
            source_paths.append(source_path)
    segment_route_details = _v56_collect_segment_route_details(segments)
    chunk_route_details = _v56_collect_chunk_route_details(groups, chunk_reports)
    return {
        "strategy_version": "render_diagnostics_v2",
        "backend": _v56_backend_report_payload(
            getattr(renderer, "backend_execution", None) or getattr(renderer, "backend_decision", None)
        ),
        "chunk_reuse": {
            "cached": cached,
            "rendered": rendered,
            "total": len(groups),
        },
        "smart_invalidation": {
            "enabled": True,
            "keys": ["engine_version", "render_params", "source_path", "file_size", "mtime_ns"],
            "fingerprinted_source_count": len(set(source_paths)),
        },
        "audio_mix": {
            "music_mode": settings.get("music_mode"),
            "keep_source_audio": bool(settings.get("keep_source_audio", True)),
            "source_audio_volume": settings.get("source_audio_volume"),
            "bgm_volume": settings.get("bgm_volume"),
            "auto_ducking": bool(settings.get("auto_ducking", True)),
            "normalize_audio": bool(settings.get("normalize_audio", False)),
            "target_lufs": settings.get("target_lufs"),
            "force_chunk_audio_track": bool(force_chunk_audio_track),
        },
        "encoding": {
            "selected_video_encoder": selected_encoder,
            "selected_video_encoder_args": encoder_args,
            "default_hardware_auto": should_default_to_hardware_encoding_fn(getattr(renderer, "params", {}) or {}),
        },
        "proxy_media": renderer._proxy_media_summary() if hasattr(renderer, "_proxy_media_summary") else {},
        "routing": {
            "segments": _v56_route_reason_summary(segment_route_details, "route", "reason"),
            "chunks": _v56_route_reason_summary(chunk_route_details, "route", "reason"),
            "segment_details": segment_route_details,
            "chunk_details": chunk_route_details,
        },
        "timings": dict(timings or getattr(renderer, "last_render_timings", {}) or {}),
        "observability": _v56_observability_summary(
            renderer,
            segment_route_details=segment_route_details,
            chunk_route_details=chunk_route_details,
            timings=timings,
        ),
    }
