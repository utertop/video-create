"""Stable render orchestration for the V5.6 renderer."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Dict, List, Optional, Tuple

from render_backends import (
    BackendDecision,
    BackendExecutionResult,
    coerce_backend_decision,
    coerce_backend_execution_result,
    merge_backend_reason_tags,
    resolve_render_backend as backend_selector_resolve_render_backend,
    run_ffmpeg_stable_backend,
    run_legacy_moviepy_backend,
    run_mlt_backend,
)
from video_engine.constants import ENGINE_VERSION
from video_engine import render_diagnostics as render_diagnostics_helpers
from video_engine.render_cache import (
    _v56_atomic_replace,
    _v56_build_chunk_groups,
    _v56_write_build_report,
)
from video_engine.render_routes import _should_auto_use_stable_renderer


EmitEvent = Callable[..., None]
ReadJson = Callable[[str], Dict[str, Any]]
ValidateVideo = Callable[[Path], Tuple[bool, str, Optional[float]]]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def should_use_stable_renderer(plan: Dict[str, Any], params: Dict[str, Any]) -> bool:
    performance_mode = str(params.get("performance_mode") or plan.get("render_settings", {}).get("performance_mode") or "").lower()
    mode = str(params.get("render_mode") or params.get("long_video_mode") or "auto").lower()

    # Explicit render mode has the highest priority.
    if mode in {"stable", "long", "long_stable", "true", "1", "yes"}:
        return True
    if mode in {"standard", "classic", "moviepy"}:
        return False

    if performance_mode == "stable":
        return True

    # "quality" means keep higher visual quality, not force the unsafe monolithic
    # MoviePy timeline. Large projects still need chunked stable rendering.
    total_duration = float(plan.get("total_duration") or 0.0)
    segments = list(plan.get("segments", []) or [])
    return _should_auto_use_stable_renderer(total_duration, segments, params)


def resolve_render_backend_decision(plan: Dict[str, Any], params: Dict[str, Any]) -> BackendDecision:
    return backend_selector_resolve_render_backend(plan, params, should_use_stable_renderer)


def resolve_render_backend(plan: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    return resolve_render_backend_decision(plan, params).to_dict()


def backend_report_payload(
    decision: Optional[Any],
    fallback_used: Optional[str] = None,
    fallback_reason: Optional[str] = None,
) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_backend_report_payload(
        decision,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )


class V56StableRenderer:
    def __init__(
        self,
        plan: Dict[str, Any],
        output: str,
        params: Dict[str, Any],
        plan_path: Optional[str] = None,
        *,
        renderer_cls: Any,
        has_moviepy: bool,
        emit_event_fn: EmitEvent = _noop_emit_event,
        stable_should_force_chunk_audio_track_fn: Callable[[Any, List[Dict[str, Any]]], bool],
        validate_video_fn: ValidateVideo,
        write_chunk_video_fn: Callable[..., None],
        concat_chunks_ffmpeg_fn: Callable[..., bool],
        concat_chunks_ffmpeg_reencode_fn: Callable[..., bool],
        concat_chunks_moviepy_fn: Callable[..., None],
        safe_apply_final_bgm_mix_fn: Callable[..., Tuple[bool, Optional[Exception]]],
        classify_render_failure_fn: Callable[[Any, str], Dict[str, Any]] = render_diagnostics_helpers._v56_classify_render_failure,
        build_recovery_summary_fn: Callable[..., Dict[str, Any]] = render_diagnostics_helpers._v56_build_recovery_summary,
        render_diagnostics_fn: Callable[..., Dict[str, Any]] = render_diagnostics_helpers._v56_render_diagnostics,
        report_summary_fields_fn: Callable[..., Dict[str, Any]] = render_diagnostics_helpers._v56_report_summary_fields,
        collect_segment_route_details_fn: Callable[..., List[Dict[str, Any]]] = render_diagnostics_helpers._v56_collect_segment_route_details,
        collect_chunk_route_details_fn: Callable[..., List[Dict[str, Any]]] = render_diagnostics_helpers._v56_collect_chunk_route_details,
    ):
        self.plan = plan
        self.output = Path(output)
        self.params = params or {}
        self.backend_decision = coerce_backend_decision(
            self.params.get("_backend_decision") or resolve_render_backend_decision(self.plan, self.params)
        )
        self.backend_execution = coerce_backend_execution_result(
            self.params.get("_backend_execution") or self.backend_decision
        )
        self.plan_path = Path(plan_path).resolve() if plan_path else None

        if self.plan_path:
            self.project_dir = self.plan_path.parent
        else:
            self.project_dir = self.output.parent / ".video_create_project"

        self.chunk_dir = self.project_dir / "chunks" / self.output.stem
        self.chunk_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.chunk_dir / "chunk_manifest.json"
        self.report_path = self.project_dir / "build_report.json"

        self.fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        self.chunk_seconds = float(self.params.get("chunk_seconds") or self.params.get("stable_chunk_seconds") or 120)

        self.renderer_cls = renderer_cls
        self.has_moviepy = bool(has_moviepy)
        self.emit_event = emit_event_fn
        self.stable_should_force_chunk_audio_track = stable_should_force_chunk_audio_track_fn
        self.validate_video = validate_video_fn
        self.write_chunk_video = write_chunk_video_fn
        self.concat_chunks_ffmpeg = concat_chunks_ffmpeg_fn
        self.concat_chunks_ffmpeg_reencode = concat_chunks_ffmpeg_reencode_fn
        self.concat_chunks_moviepy = concat_chunks_moviepy_fn
        self.safe_apply_final_bgm_mix = safe_apply_final_bgm_mix_fn
        self.classify_render_failure = classify_render_failure_fn
        self.build_recovery_summary = build_recovery_summary_fn
        self.render_diagnostics = render_diagnostics_fn
        self.report_summary_fields = report_summary_fields_fn
        self.collect_segment_route_details = collect_segment_route_details_fn
        self.collect_chunk_route_details = collect_chunk_route_details_fn

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            try:
                with self.manifest_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"chunks": {}}
        return {"chunks": {}}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def _write_failure_report(
        self,
        *,
        renderer: Any,
        manifest: Dict[str, Any],
        groups: List[Dict[str, Any]],
        chunk_reports: List[Dict[str, Any]],
        chunk_route_counts: Dict[str, int],
        timings: Dict[str, Any],
        force_chunk_audio_track: bool,
        final_output: Path,
        error: Any,
        stage: str,
        failed_chunk: Optional[str] = None,
        resumed_from_manifest: bool = False,
        reused_chunk_count: int = 0,
    ) -> None:
        failure = self.classify_render_failure(error, stage)
        segment_routes = self.collect_segment_route_details(self.plan.get("segments", []) or [])
        chunk_routes = self.collect_chunk_route_details(groups, chunk_reports)
        backend_payload = backend_report_payload(self.backend_execution)
        diagnostics = self.render_diagnostics(renderer, groups, chunk_reports, force_chunk_audio_track, timings)
        report = {
            "engine_version": ENGINE_VERSION,
            "status": "failed",
            "failed_chunk": failed_chunk,
            "failed_stage": stage,
            "error": str(error),
            "failure": failure,
            "output_path": str(final_output),
            "selected_backend": self.backend_execution.selected_backend_name,
            "backend": backend_payload,
            "chunk_dir": str(self.chunk_dir),
            "chunks": chunk_reports,
            "photo_segment_cache": renderer._photo_segment_cache_summary(),
            "card_segment_cache": renderer._card_segment_cache_summary(),
            "video_segment_cache": renderer._video_segment_cache_summary(),
            "proxy_media": renderer._proxy_media_summary(),
            "cache_cleanup": renderer.cache_cleanup_stats,
            "render_scheduler": renderer.render_scheduler_summary,
            "segment_routes": segment_routes,
            "chunk_routes": chunk_routes,
            "timings": dict(timings),
            "recovery": self.build_recovery_summary(
                manifest,
                chunk_reports=chunk_reports,
                failed_chunk=failed_chunk,
                failure=failure,
                manifest_path=self.manifest_path,
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            ),
            "chunk_scheduler": {
                "strategy_version": "chunk_rules_v1",
                "route_counts": chunk_route_counts,
                "total_chunks": len(groups),
            },
            "diagnostics": diagnostics,
            **self.report_summary_fields(backend_payload, diagnostics, render_intent="final"),
            "created_at": datetime.now().isoformat(),
        }
        _v56_write_build_report(self.report_path, report)

    def render(self) -> None:
        if not self.has_moviepy:
            raise RuntimeError("MoviePy unavailable; stable renderer cannot render video")

        started_at = datetime.now()
        tmp_output = self.output.with_suffix(".rendering.tmp.mp4")
        final_output = self.output

        if tmp_output.exists():
            try:
                tmp_output.unlink()
            except Exception:
                pass

        renderer = self.renderer_cls(self.plan, str(self.output), self.params)
        segments = self.plan.get("segments", [])
        force_chunk_audio_track = self.stable_should_force_chunk_audio_track(renderer, segments)
        groups = _v56_build_chunk_groups(segments, self.chunk_seconds, self.params)
        timings: Dict[str, Any] = {"total_render_seconds": 0.0}
        chunk_route_counts: Dict[str, int] = {}
        for group in groups:
            route = str(group.get("runtime_chunk_route") or "moviepy_chunk")
            chunk_route_counts[route] = chunk_route_counts.get(route, 0) + 1
        manifest = self._load_manifest()
        manifest.setdefault("engine_version", ENGINE_VERSION)
        manifest.setdefault("chunks", {})
        manifest.setdefault("render_attempts", 0)
        manifest["render_attempts"] = int(manifest.get("render_attempts") or 0) + 1
        manifest["last_started_at"] = datetime.now().isoformat()
        resumed_from_manifest = any(
            isinstance(item, dict) and item.get("status") in {"done", "failed"}
            for item in (manifest.get("chunks") or {}).values()
        )
        reused_chunk_count = 0
        self._save_manifest(manifest)
        if chunk_route_counts:
            compact = ", ".join(f"{key}={value}" for key, value in sorted(chunk_route_counts.items()))
            self.emit_event("log", message=f"Chunk scheduler summary: {compact}")

        self.emit_event(
            "phase",
            phase="render",
            message=f"Using V5.6 stable render mode: {len(groups)} chunks, {int(self.chunk_seconds)} seconds each",
            percent=8,
        )

        rendered_chunks: List[Path] = []
        chunk_reports: List[Dict[str, Any]] = []
        chunk_render_started = perf_counter()

        for group in groups:
            idx = int(group["index"])
            chunk_name = f"chunk_{idx:03d}.mp4"
            chunk_path = self.chunk_dir / chunk_name
            key = str(group["cache_key"])
            existing = manifest.get("chunks", {}).get(chunk_name, {})

            ok, reason, duration = self.validate_video(chunk_path)
            if existing.get("cache_key") == key and existing.get("status") == "done" and ok:
                reused_chunk_count += 1
                self.emit_event(
                    "phase",
                    phase="render",
                    message=f"Reusing cached chunk {chunk_name}",
                    percent=min(94, 10 + int((idx / max(len(groups), 1)) * 80)),
                )
                rendered_chunks.append(chunk_path)
                chunk_reports.append({
                    "name": chunk_name,
                    "status": "cached",
                    "duration": duration,
                    "render_seconds": 0.0,
                    "cache_key": key,
                    "runtime_chunk_route": group.get("runtime_chunk_route"),
                    "runtime_chunk_route_reason": group.get("runtime_chunk_route_reason"),
                })
                continue

            try:
                single_chunk_started = perf_counter()
                self.write_chunk_video(
                    renderer,
                    group,
                    chunk_path,
                    self.fps,
                    self.params,
                    ensure_audio_track=force_chunk_audio_track,
                )
                ok, reason, duration = self.validate_video(chunk_path)
                if not ok:
                    raise RuntimeError(reason)
                single_chunk_seconds = round(perf_counter() - single_chunk_started, 4)

                manifest["chunks"][chunk_name] = {
                    "status": "done",
                    "cache_key": key,
                    "path": str(chunk_path),
                    "duration": duration,
                    "attempt_count": int(existing.get("attempt_count") or 0) + 1,
                    "runtime_chunk_route": group.get("runtime_chunk_route"),
                    "runtime_chunk_route_reason": group.get("runtime_chunk_route_reason"),
                    "render_seconds": single_chunk_seconds,
                    "updated_at": datetime.now().isoformat(),
                }
                manifest["last_completed_chunk"] = chunk_name
                self._save_manifest(manifest)
                rendered_chunks.append(chunk_path)
                chunk_reports.append({
                    "name": chunk_name,
                    "status": "rendered",
                    "duration": duration,
                    "render_seconds": single_chunk_seconds,
                    "cache_key": key,
                    "runtime_chunk_route": group.get("runtime_chunk_route"),
                    "runtime_chunk_route_reason": group.get("runtime_chunk_route_reason"),
                })
            except Exception as exc:
                failure = self.classify_render_failure(exc, "chunk_render")
                manifest["chunks"][chunk_name] = {
                    "status": "failed",
                    "cache_key": key,
                    "path": str(chunk_path),
                    "error": str(exc),
                    "attempt_count": int(existing.get("attempt_count") or 0) + 1,
                    "failure": failure,
                    "runtime_chunk_route": group.get("runtime_chunk_route"),
                    "runtime_chunk_route_reason": group.get("runtime_chunk_route_reason"),
                    "updated_at": datetime.now().isoformat(),
                }
                manifest["last_failed_chunk"] = chunk_name
                manifest["last_failure"] = failure
                self._save_manifest(manifest)
                self._write_failure_report(
                    renderer=renderer,
                    manifest=manifest,
                    groups=groups,
                    chunk_reports=chunk_reports,
                    chunk_route_counts=chunk_route_counts,
                    timings=timings,
                    force_chunk_audio_track=force_chunk_audio_track,
                    final_output=final_output,
                    error=exc,
                    stage="chunk_render",
                    failed_chunk=chunk_name,
                    resumed_from_manifest=resumed_from_manifest,
                    reused_chunk_count=reused_chunk_count,
                )
                raise

        if not rendered_chunks:
            exc = RuntimeError("stable render produced no successful chunks")
            manifest["last_failure"] = self.classify_render_failure(exc, "chunk_render")
            self._save_manifest(manifest)
            self._write_failure_report(
                renderer=renderer,
                manifest=manifest,
                groups=groups,
                chunk_reports=chunk_reports,
                chunk_route_counts=chunk_route_counts,
                timings=timings,
                force_chunk_audio_track=force_chunk_audio_track,
                final_output=final_output,
                error=exc,
                stage="chunk_render",
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            )
            raise exc

        timings["chunk_render_seconds"] = round(perf_counter() - chunk_render_started, 4)
        concat_started = perf_counter()
        concat_strategy = "ffmpeg_copy"
        concat_ok = self.concat_chunks_ffmpeg(rendered_chunks, tmp_output, self.project_dir)
        if not concat_ok:
            concat_strategy = "ffmpeg_reencode"
            concat_ok = self.concat_chunks_ffmpeg_reencode(rendered_chunks, tmp_output, self.project_dir, self.fps, self.params)
        if not concat_ok:
            concat_strategy = "moviepy_fallback"
            try:
                self.concat_chunks_moviepy(rendered_chunks, tmp_output, self.fps, self.params)
            except Exception as exc:
                manifest["last_failure"] = self.classify_render_failure(exc, "concat")
                self._save_manifest(manifest)
                self._write_failure_report(
                    renderer=renderer,
                    manifest=manifest,
                    groups=groups,
                    chunk_reports=chunk_reports,
                    chunk_route_counts=chunk_route_counts,
                    timings=timings,
                    force_chunk_audio_track=force_chunk_audio_track,
                    final_output=final_output,
                    error=exc,
                    stage="concat",
                    resumed_from_manifest=resumed_from_manifest,
                    reused_chunk_count=reused_chunk_count,
                )
                raise
        timings["concat_seconds"] = round(perf_counter() - concat_started, 4)
        timings["concat_strategy"] = concat_strategy

        ok, reason, final_duration = self.validate_video(tmp_output)
        if not ok:
            exc = RuntimeError(f"final stable output validation failed: {reason}")
            manifest["last_failure"] = self.classify_render_failure(exc, "output_validate")
            self._save_manifest(manifest)
            self._write_failure_report(
                renderer=renderer,
                manifest=manifest,
                groups=groups,
                chunk_reports=chunk_reports,
                chunk_route_counts=chunk_route_counts,
                timings=timings,
                force_chunk_audio_track=force_chunk_audio_track,
                final_output=final_output,
                error=exc,
                stage="output_validate",
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            )
            raise exc

        mixed_output = tmp_output.with_suffix(".audio.tmp.mp4")
        final_mix_started = perf_counter()
        audio_mix_applied = False
        mix_ok, mix_error = self.safe_apply_final_bgm_mix(
            tmp_output,
            mixed_output,
            renderer.audio_settings,
            final_duration,
            prepared_bgm_path=renderer._prepare_music_bed(final_duration) or renderer._prepare_music_path(),
            prepared_bgm_is_bed=True,
        )
        if mix_error is not None:
            manifest["last_failure"] = self.classify_render_failure(mix_error, "audio_mix")
            self._save_manifest(manifest)
            self._write_failure_report(
                renderer=renderer,
                manifest=manifest,
                groups=groups,
                chunk_reports=chunk_reports,
                chunk_route_counts=chunk_route_counts,
                timings=timings,
                force_chunk_audio_track=force_chunk_audio_track,
                final_output=final_output,
                error=mix_error,
                stage="audio_mix",
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            )
            raise mix_error
        if mix_ok:
            audio_mix_applied = True
            try:
                tmp_output.unlink()
            except Exception:
                pass
            os.replace(str(mixed_output), str(tmp_output))
            ok, reason, final_duration = self.validate_video(tmp_output)
            if not ok:
                exc = RuntimeError(f"final audio mix validation failed: {reason}")
                manifest["last_failure"] = self.classify_render_failure(exc, "audio_mix")
                self._save_manifest(manifest)
                self._write_failure_report(
                    renderer=renderer,
                    manifest=manifest,
                    groups=groups,
                    chunk_reports=chunk_reports,
                    chunk_route_counts=chunk_route_counts,
                    timings=timings,
                    force_chunk_audio_track=force_chunk_audio_track,
                    final_output=final_output,
                    error=exc,
                    stage="audio_mix",
                    resumed_from_manifest=resumed_from_manifest,
                    reused_chunk_count=reused_chunk_count,
                )
                raise exc

        timings["final_audio_mix_seconds"] = round(perf_counter() - final_mix_started, 4)
        timings["final_audio_mix_applied"] = audio_mix_applied
        _v56_atomic_replace(tmp_output, final_output)

        elapsed = (datetime.now() - started_at).total_seconds()
        timings["total_render_seconds"] = round(elapsed, 4)
        renderer.last_render_timings = dict(timings)
        renderer._emit_photo_segment_cache_summary()
        renderer._emit_card_segment_cache_summary()
        renderer._emit_video_segment_cache_summary()
        renderer._emit_proxy_media_summary()
        renderer._cleanup_project_cache_dirs()
        manifest["last_completed_at"] = datetime.now().isoformat()
        manifest["last_failure"] = None
        self._save_manifest(manifest)
        backend_payload = backend_report_payload(self.backend_execution)
        diagnostics = self.render_diagnostics(renderer, groups, chunk_reports, force_chunk_audio_track, timings)
        report = {
            "engine_version": ENGINE_VERSION,
            "status": "done",
            "render_mode": "v5.6_long_video_stable",
            "output_path": str(final_output),
            "selected_backend": self.backend_execution.selected_backend_name,
            "backend": backend_payload,
            "output_size_bytes": final_output.stat().st_size if final_output.exists() else None,
            "duration_seconds": final_duration,
            "elapsed_seconds": elapsed,
            "chunk_seconds": self.chunk_seconds,
            "chunk_count": len(rendered_chunks),
            "chunk_dir": str(self.chunk_dir),
            "chunks": chunk_reports,
            "photo_segment_cache": renderer._photo_segment_cache_summary(),
            "card_segment_cache": renderer._card_segment_cache_summary(),
            "video_segment_cache": renderer._video_segment_cache_summary(),
            "proxy_media": renderer._proxy_media_summary(),
            "cache_cleanup": renderer.cache_cleanup_stats,
            "render_scheduler": renderer.render_scheduler_summary,
            "segment_routes": self.collect_segment_route_details(segments),
            "chunk_routes": self.collect_chunk_route_details(groups, chunk_reports),
            "timings": dict(timings),
            "recovery": self.build_recovery_summary(
                manifest,
                chunk_reports=chunk_reports,
                manifest_path=self.manifest_path,
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            ),
            "chunk_scheduler": {
                "strategy_version": "chunk_rules_v1",
                "route_counts": chunk_route_counts,
                "total_chunks": len(groups),
            },
            "diagnostics": diagnostics,
            **self.report_summary_fields(backend_payload, diagnostics, render_intent="final"),
            "created_at": datetime.now().isoformat(),
        }
        _v56_write_build_report(self.report_path, report)
        self.emit_event("phase", phase="done", message="Stable render complete", percent=100)


def run_render_backend(
    decision: Any,
    plan: Dict[str, Any],
    output: str,
    params: Dict[str, Any],
    plan_path: Optional[str] = None,
    *,
    engine_module: Any,
) -> BackendExecutionResult:
    resolved_decision = coerce_backend_decision(decision)
    fallback_chain = list(resolved_decision.fallback_chain or [resolved_decision.backend_name])
    ordered_candidates: List[str] = []
    for backend_name in [resolved_decision.backend_name, *fallback_chain]:
        normalized = str(backend_name or "").strip()
        if normalized and normalized not in ordered_candidates:
            ordered_candidates.append(normalized)

    failed_reasons: List[str] = []
    last_error: Optional[Exception] = None
    for backend_name in ordered_candidates:
        initial_execution = BackendExecutionResult.from_decision(
            resolved_decision,
            fallback_used=(backend_name if backend_name != resolved_decision.backend_name else None),
            fallback_reason=merge_backend_reason_tags(failed_reasons) if failed_reasons else None,
        )
        effective_params = dict(params or {})
        effective_params["_backend_decision"] = resolved_decision.to_dict()
        effective_params["_backend_execution"] = initial_execution.to_dict()

        try:
            if backend_name == "ffmpeg_stable_backend":
                result = run_ffmpeg_stable_backend(
                    engine_module,
                    resolved_decision,
                    plan,
                    output,
                    effective_params,
                    plan_path=plan_path,
                )
            elif backend_name == "legacy_moviepy_backend":
                result = run_legacy_moviepy_backend(
                    engine_module,
                    resolved_decision,
                    plan,
                    output,
                    effective_params,
                )
            elif backend_name == "mlt_backend":
                result = run_mlt_backend(
                    engine_module,
                    resolved_decision,
                    plan,
                    output,
                    effective_params,
                    plan_path=plan_path,
                )
            else:
                raise RuntimeError(f"Unknown render backend: {backend_name}")
        except Exception as exc:
            last_error = exc
            failed_reasons.append(
                str(
                    getattr(exc, "reason", None)
                    or str(exc)
                    or backend_name
                    or exc.__class__.__name__
                )
            )
            continue

        if backend_name == resolved_decision.backend_name:
            return result
        return BackendExecutionResult.from_decision(
            resolved_decision,
            actual_backend_name=result.actual_backend_name,
            fallback_used=result.actual_backend_name,
            fallback_reason=merge_backend_reason_tags(failed_reasons) if failed_reasons else None,
        )

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unable to execute render backend: {resolved_decision.backend_name}")


def render_with_v56_stability(
    plan_path: str,
    output: str,
    params: Dict[str, Any],
    *,
    read_json_fn: ReadJson,
    engine_module: Any,
) -> None:
    plan = read_json_fn(plan_path)
    decision = resolve_render_backend_decision(plan, params)
    run_render_backend(decision, plan, output, params, plan_path=plan_path, engine_module=engine_module)
