from __future__ import annotations

from typing import Any, Dict, Optional

from .base import (
    MLT_BACKEND_NAME,
    MLT_BACKEND_REASON_SCAFFOLD_ONLY,
    BackendDecision,
    BackendExecutionResult,
    coerce_backend_decision,
)


class MltBackendScaffoldError(RuntimeError):
    def __init__(self, message: str = "MLT backend scaffold is not executable yet") -> None:
        super().__init__(message)
        self.reason = MLT_BACKEND_REASON_SCAFFOLD_ONLY
        self.backend_name = MLT_BACKEND_NAME


def build_mlt_project(
    plan: Dict[str, Any],
    params: Dict[str, Any],
    output_path: str,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    _ = (plan, params, output_path, working_dir)
    raise MltBackendScaffoldError()


def run_render(
    engine: Any,
    decision: BackendDecision,
    plan: Dict[str, Any],
    output: str,
    params: Dict[str, Any],
    plan_path: Optional[str] = None,
) -> BackendExecutionResult:
    _ = (engine, plan, output, params, plan_path)
    resolved_decision = coerce_backend_decision(decision)
    if resolved_decision.backend_name != MLT_BACKEND_NAME:
        raise RuntimeError(
            f"MLT backend received mismatched decision: {resolved_decision.backend_name}"
        )
    raise MltBackendScaffoldError()
