from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_engine.render_cache import _v56_write_build_report


def main() -> None:
    with TemporaryDirectory() as tmp:
        report_path = Path(tmp) / "project" / "build_report.json"
        _v56_write_build_report(report_path, {
            "engine_version": "test",
            "status": "done",
            "render_mode": "v5.6_long_video_stable",
            "render_intent": "final",
            "selected_backend": "auto",
            "actual_backend": "ffmpeg",
            "backend": {
                "selected_backend": "auto",
                "actual_backend_name": "ffmpeg",
                "reason": "test-route",
                "fallback_chain": ["moviepy", "ffmpeg"],
                "fallback_used": "ffmpeg",
                "fallback_reason": "moviepy_failed",
                "fallback_applied": True,
            },
            "metadata": {
                "generated_from": "timeline",
                "timeline_source_path": "timeline.json",
                "source_render_plan_path": "render_plan.base.json",
                "recompute_summary": {
                    "enabled_clip_count": 3,
                    "disabled_clip_count": 1,
                    "edited_clip_count": 2,
                    "requires_full_rebuild": False,
                },
            },
            "cache_policy": {
                "render_intent": "final",
                "cache_namespace": "final",
                "uses_original_source": True,
                "allow_proxy": False,
                "proxy_allowed_for_final": False,
                "quality": "high",
                "fps": 30,
            },
            "render_scheduler": {
                "total_segments": 3,
                "route_counts": {"photo_prerender": 2, "moviepy_segment": 1},
            },
            "chunk_scheduler": {
                "total_chunks": 2,
                "route_counts": {"ffmpeg_direct_chunk": 1, "moviepy_chunk": 1},
            },
            "segment_routes": [
                {"segment_id": "seg_1", "route": "photo_prerender"},
                {"segment_id": "seg_2", "route": "moviepy_segment"},
            ],
            "chunk_routes": [
                {"name": "chunk_000.mp4", "route": "ffmpeg_direct_chunk"},
                {"name": "chunk_001.mp4", "route": "moviepy_chunk"},
            ],
            "photo_segment_cache": {"eligible": 2, "hit": 1, "created": 1},
            "video_segment_cache": {"eligible": 1, "hit": 0, "created": 1},
            "proxy_media": {"eligible": 0, "hit": 0, "created": 0},
            "timings": {
                "total_render_seconds": 4.2,
                "chunk_render_seconds": 2.0,
                "concat_seconds": 0.5,
            },
            "recovery": {
                "resumable": True,
                "resumed_from_manifest": True,
                "reused_chunk_count": 1,
                "completed_chunk_count": 2,
                "failed_chunk_count": 0,
                "reported_chunk_count": 2,
            },
            "diagnostics": {
                "observability": {
                    "cache_efficiency": {
                        "photo_segment_cache": {
                            "eligible": 2,
                            "hit_count": 1,
                            "created_count": 1,
                            "hit_rate": 0.5,
                        }
                    },
                    "fast_path_coverage": {
                        "segments": {"fast_path_rate": 0.5},
                        "chunks": {"fast_path_rate": 0.5},
                    },
                    "route_differences": {
                        "segments": {"changed_count": 1, "changed_rate": 0.5},
                    },
                    "timing_highlights": {
                        "total_render_seconds": 4.2,
                        "top_steps": [{"name": "chunk_render_seconds", "seconds": 2.0}],
                    },
                },
                "slow_path_report": {
                    "recommendations": [
                        {
                            "id": "reduce_segment_moviepy_routes",
                            "priority": "high",
                            "message": "Reduce MoviePy segment routes.",
                        }
                    ]
                },
            },
            "created_at": "2026-06-11T00:00:00",
        })

        loaded = json.loads(report_path.read_text(encoding="utf-8"))

    assert loaded["status"] == "done"
    assert loaded["build_report_version"] == "v2"
    for key in [
        "timeline_summary",
        "route_summary",
        "fallback_summary",
        "cache_summary",
        "recompute_summary",
        "performance_summary",
        "quality_summary",
        "recovery_summary",
        "migration_notes",
    ]:
        assert key in loaded, key

    assert loaded["timeline_summary"]["compiled_from_timeline"] is True
    assert loaded["timeline_summary"]["timeline_source_path"] == "timeline.json"
    assert loaded["fallback_summary"]["applied"] is True
    assert loaded["cache_summary"]["policy"]["cache_namespace"] == "final"
    assert loaded["recompute_summary"]["enabled_clip_count"] == 3
    assert loaded["quality_summary"]["uses_original_source"] is True
    assert loaded["quality_summary"]["allow_proxy"] is False
    assert loaded["quality_summary"]["final_original_source_guard"] is True
    assert loaded["route_summary"]["segment_route_difference_count"] == 1
    assert loaded["performance_summary"]["elapsed_seconds"] == 4.2
    assert loaded["recovery_summary"]["resumable"] is True
    assert loaded["report_suggestions"]


if __name__ == "__main__":
    main()
