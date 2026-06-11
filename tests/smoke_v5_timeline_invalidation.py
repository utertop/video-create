import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_engine.timeline import (
    TIMELINE_INVALIDATION_RULES_VERSION,
    build_timeline_document,
    resolve_timeline_recompute_scope,
)


def _sample_clip(kind: str = "title_card", track_id: str = "track_title_main") -> dict:
    return {
        "clip_id": f"clip_{kind}_001",
        "kind": kind,
        "track_id": track_id,
        "timeline_start": 0.0,
        "timeline_duration": 2.0,
        "timeline_end": 2.0,
        "enabled": True,
    }


def test_title_edits_are_clip_scoped() -> None:
    clip = _sample_clip()
    for operation_type in ["title_text_change", "title_style_change", "subtitle_text_change"]:
        hint = resolve_timeline_recompute_scope({"type": operation_type}, clip=clip)
        assert hint["primary_scope"] == "clip_only"
        assert hint["affected_clip_ids"] == [clip["clip_id"]]
        assert hint["affected_track_ids"] == [clip["track_id"]]
        assert hint["requires_render_plan_recompile"] is True
        assert hint["requires_audio_relayout"] is False


def test_visual_timeline_structure_edits_require_compile_not_full_rebuild() -> None:
    clip = _sample_clip("image_asset", "track_video_main")
    for operation_type in ["clip_enable_toggle", "clip_reorder", "image_duration_change"]:
        hint = resolve_timeline_recompute_scope({"type": operation_type}, clip=clip)
        assert hint["primary_scope"] == "timeline_compile"
        assert hint["affected_clip_ids"] == [clip["clip_id"]]
        assert hint["affected_track_ids"] == [clip["track_id"]]
        assert hint["requires_render_plan_recompile"] is True
        assert hint["requires_audio_relayout"] is False


def test_audio_edits_do_not_dirty_visual_tracks() -> None:
    clip = _sample_clip("audio_bgm", "track_audio_main")

    volume_hint = resolve_timeline_recompute_scope({"type": "bgm_volume_change"}, clip=clip)
    assert volume_hint["primary_scope"] == "track_only"
    assert volume_hint["affected_track_ids"] == ["track_audio_main"]
    assert volume_hint["affected_clip_ids"] == [clip["clip_id"]]
    assert volume_hint["requires_render_plan_recompile"] is False
    assert volume_hint["requires_audio_relayout"] is False

    cue_hint = resolve_timeline_recompute_scope({"type": "bgm_cue_range_change"}, clip=clip)
    assert cue_hint["primary_scope"] == "track_only"
    assert cue_hint["affected_track_ids"] == ["track_audio_main"]
    assert cue_hint["requires_render_plan_recompile"] is False
    assert cue_hint["requires_audio_relayout"] is True


def test_quality_and_aspect_ratio_scopes_are_explicit() -> None:
    preview_hint = resolve_timeline_recompute_scope({"type": "preview_quality_change"})
    assert preview_hint["primary_scope"] == "preview_only"
    assert preview_hint["requires_render_plan_recompile"] is False

    final_hint = resolve_timeline_recompute_scope({"type": "final_quality_change"})
    assert final_hint["primary_scope"] == "final_render_only"
    assert final_hint["requires_render_plan_recompile"] is False

    aspect_hint = resolve_timeline_recompute_scope({"type": "aspect_ratio_change"})
    assert aspect_hint["primary_scope"] == "full_rebuild"
    assert aspect_hint["requires_render_plan_recompile"] is True
    assert aspect_hint["requires_audio_relayout"] is False


def test_generated_timeline_exposes_rules_version() -> None:
    timeline = build_timeline_document(
        {"title": "Invalidation Smoke"},
        {
            "render_settings": {"fps": 12, "aspect_ratio": "16:9"},
            "segments": [
                {
                    "segment_id": "seg_title",
                    "type": "title",
                    "text": "Opening",
                    "subtitle": "Smoke",
                    "duration": 2.0,
                    "start_time": 0.0,
                    "end_time": 2.0,
                }
            ],
        },
    )
    assert timeline["invalidation_rules_version"] == TIMELINE_INVALIDATION_RULES_VERSION
    clip = next(iter(timeline["clip_index"].values()))
    assert clip["invalidation_hint"]["primary_scope"] == "clip_only"


if __name__ == "__main__":
    test_title_edits_are_clip_scoped()
    test_visual_timeline_structure_edits_require_compile_not_full_rebuild()
    test_audio_edits_do_not_dirty_visual_tracks()
    test_quality_and_aspect_ratio_scopes_are_explicit()
    test_generated_timeline_exposes_rules_version()
    print("V5 timeline invalidation smoke test passed")
