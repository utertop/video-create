from __future__ import annotations

import copy
from datetime import datetime
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple

from .cache import safe_id
from .constants import ENGINE_VERSION, SCHEMA_VERSION


def compile_from_timeline(
    timeline: Dict[str, Any],
    base_render_plan: Dict[str, Any],
    *,
    timeline_path: Optional[str] = None,
    source_render_plan_path: Optional[str] = None,
) -> Dict[str, Any]:
    started = perf_counter()
    timeline = timeline if isinstance(timeline, dict) else {}
    base_render_plan = base_render_plan if isinstance(base_render_plan, dict) else {}
    result = copy.deepcopy(base_render_plan)
    base_segments = [seg for seg in base_render_plan.get("segments") or [] if isinstance(seg, dict)]
    segment_lookup = {str(seg.get("segment_id") or ""): seg for seg in base_segments}
    track_order = {
        str(track.get("track_id") or ""): index
        for index, track in enumerate(sorted(timeline.get("tracks") or [], key=lambda item: int((item or {}).get("order_index") or 0)))
        if isinstance(track, dict)
    }

    visual_clips = _ordered_visual_clips(timeline, track_order)
    segments: List[Dict[str, Any]] = []
    cursor = 0.0
    skipped_disabled = 0
    changed_clip_ids: List[str] = []
    reused_cache_keys = 0

    for clip in visual_clips:
        if not clip.get("enabled", True):
            skipped_disabled += 1
            continue
        base_segment = _base_segment_for_clip(clip, segment_lookup)
        segment = _segment_from_clip(clip, base_segment, len(segments))
        duration = max(0.0, _float(clip.get("timeline_duration"), _float(segment.get("duration"), 0.0)))
        segment["duration"] = round(duration, 3)
        segment["start_time"] = round(cursor, 3)
        segment["end_time"] = round(cursor + duration, 3)
        cursor += duration

        if _clip_changed(clip):
            changed_clip_ids.append(str(clip.get("clip_id") or ""))
            if not _cache_reuse_expected(clip):
                segment["cache_key"] = _edited_cache_key(clip, segment)
        else:
            reused_cache_keys += 1
        segments.append(segment)

    result.update(
        {
            "schema_version": base_render_plan.get("schema_version") or SCHEMA_VERSION,
            "document_type": "render_plan",
            "segments": segments,
            "total_duration": round(cursor, 3),
        }
    )
    result["render_settings"] = _compile_audio_settings(timeline, copy.deepcopy(result.get("render_settings") or {}))
    result["render_scheduler"] = _compile_render_scheduler(segments)

    metadata = dict(result.get("metadata") or {})
    metadata.update(
        {
            "generated_at": datetime.now().isoformat(),
            "generated_from": "timeline",
            "timeline_source_path": timeline_path,
            "source_render_plan_path": source_render_plan_path,
            "timeline_compile_elapsed_ms": round((perf_counter() - started) * 1000, 3),
            "recompute_summary": {
                "strategy_version": "timeline_compile_recompute_v1",
                "total_clips": len(timeline.get("clip_index") or {}),
                "compiled_segments": len(segments),
                "skipped_disabled_clips": skipped_disabled,
                "changed_clip_ids": [item for item in changed_clip_ids if item],
                "reused_cache_keys": reused_cache_keys,
                "dirty": bool((timeline.get("metadata") or {}).get("dirty")),
                "last_edit_operation": (timeline.get("metadata") or {}).get("last_edit_operation"),
                "scopes": _recompute_scope_counts(timeline),
            },
        }
    )
    result["metadata"] = metadata
    return result


def _ordered_visual_clips(timeline: Dict[str, Any], track_order: Dict[str, int]) -> List[Dict[str, Any]]:
    clip_index = timeline.get("clip_index") if isinstance(timeline.get("clip_index"), dict) else {}
    clips = [clip for clip in clip_index.values() if isinstance(clip, dict) and not str(clip.get("kind") or "").startswith("audio_")]
    return sorted(
        clips,
        key=lambda clip: (
            _float(clip.get("timeline_start"), 0.0),
            track_order.get(str(clip.get("track_id") or ""), 999),
            str(clip.get("clip_id") or ""),
        ),
    )


def _base_segment_for_clip(clip: Dict[str, Any], segment_lookup: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    source = clip.get("source_ref") if isinstance(clip.get("source_ref"), dict) else {}
    segment_id = str(source.get("segment_id") or "")
    return copy.deepcopy(segment_lookup.get(segment_id) or {})


def _segment_from_clip(clip: Dict[str, Any], base_segment: Dict[str, Any], index: int) -> Dict[str, Any]:
    source = clip.get("source_ref") if isinstance(clip.get("source_ref"), dict) else {}
    content = clip.get("content_ref") if isinstance(clip.get("content_ref"), dict) else {}
    presentation = clip.get("presentation") if isinstance(clip.get("presentation"), dict) else {}
    execution = clip.get("execution") if isinstance(clip.get("execution"), dict) else {}
    segment = copy.deepcopy(base_segment)
    segment_type = segment.get("type") or _segment_type_from_clip_kind(str(clip.get("kind") or "image_asset"))

    segment.update(
        {
            "segment_id": segment.get("segment_id") or source.get("segment_id") or f"seg_timeline_{index:05d}",
            "type": segment_type,
            "source_path": content.get("source_path", segment.get("source_path")),
            "section_id": source.get("section_id", segment.get("section_id")),
            "asset_id": source.get("asset_id", segment.get("asset_id")),
            "render_route": execution.get("preferred_route", segment.get("render_route")),
            "render_route_reason": execution.get("route_reason", segment.get("render_route_reason")),
        }
    )

    if segment_type in {"title", "chapter", "end"}:
        segment["text"] = content.get("title_text", segment.get("text"))
        segment["subtitle"] = content.get("subtitle_text", segment.get("subtitle"))
        if presentation.get("title_style") is not None:
            segment["title_style"] = presentation.get("title_style")
    else:
        if content.get("title_text") is not None:
            segment["overlay_text"] = content.get("title_text")
        if content.get("subtitle_text") is not None:
            segment["overlay_subtitle"] = content.get("subtitle_text")
        if presentation.get("title_style") is not None:
            segment["overlay_title_style"] = presentation.get("title_style")

    if presentation.get("transition_type") is not None:
        transition = dict(segment.get("transition_config") or {})
        transition["type"] = presentation.get("transition_type")
        if presentation.get("transition_duration") is not None:
            transition["duration"] = presentation.get("transition_duration")
        segment["transition"] = transition.get("type")
        segment["transition_config"] = transition
    if presentation.get("motion_config") is not None:
        segment["motion_config"] = presentation.get("motion_config")
    if presentation.get("background_mode") is not None:
        segment["background_mode"] = presentation.get("background_mode")
    if presentation.get("background_source_path") is not None:
        segment["background_source_path"] = presentation.get("background_source_path")

    cache_policy = clip.get("cache_policy") if isinstance(clip.get("cache_policy"), dict) else {}
    if cache_policy.get("cache_fingerprint"):
        segment["cache_key"] = cache_policy.get("cache_fingerprint")
    elif execution.get("cache_key"):
        segment["cache_key"] = execution.get("cache_key")
    return segment


def _compile_audio_settings(timeline: Dict[str, Any], render_settings: Dict[str, Any]) -> Dict[str, Any]:
    audio_clips = [
        clip for clip in (timeline.get("clip_index") or {}).values()
        if isinstance(clip, dict) and str(clip.get("kind") or "").startswith("audio_") and clip.get("enabled", True)
    ]
    if not audio_clips:
        return render_settings

    audio = dict(render_settings.get("audio") or {})
    first = audio_clips[0]
    content = first.get("content_ref") if isinstance(first.get("content_ref"), dict) else {}
    metadata = first.get("metadata") if isinstance(first.get("metadata"), dict) else {}
    if content.get("source_path"):
        audio["music_mode"] = audio.get("music_mode") or "manual"
        audio["music_path"] = content.get("source_path")
        audio["music_source"] = "manual"
    if metadata.get("bgm_volume") is not None:
        audio["bgm_volume"] = metadata.get("bgm_volume")
    render_settings["audio"] = audio

    audio_blueprint = dict(render_settings.get("audio_blueprint") or {})
    cues = []
    for clip in sorted(audio_clips, key=lambda item: _float(item.get("timeline_start"), 0.0)):
        source = clip.get("source_ref") if isinstance(clip.get("source_ref"), dict) else {}
        content = clip.get("content_ref") if isinstance(clip.get("content_ref"), dict) else {}
        start = _float(clip.get("timeline_start"), 0.0)
        end = _float(clip.get("timeline_end"), start + _float(clip.get("timeline_duration"), 0.0))
        cues.append(
            {
                "section_id": source.get("section_id"),
                "title": content.get("title_text"),
                "phase": content.get("audio_profile") or "sustain",
                "start_time": round(start, 3),
                "end_time": round(end, 3),
                "duration": round(max(0.0, end - start), 3),
                "source_clip_id": clip.get("clip_id"),
            }
        )
    audio_blueprint["timeline_cues"] = cues
    render_settings["audio_blueprint"] = audio_blueprint
    return render_settings


def _compile_render_scheduler(segments: List[Dict[str, Any]]) -> Dict[str, Any]:
    route_counts: Dict[str, int] = {}
    total_duration = 0.0
    for segment in segments:
        route = str(segment.get("render_route") or "moviepy_required")
        route_counts[route] = route_counts.get(route, 0) + 1
        total_duration += _float(segment.get("duration"), 0.0)
    return {
        "strategy_version": "timeline_compile_segment_rules_v1",
        "route_counts": route_counts,
        "total_segments": len(segments),
        "total_duration": round(total_duration, 3),
    }


def _recompute_scope_counts(timeline: Dict[str, Any]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for clip in (timeline.get("clip_index") or {}).values():
        if not isinstance(clip, dict):
            continue
        hint = clip.get("invalidation_hint") if isinstance(clip.get("invalidation_hint"), dict) else {}
        scope = str(hint.get("primary_scope") or "none")
        counts[scope] = counts.get(scope, 0) + 1
    return counts


def _segment_type_from_clip_kind(kind: str) -> str:
    if kind == "video_asset":
        return "video"
    if kind == "image_asset":
        return "image"
    if kind == "chapter_card":
        return "chapter"
    if kind == "title_card":
        return "title"
    return "image"


def _clip_changed(clip: Dict[str, Any]) -> bool:
    edit_state = clip.get("edit_state") if isinstance(clip.get("edit_state"), dict) else {}
    return bool(edit_state.get("user_overridden"))


def _cache_reuse_expected(clip: Dict[str, Any]) -> bool:
    hint = clip.get("invalidation_hint") if isinstance(clip.get("invalidation_hint"), dict) else {}
    if hint.get("cache_reuse_expected") is not None:
        return bool(hint.get("cache_reuse_expected"))
    cache_policy = clip.get("cache_policy") if isinstance(clip.get("cache_policy"), dict) else {}
    if cache_policy.get("cache_reuse_expected") is not None:
        return bool(cache_policy.get("cache_reuse_expected"))
    return True


def _edited_cache_key(clip: Dict[str, Any], segment: Dict[str, Any]) -> str:
    edit_state = clip.get("edit_state") if isinstance(clip.get("edit_state"), dict) else {}
    return safe_id(
        "|".join(
            [
                "timeline_edit",
                str(clip.get("clip_id") or ""),
                str(segment.get("segment_id") or ""),
                str(edit_state.get("last_edited_at") or ""),
                str(edit_state.get("override_fields") or []),
                ENGINE_VERSION,
            ]
        )
    )


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)
