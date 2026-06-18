from __future__ import annotations

import audioop
import hashlib
import copy
import json
import math
import subprocess
from collections.abc import Iterable as IterableABC
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import SCHEMA_VERSION

TIMELINE_VERSION = "v1"
TIMELINE_INVALIDATION_RULES_VERSION = "timeline_invalidation_v1"
TIMELINE_CACHE_FINGERPRINT_VERSION = "timeline_cache_v1"

TIMELINE_EDIT_OPERATION_ALIASES = {
    "title_text_change": "title_text_change",
    "title_text": "title_text_change",
    "title_style_change": "title_style_change",
    "title_style": "title_style_change",
    "subtitle_text_change": "subtitle_text_change",
    "subtitle_text": "subtitle_text_change",
    "clip_enable_disable": "clip_enable_disable",
    "clip_enable_toggle": "clip_enable_disable",
    "clip_enabled_change": "clip_enable_disable",
    "clip_reorder": "clip_reorder",
    "clip_move": "clip_reorder",
    "image_duration_change": "image_duration_change",
    "clip_duration_change": "image_duration_change",
    "bgm_volume_change": "bgm_volume_change",
    "audio_volume_change": "bgm_volume_change",
    "bgm_cue_range_change": "bgm_cue_range_change",
    "audio_cue_range_change": "bgm_cue_range_change",
    "preview_quality_change": "preview_quality_change",
    "preview_settings_change": "preview_quality_change",
    "final_quality_change": "final_quality_change",
    "final_settings_change": "final_quality_change",
    "aspect_ratio_change": "aspect_ratio_change",
}


def build_timeline_document(
    blueprint: Optional[Dict[str, Any]],
    render_plan: Dict[str, Any],
    *,
    media_library: Optional[Dict[str, Any]] = None,
    existing_timeline: Optional[Dict[str, Any]] = None,
    media_library_path: Optional[str] = None,
    story_blueprint_path: Optional[str] = None,
    render_plan_path: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a V5 timeline document without changing the render plan.

    The first timeline version is a stable editable layer derived from today's
    render_plan/blueprint facts. It is intentionally conservative: it records
    identity, source links, timing, and policy hints, but does not change render
    execution.
    """

    blueprint = blueprint if isinstance(blueprint, dict) else {}
    media_library = media_library if isinstance(media_library, dict) else {}
    existing_timeline = existing_timeline if isinstance(existing_timeline, dict) else {}

    segment_lookup = _segment_lookup(existing_timeline)
    tracks = [
        _track("track_video_main", "video", "Main Video", 0),
        _track("track_title_main", "title", "Titles", 1),
        _track("track_audio_main", "audio", "Audio", 2),
    ]
    track_by_id = {track["track_id"]: track for track in tracks}
    clip_index: Dict[str, Dict[str, Any]] = {}
    dependency_graph: List[Dict[str, Any]] = []

    for occurrence, segment in enumerate(render_plan.get("segments") or []):
        if not isinstance(segment, dict):
            continue
        clip = build_clip_from_segment(segment, occurrence, segment_lookup=segment_lookup)
        clip_index[clip["clip_id"]] = clip
        track_by_id[clip["track_id"]]["clip_ids"].append(clip["clip_id"])

        section_id = ((clip.get("source_ref") or {}).get("section_id"))
        asset_id = ((clip.get("source_ref") or {}).get("asset_id"))
        if section_id or asset_id:
            dependency_graph.append(
                {
                    "dependency_id": _stable_id(
                        "dep",
                        clip["clip_id"],
                        section_id or "",
                        asset_id or "",
                    ),
                    "from_clip_id": clip["clip_id"],
                    "to_clip_id": None,
                    "kind": "derived_from_asset" if asset_id else "derived_from_section",
                    "source_section_id": section_id,
                    "source_asset_id": asset_id,
                    "strict": False,
                    "reason": "timeline clip derived from render segment",
                }
            )

    for occurrence, clip in enumerate(
        build_audio_clips(
            blueprint,
            render_plan,
            media_library,
            existing_timeline=existing_timeline,
        )
    ):
        if clip["clip_id"] in clip_index:
            clip["clip_id"] = _stable_id("clip_audio_bgm", clip["clip_id"], str(occurrence))
        clip_index[clip["clip_id"]] = clip
        track_by_id["track_audio_main"]["clip_ids"].append(clip["clip_id"])

    for track in tracks:
        track["enabled"] = bool(track["clip_ids"])

    project_ref = {
        "project_id": _stable_id("project", project_dir or "", story_blueprint_path or "", render_plan_path or ""),
        "project_dir": project_dir,
        "title": blueprint.get("title") or None,
    }
    source_ref = {
        "media_library_path": media_library_path,
        "story_blueprint_path": story_blueprint_path,
        "render_plan_path": render_plan_path,
        "generated_from_blueprint": bool(blueprint),
        "generated_at": datetime.now().isoformat(),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": "timeline",
        "timeline_version": TIMELINE_VERSION,
        "project_ref": project_ref,
        "source_ref": source_ref,
        "tracks": tracks,
        "clip_index": clip_index,
        "dependency_graph": dependency_graph,
        "invalidation_rules_version": TIMELINE_INVALIDATION_RULES_VERSION,
        "performance_policy": default_performance_policy(render_plan),
        "metadata": {
            "created_at": _existing_created_at(existing_timeline),
            "updated_at": datetime.now().isoformat(),
            "generated_from": "blueprint" if blueprint else "migration",
            "editor_mode": "auto",
            "migration_notes": [],
        },
    }


def build_timeline_from_render_plan(
    render_plan: Dict[str, Any],
    *,
    existing_timeline: Optional[Dict[str, Any]] = None,
    render_plan_path: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> Dict[str, Any]:
    return build_timeline_document(
        None,
        render_plan,
        existing_timeline=existing_timeline,
        render_plan_path=render_plan_path,
        project_dir=project_dir,
    )


def build_timeline_from_blueprint(
    blueprint: Dict[str, Any],
    render_plan: Dict[str, Any],
    *,
    media_library: Optional[Dict[str, Any]] = None,
    existing_timeline: Optional[Dict[str, Any]] = None,
    media_library_path: Optional[str] = None,
    story_blueprint_path: Optional[str] = None,
    render_plan_path: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> Dict[str, Any]:
    return build_timeline_document(
        blueprint,
        render_plan,
        media_library=media_library,
        existing_timeline=existing_timeline,
        media_library_path=media_library_path,
        story_blueprint_path=story_blueprint_path,
        render_plan_path=render_plan_path,
        project_dir=project_dir,
    )


def migrate_timeline_document(timeline: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], List[str]]:
    if not isinstance(timeline, dict):
        raise ValueError("timeline document must be an object")
    if timeline.get("document_type") != "timeline":
        raise ValueError(f"timeline document_type mismatch: {timeline.get('document_type')!r}")

    result = copy.deepcopy(timeline)
    notes: List[str] = []
    migrated = False

    def ensure_object(key: str) -> None:
        nonlocal migrated
        if not isinstance(result.get(key), dict):
            result[key] = {}
            migrated = True
            notes.append(f"timeline: ensure {key}")

    def ensure_array(key: str) -> None:
        nonlocal migrated
        if not isinstance(result.get(key), list):
            result[key] = []
            migrated = True
            notes.append(f"timeline: ensure {key}")

    schema_version = str(result.get("schema_version") or "missing")
    if schema_version != SCHEMA_VERSION:
        result["schema_version"] = SCHEMA_VERSION
        migrated = True
        notes.append(f"schema_version {schema_version} -> {SCHEMA_VERSION}")

    timeline_version = str(result.get("timeline_version") or "missing")
    if timeline_version != TIMELINE_VERSION:
        result["timeline_version"] = TIMELINE_VERSION
        migrated = True
        notes.append(f"timeline_version {timeline_version} -> {TIMELINE_VERSION}")

    ensure_object("project_ref")
    ensure_object("source_ref")
    ensure_array("tracks")
    ensure_object("clip_index")
    ensure_array("dependency_graph")
    ensure_object("metadata")
    ensure_object("performance_policy")

    if result.get("invalidation_rules_version") != TIMELINE_INVALIDATION_RULES_VERSION:
        result["invalidation_rules_version"] = TIMELINE_INVALIDATION_RULES_VERSION
        migrated = True
        notes.append("timeline: ensure invalidation_rules_version")

    policy = result["performance_policy"]
    if not isinstance(policy.get("preview"), dict):
        policy["preview"] = {
            "cache_namespace": "preview",
            "uses_original_source": False,
            "allow_proxy": True,
        }
        migrated = True
        notes.append("timeline: ensure preview performance policy")
    if not isinstance(policy.get("final"), dict):
        policy["final"] = {
            "cache_namespace": "final",
            "uses_original_source": True,
            "allow_proxy": False,
        }
        migrated = True
        notes.append("timeline: ensure final performance policy")

    metadata = result["metadata"]
    if not isinstance(metadata.get("migration_notes"), list):
        metadata["migration_notes"] = []
        migrated = True
        notes.append("timeline: ensure metadata.migration_notes")
    if notes:
        metadata["migration_notes"] = [*metadata.get("migration_notes", []), *notes]
        metadata["updated_at"] = datetime.now().isoformat()

    return migrated, result, notes


def recover_timeline_document(
    blueprint: Optional[Dict[str, Any]],
    render_plan: Dict[str, Any],
    *,
    media_library: Optional[Dict[str, Any]] = None,
    existing_timeline: Optional[Dict[str, Any]] = None,
    media_library_path: Optional[str] = None,
    story_blueprint_path: Optional[str] = None,
    render_plan_path: Optional[str] = None,
    project_dir: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[str]]:
    notes: List[str] = []
    migrated_existing: Optional[Dict[str, Any]] = None
    if isinstance(existing_timeline, dict):
        try:
            migrated, migrated_existing, migration_notes = migrate_timeline_document(existing_timeline)
            if migrated:
                notes.extend(migration_notes)
        except Exception as exc:
            notes.append(f"timeline migration failed; original timeline ignored: {exc}")
            migrated_existing = None

    if isinstance(blueprint, dict) and blueprint:
        timeline = build_timeline_from_blueprint(
            blueprint,
            render_plan,
            media_library=media_library,
            existing_timeline=migrated_existing,
            media_library_path=media_library_path,
            story_blueprint_path=story_blueprint_path,
            render_plan_path=render_plan_path,
            project_dir=project_dir,
        )
    else:
        timeline = build_timeline_from_render_plan(
            render_plan,
            existing_timeline=migrated_existing,
            render_plan_path=render_plan_path,
            project_dir=project_dir,
        )

    metadata = dict(timeline.get("metadata") or {})
    metadata["migration_notes"] = [*metadata.get("migration_notes", []), *notes]
    if notes:
        metadata["recovered"] = True
        metadata["recovery_source"] = "existing_timeline_migration"
    timeline["metadata"] = metadata
    return timeline, notes


def resolve_timeline_recompute_scope(
    operation: Dict[str, Any],
    *,
    clip: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve the smallest safe recompute scope for a timeline edit operation."""

    operation = operation if isinstance(operation, dict) else {}
    clip = clip if isinstance(clip, dict) else None
    operation_type = _normalize_timeline_edit_operation(operation.get("type") or operation.get("operation_type"))
    clip_id = _operation_clip_id(operation, clip)
    track_id = _operation_track_id(operation, clip)
    affected_clip_ids = _unique_strings(operation.get("affected_clip_ids") or ([clip_id] if clip_id else []))
    affected_track_ids = _unique_strings(operation.get("affected_track_ids") or ([track_id] if track_id else []))

    if operation_type in {"title_text_change", "title_style_change", "subtitle_text_change"}:
        return _invalidation_hint(
            "clip_only",
            affected_clip_ids,
            affected_track_ids,
            cache_reuse_expected=False,
            requires_render_plan_recompile=True,
            requires_audio_relayout=False,
            reason=f"{operation_type} affects only the edited title/subtitle clip",
        )

    if operation_type in {"clip_enable_disable", "clip_reorder", "image_duration_change"}:
        return _invalidation_hint(
            "timeline_compile",
            affected_clip_ids,
            affected_track_ids,
            cache_reuse_expected=False,
            requires_render_plan_recompile=True,
            requires_audio_relayout=False,
            reason=f"{operation_type} changes visual timeline structure or timing",
        )

    if operation_type == "bgm_volume_change":
        return _invalidation_hint(
            "track_only",
            affected_clip_ids,
            affected_track_ids or ["track_audio_main"],
            cache_reuse_expected=True,
            requires_render_plan_recompile=False,
            requires_audio_relayout=False,
            reason="bgm volume change affects audio mix only",
        )

    if operation_type == "bgm_cue_range_change":
        return _invalidation_hint(
            "track_only",
            affected_clip_ids,
            affected_track_ids or ["track_audio_main"],
            cache_reuse_expected=False,
            requires_render_plan_recompile=False,
            requires_audio_relayout=True,
            reason="bgm cue range change affects audio timeline layout only",
        )

    if operation_type == "preview_quality_change":
        return _invalidation_hint(
            "preview_only",
            [],
            [],
            cache_reuse_expected=False,
            requires_render_plan_recompile=False,
            requires_audio_relayout=False,
            reason="preview quality change invalidates preview cache only",
        )

    if operation_type == "final_quality_change":
        return _invalidation_hint(
            "final_render_only",
            [],
            [],
            cache_reuse_expected=False,
            requires_render_plan_recompile=False,
            requires_audio_relayout=False,
            reason="final quality change invalidates final render cache only",
        )

    if operation_type == "aspect_ratio_change":
        return _invalidation_hint(
            "full_rebuild",
            [],
            [],
            cache_reuse_expected=False,
            requires_render_plan_recompile=True,
            requires_audio_relayout=False,
            reason="aspect ratio change affects project-wide visual geometry",
        )

    return _invalidation_hint(
        "full_rebuild",
        affected_clip_ids,
        affected_track_ids,
        cache_reuse_expected=False,
        requires_render_plan_recompile=True,
        requires_audio_relayout=True,
        reason=f"unknown timeline edit operation: {operation_type}",
    )


def update_clip_enabled(timeline: Dict[str, Any], clip_id: str, enabled: bool) -> Dict[str, Any]:
    return _apply_clip_edit(
        timeline,
        clip_id,
        lambda clip: {**clip, "enabled": bool(enabled)},
        ["enabled"],
        {"type": "clip_enable_disable", "clip_id": clip_id},
    )


def update_clip_content(timeline: Dict[str, Any], clip_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    patch = patch if isinstance(patch, dict) else {}
    operation_type = "subtitle_text_change" if "subtitle_text" in patch and "title_text" not in patch else "title_text_change"

    def updater(clip: Dict[str, Any]) -> Dict[str, Any]:
        content = dict(clip.get("content_ref") or {})
        content.update(patch)
        return {**clip, "content_ref": content}

    return _apply_clip_edit(
        timeline,
        clip_id,
        updater,
        [f"content_ref.{key}" for key in patch.keys()],
        {"type": operation_type, "clip_id": clip_id},
    )


def update_clip_presentation(timeline: Dict[str, Any], clip_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    patch = patch if isinstance(patch, dict) else {}

    def updater(clip: Dict[str, Any]) -> Dict[str, Any]:
        presentation = dict(clip.get("presentation") or {})
        presentation.update(patch)
        return {**clip, "presentation": presentation}

    return _apply_clip_edit(
        timeline,
        clip_id,
        updater,
        [f"presentation.{key}" for key in patch.keys()],
        {"type": "title_style_change", "clip_id": clip_id},
    )


def update_clip_duration(timeline: Dict[str, Any], clip_id: str, duration: float) -> Dict[str, Any]:
    result = copy.deepcopy(timeline)
    location = _find_clip_location(result, clip_id)
    if not location:
        return result

    track, index = location
    clip_index = result.get("clip_index") or {}
    clip = clip_index.get(clip_id)
    if not isinstance(clip, dict):
        return result

    next_duration = round(max(0.1, _float(duration, clip.get("timeline_duration") or 0.1)), 3)
    delta = next_duration - _float(clip.get("timeline_duration"), 0.0)
    affected_ids = [str(item) for item in track.get("clip_ids", [])[index:]]
    operation = {
        "type": "image_duration_change",
        "clip_id": clip_id,
        "track_id": track.get("track_id"),
        "affected_clip_ids": affected_ids,
        "affected_track_ids": [track.get("track_id")],
    }
    now = datetime.now().isoformat()

    for affected_id in affected_ids:
        affected = clip_index.get(affected_id)
        if not isinstance(affected, dict):
            continue
        if affected_id == clip_id:
            source_in = affected.get("source_in")
            updated = {
                **affected,
                "timeline_duration": next_duration,
                "timeline_end": round(_float(affected.get("timeline_start"), 0.0) + next_duration, 3),
                "source_out": round(_float(source_in, 0.0) + next_duration, 3) if source_in is not None else affected.get("source_out"),
            }
            clip_index[affected_id] = _with_edit_metadata(updated, ["timeline_duration", "timeline_end", "source_out"], now, operation)
        else:
            clip_index[affected_id] = {
                **affected,
                "timeline_start": round(_float(affected.get("timeline_start"), 0.0) + delta, 3),
                "timeline_end": round(_float(affected.get("timeline_end"), 0.0) + delta, 3),
            }

    return _mark_timeline_dirty(result, "image_duration_change", now)


def move_clip(timeline: Dict[str, Any], clip_id: str, target_index: int) -> Dict[str, Any]:
    result = copy.deepcopy(timeline)
    location = _find_clip_location(result, clip_id)
    if not location:
        return result

    track, index = location
    clip_ids = [str(item) for item in track.get("clip_ids") or []]
    clip_ids.pop(index)
    clamped = max(0, min(int(target_index), len(clip_ids)))
    clip_ids.insert(clamped, clip_id)
    track["clip_ids"] = clip_ids

    now = datetime.now().isoformat()
    operation = {
        "type": "clip_reorder",
        "clip_id": clip_id,
        "track_id": track.get("track_id"),
        "affected_clip_ids": clip_ids,
        "affected_track_ids": [track.get("track_id")],
    }
    _relayout_track_clips(result.get("clip_index") or {}, clip_ids, now, operation)
    return _mark_timeline_dirty(result, "clip_reorder", now)


def update_bgm_cue_volume(timeline: Dict[str, Any], clip_id: str, volume: float) -> Dict[str, Any]:
    safe_volume = min(1.0, max(0.0, _float(volume, 0.0)))

    def updater(clip: Dict[str, Any]) -> Dict[str, Any]:
        metadata = dict(clip.get("metadata") or {})
        metadata["bgm_volume"] = safe_volume
        return {**clip, "metadata": metadata}

    return _apply_clip_edit(
        timeline,
        clip_id,
        updater,
        ["metadata.bgm_volume"],
        {"type": "bgm_volume_change", "clip_id": clip_id},
    )


def update_preview_quality_profile(timeline: Dict[str, Any], profile: str) -> Dict[str, Any]:
    result = copy.deepcopy(timeline if isinstance(timeline, dict) else {})
    profile = str(profile or "balanced")
    if profile not in {"auto", "performance", "balanced", "high", "original"}:
        profile = "balanced"
    resolved = _resolve_preview_quality_profile(profile)
    policy = dict(result.get("performance_policy") or {})
    preview = dict(policy.get("preview") or {})
    preview.update(
        {
            "profile": profile,
            "mode": resolved["mode"],
            "fps": resolved["fps"],
            "cache_namespace": "preview",
        }
    )
    if resolved.get("height") is None:
        preview.pop("height", None)
    else:
        preview["height"] = resolved["height"]
    policy["preview"] = preview

    final = dict(policy.get("final") or {})
    final.update(
        {
            "uses_original_source": True,
            "allow_proxy": False,
            "cache_namespace": "final",
        }
    )
    policy["final"] = final
    policy["thumbnail"] = {**dict(policy.get("thumbnail") or {}), "cache_namespace": "thumbnail"}
    policy["proxy"] = {**dict(policy.get("proxy") or {}), "cache_namespace": "proxy"}
    policy["cache_fingerprint_version"] = policy.get("cache_fingerprint_version") or TIMELINE_CACHE_FINGERPRINT_VERSION
    result["performance_policy"] = policy

    now = datetime.now().isoformat()
    metadata = dict(result.get("metadata") or {})
    metadata.update(
        {
            "updated_at": now,
            "editor_mode": "guided",
            "preview_settings_dirty": True,
            "preview_quality_profile": profile,
            "preview_quality_updated_at": now,
            "last_edit_operation": "preview_quality_change",
        }
    )
    result["metadata"] = metadata
    return result


def build_timeline_preview_manifest(
    timeline: Dict[str, Any],
    *,
    media_library: Optional[Dict[str, Any]] = None,
    proxy_media_manifest: Optional[Dict[str, Any]] = None,
    project_dir: Optional[str] = None,
    timeline_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a deterministic manifest for timeline preview assets.

    The manifest is intentionally an index, not a generator. It lets the UI and
    later workers know which thumbnails, proxy files, waveforms, and preview
    segments belong to each clip under the current preview quality policy.
    """

    if not isinstance(timeline, dict):
        raise ValueError("timeline document must be an object")
    if timeline.get("document_type") != "timeline":
        raise ValueError(f"timeline document_type mismatch: {timeline.get('document_type')!r}")

    media_library = media_library if isinstance(media_library, dict) else {}
    project_ref = timeline.get("project_ref") if isinstance(timeline.get("project_ref"), dict) else {}
    effective_project_dir = project_dir or project_ref.get("project_dir")
    cache_root, render_cache_root = _timeline_preview_cache_roots(effective_project_dir)
    asset_by_id, asset_by_path = _timeline_asset_lookup(media_library)
    proxy_lookup = _timeline_proxy_lookup(proxy_media_manifest or media_library.get("proxy_media_manifest"))

    policy = dict(timeline.get("performance_policy") or {})
    preview_policy = _normalized_preview_policy(policy.get("preview"))
    cache_namespaces = {
        "preview": preview_policy.get("cache_namespace") or "preview",
        "final": (dict(policy.get("final") or {})).get("cache_namespace") or "final",
        "thumbnail": (dict(policy.get("thumbnail") or {})).get("cache_namespace") or "thumbnail",
        "proxy": (dict(policy.get("proxy") or {})).get("cache_namespace") or "proxy",
    }

    clips: Dict[str, Any] = {}
    summary = {
        "total_clips": 0,
        "visual_clips": 0,
        "audio_clips": 0,
        "thumbnail_ready": 0,
        "thumbnail_planned": 0,
        "thumbnail_failed": 0,
        "proxy_ready": 0,
        "proxy_planned": 0,
        "proxy_failed": 0,
        "waveform_ready": 0,
        "waveform_planned": 0,
        "waveform_failed": 0,
        "preview_segment_ready": 0,
        "preview_segment_planned": 0,
        "preview_segment_failed": 0,
        "missing_sources": 0,
    }

    clip_index = timeline.get("clip_index") if isinstance(timeline.get("clip_index"), dict) else {}
    for clip_id, raw_clip in clip_index.items():
        if not isinstance(raw_clip, dict):
            continue
        clip = raw_clip
        clip_id = str(clip.get("clip_id") or clip_id)
        kind = str(clip.get("kind") or "unknown")
        content_ref = clip.get("content_ref") if isinstance(clip.get("content_ref"), dict) else {}
        source_ref = clip.get("source_ref") if isinstance(clip.get("source_ref"), dict) else {}
        source_path = _first_string(
            content_ref.get("source_path"),
            content_ref.get("background_source_path"),
            source_ref.get("source_path"),
        )
        asset_id = _first_string(source_ref.get("asset_id"), content_ref.get("asset_id"))
        asset = asset_by_id.get(asset_id or "") or asset_by_path.get(_norm_path(source_path))
        source_path = source_path or _first_string((asset or {}).get("absolute_path"), (asset or {}).get("path"))
        source_state = _source_state(source_path)
        source_fingerprint = _source_fingerprint(source_path)
        artifact_key = _stable_id(
            "tl_asset",
            clip_id,
            kind,
            source_path or "",
            preview_policy.get("profile") or "",
            preview_policy.get("mode") or "",
            preview_policy.get("height") or "",
            preview_policy.get("fps") or "",
            source_fingerprint.get("fingerprint") if source_fingerprint else "",
        )

        entry = {
            "clip_id": clip_id,
            "kind": kind,
            "track_id": clip.get("track_id"),
            "enabled": bool(clip.get("enabled", True)),
            "timeline_start": _float(clip.get("timeline_start"), 0.0),
            "timeline_duration": _float(clip.get("timeline_duration"), 0.0),
            "timeline_end": _float(clip.get("timeline_end"), 0.0),
            "source_ref": {
                "asset_id": asset_id,
                "source_path": source_path,
                "source_state": source_state,
                "source_fingerprint": source_fingerprint,
            },
            "artifact_key": artifact_key,
        }

        summary["total_clips"] += 1
        if source_state == "missing":
            summary["missing_sources"] += 1

        if _is_visual_clip(kind):
            summary["visual_clips"] += 1
            entry["thumbnail"] = _thumbnail_artifact(
                clip,
                asset or {},
                source_state,
                artifact_key,
                cache_root,
                cache_namespaces["thumbnail"],
            )
            _count_artifact(summary, "thumbnail", entry["thumbnail"])
            entry["preview_segment"] = _preview_segment_artifact(
                source_state,
                artifact_key,
                render_cache_root,
                cache_namespaces["preview"],
                preview_policy,
            )
            _count_artifact(summary, "preview_segment", entry["preview_segment"])
        else:
            entry["thumbnail"] = _not_applicable_artifact(cache_namespaces["thumbnail"])
            entry["preview_segment"] = _not_applicable_artifact(cache_namespaces["preview"])

        if kind == "video_asset":
            entry["proxy"] = _proxy_artifact(
                source_path,
                source_state,
                artifact_key,
                cache_root,
                cache_namespaces["proxy"],
                preview_policy,
                proxy_lookup,
            )
            _count_artifact(summary, "proxy", entry["proxy"])
        else:
            entry["proxy"] = _not_applicable_artifact(cache_namespaces["proxy"])

        if _is_audio_clip(kind):
            summary["audio_clips"] += 1
            entry["waveform"] = _waveform_artifact(
                source_state,
                artifact_key,
                cache_root,
                cache_namespaces["preview"],
            )
            _count_artifact(summary, "waveform", entry["waveform"])
        else:
            entry["waveform"] = _not_applicable_artifact(cache_namespaces["preview"])

        clips[clip_id] = entry

    return {
        "schema_version": SCHEMA_VERSION,
        "document_type": "timeline_preview_manifest",
        "manifest_version": "timeline_preview_manifest_v1",
        "timeline_version": timeline.get("timeline_version") or TIMELINE_VERSION,
        "generated_at": datetime.now().isoformat(),
        "timeline_path": timeline_path,
        "project_ref": project_ref,
        "source_ref": timeline.get("source_ref") if isinstance(timeline.get("source_ref"), dict) else {},
        "preview_policy": preview_policy,
        "final_policy": dict(policy.get("final") or {}),
        "cache_namespaces": cache_namespaces,
        "cache_roots": {
            "asset_cache_root": str(cache_root) if cache_root else None,
            "render_cache_root": str(render_cache_root) if render_cache_root else None,
        },
        "summary": summary,
        "clips": clips,
    }


def generate_timeline_preview_assets(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Generate missing preview assets described by a timeline preview manifest."""

    return generate_timeline_preview_assets_with_events(manifest)


def generate_timeline_preview_assets_with_events(
    manifest: Dict[str, Any],
    *,
    emit_event_fn=None,
    batch_size: int = 8,
) -> Dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ValueError("timeline preview manifest must be an object")
    if manifest.get("document_type") != "timeline_preview_manifest":
        raise ValueError(f"timeline preview manifest document_type mismatch: {manifest.get('document_type')!r}")

    result = copy.deepcopy(manifest)
    clips = result.get("clips") if isinstance(result.get("clips"), dict) else {}
    report = {
        "generated_at": datetime.now().isoformat(),
        "thumbnail": {"created": 0, "hit": 0, "failed": 0, "skipped": 0},
        "proxy": {"created": 0, "hit": 0, "failed": 0, "skipped": 0},
        "waveform": {"created": 0, "hit": 0, "failed": 0, "skipped": 0},
        "preview_segment": {"created": 0, "hit": 0, "failed": 0, "skipped": 0},
    }

    total_tasks = _count_preview_asset_tasks(clips)
    completed_tasks = 0
    batch_size = max(1, int(batch_size or 8))
    _emit_preview_asset_progress(emit_event_fn, None, completed_tasks, total_tasks, "running", None)

    for clip in clips.values():
        if not isinstance(clip, dict):
            continue
        source_ref = clip.get("source_ref") if isinstance(clip.get("source_ref"), dict) else {}
        source_path = _first_string(source_ref.get("source_path"))

        thumbnail = clip.get("thumbnail") if isinstance(clip.get("thumbnail"), dict) else {}
        clip["thumbnail"] = _generate_thumbnail_asset(clip, thumbnail, source_path, report["thumbnail"])
        completed_tasks = _advance_preview_asset_progress(
            clip,
            "thumbnail",
            completed_tasks,
            total_tasks,
            clip["thumbnail"],
            emit_event_fn=emit_event_fn,
            batch_size=batch_size,
        )

        proxy = clip.get("proxy") if isinstance(clip.get("proxy"), dict) else {}
        clip["proxy"] = _generate_proxy_asset(proxy, source_path, report["proxy"])
        completed_tasks = _advance_preview_asset_progress(
            clip,
            "proxy",
            completed_tasks,
            total_tasks,
            clip["proxy"],
            emit_event_fn=emit_event_fn,
            batch_size=batch_size,
        )

        waveform = clip.get("waveform") if isinstance(clip.get("waveform"), dict) else {}
        clip["waveform"] = _generate_waveform_asset(waveform, source_path, report["waveform"])
        completed_tasks = _advance_preview_asset_progress(
            clip,
            "waveform",
            completed_tasks,
            total_tasks,
            clip["waveform"],
            emit_event_fn=emit_event_fn,
            batch_size=batch_size,
        )

        preview_segment = clip.get("preview_segment") if isinstance(clip.get("preview_segment"), dict) else {}
        clip["preview_segment"] = _generate_preview_segment_asset(
            clip,
            preview_segment,
            source_path,
            report["preview_segment"],
        )
        completed_tasks = _advance_preview_asset_progress(
            clip,
            "preview_segment",
            completed_tasks,
            total_tasks,
            clip["preview_segment"],
            emit_event_fn=emit_event_fn,
            batch_size=batch_size,
        )

    result["clips"] = clips
    result["summary"] = _timeline_preview_manifest_summary(clips)
    result["generation_report"] = report
    result["generated_assets_at"] = report["generated_at"]
    _emit_preview_asset_progress(emit_event_fn, None, total_tasks, total_tasks, "done", "timeline preview assets generated")
    return result


def build_clip_from_segment(
    segment: Dict[str, Any],
    occurrence: int,
    *,
    segment_lookup: Dict[Tuple[str, str, str, str, str], str],
) -> Dict[str, Any]:
    segment_type = str(segment.get("type") or "image")
    kind = _clip_kind_for_segment(segment)
    track_id = "track_title_main" if kind in {"title_card", "chapter_card", "subtitle_overlay"} else "track_video_main"
    source_ref = {
        "section_id": segment.get("section_id"),
        "asset_id": segment.get("asset_id"),
        "segment_id": segment.get("segment_id"),
        "directory_node_id": None,
    }
    content_ref = {
        "source_path": segment.get("source_path"),
        "title_text": segment.get("text") or segment.get("overlay_text"),
        "subtitle_text": segment.get("subtitle") or segment.get("overlay_subtitle"),
        "audio_profile": None,
        "template_id": None,
    }
    lookup_key = _segment_lookup_key(segment, kind)
    clip_id = segment_lookup.get(lookup_key) or _stable_id(
        f"clip_{kind}",
        source_ref.get("section_id") or "",
        source_ref.get("asset_id") or "",
        source_ref.get("segment_id") or "",
        content_ref.get("source_path") or "",
        str(occurrence),
    )
    start = _float(segment.get("start_time"), 0.0)
    duration = _float(segment.get("duration"), max(0.0, _float(segment.get("end_time"), start) - start))
    end = _float(segment.get("end_time"), start + duration)

    return {
        "clip_id": clip_id,
        "kind": kind,
        "track_id": track_id,
        "timeline_start": round(start, 3),
        "timeline_duration": round(max(0.0, duration), 3),
        "timeline_end": round(end, 3),
        "source_in": 0.0 if segment_type in {"video", "image"} else None,
        "source_out": round(duration, 3) if segment_type in {"video", "image"} else None,
        "playback_rate": 1.0,
        "enabled": True,
        "source_ref": source_ref,
        "content_ref": content_ref,
        "edit_state": {
            "auto_generated": True,
            "user_overridden": False,
            "override_fields": [],
            "origin": "plan",
            "last_edited_at": None,
        },
        "presentation": _presentation_from_segment(segment),
        "execution": {
            "preferred_route": segment.get("render_route"),
            "route_reason": segment.get("render_route_reason"),
            "cache_key": segment.get("cache_key"),
            "preview_supported": True,
            "final_render_supported": True,
        },
        "invalidation_hint": {
            "primary_scope": "clip_only" if kind in {"title_card", "chapter_card", "subtitle_overlay"} else "timeline_compile",
            "affected_track_ids": [track_id],
            "affected_clip_ids": [clip_id],
            "cache_reuse_expected": True,
            "requires_render_plan_recompile": kind not in {"title_card", "chapter_card", "subtitle_overlay"},
            "requires_audio_relayout": False,
            "reason": "initial timeline generation from render segment",
        },
        "cache_policy": {
            "cache_namespace": "final",
            "cache_fingerprint": segment.get("cache_key"),
            "cache_reuse_expected": True,
        },
        "metadata": {
            "render_segment_type": segment_type,
            "transition": segment.get("transition"),
            "render_route_tags": segment.get("render_route_tags") or [],
        },
    }


def build_audio_clips(
    blueprint: Dict[str, Any],
    render_plan: Dict[str, Any],
    media_library: Dict[str, Any],
    *,
    existing_timeline: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    existing_audio = _existing_audio_lookup(existing_timeline)
    settings = render_plan.get("render_settings") or {}
    audio_blueprint = settings.get("audio_blueprint") or (blueprint.get("metadata") or {}).get("audio_blueprint") or {}
    audio_settings = settings.get("audio") or (blueprint.get("metadata") or {}).get("audio") or {}
    cues = audio_blueprint.get("timeline_cues") or audio_blueprint.get("section_cues") or []
    clips: List[Dict[str, Any]] = []

    music_path = audio_settings.get("music_path")
    selected_asset_id = audio_settings.get("selected_asset_id")
    if not music_path and selected_asset_id:
        music_path = _asset_path(media_library, selected_asset_id)
    if not music_path:
        selected_candidate = audio_blueprint.get("selected_candidate") if isinstance(audio_blueprint, dict) else None
        if isinstance(selected_candidate, dict):
            music_path = selected_candidate.get("absolute_path")
            selected_asset_id = selected_candidate.get("asset_id") or selected_asset_id

    if isinstance(cues, list) and cues:
        for occurrence, cue in enumerate(cue for cue in cues if isinstance(cue, dict)):
            start = _float(cue.get("start_time"), 0.0)
            duration = _float(cue.get("duration"), max(0.0, _float(cue.get("end_time"), start) - start))
            end = _float(cue.get("end_time"), start + duration)
            clip_id = existing_audio.get(str(cue.get("section_id") or "")) or _stable_id(
                "clip_audio_bgm",
                cue.get("section_id") or "",
                music_path or "",
                str(occurrence),
            )
            clips.append(_audio_clip(clip_id, start, duration, end, music_path, selected_asset_id, cue))
    elif music_path or audio_settings.get("music_mode") in {"auto", "manual"}:
        duration = _float(render_plan.get("total_duration"), 0.0)
        clip_id = existing_audio.get("") or _stable_id("clip_audio_bgm", music_path or "music", "full")
        clips.append(_audio_clip(clip_id, 0.0, duration, duration, music_path, selected_asset_id, {}))

    return clips


def default_performance_policy(render_plan: Dict[str, Any]) -> Dict[str, Any]:
    settings = render_plan.get("render_settings") or {}
    return {
        "preview": {
            "profile": "balanced",
            "mode": "proxy",
            "height": int(settings.get("preview_height") or 540),
            "fps": min(int(settings.get("fps") or 30), 15),
            "cache_namespace": "preview",
            "preferred_backend": "legacy_moviepy_backend",
        },
        "final": {
            "uses_original_source": True,
            "allow_proxy": False,
            "cache_namespace": "final",
            "preferred_backend": "ffmpeg_stable_backend",
        },
        "thumbnail": {"cache_namespace": "thumbnail"},
        "proxy": {"cache_namespace": "proxy"},
        "cache_fingerprint_version": TIMELINE_CACHE_FINGERPRINT_VERSION,
    }


def _resolve_preview_quality_profile(profile: str) -> Dict[str, Any]:
    if profile == "performance":
        return {"mode": "low_res", "height": 540, "fps": 15}
    if profile == "high":
        return {"mode": "proxy", "height": 1080, "fps": 30}
    if profile == "original":
        return {"mode": "original", "height": None, "fps": 30}
    return {"mode": "proxy", "height": 720, "fps": 24}


def _audio_clip(
    clip_id: str,
    start: float,
    duration: float,
    end: float,
    music_path: Optional[str],
    asset_id: Optional[str],
    cue: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "clip_id": clip_id,
        "kind": "audio_bgm",
        "track_id": "track_audio_main",
        "timeline_start": round(start, 3),
        "timeline_duration": round(max(0.0, duration), 3),
        "timeline_end": round(end, 3),
        "source_in": round(start, 3),
        "source_out": round(end, 3),
        "playback_rate": 1.0,
        "enabled": True,
        "source_ref": {
            "section_id": cue.get("section_id"),
            "asset_id": asset_id,
            "segment_id": None,
            "directory_node_id": None,
        },
        "content_ref": {
            "source_path": music_path,
            "title_text": cue.get("title"),
            "subtitle_text": None,
            "audio_profile": cue.get("energy") or cue.get("phase"),
            "template_id": None,
        },
        "edit_state": {
            "auto_generated": True,
            "user_overridden": False,
            "override_fields": [],
            "origin": "plan",
            "last_edited_at": None,
        },
        "execution": {
            "preferred_route": "audio_mix",
            "route_reason": "audio timeline cue",
            "cache_key": None,
            "preview_supported": True,
            "final_render_supported": True,
        },
        "invalidation_hint": {
            "primary_scope": "track_only",
            "affected_track_ids": ["track_audio_main"],
            "affected_clip_ids": [clip_id],
            "cache_reuse_expected": True,
            "requires_render_plan_recompile": False,
            "requires_audio_relayout": True,
            "reason": "audio cue generated from render settings",
        },
        "cache_policy": {
            "cache_namespace": "final",
            "cache_fingerprint": None,
            "cache_reuse_expected": True,
        },
        "metadata": {"cue": cue},
    }


def _clip_kind_for_segment(segment: Dict[str, Any]) -> str:
    segment_type = str(segment.get("type") or "")
    if segment_type == "video":
        return "video_asset"
    if segment_type == "image":
        return "image_asset"
    if segment_type == "chapter":
        return "chapter_card"
    if segment_type in {"title", "end"}:
        return "title_card"
    if segment.get("overlay_text") or segment.get("overlay_subtitle"):
        return "subtitle_overlay"
    return "image_asset"


def _presentation_from_segment(segment: Dict[str, Any]) -> Dict[str, Any]:
    transition = segment.get("transition_config") if isinstance(segment.get("transition_config"), dict) else {}
    return {
        "title_style": segment.get("title_style") or segment.get("overlay_title_style"),
        "transition_type": transition.get("type") or segment.get("transition"),
        "transition_duration": transition.get("duration"),
        "motion_config": segment.get("motion_config"),
        "background_mode": segment.get("background_mode"),
        "background_source_path": segment.get("background_source_path"),
    }


def _track(track_id: str, kind: str, name: str, order_index: int) -> Dict[str, Any]:
    return {
        "track_id": track_id,
        "kind": kind,
        "name": name,
        "order_index": order_index,
        "enabled": True,
        "locked": False,
        "lane_mode": "single",
        "clip_ids": [],
        "metadata": {"generated": True},
    }


def _segment_lookup(existing_timeline: Dict[str, Any]) -> Dict[Tuple[str, str, str, str, str], str]:
    lookup: Dict[Tuple[str, str, str, str, str], str] = {}
    clip_index = existing_timeline.get("clip_index") if isinstance(existing_timeline, dict) else None
    if not isinstance(clip_index, dict):
        return lookup
    for clip_id, clip in clip_index.items():
        if not isinstance(clip, dict):
            continue
        source = clip.get("source_ref") or {}
        content = clip.get("content_ref") or {}
        key = (
            str(clip.get("kind") or ""),
            str(source.get("section_id") or ""),
            str(source.get("asset_id") or ""),
            str(source.get("segment_id") or ""),
            str(content.get("source_path") or content.get("title_text") or ""),
        )
        lookup[key] = str(clip_id)
    return lookup


def _segment_lookup_key(segment: Dict[str, Any], kind: str) -> Tuple[str, str, str, str, str]:
    return (
        kind,
        str(segment.get("section_id") or ""),
        str(segment.get("asset_id") or ""),
        str(segment.get("segment_id") or ""),
        str(segment.get("source_path") or segment.get("text") or ""),
    )


def _existing_audio_lookup(existing_timeline: Optional[Dict[str, Any]]) -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    clip_index = (existing_timeline or {}).get("clip_index")
    if not isinstance(clip_index, dict):
        return lookup
    for clip_id, clip in clip_index.items():
        if not isinstance(clip, dict) or clip.get("kind") != "audio_bgm":
            continue
        source = clip.get("source_ref") or {}
        lookup[str(source.get("section_id") or "")] = str(clip_id)
    return lookup


def _asset_path(media_library: Dict[str, Any], asset_id: str) -> Optional[str]:
    for asset in media_library.get("assets") or []:
        if isinstance(asset, dict) and asset.get("asset_id") == asset_id:
            return asset.get("absolute_path")
    return None


def _existing_created_at(existing_timeline: Dict[str, Any]) -> str:
    metadata = existing_timeline.get("metadata") if isinstance(existing_timeline, dict) else None
    if isinstance(metadata, dict) and metadata.get("created_at"):
        return str(metadata["created_at"])
    return datetime.now().isoformat()


def _apply_clip_edit(
    timeline: Dict[str, Any],
    clip_id: str,
    updater,
    override_fields: List[str],
    operation: Dict[str, Any],
) -> Dict[str, Any]:
    result = copy.deepcopy(timeline)
    clip_index = result.get("clip_index") if isinstance(result.get("clip_index"), dict) else {}
    clip = clip_index.get(clip_id)
    if not isinstance(clip, dict):
        return result
    now = datetime.now().isoformat()
    clip_index[clip_id] = _with_edit_metadata(updater(clip), override_fields, now, operation)
    result["clip_index"] = clip_index
    return _mark_timeline_dirty(result, str(operation.get("type") or "timeline_edit"), now)


def _with_edit_metadata(
    clip: Dict[str, Any],
    override_fields: List[str],
    now: str,
    operation: Dict[str, Any],
) -> Dict[str, Any]:
    edit_state = dict(clip.get("edit_state") or {"auto_generated": True})
    previous_fields = edit_state.get("override_fields") if isinstance(edit_state.get("override_fields"), list) else []
    edit_state.update(
        {
            "auto_generated": False,
            "user_overridden": True,
            "override_fields": _unique_strings([*previous_fields, *override_fields]),
            "origin": "timeline_edit",
            "last_edited_at": now,
        }
    )
    return {
        **clip,
        "edit_state": edit_state,
        "invalidation_hint": resolve_timeline_recompute_scope(operation, clip=clip),
    }


def _mark_timeline_dirty(timeline: Dict[str, Any], operation_type: str, now: str) -> Dict[str, Any]:
    metadata = dict(timeline.get("metadata") or {})
    metadata.update(
        {
            "updated_at": now,
            "editor_mode": "guided",
            "dirty": True,
            "dirty_reason": "timeline_edit",
            "last_edit_operation": operation_type,
        }
    )
    timeline["metadata"] = metadata
    return timeline


def _find_clip_location(timeline: Dict[str, Any], clip_id: str):
    for track in timeline.get("tracks") or []:
        if not isinstance(track, dict):
            continue
        clip_ids = track.get("clip_ids")
        if not isinstance(clip_ids, list):
            continue
        if clip_id in clip_ids:
            return track, clip_ids.index(clip_id)
    return None


def _relayout_track_clips(
    clip_index: Dict[str, Any],
    clip_ids: List[str],
    now: str,
    operation: Dict[str, Any],
) -> None:
    cursor = 0.0
    for clip_id in clip_ids:
        clip = clip_index.get(clip_id)
        if not isinstance(clip, dict):
            continue
        duration = max(0.0, _float(clip.get("timeline_duration"), 0.0))
        updated = {
            **clip,
            "timeline_start": round(cursor, 3),
            "timeline_end": round(cursor + duration, 3),
        }
        if clip_id == operation.get("clip_id"):
            updated = _with_edit_metadata(updated, ["track_order", "timeline_start", "timeline_end"], now, operation)
        clip_index[clip_id] = updated
        cursor += duration


def _normalize_timeline_edit_operation(value: Any) -> str:
    key = str(value or "").strip()
    return TIMELINE_EDIT_OPERATION_ALIASES.get(key, key or "unknown")


def _operation_clip_id(operation: Dict[str, Any], clip: Optional[Dict[str, Any]]) -> Optional[str]:
    value = operation.get("clip_id")
    if value is None and clip:
        value = clip.get("clip_id")
    return str(value) if value not in {None, ""} else None


def _operation_track_id(operation: Dict[str, Any], clip: Optional[Dict[str, Any]]) -> Optional[str]:
    value = operation.get("track_id")
    if value is None and clip:
        value = clip.get("track_id")
    return str(value) if value not in {None, ""} else None


def _unique_strings(values: Any) -> List[str]:
    if isinstance(values, (str, bytes)):
        values = [values]
    if not isinstance(values, IterableABC):
        return []
    result: List[str] = []
    seen = set()
    for value in values:
        if value in {None, ""}:
            continue
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _invalidation_hint(
    primary_scope: str,
    affected_clip_ids: List[str],
    affected_track_ids: List[str],
    *,
    cache_reuse_expected: bool,
    requires_render_plan_recompile: bool,
    requires_audio_relayout: bool,
    reason: str,
) -> Dict[str, Any]:
    return {
        "primary_scope": primary_scope,
        "affected_clip_ids": affected_clip_ids,
        "affected_track_ids": affected_track_ids,
        "cache_reuse_expected": cache_reuse_expected,
        "requires_render_plan_recompile": requires_render_plan_recompile,
        "requires_audio_relayout": requires_audio_relayout,
        "reason": reason,
    }


def _stable_id(prefix: str, *parts: Any) -> str:
    raw = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}_{digest}"


def _normalized_preview_policy(source: Any) -> Dict[str, Any]:
    preview = dict(source or {}) if isinstance(source, dict) else {}
    profile = str(preview.get("profile") or "balanced")
    if profile not in {"auto", "performance", "balanced", "high", "original"}:
        profile = "balanced"
    resolved = _resolve_preview_quality_profile(profile)
    result = {
        "profile": profile,
        "mode": preview.get("mode") or resolved["mode"],
        "fps": int(preview.get("fps") or resolved["fps"]),
        "cache_namespace": preview.get("cache_namespace") or "preview",
    }
    height = preview.get("height", resolved.get("height"))
    if height is not None:
        result["height"] = int(height)
    return result


def _timeline_preview_cache_roots(project_dir: Optional[str]) -> Tuple[Optional[Path], Optional[Path]]:
    if not project_dir:
        return None, None
    project_path = Path(str(project_dir))
    doc_dir = project_path if project_path.name == ".video_create_project" else project_path / ".video_create_project"
    workspace_dir = doc_dir.parent if doc_dir.name == ".video_create_project" else project_path
    return workspace_dir / ".cache_video_create_v5", doc_dir / "render_cache"


def _timeline_asset_lookup(media_library: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    by_id: Dict[str, Dict[str, Any]] = {}
    by_path: Dict[str, Dict[str, Any]] = {}
    for asset in media_library.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("asset_id") or "")
        if asset_id:
            by_id[asset_id] = asset
        for path in (asset.get("absolute_path"), asset.get("path"), asset.get("source_path")):
            norm = _norm_path(path)
            if norm:
                by_path[norm] = asset
    return by_id, by_path


def _timeline_proxy_lookup(proxy_media_manifest: Any) -> Dict[str, Dict[str, Any]]:
    lookup: Dict[str, Dict[str, Any]] = {}
    if not isinstance(proxy_media_manifest, dict):
        return lookup

    entries: List[Any]
    if isinstance(proxy_media_manifest.get("assets"), list):
        entries = proxy_media_manifest.get("assets") or []
    else:
        entries = list(proxy_media_manifest.values())
        for key, value in proxy_media_manifest.items():
            if isinstance(value, dict):
                norm_key = _norm_path(key)
                if norm_key:
                    lookup[norm_key] = value

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source = _first_string(entry.get("source_path"), entry.get("absolute_path"), entry.get("path"))
        norm = _norm_path(source)
        if norm:
            lookup[norm] = entry
    return lookup


def _first_string(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return None


def _norm_path(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return ""
    try:
        return str(Path(value).resolve()).lower()
    except Exception:
        return value.replace("\\", "/").lower()


def _source_state(source_path: Optional[str]) -> str:
    if not source_path:
        return "generated"
    return "ready" if Path(source_path).exists() else "missing"


def _source_fingerprint(source_path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not source_path:
        return None
    path = Path(source_path)
    if not path.exists():
        return {
            "path": source_path,
            "exists": False,
            "fingerprint": _stable_id("missing_source", source_path),
        }
    stat = path.stat()
    fingerprint = _stable_id("source", str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    return {
        "path": str(path),
        "exists": True,
        "size_bytes": stat.st_size,
        "modified_ns": stat.st_mtime_ns,
        "fingerprint": fingerprint,
    }


def _is_visual_clip(kind: str) -> bool:
    return kind in {"video_asset", "image_asset", "title_card", "chapter_card", "subtitle_overlay"}


def _is_audio_clip(kind: str) -> bool:
    return kind in {"audio_bgm", "audio_source", "audio_effect"}


def _thumbnail_artifact(
    clip: Dict[str, Any],
    asset: Dict[str, Any],
    source_state: str,
    artifact_key: str,
    cache_root: Optional[Path],
    namespace: str,
) -> Dict[str, Any]:
    asset_thumb = _first_string(asset.get("thumbnail_path"), asset.get("thumbnail"))
    if asset_thumb:
        return _artifact(namespace, asset_thumb, status="ready" if Path(asset_thumb).exists() else "planned")
    path = cache_root / "timeline_thumbnails" / f"{artifact_key}.jpg" if cache_root else None
    status = _planned_status(path, source_state, generated_ok=_is_generated_visual_clip(str(clip.get("kind") or "")))
    return _artifact(namespace, str(path) if path else None, status=status)


def _proxy_artifact(
    source_path: Optional[str],
    source_state: str,
    artifact_key: str,
    cache_root: Optional[Path],
    namespace: str,
    preview_policy: Dict[str, Any],
    proxy_lookup: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    if preview_policy.get("mode") == "original":
        return _artifact(namespace, source_path, status="bypass_original", profile=preview_policy.get("profile"))

    manifest_path = _select_proxy_manifest_path(proxy_lookup.get(_norm_path(source_path)), preview_policy)
    if manifest_path:
        return _artifact(
            namespace,
            manifest_path,
            status="ready" if Path(manifest_path).exists() else "planned",
            profile=preview_policy.get("profile"),
            mode=preview_policy.get("mode"),
            height=preview_policy.get("height"),
            fps=preview_policy.get("fps"),
            source="proxy_media_manifest",
        )

    path = cache_root / "timeline_proxies" / f"{artifact_key}.mp4" if cache_root else None
    return _artifact(
        namespace,
        str(path) if path else None,
        status=_planned_status(path, source_state),
        profile=preview_policy.get("profile"),
        mode=preview_policy.get("mode"),
        height=preview_policy.get("height"),
        fps=preview_policy.get("fps"),
    )


def _select_proxy_manifest_path(entry: Optional[Dict[str, Any]], preview_policy: Dict[str, Any]) -> Optional[str]:
    if not isinstance(entry, dict):
        return None
    profiles = entry.get("profiles") if isinstance(entry.get("profiles"), dict) else {}
    preferred_names = [
        f"{preview_policy.get('mode')}_{preview_policy.get('height') or 'original'}p",
        str(preview_policy.get("profile") or ""),
        "scan_proxy_v1",
        "default",
    ]
    for name in preferred_names:
        profile = profiles.get(name)
        if isinstance(profile, dict) and isinstance(profile.get("path"), str):
            return profile["path"]
    for profile in profiles.values():
        if isinstance(profile, dict) and isinstance(profile.get("path"), str):
            return profile["path"]
    if isinstance(entry.get("path"), str):
        return entry["path"]
    return None


def _waveform_artifact(
    source_state: str,
    artifact_key: str,
    cache_root: Optional[Path],
    namespace: str,
) -> Dict[str, Any]:
    path = cache_root / "timeline_waveforms" / f"{artifact_key}.json" if cache_root else None
    return _artifact(namespace, str(path) if path else None, status=_planned_status(path, source_state))


def _preview_segment_artifact(
    source_state: str,
    artifact_key: str,
    render_cache_root: Optional[Path],
    namespace: str,
    preview_policy: Dict[str, Any],
) -> Dict[str, Any]:
    path = render_cache_root / "preview_segments" / f"{artifact_key}.mp4" if render_cache_root else None
    return _artifact(
        namespace,
        str(path) if path else None,
        status=_planned_status(path, source_state, generated_ok=True),
        cache_key=artifact_key,
        profile=preview_policy.get("profile"),
        mode=preview_policy.get("mode"),
        height=preview_policy.get("height"),
        fps=preview_policy.get("fps"),
    )


def _planned_status(path: Optional[Path], source_state: str, *, generated_ok: bool = False) -> str:
    if path and path.exists():
        return "ready"
    if source_state == "missing":
        return "missing_source"
    if source_state == "generated" and not generated_ok:
        return "not_applicable"
    return "planned"


def _is_generated_visual_clip(kind: str) -> bool:
    return kind in {"title_card", "chapter_card", "subtitle_overlay"}


def _artifact(namespace: str, path: Optional[str], *, status: str, **extra: Any) -> Dict[str, Any]:
    result = {
        "cache_namespace": namespace,
        "path": path,
        "status": status,
    }
    result.update({key: value for key, value in extra.items() if value is not None})
    return result


def _not_applicable_artifact(namespace: str) -> Dict[str, Any]:
    return _artifact(namespace, None, status="not_applicable")


def _count_artifact(summary: Dict[str, Any], prefix: str, artifact: Dict[str, Any]) -> None:
    status = artifact.get("status")
    if status == "ready":
        summary[f"{prefix}_ready"] += 1
    elif status == "planned":
        summary[f"{prefix}_planned"] += 1
    elif status == "failed":
        summary[f"{prefix}_failed"] += 1


def _timeline_preview_manifest_summary(clips: Dict[str, Any]) -> Dict[str, int]:
    summary = {
        "total_clips": 0,
        "visual_clips": 0,
        "audio_clips": 0,
        "thumbnail_ready": 0,
        "thumbnail_planned": 0,
        "thumbnail_failed": 0,
        "proxy_ready": 0,
        "proxy_planned": 0,
        "proxy_failed": 0,
        "waveform_ready": 0,
        "waveform_planned": 0,
        "waveform_failed": 0,
        "preview_segment_ready": 0,
        "preview_segment_planned": 0,
        "preview_segment_failed": 0,
        "missing_sources": 0,
    }
    for clip in clips.values():
        if not isinstance(clip, dict):
            continue
        kind = str(clip.get("kind") or "")
        summary["total_clips"] += 1
        if _is_visual_clip(kind):
            summary["visual_clips"] += 1
        if _is_audio_clip(kind):
            summary["audio_clips"] += 1
        source_ref = clip.get("source_ref") if isinstance(clip.get("source_ref"), dict) else {}
        if source_ref.get("source_state") == "missing":
            summary["missing_sources"] += 1
        for prefix in ("thumbnail", "proxy", "waveform", "preview_segment"):
            artifact = clip.get(prefix) if isinstance(clip.get(prefix), dict) else {}
            _count_artifact(summary, prefix, artifact)
    return summary


def _count_preview_asset_tasks(clips: Dict[str, Any]) -> int:
    total = 0
    for clip in clips.values():
        if not isinstance(clip, dict):
            continue
        for key in ("thumbnail", "proxy", "waveform", "preview_segment"):
            artifact = clip.get(key) if isinstance(clip.get(key), dict) else {}
            status = artifact.get("status")
            if status in {"not_applicable", "bypass_original", "missing_source"}:
                continue
            total += 1
    return total


def _advance_preview_asset_progress(
    clip: Dict[str, Any],
    artifact_kind: str,
    completed: int,
    total: int,
    artifact: Dict[str, Any],
    *,
    emit_event_fn=None,
    batch_size: int = 8,
) -> int:
    status = artifact.get("status") if isinstance(artifact, dict) else None
    if status in {"not_applicable", "bypass_original", "missing_source"}:
        return completed
    next_completed = completed + 1
    if emit_event_fn and (next_completed == total or next_completed % max(1, batch_size) == 0 or status == "failed"):
        clip_id = str(clip.get("clip_id") or "")
        message = f"Preview asset {next_completed}/{max(1, total)}: {artifact_kind} {clip_id} {status or 'done'}"
        _emit_preview_asset_progress(
            emit_event_fn,
            clip_id,
            next_completed,
            total,
            str(status or "done"),
            message,
            artifact_kind=artifact_kind,
        )
    return next_completed


def _emit_preview_asset_progress(
    emit_event_fn,
    clip_id: Optional[str],
    current: int,
    total: int,
    status: str,
    message: Optional[str],
    *,
    artifact_kind: Optional[str] = None,
) -> None:
    if not emit_event_fn:
        return
    safe_total = max(1, int(total or 0))
    safe_current = max(0, min(int(current or 0), safe_total))
    emit_event_fn(
        "timeline_preview_assets",
        phase="preview_assets",
        current=safe_current,
        total=safe_total,
        percent=round((safe_current / safe_total) * 100, 2),
        status=status,
        clip_id=clip_id,
        artifact_kind=artifact_kind,
        message=message or "Preparing timeline preview assets",
    )


def _generate_thumbnail_asset(
    clip: Dict[str, Any],
    artifact: Dict[str, Any],
    source_path: Optional[str],
    stats: Dict[str, int],
) -> Dict[str, Any]:
    result = dict(artifact or {})
    if result.get("status") == "not_applicable":
        stats["skipped"] += 1
        return result
    path = _artifact_path(result)
    if path and path.is_file():
        stats["hit"] += 1
        return {**result, "status": "ready", "path": str(path)}
    if not path:
        stats["skipped"] += 1
        return result

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        kind = str(clip.get("kind") or "")
        if source_path and Path(source_path).is_file() and kind == "image_asset":
            _write_image_thumbnail(Path(source_path), path)
        elif source_path and Path(source_path).is_file() and kind == "video_asset":
            _write_video_thumbnail(Path(source_path), path, int(result.get("height") or 270))
        elif _is_generated_visual_clip(kind):
            _write_generated_clip_thumbnail(clip, path)
        else:
            raise RuntimeError("thumbnail source is unavailable")
        stats["created"] += 1
        return {**result, "status": "ready", "path": str(path), "generated_at": datetime.now().isoformat()}
    except Exception as exc:
        stats["failed"] += 1
        return {**result, "status": "failed", "error": str(exc)}


def _generate_proxy_asset(
    artifact: Dict[str, Any],
    source_path: Optional[str],
    stats: Dict[str, int],
) -> Dict[str, Any]:
    result = dict(artifact or {})
    if result.get("status") in {"not_applicable", "bypass_original"}:
        stats["skipped"] += 1
        return result
    path = _artifact_path(result)
    if path and path.is_file():
        stats["hit"] += 1
        return {**result, "status": "ready", "path": str(path)}
    if not path or not source_path or not Path(source_path).is_file():
        stats["skipped"] += 1
        return result

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        height = int(result.get("height") or 720)
        fps = int(result.get("fps") or 24)
        _write_video_proxy(Path(source_path), path, height, fps)
        stats["created"] += 1
        return {**result, "status": "ready", "path": str(path), "generated_at": datetime.now().isoformat()}
    except Exception as exc:
        stats["failed"] += 1
        return {**result, "status": "failed", "error": str(exc)}


def _generate_waveform_asset(
    artifact: Dict[str, Any],
    source_path: Optional[str],
    stats: Dict[str, int],
) -> Dict[str, Any]:
    result = dict(artifact or {})
    if result.get("status") == "not_applicable":
        stats["skipped"] += 1
        return result
    path = _artifact_path(result)
    if path and path.is_file():
        stats["hit"] += 1
        return {**result, "status": "ready", "path": str(path)}
    if not path or not source_path or not Path(source_path).is_file():
        stats["skipped"] += 1
        return result

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_waveform_json(Path(source_path), path)
        stats["created"] += 1
        return {**result, "status": "ready", "path": str(path), "generated_at": datetime.now().isoformat()}
    except Exception as exc:
        stats["failed"] += 1
        return {**result, "status": "failed", "error": str(exc)}


def _generate_preview_segment_asset(
    clip: Dict[str, Any],
    artifact: Dict[str, Any],
    source_path: Optional[str],
    stats: Dict[str, int],
) -> Dict[str, Any]:
    result = dict(artifact or {})
    if result.get("status") == "not_applicable":
        stats["skipped"] += 1
        return result
    path = _artifact_path(result)
    if path and path.is_file():
        stats["hit"] += 1
        return {**result, "status": "ready", "path": str(path)}
    if not path:
        stats["skipped"] += 1
        return result

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        height = int(result.get("height") or 540)
        fps = int(result.get("fps") or 15)
        duration = max(0.25, min(_float(clip.get("timeline_duration"), 1.0), 6.0))
        kind = str(clip.get("kind") or "")
        proxy = clip.get("proxy") if isinstance(clip.get("proxy"), dict) else {}
        proxy_path = _artifact_path(proxy)
        if kind == "video_asset" and proxy_path and proxy_path.is_file():
            _write_video_preview_segment(proxy_path, path, duration, height, fps)
        elif kind == "video_asset" and source_path and Path(source_path).is_file():
            _write_video_preview_segment(Path(source_path), path, duration, height, fps)
        else:
            thumbnail = clip.get("thumbnail") if isinstance(clip.get("thumbnail"), dict) else {}
            thumbnail_path = _artifact_path(thumbnail)
            if thumbnail_path and thumbnail_path.is_file():
                _write_image_preview_segment(thumbnail_path, path, duration, height, fps)
            else:
                raise RuntimeError("preview segment thumbnail/source is unavailable")
        stats["created"] += 1
        return {**result, "status": "ready", "path": str(path), "generated_at": datetime.now().isoformat()}
    except Exception as exc:
        stats["failed"] += 1
        return {**result, "status": "failed", "error": str(exc)}


def _artifact_path(artifact: Dict[str, Any]) -> Optional[Path]:
    value = artifact.get("path") if isinstance(artifact, dict) else None
    if not isinstance(value, str) or not value:
        return None
    return Path(value)


def _write_image_thumbnail(source: Path, output: Path, width: int = 480, height: int = 270) -> None:
    from PIL import Image, ImageOps

    with Image.open(source) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((width, height), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (width, height), (22, 32, 28))
        x = (width - img.width) // 2
        y = (height - img.height) // 2
        canvas.paste(img, (x, y))
        canvas.save(output, quality=84)


def _write_video_thumbnail(source: Path, output: Path, height: int = 270) -> None:
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-ss",
        "0",
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-vf",
        f"scale=-2:{max(120, min(height, 540))}",
        str(output),
    ]
    _run_ffmpeg(cmd)


def _write_generated_clip_thumbnail(clip: Dict[str, Any], output: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    width, height = 480, 270
    image = Image.new("RGB", (width, height), (18, 38, 32))
    draw = ImageDraw.Draw(image)
    title = _first_string(
        ((clip.get("content_ref") or {}) if isinstance(clip.get("content_ref"), dict) else {}).get("title_text"),
        str(clip.get("kind") or "Title"),
    ) or "Title"
    subtitle = _first_string(
        ((clip.get("content_ref") or {}) if isinstance(clip.get("content_ref"), dict) else {}).get("subtitle_text")
    )
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 30)
        small = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 18)
    except Exception:
        font = ImageFont.load_default()
        small = ImageFont.load_default()
    draw.rectangle((0, height - 84, width, height), fill=(8, 24, 18))
    draw.text((28, height - 70), title[:32], fill=(236, 253, 245), font=font)
    if subtitle:
        draw.text((30, height - 34), subtitle[:48], fill=(167, 243, 208), font=small)
    image.save(output, quality=84)


def _write_video_proxy(source: Path, output: Path, height: int, fps: int) -> None:
    height = max(240, min(int(height or 720), 1080))
    fps = max(8, min(int(fps or 24), 30))
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(source),
        "-vf",
        f"scale=-2:{height},fps={fps}",
        "-map",
        "0:v:0",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "28",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "96k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    _run_ffmpeg(cmd)


def _write_video_preview_segment(source: Path, output: Path, duration: float, height: int, fps: int) -> None:
    height = max(240, min(int(height or 540), 1080))
    fps = max(8, min(int(fps or 15), 30))
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-vf",
        f"scale=-2:{height},fps={fps}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    _run_ffmpeg(cmd)


def _write_image_preview_segment(source: Path, output: Path, duration: float, height: int, fps: int) -> None:
    height = max(240, min(int(height or 540), 1080))
    fps = max(8, min(int(fps or 15), 30))
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-loop",
        "1",
        "-i",
        str(source),
        "-t",
        f"{duration:.3f}",
        "-vf",
        f"scale=-2:{height},fps={fps}",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    _run_ffmpeg(cmd)


def _write_waveform_json(source: Path, output: Path, bucket_count: int = 512) -> None:
    sample_rate = 4000
    sample_width = 2
    channels = 1
    pcm = _decode_audio_pcm_mono(source, sample_rate=sample_rate)
    if not pcm:
        raise RuntimeError("waveform decode produced no PCM samples")

    bytes_per_frame = sample_width
    total_frames = len(pcm) // bytes_per_frame
    bucket_frames = max(1, math.ceil(total_frames / max(1, bucket_count)))
    peaks: List[float] = []
    max_peak = float((1 << (8 * sample_width - 1)) - 1)
    for start_frame in range(0, total_frames, bucket_frames):
        start = start_frame * bytes_per_frame
        end = min(len(pcm), (start_frame + bucket_frames) * bytes_per_frame)
        chunk = pcm[start:end]
        if not chunk:
            continue
        peak = audioop.max(chunk, sample_width)
        peaks.append(round(min(1.0, peak / max_peak), 4) if max_peak > 0 else 0.0)
        if len(peaks) >= bucket_count:
            break
    output.write_text(
        json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "document_type": "timeline_waveform_peaks",
                "source_path": str(source),
                "duration_seconds": round(total_frames / sample_rate, 4) if sample_rate else 0,
                "sample_rate": sample_rate,
                "channels": channels,
                "bucket_count": len(peaks),
                "peaks": peaks,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _decode_audio_pcm_mono(source: Path, *, sample_rate: int) -> bytes:
    cmd = [
        _ffmpeg_exe(),
        "-hide_banner",
        "-nostdin",
        "-i",
        str(source),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.decode("utf-8", errors="replace") if isinstance(completed.stderr, bytes) else str(completed.stderr)
        raise RuntimeError((stderr or "ffmpeg audio decode failed")[-900:])
    return completed.stdout or b""


def _ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def _run_ffmpeg(cmd: List[str]) -> None:
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "ffmpeg failed")[-900:])


def _float(value: Any, fallback: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(fallback)
