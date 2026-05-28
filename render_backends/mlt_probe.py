from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from .base import MLT_BACKEND_NAME, MLT_BACKEND_REASON_NOT_INSTALLED


MLT_PROBE_VERSION = "mlt_probe_v1"
DEFAULT_MLT_EXECUTABLE_CANDIDATES = ("melt", "mlt-melt")


@dataclass(frozen=True)
class MltProbeResult:
    available: bool
    executable: Optional[str] = None
    version: Optional[str] = None
    reason: Optional[str] = None
    probe_version: str = MLT_PROBE_VERSION
    search_candidates: tuple[str, ...] = DEFAULT_MLT_EXECUTABLE_CANDIDATES
    stderr: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "executable": self.executable,
            "version": self.version,
            "reason": self.reason,
            "probe_version": self.probe_version,
            "search_candidates": list(self.search_candidates),
            "stderr": self.stderr,
        }


def _extract_version(raw_output: str) -> Optional[str]:
    first_line = str(raw_output or "").strip().splitlines()
    if not first_line:
        return None
    return first_line[0].strip() or None


def probe_mlt_runtime(
    candidates: Optional[Sequence[str]] = None,
    *,
    timeout_seconds: float = 5.0,
) -> MltProbeResult:
    search_candidates = tuple(candidates or DEFAULT_MLT_EXECUTABLE_CANDIDATES)
    for candidate in search_candidates:
        executable = shutil.which(candidate)
        if not executable:
            continue
        try:
            completed = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except Exception as exc:
            return MltProbeResult(
                available=False,
                executable=executable,
                reason=f"{MLT_BACKEND_NAME}_probe_failed",
                search_candidates=search_candidates,
                stderr=str(exc),
            )

        raw_output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        if completed.returncode == 0:
            return MltProbeResult(
                available=True,
                executable=executable,
                version=_extract_version(raw_output),
                reason=f"{MLT_BACKEND_NAME}_runtime_available",
                search_candidates=search_candidates,
                stderr=(completed.stderr or "").strip() or None,
            )
        return MltProbeResult(
            available=False,
            executable=executable,
            version=_extract_version(raw_output),
            reason=f"{MLT_BACKEND_NAME}_version_probe_failed",
            search_candidates=search_candidates,
            stderr=(completed.stderr or completed.stdout or "").strip() or None,
        )

    return MltProbeResult(
        available=False,
        reason=MLT_BACKEND_REASON_NOT_INSTALLED,
        search_candidates=search_candidates,
    )
