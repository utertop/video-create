from __future__ import annotations

from typing import Any, Callable, Dict

from .base import BackendDecision


def resolve_render_backend(
    plan: Dict[str, Any],
    params: Dict[str, Any],
    should_use_stable_renderer: Callable[[Dict[str, Any], Dict[str, Any]], bool],
) -> BackendDecision:
    effective_params = dict(params or {})
    if bool(effective_params.get("preview")):
        return BackendDecision(
            backend_name="legacy_moviepy_backend",
            backend_family="standard_timeline",
            backend_mode="preview",
            reason="preview_render_uses_standard_renderer",
            fallback_chain=["legacy_moviepy_backend"],
            capability_flags=["preview", "timeline", "moviepy"],
        )

    if should_use_stable_renderer(plan, effective_params):
        return BackendDecision(
            backend_name="ffmpeg_stable_backend",
            backend_family="long_video_stable",
            backend_mode="final_render",
            reason="stable_renderer_selected",
            fallback_chain=["ffmpeg_stable_backend", "legacy_moviepy_backend"],
            capability_flags=["stable", "chunked", "ffmpeg", "fallback_moviepy"],
        )

    return BackendDecision(
        backend_name="legacy_moviepy_backend",
        backend_family="standard_timeline",
        backend_mode="final_render",
        reason="standard_renderer_selected",
        fallback_chain=["legacy_moviepy_backend"],
        capability_flags=["timeline", "moviepy"],
    )
