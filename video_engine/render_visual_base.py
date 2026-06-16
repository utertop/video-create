"""Standard visual-base cache and materialization helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from video_engine.constants import ENGINE_VERSION
from video_engine.render_cache import (
    _v56_atomic_replace,
    _v56_segment_cache_key,
    _v56_stable_json_hash,
)
from video_engine.render_routes import (
    _v56_chunk_route_family,
    _v56_is_ffmpeg_fitted_video_chunk_route,
    _v56_segment_route_for_chunk_planning,
)


EmitEvent = Callable[..., None]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def standard_visual_cache_path(renderer: Any) -> Path:
    fps = int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30)
    key_payload = {
        "version": "standard_visual_base_v1",
        "engine_version": ENGINE_VERSION,
        "segments": renderer.plan.get("segments", []) or [],
        "aspect_ratio": renderer.params.get("aspect_ratio") or renderer.plan.get("render_settings", {}).get("aspect_ratio"),
        "fps": fps,
        "quality": renderer.params.get("quality") or renderer.plan.get("render_settings", {}).get("quality"),
        "python_quality": renderer.params.get("python_quality"),
        "preview": bool(renderer.params.get("preview")),
        "preview_height": renderer.params.get("preview_height"),
        "watermark": renderer.params.get("watermark"),
        "target_size": list(renderer.target_size),
        "audio_visual": renderer._visual_stage_audio_cache_payload(),
    }
    return renderer._cache_bucket_path(
        "final_video_bases",
        ".mp4",
        json.dumps(key_payload, ensure_ascii=False, sort_keys=True),
    )


def emit_visual_base_cache_summary(renderer: Any, *, emit_event_fn: EmitEvent = _noop_emit_event) -> None:
    stats = dict(renderer.visual_base_cache_stats)
    if stats["eligible"] <= 0:
        return
    emit_event_fn(
        "log",
        message=(
            "Visual base cache summary: "
            f"eligible={stats['eligible']}, "
            f"hit={stats['hit']}, "
            f"created={stats['created']}, "
            f"fallback={stats['fallback']}, "
            f"chunk_groups={stats['chunk_groups']}, "
            f"chunk_hit={stats['chunk_hit']}, "
            f"chunk_created={stats['chunk_created']}, "
            f"saved_render_seconds={stats['saved_render_seconds']}"
        ),
    )
    emit_event_fn("visual_base_cache", **stats)


def should_use_chunked_visual_base(renderer: Any) -> bool:
    if renderer.params.get("watermark"):
        return False
    segments = list(renderer.plan.get("segments") or [])
    if len(segments) < 2:
        return False
    enabled = renderer.params.get("visual_base_chunk_cache")
    if enabled is None:
        enabled = True
    return bool(enabled)


def is_safe_standard_visual_chunk_boundary(next_seg: Dict[str, Any]) -> bool:
    transition = next_seg.get("transition_config") or {}
    transition_type = str(transition.get("type") or next_seg.get("transition") or "none")
    transition_duration = float(transition.get("duration") or 0.0)
    return transition_type in {"none", "cut"} and transition_duration <= 0.05


def standard_visual_transition_influence(seg: Dict[str, Any]) -> Dict[str, Any]:
    transition = seg.get("transition_config") or {}
    transition_type = str(transition.get("type") or seg.get("transition") or "none")
    transition_duration = float(transition.get("duration") or 0.0)
    if transition_type in {"none", "cut"} and transition_duration <= 0.05:
        return {"type": transition_type, "backward": 0, "forward": 0, "safe_split": True}

    transition_influence_map = {
        "soft_crossfade": {"backward": 1, "forward": 0, "safe_split": False},
        "quick_zoom": {"backward": 1, "forward": 0, "safe_split": False},
        "flash_cut": {"backward": 1, "forward": 0, "safe_split": False},
        "fade_through_dark": {"backward": 1, "forward": 1, "safe_split": False},
        "fade_through_white": {"backward": 1, "forward": 1, "safe_split": False},
    }
    influence = transition_influence_map.get(
        transition_type,
        {"backward": 1, "forward": 1, "safe_split": False},
    )
    return {"type": transition_type, **influence}


def standard_visual_chunk_route_payload(renderer: Any, items: List[Dict[str, Any]]) -> Dict[str, Any]:
    routes = [_v56_segment_route_for_chunk_planning(seg, renderer.params) for seg in items]
    route_counts: Dict[str, int] = {}
    for route in routes:
        route_counts[route] = route_counts.get(route, 0) + 1
    if items and all(route == "direct_chunk_candidate" for route in routes):
        return {
            "runtime_chunk_route": "ffmpeg_direct_chunk",
            "runtime_chunk_route_reason": "all_segments_direct_chunk_safe",
            "runtime_chunk_route_tags": ["ffmpeg", "chunk", "direct", "visual_base"],
            "runtime_chunk_route_counts": route_counts,
        }
    if items and all(_v56_is_ffmpeg_fitted_video_chunk_route(route) for route in routes):
        return {
            "runtime_chunk_route": "ffmpeg_fitted_video_chunk",
            "runtime_chunk_route_reason": "all_segments_ffmpeg_fitted_video_safe",
            "runtime_chunk_route_tags": ["ffmpeg", "chunk", "video_fit", "visual_base"],
            "runtime_chunk_route_counts": route_counts,
        }
    if items and all(renderer._can_use_ffmpeg_card_chunk_segment(seg) for seg in items):
        return {
            "runtime_chunk_route": "ffmpeg_card_chunk",
            "runtime_chunk_route_reason": "all_segments_ffmpeg_card_chunk_safe",
            "runtime_chunk_route_tags": ["ffmpeg", "chunk", "card", "visual_base"],
            "runtime_chunk_route_counts": route_counts,
        }
    if items and all(renderer._can_use_ffmpeg_image_chunk_segment(seg) for seg in items):
        return {
            "runtime_chunk_route": "ffmpeg_image_chunk",
            "runtime_chunk_route_reason": "all_segments_ffmpeg_image_chunk_safe",
            "runtime_chunk_route_tags": ["ffmpeg", "chunk", "image", "visual_base"],
            "runtime_chunk_route_counts": route_counts,
        }
    return {
        "runtime_chunk_route": "moviepy_chunk",
        "runtime_chunk_route_reason": "safe_cut_boundary_visual_chunk",
        "runtime_chunk_route_tags": ["moviepy", "chunk", "timeline", "visual_base"],
        "runtime_chunk_route_counts": route_counts,
    }


def build_standard_visual_transition_units(renderer: Any) -> List[List[Dict[str, Any]]]:
    segments = list(renderer.plan.get("segments") or [])
    if not segments:
        return []
    ranges: List[Tuple[int, int]] = []
    for idx, seg in enumerate(segments):
        influence = standard_visual_transition_influence(seg)
        if influence.get("safe_split"):
            continue
        start = max(0, idx - int(influence.get("backward") or 0))
        end = min(len(segments) - 1, idx + int(influence.get("forward") or 0))
        ranges.append((start, end))

    merged_ranges: List[Tuple[int, int]] = []
    for start, end in ranges:
        if not merged_ranges or start > merged_ranges[-1][1] + 1:
            merged_ranges.append((start, end))
        else:
            prev_start, prev_end = merged_ranges[-1]
            merged_ranges[-1] = (prev_start, max(prev_end, end))

    units: List[List[Dict[str, Any]]] = []
    cursor = 0
    for start, end in merged_ranges:
        while cursor < start:
            units.append([segments[cursor]])
            cursor += 1
        units.append(segments[start:end + 1])
        cursor = end + 1
    while cursor < len(segments):
        units.append([segments[cursor]])
        cursor += 1
    return units


def build_standard_visual_chunk_groups(renderer: Any) -> List[Dict[str, Any]]:
    units = build_standard_visual_transition_units(renderer)
    if not units:
        return []
    max_segments = max(2, int(renderer.params.get("visual_base_chunk_max_segments") or 6))
    max_seconds = max(4.0, float(renderer.params.get("visual_base_chunk_seconds") or 20.0))
    groups: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_duration = 0.0
    current_keys: List[str] = []
    current_segment_count = 0
    current_family: Optional[str] = None

    def flush() -> None:
        nonlocal current, current_duration, current_keys, current_segment_count, current_family
        if not current:
            return
        groups.append({
            "index": len(groups),
            "segments": list(current),
            "duration": round(current_duration, 3),
            "cache_key": _v56_stable_json_hash(current_keys),
            **standard_visual_chunk_route_payload(renderer, current),
        })
        current = []
        current_duration = 0.0
        current_keys = []
        current_segment_count = 0
        current_family = None

    for unit in units:
        unit_duration = sum(float(seg.get("duration") or 0.0) for seg in unit)
        unit_segment_count = len(unit)
        unit_family = "timeline"
        if unit and all(_v56_chunk_route_family(seg, renderer.params) == "direct" for seg in unit):
            unit_family = "direct"
        elif unit and all(_v56_chunk_route_family(seg, renderer.params) == "card" for seg in unit):
            unit_family = "card"
        elif unit and all(_v56_chunk_route_family(seg, renderer.params) == "image" for seg in unit):
            unit_family = "image"
        if current:
            count_exceeded = (current_segment_count + unit_segment_count) > max_segments
            time_exceeded = (current_duration + unit_duration) > max_seconds
            family_changed = current_family != unit_family
            if count_exceeded or time_exceeded or family_changed:
                flush()
        current.extend(unit)
        current_duration += unit_duration
        current_segment_count += unit_segment_count
        current_family = unit_family
        for seg in unit:
            current_keys.append(_v56_segment_cache_key(seg, renderer.params))

    flush()
    return groups


def render_visual_timeline_clip(renderer: Any, *, emit_event_fn: EmitEvent = _noop_emit_event) -> Tuple[Any, List[Dict[str, Any]]]:
    clips: List[Any] = []
    rendered_segments: List[Dict[str, Any]] = []
    segments = renderer.plan.get("segments", [])
    total = max(1, len(segments))
    renderer._emit_render_scheduler_summary()

    for idx, seg in enumerate(segments, 1):
        emit_event_fn(
            "phase",
            phase="render",
            message=f"Processing segment {idx}/{total}: {seg.get('type')}",
            percent=min(90, int(idx / total * 90)),
        )
        clip = renderer._segment(seg)
        if clip is not None:
            clips.append(clip)
            rendered_segments.append(seg)

    if not clips:
        raise RuntimeError("No valid clips generated")

    emit_event_fn("phase", phase="render", message="Composing final video timeline", percent=91)
    final = renderer._compose_timeline(clips, rendered_segments)

    if renderer.params.get("watermark"):
        emit_event_fn("phase", phase="render", message="Applying watermark", percent=92)
        final = renderer._add_watermark(final, str(renderer.params.get("watermark")))

    return final, rendered_segments


def write_visual_base_video(
    renderer: Any,
    output_path: Path,
    *,
    logger_factory: Any,
    quality_to_crf_fn: Callable[[Any], str],
    close_clip_fn: Callable[[Any], None],
    emit_event_fn: EmitEvent = _noop_emit_event,
) -> float:
    final = None
    duration = 0.0
    try:
        final, _rendered_segments = render_visual_timeline_clip(renderer, emit_event_fn=emit_event_fn)
        duration = float(getattr(final, "duration", 0.0) or 0.0)
        logger = logger_factory(base_percent=92, span_percent=7)
        final.write_videofile(
            str(output_path),
            fps=int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30),
            codec="libx264",
            audio_codec="aac",
            preset="medium",
            threads=4,
            temp_audiofile=str(renderer.temp_dir / "temp_audio.m4a"),
            remove_temp=True,
            ffmpeg_params=[
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                "-crf",
                quality_to_crf_fn(renderer.params.get("python_quality") or renderer.params.get("quality")),
            ],
            logger=logger,
        )
        return duration
    finally:
        if final is not None:
            close_clip_fn(final)


def write_visual_base_video_from_chunks(
    renderer: Any,
    output_path: Path,
    *,
    validate_video_fn: Callable[..., Tuple[bool, str, Optional[float]]],
    write_chunk_video_fn: Callable[..., None],
    concat_chunks_ffmpeg_fn: Callable[..., bool],
    concat_chunks_ffmpeg_reencode_fn: Callable[..., bool],
    concat_chunks_moviepy_fn: Callable[..., None],
    atomic_replace_fn: Callable[[Path, Path], None] = _v56_atomic_replace,
    emit_event_fn: EmitEvent = _noop_emit_event,
) -> Optional[float]:
    if not should_use_chunked_visual_base(renderer):
        return None
    groups = build_standard_visual_chunk_groups(renderer)
    if len(groups) < 2:
        return None

    renderer.visual_base_cache_stats["chunk_groups"] = max(
        int(renderer.visual_base_cache_stats.get("chunk_groups") or 0),
        len(groups),
    )
    chunk_bucket = renderer.render_cache_dir / "visual_base_chunks"
    chunk_bucket.mkdir(parents=True, exist_ok=True)
    chunk_work_dir = renderer.render_cache_dir / "visual_base_chunk_work"
    chunk_work_dir.mkdir(parents=True, exist_ok=True)

    rendered_chunks: List[Path] = []
    for group in groups:
        chunk_path = chunk_bucket / f"{group['cache_key']}.mp4"
        ok, _reason, _duration = validate_video_fn(chunk_path, min_size=512)
        if ok:
            renderer.visual_base_cache_stats["chunk_hit"] += 1
            rendered_chunks.append(chunk_path)
            emit_event_fn("log", message=f"Visual base chunk cache hit: {chunk_path.name}")
            continue
        write_chunk_video_fn(
            renderer,
            group,
            chunk_path,
            int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30),
            renderer.params,
            ensure_audio_track=False,
        )
        ok, reason, _duration = validate_video_fn(chunk_path, min_size=512)
        if not ok:
            raise RuntimeError(f"visual base chunk validation failed: {reason}")
        renderer.visual_base_cache_stats["chunk_created"] += 1
        rendered_chunks.append(chunk_path)
        emit_event_fn("log", message=f"Visual base chunk cache created: {chunk_path.name}")

    tmp_output = output_path.with_suffix(".assembling.tmp.mp4")
    try:
        if tmp_output.exists():
            tmp_output.unlink()
    except Exception:
        pass

    concat_ok = concat_chunks_ffmpeg_fn(rendered_chunks, tmp_output, chunk_work_dir)
    if not concat_ok:
        concat_ok = concat_chunks_ffmpeg_reencode_fn(
            rendered_chunks,
            tmp_output,
            chunk_work_dir,
            int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30),
            renderer.params,
        )
    if not concat_ok:
        concat_chunks_moviepy_fn(
            rendered_chunks,
            tmp_output,
            int(renderer.params.get("fps") or renderer.plan.get("render_settings", {}).get("fps") or 30),
            renderer.params,
        )

    ok, reason, duration = validate_video_fn(tmp_output, min_size=512)
    if not ok:
        raise RuntimeError(f"visual base chunk concat failed: {reason}")
    atomic_replace_fn(tmp_output, output_path)
    return float(duration or 0.0)


def materialize_standard_visual_base(
    renderer: Any,
    *,
    validate_video_fn: Callable[..., Tuple[bool, str, Optional[float]]],
    write_visual_base_video_fn: Callable[[Path], float],
    write_visual_base_video_from_chunks_fn: Callable[[Path], Optional[float]],
    emit_event_fn: EmitEvent = _noop_emit_event,
) -> Tuple[Path, float]:
    renderer.visual_base_cache_stats["eligible"] += 1
    out = standard_visual_cache_path(renderer)
    ok, _reason, duration = validate_video_fn(out, min_size=512)
    if ok:
        renderer.visual_base_cache_stats["hit"] += 1
        renderer.visual_base_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
        emit_event_fn("log", message=f"Visual base cache hit: {out.name}")
        return out, float(duration or 0.0)

    try:
        if out.exists():
            out.unlink()
    except Exception:
        pass

    try:
        chunked_duration = write_visual_base_video_from_chunks_fn(out)
        duration = chunked_duration if chunked_duration is not None else write_visual_base_video_fn(out)
        ok, _reason, validated_duration = validate_video_fn(out, min_size=512)
        if ok:
            renderer.visual_base_cache_stats["created"] += 1
            emit_event_fn("log", message=f"Visual base cache created: {out.name}")
            return out, float(validated_duration or duration or 0.0)
    except Exception:
        renderer.visual_base_cache_stats["fallback"] += 1
        raise

    renderer.visual_base_cache_stats["fallback"] += 1
    raise RuntimeError("Failed to materialize standard visual base video")
