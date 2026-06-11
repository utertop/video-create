from __future__ import annotations

from typing import Any, Dict


def make_minimal_timeline() -> Dict[str, Any]:
    return {
        "schema_version": "5.5",
        "document_type": "timeline",
        "timeline_version": "v1",
        "project_ref": {
            "project_id": "project_demo",
            "project_dir": "D:/demo/.video_create_project",
            "title": "Timeline Demo",
        },
        "source_ref": {
            "media_library_path": "media_library.json",
            "story_blueprint_path": "story_blueprint.json",
            "render_plan_path": "render_plan.json",
            "generated_from_blueprint": True,
            "generated_at": "2026-06-11T00:00:00Z",
        },
        "tracks": [
            {
                "track_id": "track_video_main",
                "kind": "video",
                "name": "Main Video",
                "order_index": 0,
                "enabled": True,
                "lane_mode": "single",
                "clip_ids": ["clip_image_demo"],
            },
            {
                "track_id": "track_title_main",
                "kind": "title",
                "name": "Titles",
                "order_index": 1,
                "enabled": True,
                "clip_ids": ["clip_title_demo"],
            },
            {
                "track_id": "track_audio_main",
                "kind": "audio",
                "name": "Audio",
                "order_index": 2,
                "enabled": True,
                "clip_ids": ["clip_bgm_demo"],
            },
        ],
        "clip_index": {
            "clip_image_demo": {
                "clip_id": "clip_image_demo",
                "kind": "image_asset",
                "track_id": "track_video_main",
                "timeline_start": 0.0,
                "timeline_duration": 4.0,
                "timeline_end": 4.0,
                "source_in": None,
                "source_out": None,
                "playback_rate": 1.0,
                "enabled": True,
                "source_ref": {
                    "section_id": "section_demo",
                    "asset_id": "asset_image_demo",
                    "segment_id": "seg_image_demo",
                },
                "edit_state": {
                    "auto_generated": True,
                    "user_overridden": False,
                    "origin": "plan",
                },
                "invalidation_hint": {
                    "primary_scope": "clip_only",
                    "affected_clip_ids": ["clip_image_demo"],
                    "cache_reuse_expected": True,
                    "requires_render_plan_recompile": False,
                    "reason": "initial_schema_smoke",
                },
            },
            "clip_title_demo": {
                "clip_id": "clip_title_demo",
                "kind": "title_card",
                "track_id": "track_title_main",
                "timeline_start": 0.0,
                "timeline_duration": 2.0,
                "timeline_end": 2.0,
                "enabled": True,
                "content_ref": {
                    "title_text": "Timeline Demo",
                    "subtitle_text": "Schema Smoke",
                },
            },
            "clip_bgm_demo": {
                "clip_id": "clip_bgm_demo",
                "kind": "audio_bgm",
                "track_id": "track_audio_main",
                "timeline_start": 0.0,
                "timeline_duration": 4.0,
                "timeline_end": 4.0,
                "enabled": True,
                "content_ref": {
                    "source_path": "D:/demo/music.mp3",
                    "audio_profile": "soft_travel",
                },
            },
        },
        "dependency_graph": [
            {
                "dependency_id": "dep_title_section_demo",
                "from_clip_id": "clip_title_demo",
                "to_clip_id": "clip_image_demo",
                "kind": "derived_from_section",
                "source_section_id": "section_demo",
                "strict": False,
                "reason": "title belongs to source section",
            }
        ],
        "invalidation_rules_version": "timeline_invalidation_v1",
        "performance_policy": {
            "preview": {
                "mode": "proxy",
                "height": 540,
                "fps": 15,
                "cache_namespace": "preview",
                "preferred_backend": "legacy_moviepy_backend",
            },
            "final": {
                "uses_original_source": True,
                "allow_proxy": False,
                "cache_namespace": "final",
                "preferred_backend": "ffmpeg_stable_backend",
            },
            "thumbnail": {"cache_namespace": "thumbnail"},
            "proxy": {"cache_namespace": "proxy"},
            "cache_fingerprint_version": "timeline_cache_v1",
        },
        "metadata": {
            "created_at": "2026-06-11T00:00:00Z",
            "generated_from": "blueprint",
            "editor_mode": "auto",
            "migration_notes": [],
        },
    }


def assert_timeline_schema(doc: Dict[str, Any]) -> None:
    assert doc["document_type"] == "timeline"
    assert doc["schema_version"] == "5.5"
    assert doc["timeline_version"] == "v1"

    tracks = doc["tracks"]
    assert {track["kind"] for track in tracks} >= {"video", "audio", "title"}

    clip_index = doc["clip_index"]
    assert clip_index
    track_ids = {track["track_id"] for track in tracks}

    for track in tracks:
        assert isinstance(track["clip_ids"], list)
        for clip_id in track["clip_ids"]:
            assert clip_id in clip_index

    for clip_id, clip in clip_index.items():
        assert clip["clip_id"] == clip_id
        assert clip["track_id"] in track_ids
        assert isinstance(clip["enabled"], bool)
        assert clip["timeline_start"] >= 0
        assert clip["timeline_duration"] >= 0
        assert round(clip["timeline_start"] + clip["timeline_duration"], 6) == round(clip["timeline_end"], 6)
        assert "source_in" in clip or clip["kind"] in {"title_card", "audio_bgm", "audio_source", "audio_effect"}
        assert "source_out" in clip or clip["kind"] in {"title_card", "audio_bgm", "audio_source", "audio_effect"}

    policy = doc["performance_policy"]
    assert policy["preview"]["cache_namespace"] == "preview"
    assert policy["final"]["cache_namespace"] == "final"
    assert policy["final"]["uses_original_source"] is True
    assert policy["final"]["allow_proxy"] is False
    assert policy["thumbnail"]["cache_namespace"] == "thumbnail"
    assert policy["proxy"]["cache_namespace"] == "proxy"

    scopes = {
        "none",
        "preview_only",
        "clip_only",
        "track_only",
        "timeline_compile",
        "final_render_only",
        "full_rebuild",
    }
    for clip in clip_index.values():
        hint = clip.get("invalidation_hint")
        if hint:
            assert hint["primary_scope"] in scopes


def test_minimal_timeline_schema() -> None:
    assert_timeline_schema(make_minimal_timeline())


if __name__ == "__main__":
    test_minimal_timeline_schema()
    print("V5 timeline schema smoke test passed")
