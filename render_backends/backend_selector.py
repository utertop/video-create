from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, Optional

from .base import (
    BACKEND_MODE_FINAL_RENDER,
    BACKEND_MODE_PREVIEW,
    BACKEND_REASON_PREVIEW_STANDARD_RENDERER,
    BACKEND_REASON_STABLE_RENDERER_SELECTED,
    BACKEND_REASON_STANDARD_RENDERER_SELECTED,
    CAPABILITY_FLAG_CHUNKED,
    CAPABILITY_FLAG_FALLBACK_MOVIEPY,
    CAPABILITY_FLAG_FFMPEG,
    MLT_BACKEND_CAPABILITY_FLAGS,
    CAPABILITY_FLAG_MOVIEPY,
    CAPABILITY_FLAG_PREVIEW,
    CAPABILITY_FLAG_STABLE,
    CAPABILITY_FLAG_TIMELINE,
    FFMPEG_STABLE_BACKEND_NAME,
    LEGACY_MOVIEPY_BACKEND_NAME,
    LONG_VIDEO_STABLE_BACKEND_FAMILY,
    MLT_BACKEND_FAMILY,
    MLT_BACKEND_NAME,
    MLT_BACKEND_REASON_GATE_DISABLED,
    MLT_BACKEND_REASON_NOT_INSTALLED,
    MLT_BACKEND_REASON_PREVIEW_NOT_SUPPORTED,
    MLT_BACKEND_REASON_SELECTED,
    MLT_BACKEND_REASON_UNSUPPORTED_SEGMENT_TYPE,
    MLT_BACKEND_REASON_UNSUPPORTED_TRANSITION,
    STANDARD_TIMELINE_BACKEND_FAMILY,
    BackendDecision,
    merge_backend_reason_tags,
)
from .mlt_probe import MltProbeResult, probe_mlt_runtime

_MLT_ALLOWED_SEGMENT_TYPES = {"image", "video"}
_MLT_ALLOWED_TRANSITIONS = {"cut", "crossfade", "soft_crossfade"}
_MLT_EXPERIMENTAL_GATE_VALUES = {"mlt", "mlt_experimental"}


def _normalize_param_flag(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_mlt_experimental_requested(params: Dict[str, Any]) -> bool:
    for key in ("engine", "render_backend", "backend"):
        if _normalize_param_flag(params.get(key)) in _MLT_EXPERIMENTAL_GATE_VALUES:
            return True
    return False


def _coerce_mlt_probe_result(value: Optional[Any]) -> Optional[MltProbeResult]:
    if value is None or isinstance(value, MltProbeResult):
        return value
    payload = dict(value or {})
    return MltProbeResult(
        available=bool(payload.get("available")),
        executable=payload.get("executable"),
        version=payload.get("version"),
        reason=payload.get("reason"),
        probe_version=str(payload.get("probe_version") or "mlt_probe_v1"),
        search_candidates=tuple(payload.get("search_candidates") or ()),
        stderr=payload.get("stderr"),
    )


def _iter_segments(plan: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    for segment in list(plan.get("segments") or []):
        if isinstance(segment, dict):
            yield segment


def collect_mlt_rejection_reasons(
    plan: Dict[str, Any],
    params: Dict[str, Any],
    probe: Optional[Any] = None,
) -> list[str]:
    effective_params = dict(params or {})
    reasons: list[str] = []

    if not _is_mlt_experimental_requested(effective_params):
        return [MLT_BACKEND_REASON_GATE_DISABLED]

    if bool(effective_params.get("preview")):
        return [MLT_BACKEND_REASON_PREVIEW_NOT_SUPPORTED]

    resolved_probe = _coerce_mlt_probe_result(probe) or probe_mlt_runtime()
    if not resolved_probe.available:
        return [str(resolved_probe.reason or MLT_BACKEND_REASON_NOT_INSTALLED)]

    for segment in _iter_segments(plan):
        segment_type = _normalize_param_flag(segment.get("type"))
        if segment_type and segment_type not in _MLT_ALLOWED_SEGMENT_TYPES:
            reasons.append(MLT_BACKEND_REASON_UNSUPPORTED_SEGMENT_TYPE)
            break

    for segment in _iter_segments(plan):
        transition_config = segment.get("transition_config") or {}
        transition_type = transition_config.get("type") if isinstance(transition_config, dict) else None
        transition = _normalize_param_flag(transition_type or segment.get("transition") or "cut")
        if transition and transition not in _MLT_ALLOWED_TRANSITIONS:
            reasons.append(MLT_BACKEND_REASON_UNSUPPORTED_TRANSITION)
            break

    return reasons


def should_use_mlt_backend(
    plan: Dict[str, Any],
    params: Dict[str, Any],
    probe: Optional[Any] = None,
) -> bool:
    rejections = collect_mlt_rejection_reasons(
        plan,
        params,
        probe,
    )
    return len(rejections) == 0


def _build_preview_decision() -> BackendDecision:
    return BackendDecision(
        backend_name=LEGACY_MOVIEPY_BACKEND_NAME,
        backend_family=STANDARD_TIMELINE_BACKEND_FAMILY,
        backend_mode=BACKEND_MODE_PREVIEW,
        reason=BACKEND_REASON_PREVIEW_STANDARD_RENDERER,
        fallback_chain=[LEGACY_MOVIEPY_BACKEND_NAME],
        capability_flags=[CAPABILITY_FLAG_PREVIEW, CAPABILITY_FLAG_TIMELINE, CAPABILITY_FLAG_MOVIEPY],
    )


def _build_stable_decision(reason: str) -> BackendDecision:
    return BackendDecision(
        backend_name=FFMPEG_STABLE_BACKEND_NAME,
        backend_family=LONG_VIDEO_STABLE_BACKEND_FAMILY,
        backend_mode=BACKEND_MODE_FINAL_RENDER,
        reason=reason,
        fallback_chain=[FFMPEG_STABLE_BACKEND_NAME, LEGACY_MOVIEPY_BACKEND_NAME],
        capability_flags=[
            CAPABILITY_FLAG_STABLE,
            CAPABILITY_FLAG_CHUNKED,
            CAPABILITY_FLAG_FFMPEG,
            CAPABILITY_FLAG_FALLBACK_MOVIEPY,
        ],
    )


def _build_mlt_decision() -> BackendDecision:
    return BackendDecision(
        backend_name=MLT_BACKEND_NAME,
        backend_family=MLT_BACKEND_FAMILY,
        backend_mode=BACKEND_MODE_FINAL_RENDER,
        reason=MLT_BACKEND_REASON_SELECTED,
        fallback_chain=[
            MLT_BACKEND_NAME,
            FFMPEG_STABLE_BACKEND_NAME,
            LEGACY_MOVIEPY_BACKEND_NAME,
        ],
        capability_flags=list(MLT_BACKEND_CAPABILITY_FLAGS),
    )


def _build_standard_decision(reason: str) -> BackendDecision:
    return BackendDecision(
        backend_name=LEGACY_MOVIEPY_BACKEND_NAME,
        backend_family=STANDARD_TIMELINE_BACKEND_FAMILY,
        backend_mode=BACKEND_MODE_FINAL_RENDER,
        reason=reason,
        fallback_chain=[LEGACY_MOVIEPY_BACKEND_NAME],
        capability_flags=[CAPABILITY_FLAG_TIMELINE, CAPABILITY_FLAG_MOVIEPY],
    )


def resolve_render_backend(
    plan: Dict[str, Any],
    params: Dict[str, Any],
    should_use_stable_renderer: Callable[[Dict[str, Any], Dict[str, Any]], bool],
    probe_mlt_runtime_fn: Optional[Callable[[], MltProbeResult]] = None,
) -> BackendDecision:
    effective_params = dict(params or {})
    if bool(effective_params.get("preview")):
        return _build_preview_decision()

    mlt_requested = _is_mlt_experimental_requested(effective_params)
    mlt_rejections: list[str] = []
    if mlt_requested:
        resolved_probe = (probe_mlt_runtime_fn or probe_mlt_runtime)()
        mlt_rejections = collect_mlt_rejection_reasons(
            plan,
            effective_params,
            resolved_probe,
        )
        if not mlt_rejections:
            return _build_mlt_decision()

    if should_use_stable_renderer(plan, effective_params):
        reason = BACKEND_REASON_STABLE_RENDERER_SELECTED
        if mlt_requested and mlt_rejections:
            reason = merge_backend_reason_tags(reason, mlt_rejections)
        return _build_stable_decision(reason)

    reason = BACKEND_REASON_STANDARD_RENDERER_SELECTED
    if mlt_requested and mlt_rejections:
        reason = merge_backend_reason_tags(reason, mlt_rejections)
    return _build_standard_decision(reason)
