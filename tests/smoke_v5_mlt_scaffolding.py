import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import render_backends as backends


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


def test_run_mlt_backend_scaffold_fails_explicitly() -> None:
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

    try:
        backends.run_mlt_backend(
            engine=None,
            decision=decision,
            plan={"segments": []},
            output="tests/tmp_vcs_mlt_scaffold/output.mp4",
            params={},
        )
        raise AssertionError("expected scaffold backend to raise")
    except backends.MltBackendScaffoldError as exc:
        assert exc.reason == backends.MLT_BACKEND_REASON_SCAFFOLD_ONLY
        assert exc.backend_name == backends.MLT_BACKEND_NAME


if __name__ == "__main__":
    test_merge_backend_reason_tags_deduplicates_and_preserves_order()
    test_probe_mlt_runtime_reports_missing_runtime_cleanly()
    test_run_mlt_backend_scaffold_fails_explicitly()
