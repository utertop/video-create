from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from video_engine.timeline import migrate_timeline_document


def old_timeline() -> Dict[str, Any]:
    return {
        "schema_version": "5.4",
        "document_type": "timeline",
        "timeline_version": "v0",
        "tracks": [],
        "clip_index": {},
    }


def test_timeline_schema_and_version_migration() -> None:
    original = old_timeline()
    before = copy.deepcopy(original)

    migrated, result, notes = migrate_timeline_document(original)

    assert original == before, "migration must not mutate caller-owned input"
    assert migrated is True
    assert result["schema_version"] == "5.5"
    assert result["timeline_version"] == "v1"
    assert result["document_type"] == "timeline"
    assert isinstance(result["project_ref"], dict)
    assert isinstance(result["source_ref"], dict)
    assert isinstance(result["dependency_graph"], list)
    assert result["performance_policy"]["preview"]["cache_namespace"] == "preview"
    assert result["performance_policy"]["final"]["uses_original_source"] is True
    assert result["performance_policy"]["final"]["allow_proxy"] is False
    assert result["invalidation_rules_version"] == "timeline_invalidation_v1"
    assert notes
    assert any("timeline_version" in note for note in notes)
    assert result["metadata"]["migration_notes"]


def test_timeline_type_mismatch_is_rejected() -> None:
    try:
        migrate_timeline_document({"schema_version": "5.5", "document_type": "render_plan"})
    except ValueError as exc:
        assert "document_type mismatch" in str(exc)
    else:
        raise AssertionError("timeline migration should reject mismatched document_type")


if __name__ == "__main__":
    test_timeline_schema_and_version_migration()
    test_timeline_type_mismatch_is_rejected()
    print("V5 schema migration smoke test passed")
