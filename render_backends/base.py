from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Union


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
