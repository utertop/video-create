import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def _make_image(path: Path, size=(1280, 720), color=(120, 160, 200)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", size, color)
    img.save(path, quality=90)


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def test_scan_outputs_content_profile() -> None:
    root = Path("d:/Automatic/video_create/tests/mock_template_scan_project")
    _reset_dir(root)
    _make_image(root / "旅行相册" / "img1.jpg", size=(1600, 900))
    _make_image(root / "旅行相册" / "img2.jpg", size=(900, 1600))
    _make_image(root / "旅行相册" / "img3.jpg", size=(1080, 1080))

    library = engine.Scanner(str(root)).scan()
    profile = ((library.get("summary") or {}).get("content_profile") or {})

    assert profile.get("visual_asset_count") == 3
    assert profile.get("image_count") == 3
    assert profile.get("video_count") == 0
    assert profile.get("dominant_media_type") == "image"
    assert profile.get("landscape_ratio", 0) > 0
    assert profile.get("portrait_ratio", 0) > 0
    assert profile.get("square_ratio", 0) > 0


def test_planner_recommends_template_and_supports_manual_override() -> None:
    library = {
        "project": {
            "source_root": "D:/mock/travel_project",
            "project_title": "杭州旅行",
        },
        "directory_nodes": [
            {
                "node_id": "dir_root",
                "name": "travel_project",
                "relative_path": "",
                "depth": 0,
                "parent_id": None,
                "detected_type": "project_root",
                "confidence": 1.0,
                "reason": "root",
                "display_title": "travel_project",
                "signals": {},
                "children": ["dir_city"],
                "title_style": None,
            },
            {
                "node_id": "dir_city",
                "name": "杭州",
                "relative_path": "杭州",
                "depth": 1,
                "parent_id": "dir_root",
                "detected_type": "city",
                "confidence": 0.95,
                "reason": "city",
                "display_title": "杭州",
                "signals": {"matched_theme_keywords": ["旅行", "风景"]},
                "children": ["dir_date"],
                "title_style": None,
            },
            {
                "node_id": "dir_date",
                "name": "2025-05-01",
                "relative_path": "杭州/2025-05-01",
                "depth": 2,
                "parent_id": "dir_city",
                "detected_type": "date",
                "confidence": 0.94,
                "reason": "date",
                "display_title": "2025-05-01",
                "signals": {},
                "children": ["dir_spot"],
                "title_style": None,
            },
            {
                "node_id": "dir_spot",
                "name": "西湖",
                "relative_path": "杭州/2025-05-01/西湖",
                "depth": 3,
                "parent_id": "dir_date",
                "detected_type": "scenic_spot",
                "confidence": 0.93,
                "reason": "spot",
                "display_title": "西湖",
                "signals": {"matched_theme_keywords": ["旅行", "风景", "大海"]},
                "children": [],
                "title_style": None,
            },
        ],
        "assets": [
            {
                "asset_id": "asset_1",
                "type": "image",
                "relative_path": "杭州/2025-05-01/西湖/1.jpg",
                "absolute_path": "D:/mock/travel_project/杭州/2025-05-01/西湖/1.jpg",
                "thumbnail_path": None,
                "file": {"name": "1.jpg", "extension": ".jpg", "size_bytes": 1024, "modified_time": "2025-05-01T10:00:00", "content_hash": "a"},
                "media": {"width": 1600, "height": 900},
                "classification": {"directory_node_id": "dir_spot"},
                "status": "ready",
            },
            {
                "asset_id": "asset_2",
                "type": "image",
                "relative_path": "杭州/2025-05-01/西湖/2.jpg",
                "absolute_path": "D:/mock/travel_project/杭州/2025-05-01/西湖/2.jpg",
                "thumbnail_path": None,
                "file": {"name": "2.jpg", "extension": ".jpg", "size_bytes": 1024, "modified_time": "2025-05-01T10:00:01", "content_hash": "b"},
                "media": {"width": 1600, "height": 900},
                "classification": {"directory_node_id": "dir_spot"},
                "status": "ready",
            },
        ],
        "summary": {
            "total_assets": 2,
            "image_count": 2,
            "video_count": 0,
            "audio_count": 0,
            "skipped_count": 0,
            "error_count": 0,
            "content_profile": {
                "visual_asset_count": 2,
                "image_count": 2,
                "video_count": 0,
                "audio_count": 0,
                "image_ratio": 1.0,
                "video_ratio": 0.0,
                "portrait_ratio": 0.0,
                "landscape_ratio": 1.0,
                "square_ratio": 0.0,
                "dominant_media_type": "image",
                "mixed_media": False,
                "total_video_duration_seconds": 0.0,
                "avg_video_duration_seconds": 0.0,
                "top_level_section_count": 1,
                "chapter_node_count": 0,
                "city_node_count": 1,
                "date_node_count": 1,
                "scenic_spot_node_count": 1,
                "top_keywords": [{"keyword": "旅行", "count": 4}, {"keyword": "风景", "count": 4}],
            },
        },
    }

    planner = engine.Planner(library)
    blueprint = planner.plan(template_mode="auto")
    template_matching = (blueprint.get("metadata") or {}).get("template_matching") or {}

    assert template_matching.get("selected_template_id") == "travel_postcard"
    assert template_matching.get("selected_source") == "auto"
    assert blueprint["metadata"]["edit_strategy"] == "travel_soft"
    assert blueprint["metadata"]["performance_mode"] == "balanced"
    assert blueprint["metadata"]["image_motion_profile"] == "travel_gentle"
    assert blueprint["metadata"]["title_style"]["preset"] == "travel_postcard"
    assert blueprint["metadata"]["overlay_title_style"]["motion"] == "postcard_drift"
    assert template_matching.get("recommendations")
    assert template_matching["recommendations"][0]["template_id"] == "travel_postcard"
    first_section = blueprint["sections"][0]
    assert first_section["title_style"]["motion"] == "postcard_drift"

    manual_blueprint = planner.plan(template_mode="daily_vlog")
    manual_template_matching = (manual_blueprint.get("metadata") or {}).get("template_matching") or {}
    assert manual_template_matching.get("selected_template_id") == "daily_vlog"
    assert manual_template_matching.get("selected_source") == "manual"
    assert manual_blueprint["metadata"]["image_motion_profile"] == "casual_story"


if __name__ == "__main__":
    try:
        test_scan_outputs_content_profile()
        test_planner_recommends_template_and_supports_manual_override()
        print("V5 template matching smoke test passed")
    except Exception as exc:
        print(f"V5 template matching smoke test failed: {exc}")
        raise
