import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_engine.timeline import (
    move_clip,
    update_bgm_cue_volume,
    update_clip_content,
    update_clip_duration,
    update_clip_enabled,
    update_clip_presentation,
)


def _timeline() -> dict:
    return {
        "schema_version": "5.5",
        "document_type": "timeline",
        "timeline_version": "v1",
        "project_ref": {},
        "source_ref": {"generated_from_blueprint": True},
        "tracks": [
            {
                "track_id": "track_video_main",
                "kind": "video",
                "name": "Main Video",
                "order_index": 0,
                "enabled": True,
                "clip_ids": ["clip_img_1", "clip_img_2", "clip_img_3"],
            },
            {
                "track_id": "track_title_main",
                "kind": "title",
                "name": "Titles",
                "order_index": 1,
                "enabled": True,
                "clip_ids": ["clip_title_1"],
            },
            {
                "track_id": "track_audio_main",
                "kind": "audio",
                "name": "Audio",
                "order_index": 2,
                "enabled": True,
                "clip_ids": ["clip_bgm_1"],
            },
        ],
        "clip_index": {
            "clip_img_1": _clip("clip_img_1", "image_asset", "track_video_main", 0, 2),
            "clip_img_2": _clip("clip_img_2", "image_asset", "track_video_main", 2, 3),
            "clip_img_3": _clip("clip_img_3", "image_asset", "track_video_main", 5, 4),
            "clip_title_1": {
                **_clip("clip_title_1", "title_card", "track_title_main", 0, 2),
                "content_ref": {"title_text": "Old Title", "subtitle_text": "Old Subtitle"},
                "presentation": {"title_style": {"preset": "cinematic_bold", "motion": "fade_only"}},
            },
            "clip_bgm_1": {
                **_clip("clip_bgm_1", "audio_bgm", "track_audio_main", 0, 9),
                "metadata": {"bgm_volume": 0.28},
            },
        },
        "metadata": {"editor_mode": "auto", "dirty": False},
    }


def _clip(clip_id: str, kind: str, track_id: str, start: float, duration: float) -> dict:
    return {
        "clip_id": clip_id,
        "kind": kind,
        "track_id": track_id,
        "timeline_start": start,
        "timeline_duration": duration,
        "timeline_end": start + duration,
        "source_in": 0.0,
        "source_out": duration,
        "playback_rate": 1.0,
        "enabled": True,
        "source_ref": {"section_id": "section_1", "asset_id": clip_id, "segment_id": f"seg_{clip_id}"},
        "content_ref": {"source_path": f"{clip_id}.jpg"},
        "edit_state": {"auto_generated": True, "user_overridden": False, "override_fields": [], "origin": "plan"},
    }


def test_clip_enable_edit_marks_dirty_and_scoped() -> None:
    timeline = update_clip_enabled(_timeline(), "clip_img_1", False)
    clip = timeline["clip_index"]["clip_img_1"]
    assert clip["enabled"] is False
    assert clip["edit_state"]["user_overridden"] is True
    assert "enabled" in clip["edit_state"]["override_fields"]
    assert clip["invalidation_hint"]["primary_scope"] == "timeline_compile"
    assert timeline["metadata"]["dirty"] is True


def test_title_content_and_style_edits_are_clip_scoped() -> None:
    timeline = update_clip_content(_timeline(), "clip_title_1", {"title_text": "New Title"})
    clip = timeline["clip_index"]["clip_title_1"]
    assert clip["content_ref"]["title_text"] == "New Title"
    assert clip["invalidation_hint"]["primary_scope"] == "clip_only"
    assert "content_ref.title_text" in clip["edit_state"]["override_fields"]

    timeline = update_clip_presentation(timeline, "clip_title_1", {"title_style": {"preset": "film_subtitle"}})
    clip = timeline["clip_index"]["clip_title_1"]
    assert clip["presentation"]["title_style"]["preset"] == "film_subtitle"
    assert clip["invalidation_hint"]["primary_scope"] == "clip_only"
    assert "presentation.title_style" in clip["edit_state"]["override_fields"]


def test_duration_edit_shifts_following_clips() -> None:
    timeline = update_clip_duration(_timeline(), "clip_img_1", 4.5)
    assert timeline["clip_index"]["clip_img_1"]["timeline_duration"] == 4.5
    assert timeline["clip_index"]["clip_img_1"]["timeline_end"] == 4.5
    assert timeline["clip_index"]["clip_img_2"]["timeline_start"] == 4.5
    assert timeline["clip_index"]["clip_img_2"]["timeline_end"] == 7.5
    assert timeline["clip_index"]["clip_img_3"]["timeline_start"] == 7.5
    assert timeline["clip_index"]["clip_img_1"]["invalidation_hint"]["primary_scope"] == "timeline_compile"


def test_move_clip_reorders_and_relays_track() -> None:
    timeline = move_clip(_timeline(), "clip_img_3", 0)
    track = next(track for track in timeline["tracks"] if track["track_id"] == "track_video_main")
    assert track["clip_ids"] == ["clip_img_3", "clip_img_1", "clip_img_2"]
    assert timeline["clip_index"]["clip_img_3"]["timeline_start"] == 0
    assert timeline["clip_index"]["clip_img_1"]["timeline_start"] == 4
    assert timeline["clip_index"]["clip_img_2"]["timeline_start"] == 6
    assert timeline["clip_index"]["clip_img_3"]["invalidation_hint"]["primary_scope"] == "timeline_compile"


def test_bgm_volume_edit_stays_audio_scoped() -> None:
    timeline = update_bgm_cue_volume(_timeline(), "clip_bgm_1", 0.42)
    clip = timeline["clip_index"]["clip_bgm_1"]
    assert clip["metadata"]["bgm_volume"] == 0.42
    assert clip["invalidation_hint"]["primary_scope"] == "track_only"
    assert clip["invalidation_hint"]["affected_track_ids"] == ["track_audio_main"]
    assert clip["invalidation_hint"]["requires_audio_relayout"] is False


if __name__ == "__main__":
    test_clip_enable_edit_marks_dirty_and_scoped()
    test_title_content_and_style_edits_are_clip_scoped()
    test_duration_edit_shifts_following_clips()
    test_move_clip_reorders_and_relays_track()
    test_bgm_volume_edit_stays_audio_scoped()
    print("V5 timeline edit ops smoke test passed")
