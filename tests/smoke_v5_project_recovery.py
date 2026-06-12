from __future__ import annotations

import json
import shutil
import sys
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine
from video_engine.timeline import recover_timeline_document


def render_plan() -> Dict[str, Any]:
    return {
        "schema_version": "5.5",
        "document_type": "render_plan",
        "segments": [
            {
                "segment_id": "seg_title",
                "type": "title",
                "section_id": "section_1",
                "start_time": 0.0,
                "duration": 2.0,
                "end_time": 2.0,
                "title_text": "Recovered",
            },
            {
                "segment_id": "seg_image",
                "type": "image",
                "section_id": "section_1",
                "asset_id": "asset_image_1",
                "source_path": "D:/mock/image.jpg",
                "start_time": 2.0,
                "duration": 3.0,
                "end_time": 5.0,
            },
        ],
        "render_settings": {},
    }


def blueprint() -> Dict[str, Any]:
    return {
        "schema_version": "5.5",
        "document_type": "story_blueprint",
        "title": "Recovered Project",
        "subtitle": "",
        "metadata": {},
        "sections": [
            {
                "section_id": "section_1",
                "section_type": "chapter",
                "title": "Chapter",
                "enabled": True,
                "asset_refs": [{"asset_id": "asset_image_1", "enabled": True}],
                "children": [],
            }
        ],
    }


def library() -> Dict[str, Any]:
    return {
        "schema_version": "5.5",
        "document_type": "media_library",
        "assets": [
            {
                "asset_id": "asset_image_1",
                "type": "image",
                "status": "ready",
                "absolute_path": "D:/mock/image.jpg",
                "relative_path": "image.jpg",
                "media": {"orientation": "landscape"},
            }
        ],
    }


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_recover_timeline_document_uses_migrated_existing_identity() -> None:
    existing = {
        "schema_version": "5.4",
        "document_type": "timeline",
        "timeline_version": "v0",
        "tracks": [],
        "clip_index": {
            "clip_preserved": {
                "clip_id": "clip_preserved",
                "kind": "image_asset",
                "source_ref": {
                    "segment_id": "seg_image",
                    "section_id": "section_1",
                    "asset_id": "asset_image_1",
                    "source_path": "D:/mock/image.jpg",
                },
                "content_ref": {
                    "source_path": "D:/mock/image.jpg",
                },
            }
        },
    }
    timeline, notes = recover_timeline_document(
        blueprint(),
        render_plan(),
        media_library=library(),
        existing_timeline=existing,
        render_plan_path="render_plan.json",
        project_dir="D:/mock/project",
    )

    assert timeline["document_type"] == "timeline"
    assert timeline["timeline_version"] == "v1"
    assert "clip_preserved" in timeline["clip_index"], "existing clip identity should survive migration"
    assert notes
    assert timeline["metadata"]["recovered"] is True


def test_timeline_generate_ignores_broken_existing_timeline_file() -> None:
    root = Path("tests/tmp_vcs_project_recovery")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    plan_path = root / "render_plan.json"
    blueprint_path = root / "story_blueprint.json"
    library_path = root / "media_library.json"
    broken_timeline_path = root / "timeline.json"
    output_path = root / "timeline_recovered.json"

    write_json(plan_path, render_plan())
    write_json(blueprint_path, blueprint())
    write_json(library_path, library())
    broken_timeline_path.write_text("{ broken timeline json", encoding="utf-8")

    engine.command_timeline_generate(
        Namespace(
            render_plan=str(plan_path),
            blueprint=str(blueprint_path),
            library=str(library_path),
            output=str(output_path),
            existing_timeline=str(broken_timeline_path),
            project_dir=str(root),
        )
    )

    assert broken_timeline_path.read_text(encoding="utf-8") == "{ broken timeline json"
    recovered = json.loads(output_path.read_text(encoding="utf-8"))
    assert recovered["document_type"] == "timeline"
    assert recovered["timeline_version"] == "v1"
    assert recovered["metadata"]["generated_from"] == "blueprint"
    assert recovered["performance_policy"]["final"]["allow_proxy"] is False


if __name__ == "__main__":
    test_recover_timeline_document_uses_migrated_existing_identity()
    test_timeline_generate_ignores_broken_existing_timeline_file()
    print("V5 project recovery smoke test passed")
