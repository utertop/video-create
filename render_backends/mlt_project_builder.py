from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from xml.etree.ElementTree import Element, ElementTree, SubElement

from .base import (
    MLT_BACKEND_REASON_MISSING_SOURCE_PATH,
    MLT_BACKEND_REASON_UNSUPPORTED_SEGMENT_TYPE,
    MLT_BACKEND_REASON_UNSUPPORTED_TEXT_OVERLAY,
    MLT_BACKEND_REASON_UNSUPPORTED_TRANSITION,
)

_ALLOWED_SEGMENT_TYPES = {"image", "video"}
_ALLOWED_TRANSITIONS = {"none", "cut", "crossfade", "soft_crossfade"}
_ALLOWED_OVERLAY_MOTIONS = {
    "fade_slide_up",
    "editorial_fade",
    "static_hold",
    "lower_third_slide",
    "cinematic_reveal",
    "postcard_drift",
}
_ALLOWED_OVERLAY_POSITIONS = {"lower_left", "lower_center", "center"}


@dataclass(frozen=True)
class MltProjectBuildResult:
    supported: bool
    project_path: str
    asset_manifest_path: str
    rejection_reasons: list[str] = field(default_factory=list)
    route_counts: Dict[str, int] = field(default_factory=dict)
    producers: list[Dict[str, Any]] = field(default_factory=list)
    overlays: list[Dict[str, Any]] = field(default_factory=list)
    transitions: list[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "supported": self.supported,
            "project_path": self.project_path,
            "asset_manifest_path": self.asset_manifest_path,
            "rejection_reasons": list(self.rejection_reasons),
            "route_counts": dict(self.route_counts),
            "producers": list(self.producers),
            "overlays": list(self.overlays),
            "transitions": list(self.transitions),
        }


def _parse_aspect_ratio(value: str) -> tuple[int, int]:
    normalized = str(value or "16:9").strip()
    if ":" in normalized:
        left, right = normalized.split(":", 1)
        try:
            width_ratio = int(left)
            height_ratio = int(right)
            if width_ratio > 0 and height_ratio > 0:
                return width_ratio, height_ratio
        except Exception:
            pass
    return 16, 9


def _profile_dimensions(plan: Dict[str, Any]) -> tuple[int, int]:
    settings = dict(plan.get("render_settings") or {})
    ratio_w, ratio_h = _parse_aspect_ratio(settings.get("aspect_ratio") or "16:9")
    base_height = int(settings.get("height") or 1080)
    base_width = int(round(base_height * ratio_w / max(ratio_h, 1)))
    return base_width, base_height


def _segment_duration_frames(segment: Dict[str, Any], fps: float) -> int:
    duration_seconds = max(float(segment.get("duration") or 0.0), 0.04)
    return max(1, int(round(duration_seconds * fps)))


def _append_property(node: Element, name: str, value: Any) -> None:
    child = SubElement(node, "property", {"name": name})
    child.text = str(value)


def _normalize_transition_type(segment: Dict[str, Any]) -> str:
    transition_config = segment.get("transition_config") or {}
    transition_type = transition_config.get("type") if isinstance(transition_config, dict) else None
    return str(transition_type or segment.get("transition") or "none").strip().lower()


def _is_supported_overlay(segment: Dict[str, Any]) -> bool:
    text = segment.get("overlay_text")
    if not text:
        return True
    subtitle = segment.get("overlay_subtitle")
    overlay_duration = float(segment.get("overlay_duration") or 1.8)
    style = dict(segment.get("overlay_title_style") or {})
    motion = str(style.get("motion") or "fade_slide_up")
    position = str(style.get("position") or "lower_left")
    if motion not in _ALLOWED_OVERLAY_MOTIONS:
        return False
    if position not in _ALLOWED_OVERLAY_POSITIONS:
        return False
    if len(str(text)) > 42 or len(str(subtitle or "")) > 64:
        return False
    return overlay_duration <= 3.2


def _build_working_paths(output_path: str, working_dir: Optional[str]) -> tuple[Path, Path, Path]:
    output = Path(output_path).resolve()
    mlt_root = Path(working_dir).resolve() if working_dir else output.parent.joinpath(".video_create_project", "mlt")
    project_path = mlt_root / "project.mlt"
    asset_manifest_path = mlt_root / "assets_manifest.json"
    return mlt_root, project_path, asset_manifest_path


def map_transition_to_mlt_mix(segment: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    transition_type = _normalize_transition_type(segment)
    if transition_type in {"none", "cut"}:
        return None
    duration = float((segment.get("transition_config") or {}).get("duration") or 0.0)
    return {
        "segment_id": segment.get("segment_id") or f"seg_{index:05d}",
        "type": "mix",
        "style": "crossfade" if transition_type in {"crossfade", "soft_crossfade"} else transition_type,
        "duration": round(duration, 3),
    }


def map_text_overlay_to_mlt_filter(segment: Dict[str, Any], index: int) -> Optional[Dict[str, Any]]:
    if not segment.get("overlay_text"):
        return None
    style = dict(segment.get("overlay_title_style") or {})
    return {
        "segment_id": segment.get("segment_id") or f"seg_{index:05d}",
        "service": "dynamictext",
        "text": str(segment.get("overlay_text") or ""),
        "subtitle": str(segment.get("overlay_subtitle") or ""),
        "duration": round(float(segment.get("overlay_duration") or 1.8), 3),
        "style": style,
    }


def map_segment_to_mlt_entry(segment: Dict[str, Any], index: int, fps: float) -> Dict[str, Any]:
    segment_type = str(segment.get("type") or "").strip().lower()
    frames = _segment_duration_frames(segment, fps)
    producer_id = f"producer_{index:05d}"
    entry_id = f"entry_{index:05d}"
    return {
        "segment_id": segment.get("segment_id") or entry_id,
        "producer_id": producer_id,
        "entry_id": entry_id,
        "type": segment_type,
        "resource": str(segment.get("source_path") or ""),
        "frames": frames,
        "in_frame": 0,
        "out_frame": max(frames - 1, 0),
        "duration_seconds": round(float(segment.get("duration") or 0.0), 3),
    }


def build_mlt_project(
    plan: Dict[str, Any],
    params: Dict[str, Any],
    output_path: str,
    working_dir: Optional[str] = None,
) -> MltProjectBuildResult:
    _ = params
    settings = dict(plan.get("render_settings") or {})
    fps = max(float(settings.get("fps") or 25), 1.0)
    width, height = _profile_dimensions(plan)
    mlt_root, project_path, asset_manifest_path = _build_working_paths(output_path, working_dir)

    rejection_reasons: list[str] = []
    route_counts = {"segments": 0, "image_segments": 0, "video_segments": 0, "crossfade_transitions": 0, "text_overlays": 0}
    producers: list[Dict[str, Any]] = []
    overlays: list[Dict[str, Any]] = []
    transitions: list[Dict[str, Any]] = []

    for index, segment in enumerate(list(plan.get("segments") or [])):
        segment_type = str(segment.get("type") or "").strip().lower()
        if segment_type not in _ALLOWED_SEGMENT_TYPES:
            rejection_reasons.append(MLT_BACKEND_REASON_UNSUPPORTED_SEGMENT_TYPE)
            continue
        if not str(segment.get("source_path") or "").strip():
            rejection_reasons.append(MLT_BACKEND_REASON_MISSING_SOURCE_PATH)
            continue
        transition_type = _normalize_transition_type(segment)
        if transition_type not in _ALLOWED_TRANSITIONS:
            rejection_reasons.append(MLT_BACKEND_REASON_UNSUPPORTED_TRANSITION)
            continue
        if not _is_supported_overlay(segment):
            rejection_reasons.append(MLT_BACKEND_REASON_UNSUPPORTED_TEXT_OVERLAY)
            continue

        producer = map_segment_to_mlt_entry(segment, index, fps)
        producers.append(producer)
        route_counts["segments"] += 1
        route_counts[f"{segment_type}_segments"] += 1

        transition = map_transition_to_mlt_mix(segment, index)
        if transition:
            transitions.append(transition)
            route_counts["crossfade_transitions"] += 1

        overlay = map_text_overlay_to_mlt_filter(segment, index)
        if overlay:
            overlays.append(overlay)
            route_counts["text_overlays"] += 1

    # Normalize rejection reasons without hiding distinct categories.
    seen: list[str] = []
    for reason in rejection_reasons:
        if reason not in seen:
            seen.append(reason)
    rejection_reasons = seen

    supported = len(rejection_reasons) == 0 and len(producers) > 0
    if not producers and not rejection_reasons:
        rejection_reasons.append(MLT_BACKEND_REASON_UNSUPPORTED_SEGMENT_TYPE)
        supported = False

    mlt_root.mkdir(parents=True, exist_ok=True)

    project = Element("mlt", {"LC_NUMERIC": "C", "version": "7.22.0", "title": "Video Create Studio MLT Project"})
    profile = SubElement(
        project,
        "profile",
        {
            "description": "Video Create Studio MLT",
            "width": str(width),
            "height": str(height),
            "progressive": "1",
            "sample_aspect_num": "1",
            "sample_aspect_den": "1",
            "display_aspect_num": str(_parse_aspect_ratio(settings.get("aspect_ratio") or "16:9")[0]),
            "display_aspect_den": str(_parse_aspect_ratio(settings.get("aspect_ratio") or "16:9")[1]),
            "frame_rate_num": str(int(round(fps))),
            "frame_rate_den": "1",
            "colorspace": "709",
        },
    )
    _ = profile

    for producer in producers:
        producer_node = SubElement(project, "producer", {"id": producer["producer_id"]})
        if producer["type"] == "image":
            _append_property(producer_node, "mlt_service", "qimage")
            _append_property(producer_node, "resource", producer["resource"])
            _append_property(producer_node, "ttl", producer["frames"])
        else:
            _append_property(producer_node, "mlt_service", "avformat-novalidate")
            _append_property(producer_node, "resource", producer["resource"])
        _append_property(producer_node, "length", producer["out_frame"])
        _append_property(producer_node, "out", producer["out_frame"])
        _append_property(producer_node, "kdenlive:id", producer["segment_id"])

    playlist = SubElement(project, "playlist", {"id": "playlist_main"})
    for producer in producers:
        entry = SubElement(
            playlist,
            "entry",
            {
                "producer": producer["producer_id"],
                "in": str(producer["in_frame"]),
                "out": str(producer["out_frame"]),
            },
        )
        _append_property(entry, "vcs.segment_id", producer["segment_id"])
        _append_property(entry, "vcs.duration_seconds", producer["duration_seconds"])

    tractor = SubElement(project, "tractor", {"id": "tractor_main"})
    multitrack = SubElement(tractor, "multitrack", {"id": "multitrack_main"})
    SubElement(multitrack, "track", {"producer": "playlist_main"})

    for index, transition in enumerate(transitions):
        transition_node = SubElement(tractor, "transition", {"id": f"transition_{index:05d}"})
        _append_property(transition_node, "mlt_service", transition["type"])
        _append_property(transition_node, "a_track", 0)
        _append_property(transition_node, "b_track", 0)
        _append_property(transition_node, "vcs.segment_id", transition["segment_id"])
        _append_property(transition_node, "vcs.transition.style", transition["style"])
        _append_property(transition_node, "vcs.transition.duration", transition["duration"])

    for index, overlay in enumerate(overlays):
        filter_node = SubElement(tractor, "filter", {"id": f"filter_{index:05d}"})
        _append_property(filter_node, "mlt_service", overlay["service"])
        _append_property(filter_node, "argument", overlay["text"])
        _append_property(filter_node, "geometry", "10%/80%:80%x18%")
        _append_property(filter_node, "family", "Noto Sans CJK SC")
        _append_property(filter_node, "size", 48)
        _append_property(filter_node, "halign", "left")
        _append_property(filter_node, "valign", "middle")
        _append_property(filter_node, "outline", 2)
        _append_property(filter_node, "fgcolour", "#FFFFFFFF")
        _append_property(filter_node, "bgcolour", "#00000000")
        _append_property(filter_node, "vcs.segment_id", overlay["segment_id"])
        if overlay["subtitle"]:
            _append_property(filter_node, "vcs.subtitle", overlay["subtitle"])
        _append_property(filter_node, "vcs.overlay_duration", overlay["duration"])
        _append_property(filter_node, "vcs.overlay_style", json.dumps(overlay["style"], ensure_ascii=False, sort_keys=True))

    ElementTree(project).write(project_path, encoding="utf-8", xml_declaration=True)

    asset_manifest = {
        "builder_version": "mlt_project_builder_v1",
        "supported": supported,
        "rejection_reasons": rejection_reasons,
        "route_counts": route_counts,
        "project_path": str(project_path),
        "assets": producers,
        "transitions": transitions,
        "overlays": overlays,
    }
    asset_manifest_path.write_text(
        json.dumps(asset_manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return MltProjectBuildResult(
        supported=supported,
        project_path=str(project_path),
        asset_manifest_path=str(asset_manifest_path),
        rejection_reasons=rejection_reasons,
        route_counts=route_counts,
        producers=producers,
        overlays=overlays,
        transitions=transitions,
    )
