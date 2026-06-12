"""Render diagnostics and build-report helpers for the V5 renderer."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from render_backends import build_backend_report_payload as backend_report_payload


SelectVideoEncoder = Callable[[Dict[str, Any]], Tuple[str, List[str]]]
ShouldUseHardwareEncoding = Callable[[Dict[str, Any]], bool]
VideoHasAudioStream = Callable[[Path], bool]

FAST_SEGMENT_ROUTES = ("photo_prerender", "direct_chunk_candidate", "video_fit", "video_motion_fit")
FAST_CHUNK_ROUTES = ("ffmpeg_direct_chunk", "ffmpeg_fitted_video_chunk", "ffmpeg_card_chunk", "ffmpeg_image_chunk")


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
            "asset_id": seg.get("asset_id"),
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
            "source_name": Path(str(seg.get("source_path"))).name if seg.get("source_path") else None,
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
            "render_seconds": report.get("render_seconds"),
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


def _v56_segment_blockers(item: Dict[str, Any]) -> List[str]:
    route = str(item.get("route") or "")
    if route in FAST_SEGMENT_ROUTES:
        return []

    blockers: List[str] = []
    reason = str(item.get("reason") or "")
    if reason:
        blockers.append(f"reason:{reason}")
    if route:
        blockers.append(f"route:{route}")

    stype = str(item.get("type") or "")
    transition = str(item.get("transition") or "none")
    if transition not in {"", "none", "cut"}:
        blockers.append(f"transition:{transition}")

    motion = str(item.get("motion") or "none")
    if stype == "video" and motion not in {"none", "still_hold"}:
        blockers.append(f"video_motion:{motion}")
    elif stype == "image" and motion not in {"none", "still_hold", "gentle_push", "slow_push", "subtle_ken_burns", "micro_zoom"}:
        blockers.append(f"image_motion:{motion}")

    if bool(item.get("has_overlay")):
        blockers.append("overlay:text")
    if stype in {"title", "chapter", "end"}:
        blockers.append(f"card_type:{stype}")
    return blockers


def _v56_chunk_blockers(item: Dict[str, Any]) -> List[str]:
    route = str(item.get("route") or "")
    if route in FAST_CHUNK_ROUTES:
        return []

    blockers: List[str] = []
    reason = str(item.get("reason") or "")
    if reason:
        blockers.append(f"reason:{reason}")
    if route:
        blockers.append(f"route:{route}")
    for segment_route, count in sorted((item.get("route_counts") or {}).items()):
        if int(count or 0) > 0:
            blockers.append(f"contains:{segment_route}")
    return blockers


def _v56_ranked_blockers(items: List[Dict[str, Any]], blocker_fn: Callable[[Dict[str, Any]], List[str]], limit: int = 8) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for item in items:
        for blocker in blocker_fn(item):
            counts[blocker] = counts.get(blocker, 0) + 1
    return _v56_top_named_counts(counts, limit=limit)


def _v56_slow_segment_samples(items: List[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    samples: List[Dict[str, Any]] = []
    for item in items:
        blockers = _v56_segment_blockers(item)
        if not blockers:
            continue
        samples.append({
            "segment_id": item.get("segment_id"),
            "asset_id": item.get("asset_id"),
            "type": item.get("type"),
            "source_name": item.get("source_name"),
            "start_time": item.get("start_time"),
            "duration": item.get("duration"),
            "route": item.get("route"),
            "reason": item.get("reason"),
            "transition": item.get("transition"),
            "motion": item.get("motion"),
            "has_overlay": bool(item.get("has_overlay")),
            "blockers": blockers[:6],
        })
        if len(samples) >= limit:
            break
    return samples


def _v56_slow_chunk_samples(items: List[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    slow_items = [item for item in items if _v56_chunk_blockers(item)]
    slow_items.sort(key=lambda item: (-(float(item.get("render_seconds") or 0.0)), int(item.get("index") or 0)))
    samples: List[Dict[str, Any]] = []
    for item in slow_items[:limit]:
        samples.append({
            "name": item.get("name"),
            "index": item.get("index"),
            "status": item.get("status"),
            "segment_count": item.get("segment_count"),
            "duration": item.get("duration"),
            "render_seconds": item.get("render_seconds"),
            "route": item.get("route"),
            "reason": item.get("reason"),
            "route_counts": dict(item.get("route_counts") or {}),
            "blockers": _v56_chunk_blockers(item)[:8],
        })
    return samples


def _v56_slow_path_recommendations(
    *,
    segment_fast_path: Dict[str, Any],
    chunk_fast_path: Dict[str, Any],
    segment_blockers: List[Dict[str, Any]],
    chunk_blockers: List[Dict[str, Any]],
    selected_encoder: str,
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []
    segment_rate = segment_fast_path.get("fast_path_rate")
    chunk_rate = chunk_fast_path.get("fast_path_rate")

    if chunk_rate is not None and float(chunk_rate) < 0.5:
        recommendations.append({
            "id": "increase_chunk_fast_path_coverage",
            "priority": "high",
            "message": "Most chunks still render through MoviePy; expand FFmpeg image/video/card chunk coverage first.",
        })
    if segment_rate is not None and float(segment_rate) < 0.5:
        recommendations.append({
            "id": "reduce_segment_moviepy_routes",
            "priority": "high",
            "message": "Most segments are not on a fast path; inspect top segment blockers before tuning encoding.",
        })

    blocker_names = {str(item.get("name") or "") for item in [*segment_blockers, *chunk_blockers]}
    if any("transition:" in name for name in blocker_names):
        recommendations.append({
            "id": "simplify_long_video_transitions",
            "priority": "medium",
            "message": "Complex transitions are blocking FFmpeg routes; use cut/light transitions for long-video stable exports.",
        })
    if any("overlay:text" in name for name in blocker_names):
        recommendations.append({
            "id": "cache_or_limit_text_overlays",
            "priority": "medium",
            "message": "Text overlays are keeping segments on MoviePy; prefer cacheable overlay styles or prerendered cards.",
        })
    if str(selected_encoder or "") == "libx264":
        recommendations.append({
            "id": "enable_hardware_encoder_auto",
            "priority": "medium",
            "message": "Final encoding is using libx264; hardware_encoder=auto may reduce export time on supported GPUs.",
        })
    if not recommendations:
        recommendations.append({
            "id": "fast_paths_healthy",
            "priority": "low",
            "message": "Fast-path coverage looks healthy; focus on the top timing step or unusually slow chunks.",
        })
    return recommendations[:6]


def _v56_slow_path_report(
    segment_route_details: List[Dict[str, Any]],
    chunk_route_details: List[Dict[str, Any]],
    *,
    selected_encoder: str,
) -> Dict[str, Any]:
    segment_fast_path = _v56_fast_path_coverage(
        segment_route_details,
        fast_routes=FAST_SEGMENT_ROUTES,
        limit=8,
    )
    chunk_fast_path = _v56_fast_path_coverage(
        chunk_route_details,
        fast_routes=FAST_CHUNK_ROUTES,
        limit=8,
    )
    segment_blockers = _v56_ranked_blockers(segment_route_details, _v56_segment_blockers)
    chunk_blockers = _v56_ranked_blockers(chunk_route_details, _v56_chunk_blockers)
    return {
        "strategy_version": "slow_path_report_v1",
        "segments": {
            **segment_fast_path,
            "top_blockers": segment_blockers,
            "samples": _v56_slow_segment_samples(segment_route_details),
        },
        "chunks": {
            **chunk_fast_path,
            "top_blockers": chunk_blockers,
            "samples": _v56_slow_chunk_samples(chunk_route_details),
        },
        "recommendations": _v56_slow_path_recommendations(
            segment_fast_path=segment_fast_path,
            chunk_fast_path=chunk_fast_path,
            segment_blockers=segment_blockers,
            chunk_blockers=chunk_blockers,
            selected_encoder=selected_encoder,
        ),
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
        "cache_policy": dict(getattr(renderer, "cache_policy_summary", {}) or {}),
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
                fast_routes=FAST_SEGMENT_ROUTES,
            ),
            "chunks": _v56_fast_path_coverage(
                chunk_route_details,
                fast_routes=FAST_CHUNK_ROUTES,
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
    slow_path_report = dict((diagnostics or {}).get("slow_path_report") or {})
    slow_segments = dict(slow_path_report.get("segments") or {})
    slow_chunks = dict(slow_path_report.get("chunks") or {})
    top_blockers = list(slow_segments.get("top_blockers") or slow_chunks.get("top_blockers") or [])
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
        "slow_segment_count": int(slow_segments.get("non_fast_path_count") or 0),
        "slow_chunk_count": int(slow_chunks.get("non_fast_path_count") or 0),
        "top_slow_path_blockers": top_blockers[:5],
        "segment_route_difference_count": int(route_differences.get("changed_count") or 0),
        "segment_route_difference_rate": route_differences.get("changed_rate"),
    }


def _v56_build_report_v2_fields(report: Dict[str, Any]) -> Dict[str, Any]:
    report = dict(report or {})
    backend = dict(report.get("backend") or {})
    diagnostics = dict(report.get("diagnostics") or {})
    observability = dict(diagnostics.get("observability") or {})
    cache_efficiency = dict(observability.get("cache_efficiency") or {})
    fast_path = dict(observability.get("fast_path_coverage") or {})
    route_differences = dict(observability.get("route_differences") or {})
    cache_policy = dict(report.get("cache_policy") or observability.get("cache_policy") or {})
    render_scheduler = dict(report.get("render_scheduler") or {})
    chunk_scheduler = dict(report.get("chunk_scheduler") or {})
    timings = dict(report.get("timings") or {})
    metadata = dict(report.get("metadata") or {})
    recompute = dict(
        report.get("recompute_summary")
        or metadata.get("recompute_summary")
        or (diagnostics.get("smart_invalidation") or {}).get("recompute_summary")
        or {}
    )
    recovery = dict(report.get("recovery") or {})
    failure = dict(report.get("failure") or recovery.get("failure") or {})
    slow_path_report = dict(diagnostics.get("slow_path_report") or {})
    slow_recommendations = list(slow_path_report.get("recommendations") or [])
    segment_routes = list(report.get("segment_routes") or [])
    chunk_routes = list(report.get("chunk_routes") or [])
    chunks = list(report.get("chunks") or [])

    segment_fast_path = dict(fast_path.get("segments") or {})
    chunk_fast_path = dict(fast_path.get("chunks") or {})
    segment_route_diff = dict(route_differences.get("segments") or {})
    source_kind = "timeline" if metadata.get("generated_from") == "timeline" else "render_plan"

    timeline_summary = {
        "source": source_kind,
        "compiled_from_timeline": source_kind == "timeline",
        "timeline_source_path": metadata.get("timeline_source_path"),
        "source_render_plan_path": metadata.get("source_render_plan_path"),
        "total_segments": int(
            render_scheduler.get("total_segments")
            or len(segment_routes)
            or report.get("chunk_count")
            or 0
        ),
        "enabled_clip_count": recompute.get("enabled_clip_count"),
        "disabled_clip_count": recompute.get("disabled_clip_count"),
        "edited_clip_count": recompute.get("edited_clip_count"),
    }

    route_summary = {
        "render_mode": report.get("render_mode"),
        "selected_backend": report.get("selected_backend"),
        "actual_backend": report.get("actual_backend") or backend.get("actual_backend_name"),
        "backend_reason": report.get("backend_reason") or backend.get("reason"),
        "segment_route_counts": dict(render_scheduler.get("route_counts") or {}),
        "chunk_route_counts": dict(chunk_scheduler.get("route_counts") or {}),
        "segment_fast_path_rate": report.get("segment_fast_path_rate") or segment_fast_path.get("fast_path_rate"),
        "chunk_fast_path_rate": report.get("chunk_fast_path_rate") or chunk_fast_path.get("fast_path_rate"),
        "segment_route_difference_count": report.get("segment_route_difference_count") or segment_route_diff.get("changed_count") or 0,
        "segment_route_difference_rate": report.get("segment_route_difference_rate") or segment_route_diff.get("changed_rate"),
        "segment_route_sample_count": len(segment_routes),
        "chunk_route_sample_count": len(chunk_routes),
    }

    fallback_summary = {
        "applied": bool(report.get("fallback_applied") or backend.get("fallback_applied")),
        "used": report.get("fallback_used") or backend.get("fallback_used"),
        "reason": report.get("fallback_reason") or backend.get("fallback_reason"),
        "chain": list(report.get("fallback_chain") or backend.get("fallback_chain") or []),
    }

    cache_summary = {
        "policy": cache_policy,
        "cleanup": dict(report.get("cache_cleanup") or {}),
        "efficiency": cache_efficiency,
        "visual_base_cache": dict(report.get("visual_base_cache") or {}),
        "photo_segment_cache": dict(report.get("photo_segment_cache") or {}),
        "card_segment_cache": dict(report.get("card_segment_cache") or {}),
        "video_segment_cache": dict(report.get("video_segment_cache") or {}),
        "proxy_media": dict(report.get("proxy_media") or {}),
    }

    recompute_summary = {
        **recompute,
        "render_intent": report.get("render_intent") or cache_policy.get("render_intent"),
        "cache_namespace": cache_policy.get("cache_namespace"),
        "timeline_dirty": bool(metadata.get("timeline_dirty") or recompute.get("timeline_dirty")),
    }

    performance_summary = {
        "elapsed_seconds": report.get("elapsed_seconds") or timings.get("total_render_seconds"),
        "duration_seconds": report.get("duration_seconds"),
        "output_size_bytes": report.get("output_size_bytes"),
        "chunk_count": report.get("chunk_count") or len(chunks) or None,
        "timing_highlights": dict(observability.get("timing_highlights") or {}),
        "slow_path_report": slow_path_report,
    }

    quality_summary = {
        "render_intent": report.get("render_intent") or cache_policy.get("render_intent"),
        "uses_original_source": cache_policy.get("uses_original_source"),
        "allow_proxy": cache_policy.get("allow_proxy"),
        "proxy_allowed_for_final": cache_policy.get("proxy_allowed_for_final"),
        "quality": cache_policy.get("quality"),
        "python_quality": cache_policy.get("python_quality"),
        "fps": cache_policy.get("fps"),
        "preview_height": cache_policy.get("preview_height"),
        "final_original_source_guard": bool(cache_policy.get("render_intent") == "final" and cache_policy.get("uses_original_source") is True),
    }

    recovery_summary = {
        **recovery,
        "status": report.get("status"),
        "failed_stage": report.get("failed_stage"),
        "failed_chunk": report.get("failed_chunk") or recovery.get("failed_chunk"),
        "failure_code": failure.get("code"),
        "failure_message": failure.get("message") or report.get("error"),
        "retryable": bool(failure.get("retryable")),
    }

    suggestions = [
        item
        for item in slow_recommendations
        if isinstance(item, dict)
    ]
    if fallback_summary["applied"]:
        suggestions.append({
            "id": "review_backend_fallback",
            "priority": "medium",
            "message": "Backend fallback was applied; inspect backend_reason and fallback_reason before tuning render quality.",
        })
    if cache_policy.get("render_intent") == "final" and cache_policy.get("allow_proxy"):
        suggestions.append({
            "id": "final_proxy_guard_violation",
            "priority": "high",
            "message": "Final render reports proxy usage is allowed; verify preview/final cache policy before export.",
        })

    return {
        "build_report_version": "v2",
        "timeline_summary": timeline_summary,
        "route_summary": route_summary,
        "fallback_summary": fallback_summary,
        "cache_summary": cache_summary,
        "recompute_summary": recompute_summary,
        "performance_summary": performance_summary,
        "quality_summary": quality_summary,
        "recovery_summary": recovery_summary,
        "migration_notes": list(report.get("migration_notes") or []),
        "report_suggestions": suggestions[:8],
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
    slow_path_report = _v56_slow_path_report(
        segment_route_details,
        chunk_route_details,
        selected_encoder=selected_encoder,
    )
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
        "slow_path_report": slow_path_report,
        "timings": dict(timings or getattr(renderer, "last_render_timings", {}) or {}),
        "observability": _v56_observability_summary(
            renderer,
            segment_route_details=segment_route_details,
            chunk_route_details=chunk_route_details,
            timings=timings,
        ),
    }
