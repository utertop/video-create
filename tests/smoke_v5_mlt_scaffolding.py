import importlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import render_backends as backends
import video_engine_v5 as engine

mlt_backend_module = importlib.import_module("render_backends.mlt_backend")
render_stable_module = importlib.import_module("video_engine.render_stable")


def test_merge_backend_reason_tags_deduplicates_and_preserves_order() -> None:
    merged = backends.merge_backend_reason_tags(
        backends.MLT_BACKEND_REASON_SELECTED,
        [backends.MLT_BACKEND_REASON_SELECTED, backends.MLT_BACKEND_REASON_NOT_INSTALLED],
        "",
        None,
        [backends.MLT_BACKEND_REASON_NOT_INSTALLED, backends.MLT_BACKEND_REASON_SCAFFOLD_ONLY],
    )

    assert merged == (
        "mlt_backend_selected+mlt_not_installed+mlt_backend_scaffold_only"
    )


def test_probe_mlt_runtime_reports_missing_runtime_cleanly() -> None:
    result = backends.probe_mlt_runtime(candidates=("missing-melt-binary-for-smoke",))
    payload = result.to_dict()

    assert isinstance(result, backends.MltProbeResult)
    assert result.available is False
    assert result.reason == backends.MLT_BACKEND_REASON_NOT_INSTALLED
    assert payload["probe_version"] == backends.MLT_PROBE_VERSION
    assert payload["search_candidates"] == ["missing-melt-binary-for-smoke"]


def test_collect_mlt_rejection_reasons_requires_experimental_gate() -> None:
    reasons = backends.collect_mlt_rejection_reasons(
        {"segments": []},
        {"render_mode": "standard"},
    )

    assert reasons == [backends.MLT_BACKEND_REASON_GATE_DISABLED]


def test_should_use_mlt_backend_accepts_supported_plan_when_runtime_is_available() -> None:
    supported_plan = {
        "segments": [
            {
                "segment_id": "seg_001",
                "type": "image",
                "duration": 2.0,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
            }
        ]
    }
    probe = backends.MltProbeResult(
        available=True,
        executable="melt",
        version="7.0.0",
        reason="mlt_backend_runtime_available",
    )

    assert (
        backends.should_use_mlt_backend(
            supported_plan,
            {"engine": "mlt_experimental"},
            probe,
        )
        is True
    )

    reasons = backends.collect_mlt_rejection_reasons(
        supported_plan,
        {"engine": "mlt_experimental"},
        probe,
    )
    assert reasons == []


def test_resolve_render_backend_selects_mlt_when_probe_and_plan_are_supported() -> None:
    supported_plan = {
        "segments": [
            {
                "segment_id": "seg_001",
                "type": "image",
                "duration": 2.0,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
            }
        ]
    }
    probe = backends.MltProbeResult(
        available=True,
        executable="melt",
        version="7.0.0",
        reason="mlt_backend_runtime_available",
    )

    decision = backends.resolve_render_backend(
        supported_plan,
        {"engine": "mlt_experimental", "render_mode": "standard"},
        lambda _plan, _params: False,
        probe_mlt_runtime_fn=lambda: probe,
    )

    assert decision.backend_name == backends.MLT_BACKEND_NAME
    assert decision.reason == backends.MLT_BACKEND_REASON_SELECTED


def test_run_mlt_backend_requires_runtime_when_probe_is_missing() -> None:
    decision = backends.BackendDecision(
        backend_name=backends.MLT_BACKEND_NAME,
        backend_family=backends.MLT_BACKEND_FAMILY,
        backend_mode=backends.BACKEND_MODE_FINAL_RENDER,
        reason=backends.MLT_BACKEND_REASON_SELECTED,
        fallback_chain=[
            backends.MLT_BACKEND_NAME,
            backends.FFMPEG_STABLE_BACKEND_NAME,
            backends.LEGACY_MOVIEPY_BACKEND_NAME,
        ],
        capability_flags=list(backends.MLT_BACKEND_CAPABILITY_FLAGS),
    )
    original_probe = mlt_backend_module.probe_mlt_runtime
    mlt_backend_module.probe_mlt_runtime = lambda *args, **kwargs: backends.MltProbeResult(
        available=False,
        reason=backends.MLT_BACKEND_REASON_NOT_INSTALLED,
    )

    try:
        try:
            backends.run_mlt_backend(
                engine=None,
                decision=decision,
                plan={"segments": []},
                output="tests/tmp_vcs_mlt_scaffold/output.mp4",
                params={},
            )
            raise AssertionError("expected MLT backend to require runtime")
        except backends.MltBackendError as exc:
            assert exc.reason == backends.MLT_BACKEND_REASON_NOT_INSTALLED
            assert exc.backend_name == backends.MLT_BACKEND_NAME
    finally:
        mlt_backend_module.probe_mlt_runtime = original_probe


def test_run_mlt_backend_builds_project_and_validates_output() -> None:
    root = Path("tests/tmp_vcs_mlt_backend_success")
    root.mkdir(parents=True, exist_ok=True)
    source_path = root / "素材01.jpg"
    source_path.write_bytes(b"fake-image")
    output_path = root / "output.mp4"
    decision = backends.BackendDecision(
        backend_name=backends.MLT_BACKEND_NAME,
        backend_family=backends.MLT_BACKEND_FAMILY,
        backend_mode=backends.BACKEND_MODE_FINAL_RENDER,
        reason=backends.MLT_BACKEND_REASON_SELECTED,
        fallback_chain=[
            backends.MLT_BACKEND_NAME,
            backends.FFMPEG_STABLE_BACKEND_NAME,
            backends.LEGACY_MOVIEPY_BACKEND_NAME,
        ],
        capability_flags=list(backends.MLT_BACKEND_CAPABILITY_FLAGS),
    )
    plan = {
        "render_settings": {"fps": 12, "aspect_ratio": "16:9"},
        "segments": [
            {
                "segment_id": "seg_001",
                "type": "image",
                "source_path": str(source_path.resolve()),
                "duration": 2.0,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
            }
        ],
    }

    original_probe = mlt_backend_module.probe_mlt_runtime
    original_run_consumer = mlt_backend_module._run_mlt_consumer
    original_validate = engine._v56_validate_video
    original_atomic_replace = engine._v56_atomic_replace

    mlt_backend_module.probe_mlt_runtime = lambda *args, **kwargs: backends.MltProbeResult(
        available=True,
        executable="melt",
        version="7.0.0",
        reason="mlt_backend_runtime_available",
    )

    def fake_run_consumer(command, *, working_dir, log_path):
        tmp_output = Path(str(command[3]).split("avformat:", 1)[1])
        tmp_output.write_bytes(b"fake-mp4")
        log_path.write_text("fake melt render", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    mlt_backend_module._run_mlt_consumer = fake_run_consumer
    engine._v56_validate_video = lambda path, min_size=1024: (Path(path).exists(), "", 2.0)
    engine._v56_atomic_replace = lambda tmp_path, final_path: Path(tmp_path).replace(final_path)

    try:
        execution = backends.run_mlt_backend(
            engine=engine,
            decision=decision,
            plan=plan,
            output=str(output_path.resolve()),
            params={"engine": "mlt_experimental"},
        )
    finally:
        mlt_backend_module.probe_mlt_runtime = original_probe
        mlt_backend_module._run_mlt_consumer = original_run_consumer
        engine._v56_validate_video = original_validate
        engine._v56_atomic_replace = original_atomic_replace

    assert execution.actual_backend_name == backends.MLT_BACKEND_NAME
    assert output_path.exists()
    assert (root / ".video_create_project" / "mlt" / "project.mlt").exists()
    assert (root / ".video_create_project" / "mlt" / "render.log").exists()


def test_run_mlt_backend_scaffold_error_class_still_carries_reason() -> None:
    exc = backends.MltBackendScaffoldError()
    assert exc.reason == backends.MLT_BACKEND_REASON_SCAFFOLD_ONLY
    assert exc.backend_name == backends.MLT_BACKEND_NAME


def test_v56_render_backend_dispatch_routes_mlt_backend_decision() -> None:
    decision = backends.BackendDecision(
        backend_name=backends.MLT_BACKEND_NAME,
        backend_family=backends.MLT_BACKEND_FAMILY,
        backend_mode=backends.BACKEND_MODE_FINAL_RENDER,
        reason=backends.MLT_BACKEND_REASON_SELECTED,
        fallback_chain=[
            backends.MLT_BACKEND_NAME,
            backends.FFMPEG_STABLE_BACKEND_NAME,
            backends.LEGACY_MOVIEPY_BACKEND_NAME,
        ],
        capability_flags=list(backends.MLT_BACKEND_CAPABILITY_FLAGS),
    )
    original_probe = mlt_backend_module.probe_mlt_runtime
    mlt_backend_module.probe_mlt_runtime = lambda *args, **kwargs: backends.MltProbeResult(
        available=False,
        reason=backends.MLT_BACKEND_REASON_NOT_INSTALLED,
    )
    original_ffmpeg = render_stable_module.run_ffmpeg_stable_backend

    def fake_ffmpeg_backend(engine_module, selected_decision, plan, output, params, plan_path=None):
        _ = (engine_module, plan, output, params, plan_path)
        return backends.BackendExecutionResult.from_decision(
            selected_decision,
            actual_backend_name=backends.FFMPEG_STABLE_BACKEND_NAME,
        )

    render_stable_module.run_ffmpeg_stable_backend = fake_ffmpeg_backend
    try:
        execution = engine._v56_run_render_backend(
            decision,
            {"segments": []},
            "tests/tmp_vcs_mlt_scaffold/output.mp4",
            {"engine": "mlt_experimental"},
        )
    finally:
        render_stable_module.run_ffmpeg_stable_backend = original_ffmpeg
        mlt_backend_module.probe_mlt_runtime = original_probe

    assert execution.selected_backend_name == backends.MLT_BACKEND_NAME
    assert execution.actual_backend_name == backends.FFMPEG_STABLE_BACKEND_NAME
    assert execution.fallback_used == backends.FFMPEG_STABLE_BACKEND_NAME
    assert execution.fallback_reason == backends.MLT_BACKEND_REASON_NOT_INSTALLED
    assert execution.fallback_applied is True


def test_v56_render_backend_dispatch_routes_mlt_backend_decision_direct() -> None:
    decision = backends.BackendDecision(
        backend_name=backends.MLT_BACKEND_NAME,
        backend_family=backends.MLT_BACKEND_FAMILY,
        backend_mode=backends.BACKEND_MODE_FINAL_RENDER,
        reason=backends.MLT_BACKEND_REASON_SELECTED,
        fallback_chain=[
            backends.MLT_BACKEND_NAME,
            backends.FFMPEG_STABLE_BACKEND_NAME,
            backends.LEGACY_MOVIEPY_BACKEND_NAME,
        ],
        capability_flags=list(backends.MLT_BACKEND_CAPABILITY_FLAGS),
    )
    original_probe = mlt_backend_module.probe_mlt_runtime
    mlt_backend_module.probe_mlt_runtime = lambda *args, **kwargs: backends.MltProbeResult(
        available=False,
        reason=backends.MLT_BACKEND_REASON_NOT_INSTALLED,
    )
    original_ffmpeg = render_stable_module.run_ffmpeg_stable_backend
    original_legacy = render_stable_module.run_legacy_moviepy_backend

    def fail_ffmpeg(*args, **kwargs):
        raise RuntimeError("forced ffmpeg fallback failure")

    def fake_legacy_backend(engine_module, selected_decision, plan, output, params):
        _ = (engine_module, plan, output, params)
        return backends.BackendExecutionResult.from_decision(
            selected_decision,
            actual_backend_name=backends.LEGACY_MOVIEPY_BACKEND_NAME,
        )

    render_stable_module.run_ffmpeg_stable_backend = fail_ffmpeg
    render_stable_module.run_legacy_moviepy_backend = fake_legacy_backend
    try:
        execution = engine._v56_run_render_backend(
            decision,
            {"segments": []},
            "tests/tmp_vcs_mlt_scaffold/output.mp4",
            {"engine": "mlt_experimental"},
        )
    finally:
        render_stable_module.run_ffmpeg_stable_backend = original_ffmpeg
        render_stable_module.run_legacy_moviepy_backend = original_legacy
        mlt_backend_module.probe_mlt_runtime = original_probe

    assert execution.actual_backend_name == backends.LEGACY_MOVIEPY_BACKEND_NAME
    assert execution.fallback_used == backends.LEGACY_MOVIEPY_BACKEND_NAME
    assert execution.fallback_reason == (
        f"{backends.MLT_BACKEND_REASON_NOT_INSTALLED}+forced ffmpeg fallback failure"
    )


def test_v56_render_backend_dispatch_routes_mlt_backend_selected_branch() -> None:
    decision = backends.BackendDecision(
        backend_name=backends.MLT_BACKEND_NAME,
        backend_family=backends.MLT_BACKEND_FAMILY,
        backend_mode=backends.BACKEND_MODE_FINAL_RENDER,
        reason=backends.MLT_BACKEND_REASON_SELECTED,
        fallback_chain=[
            backends.MLT_BACKEND_NAME,
            backends.FFMPEG_STABLE_BACKEND_NAME,
            backends.LEGACY_MOVIEPY_BACKEND_NAME,
        ],
        capability_flags=list(backends.MLT_BACKEND_CAPABILITY_FLAGS),
    )
    original_run_mlt = render_stable_module.run_mlt_backend

    def fake_mlt_backend(engine_module, selected_decision, plan, output, params, plan_path=None):
        _ = (engine_module, plan, output, params, plan_path)
        return backends.BackendExecutionResult.from_decision(
            selected_decision,
            actual_backend_name=backends.MLT_BACKEND_NAME,
        )

    render_stable_module.run_mlt_backend = fake_mlt_backend
    try:
        execution = engine._v56_run_render_backend(
            decision,
            {"segments": []},
            "tests/tmp_vcs_mlt_scaffold/output.mp4",
            {"engine": "mlt_experimental"},
        )
    finally:
        render_stable_module.run_mlt_backend = original_run_mlt

    assert execution.actual_backend_name == backends.MLT_BACKEND_NAME
    assert execution.fallback_used is None
    assert execution.fallback_applied is False


if __name__ == "__main__":
    test_merge_backend_reason_tags_deduplicates_and_preserves_order()
    test_probe_mlt_runtime_reports_missing_runtime_cleanly()
    test_collect_mlt_rejection_reasons_requires_experimental_gate()
    test_should_use_mlt_backend_accepts_supported_plan_when_runtime_is_available()
    test_resolve_render_backend_selects_mlt_when_probe_and_plan_are_supported()
    test_run_mlt_backend_requires_runtime_when_probe_is_missing()
    test_run_mlt_backend_builds_project_and_validates_output()
    test_run_mlt_backend_scaffold_error_class_still_carries_reason()
    test_v56_render_backend_dispatch_routes_mlt_backend_decision()
    test_v56_render_backend_dispatch_routes_mlt_backend_decision_direct()
    test_v56_render_backend_dispatch_routes_mlt_backend_selected_branch()
