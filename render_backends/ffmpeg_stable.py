from __future__ import annotations

from typing import Any, Dict, Optional

from .base import BackendDecision, BackendExecutionResult, coerce_backend_decision


def run_render(
    engine: Any,
    decision: BackendDecision,
    plan: Dict[str, Any],
    output: str,
    params: Dict[str, Any],
    plan_path: Optional[str] = None,
) -> BackendExecutionResult:
    resolved_decision = coerce_backend_decision(decision)
    engine.V56StableRenderer(plan, output, params, plan_path=plan_path).render()
    return BackendExecutionResult.from_decision(
        resolved_decision,
        actual_backend_name="ffmpeg_stable_backend",
    )
