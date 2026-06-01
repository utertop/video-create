from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from .base import (
    MLT_BACKEND_NAME,
    MLT_BACKEND_REASON_RENDER_FAILED,
    MLT_BACKEND_REASON_SCAFFOLD_ONLY,
    MLT_BACKEND_REASON_VALIDATION_FAILED,
    BackendDecision,
    BackendExecutionResult,
    coerce_backend_decision,
    merge_backend_reason_tags,
)
from .mlt_project_builder import MltProjectBuildResult, build_mlt_project as build_mlt_project_file_set
from .mlt_probe import MltProbeResult, probe_mlt_runtime


class MltBackendScaffoldError(RuntimeError):
    def __init__(self, message: str = "MLT backend scaffold is not executable yet") -> None:
        super().__init__(message)
        self.reason = MLT_BACKEND_REASON_SCAFFOLD_ONLY
        self.backend_name = MLT_BACKEND_NAME


class MltBackendError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        reason: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.backend_name = MLT_BACKEND_NAME
        self.details = dict(details or {})


def build_mlt_project(
    plan: Dict[str, Any],
    params: Dict[str, Any],
    output_path: str,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    result = build_mlt_project_file_set(plan, params, output_path, working_dir=working_dir)
    return result.to_dict()


def _resolve_mlt_working_dir(output: str, plan_path: Optional[str]) -> Path:
    final_output = Path(output).resolve()
    if plan_path:
        return Path(plan_path).resolve().parent / "mlt"
    return final_output.parent / ".video_create_project" / "mlt"


def _build_mlt_consumer_command(
    executable: str,
    project_path: Path,
    tmp_output: Path,
    fps: float,
) -> list[str]:
    return [
        executable,
        str(project_path),
        "-consumer",
        f"avformat:{tmp_output}",
        "vcodec=libx264",
        "acodec=aac",
        f"r={max(int(round(fps or 25.0)), 1)}",
        "progressive=1",
        "movflags=+faststart",
    ]


def _run_mlt_consumer(
    command: list[str],
    *,
    working_dir: Path,
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(working_dir),
        capture_output=True,
        text=True,
        check=False,
    )
    log_text = "\n".join(
        part for part in (completed.stdout or "", completed.stderr or "") if part
    ).strip()
    log_path.write_text(log_text, encoding="utf-8")
    return completed


def _ensure_clean_tmp_output(tmp_output: Path) -> None:
    if tmp_output.exists():
        try:
            tmp_output.unlink()
        except Exception:
            pass


def run_render(
    engine: Any,
    decision: BackendDecision,
    plan: Dict[str, Any],
    output: str,
    params: Dict[str, Any],
    plan_path: Optional[str] = None,
) -> BackendExecutionResult:
    resolved_decision = coerce_backend_decision(decision)
    if resolved_decision.backend_name != MLT_BACKEND_NAME:
        raise RuntimeError(
            f"MLT backend received mismatched decision: {resolved_decision.backend_name}"
        )

    probe = probe_mlt_runtime()
    if not probe.available or not probe.executable:
        raise MltBackendError(
            "MLT runtime is not available",
            reason=str(probe.reason or "mlt_backend_runtime_unavailable"),
            details={"probe": probe.to_dict()},
        )

    final_output = Path(output).resolve()
    working_dir = _resolve_mlt_working_dir(output, plan_path)
    build_result = build_mlt_project_file_set(plan, params, output, working_dir=str(working_dir))
    if not build_result.supported:
        raise MltBackendError(
            "MLT project builder rejected the render plan",
            reason=merge_backend_reason_tags(build_result.rejection_reasons),
            details=build_result.to_dict(),
        )

    working_dir.mkdir(parents=True, exist_ok=True)
    tmp_output = final_output.with_suffix(".rendering.tmp.mp4")
    _ensure_clean_tmp_output(tmp_output)
    log_path = working_dir / "render.log"
    fps = float((plan.get("render_settings") or {}).get("fps") or params.get("fps") or 25.0)
    command = _build_mlt_consumer_command(
        probe.executable,
        Path(build_result.project_path),
        tmp_output,
        fps,
    )
    completed = _run_mlt_consumer(
        command,
        working_dir=working_dir,
        log_path=log_path,
    )
    if completed.returncode != 0:
        raise MltBackendError(
            "MLT consumer returned a non-zero exit code",
            reason=MLT_BACKEND_REASON_RENDER_FAILED,
            details={
                "returncode": completed.returncode,
                "command": command,
                "project": build_result.to_dict(),
                "probe": probe.to_dict(),
                "log_path": str(log_path),
            },
        )

    ok, reason, _duration = engine._v56_validate_video(tmp_output)
    if not ok:
        raise MltBackendError(
            f"MLT render output validation failed: {reason}",
            reason=MLT_BACKEND_REASON_VALIDATION_FAILED,
            details={
                "validation_reason": reason,
                "project": build_result.to_dict(),
                "probe": probe.to_dict(),
                "log_path": str(log_path),
            },
        )
    engine._v56_atomic_replace(tmp_output, final_output)
    return BackendExecutionResult.from_decision(
        resolved_decision,
        actual_backend_name=MLT_BACKEND_NAME,
    )
