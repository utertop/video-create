from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Union


LEGACY_MOVIEPY_BACKEND_NAME = "legacy_moviepy_backend"
FFMPEG_STABLE_BACKEND_NAME = "ffmpeg_stable_backend"
MLT_BACKEND_NAME = "mlt_backend"

STANDARD_TIMELINE_BACKEND_FAMILY = "standard_timeline"
LONG_VIDEO_STABLE_BACKEND_FAMILY = "long_video_stable"
MLT_BACKEND_FAMILY = "standard_timeline_gpu_candidate"

BACKEND_MODE_PREVIEW = "preview"
BACKEND_MODE_FINAL_RENDER = "final_render"

BACKEND_REASON_PREVIEW_STANDARD_RENDERER = "preview_render_uses_standard_renderer"
BACKEND_REASON_STABLE_RENDERER_SELECTED = "stable_renderer_selected"
BACKEND_REASON_STANDARD_RENDERER_SELECTED = "standard_renderer_selected"

MLT_BACKEND_REASON_SELECTED = "mlt_backend_selected"
MLT_BACKEND_REASON_GATE_DISABLED = "mlt_experimental_gate_disabled"
MLT_BACKEND_REASON_NOT_INSTALLED = "mlt_not_installed"
MLT_BACKEND_REASON_MISSING_SOURCE_PATH = "mlt_missing_source_path"
MLT_BACKEND_REASON_PREVIEW_NOT_SUPPORTED = "mlt_preview_render_not_supported"
MLT_BACKEND_REASON_UNSUPPORTED_SEGMENT_TYPE = "mlt_unsupported_segment_type"
MLT_BACKEND_REASON_UNSUPPORTED_TEXT_OVERLAY = "mlt_unsupported_text_overlay"
MLT_BACKEND_REASON_UNSUPPORTED_TRANSITION = "mlt_unsupported_transition"
MLT_BACKEND_REASON_RENDER_FAILED = "mlt_render_failed"
MLT_BACKEND_REASON_VALIDATION_FAILED = "mlt_validation_failed"
MLT_BACKEND_REASON_SCAFFOLD_ONLY = "mlt_backend_scaffold_only"

CAPABILITY_FLAG_PREVIEW = "preview"
CAPABILITY_FLAG_TIMELINE = "timeline"
CAPABILITY_FLAG_MOVIEPY = "moviepy"
CAPABILITY_FLAG_STABLE = "stable"
CAPABILITY_FLAG_CHUNKED = "chunked"
CAPABILITY_FLAG_FFMPEG = "ffmpeg"
CAPABILITY_FLAG_FALLBACK_MOVIEPY = "fallback_moviepy"
CAPABILITY_FLAG_MLT = "mlt"
CAPABILITY_FLAG_XML_PROJECT = "xml_project"
CAPABILITY_FLAG_FFMPEG_CONSUMER = "ffmpeg_consumer"

MLT_BACKEND_CAPABILITY_FLAGS = (
    CAPABILITY_FLAG_MLT,
    CAPABILITY_FLAG_TIMELINE,
    CAPABILITY_FLAG_XML_PROJECT,
    CAPABILITY_FLAG_FFMPEG_CONSUMER,
    CAPABILITY_FLAG_FALLBACK_MOVIEPY,
)


@dataclass(frozen=True)
class BackendDecision:
    backend_name: str
    backend_family: str
    backend_mode: str
    reason: str
    fallback_chain: list[str] = field(default_factory=list)
    capability_flags: list[str] = field(default_factory=list)
    actual_backend_name: Optional[str] = None
    fallback_used: Optional[str] = None
    fallback_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "backend_name": self.backend_name,
            "backend_family": self.backend_family,
            "backend_mode": self.backend_mode,
            "reason": self.reason,
            "fallback_chain": list(self.fallback_chain),
            "capability_flags": list(self.capability_flags),
            "actual_backend_name": self.actual_backend_name,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True)
class BackendExecutionResult:
    decision: BackendDecision
    actual_backend_name: str
    fallback_used: Optional[str] = None
    fallback_reason: Optional[str] = None
    fallback_applied: bool = False

    @property
    def selected_backend_name(self) -> str:
        return self.decision.backend_name

    @classmethod
    def from_decision(
        cls,
        decision: Union[BackendDecision, Dict[str, Any]],
        *,
        actual_backend_name: Optional[str] = None,
        fallback_used: Optional[str] = None,
        fallback_reason: Optional[str] = None,
    ) -> "BackendExecutionResult":
        resolved = coerce_backend_decision(decision)
        return cls(
            decision=resolved,
            actual_backend_name=str(actual_backend_name or resolved.backend_name),
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            fallback_applied=bool(fallback_used),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "selected_backend": self.selected_backend_name,
            "actual_backend_name": self.actual_backend_name,
            "fallback_used": self.fallback_used,
            "fallback_reason": self.fallback_reason,
            "fallback_applied": self.fallback_applied,
        }


def merge_backend_reason_tags(*groups: Optional[Union[str, Iterable[str]]]) -> str:
    tags: list[str] = []
    for group in groups:
        if group is None:
            continue
        if isinstance(group, str):
            candidates = [group]
        else:
            candidates = [str(item) for item in group]
        for candidate in candidates:
            normalized = str(candidate or "").strip()
            if not normalized or normalized in tags:
                continue
            tags.append(normalized)
    return "+".join(tags)


def coerce_backend_decision(value: Optional[Union["BackendDecision", Dict[str, Any]]]) -> BackendDecision:
    if isinstance(value, BackendDecision):
        return value

    payload = dict(value or {})
    return BackendDecision(
        backend_name=str(payload.get("backend_name") or ""),
        backend_family=str(payload.get("backend_family") or ""),
        backend_mode=str(payload.get("backend_mode") or ""),
        reason=str(payload.get("reason") or ""),
        fallback_chain=list(payload.get("fallback_chain") or []),
        capability_flags=list(payload.get("capability_flags") or []),
        actual_backend_name=payload.get("actual_backend_name"),
        fallback_used=payload.get("fallback_used"),
        fallback_reason=payload.get("fallback_reason"),
    )


def coerce_backend_execution_result(
    value: Optional[Union["BackendExecutionResult", BackendDecision, Dict[str, Any]]],
) -> BackendExecutionResult:
    if isinstance(value, BackendExecutionResult):
        return value
    if isinstance(value, BackendDecision):
        return BackendExecutionResult.from_decision(value)

    payload = dict(value or {})
    if "decision" in payload:
        decision = coerce_backend_decision(payload.get("decision"))
        actual_backend_name = str(payload.get("actual_backend_name") or decision.backend_name)
        fallback_used = payload.get("fallback_used")
        fallback_reason = payload.get("fallback_reason")
        fallback_applied = bool(payload.get("fallback_applied"))
        if fallback_used:
            fallback_applied = True
        return BackendExecutionResult(
            decision=decision,
            actual_backend_name=actual_backend_name,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            fallback_applied=fallback_applied,
        )

    return BackendExecutionResult.from_decision(coerce_backend_decision(payload))


def build_backend_report_payload(
    decision: Optional[Union[BackendExecutionResult, BackendDecision, Dict[str, Any]]],
    fallback_used: Optional[str] = None,
    fallback_reason: Optional[str] = None,
) -> Dict[str, Any]:
    resolved = coerce_backend_execution_result(decision)
    return {
        "selected_backend": resolved.selected_backend_name,
        "backend_family": resolved.decision.backend_family,
        "backend_mode": resolved.decision.backend_mode,
        "reason": resolved.decision.reason,
        "fallback_chain": list(resolved.decision.fallback_chain),
        "capability_flags": list(resolved.decision.capability_flags),
        "actual_backend_name": resolved.actual_backend_name,
        "fallback_used": fallback_used if fallback_used is not None else resolved.fallback_used,
        "fallback_reason": fallback_reason if fallback_reason is not None else resolved.fallback_reason,
        "fallback_applied": bool(
            fallback_used if fallback_used is not None else resolved.fallback_used
        ) or resolved.fallback_applied,
    }
