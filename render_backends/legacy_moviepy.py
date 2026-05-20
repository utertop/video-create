from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .base import BackendDecision, BackendExecutionResult, coerce_backend_decision


def run_render(
    engine: Any,
    decision: BackendDecision,
    plan: Dict[str, Any],
    output: str,
    params: Dict[str, Any],
) -> BackendExecutionResult:
    resolved_decision = coerce_backend_decision(decision)
    final_output = Path(output)
    tmp_output = final_output.with_suffix(".rendering.tmp.mp4")
    if tmp_output.exists():
        try:
            tmp_output.unlink()
        except Exception:
            pass

    engine.Renderer(plan, str(tmp_output), params).render()
    ok, reason, _duration = engine._v56_validate_video(tmp_output)
    if not ok:
        raise RuntimeError(f"标准渲染结果校验失败，不覆盖旧文件: {reason}")
    engine._v56_atomic_replace(tmp_output, final_output)
    return BackendExecutionResult.from_decision(
        resolved_decision,
        actual_backend_name="legacy_moviepy_backend",
    )
