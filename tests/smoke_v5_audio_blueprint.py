from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def make_image(path: Path, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (960, 540), color)
    image.save(path, quality=92)


def make_audio(path: Path, duration: float, frequency: int = 440) -> None:
    import imageio_ffmpeg

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def build_project(root: Path) -> None:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    make_image(root / "杭州" / "2025-05-01" / "西湖" / "shot1.jpg", (52, 120, 180))
    make_image(root / "杭州" / "2025-05-01" / "西湖" / "shot2.jpg", (70, 140, 190))
    make_image(root / "杭州" / "2025-05-02" / "河坊街" / "shot3.jpg", (120, 90, 60))
    make_audio(root / "travel_bgm_theme.m4a", duration=48.0, frequency=440)
    make_audio(root / "click_sfx.m4a", duration=4.0, frequency=880)


def test_audio_blueprint_recommend_and_apply_modes() -> None:
    root = Path("tests/tmp_vcs_audio_blueprint")
    build_project(root)

    library = engine.Scanner(str(root), recursive=True).scan()

    recommend_blueprint = engine.Planner(library).plan(
        template_mode="auto",
        music_blueprint_mode="recommend",
    )
    audio_blueprint = (recommend_blueprint.get("metadata") or {}).get("audio_blueprint") or {}
    assert audio_blueprint.get("mode") == "recommend"
    assert audio_blueprint.get("template_id") == "travel_postcard"
    assert audio_blueprint.get("music_profile") == "travel_light"
    assert audio_blueprint.get("selected_candidate") is not None
    assert audio_blueprint["selected_candidate"]["relative_path"] == "travel_bgm_theme.m4a"
    assert audio_blueprint.get("recommended_audio_settings", {}).get("music_mode") == "auto"
    assert "audio" not in (recommend_blueprint.get("metadata") or {})

    recommend_plan = engine.Compiler(recommend_blueprint, library).compile()
    compiled_audio_blueprint = (recommend_plan.get("render_settings") or {}).get("audio_blueprint") or {}
    assert compiled_audio_blueprint.get("timeline_cues")
    assert compiled_audio_blueprint.get("recommended_audio_settings", {}).get("music_profile") == "travel_light"
    assert (recommend_plan.get("render_settings") or {}).get("audio") is None

    apply_blueprint = engine.Planner(library).plan(
        template_mode="auto",
        music_blueprint_mode="apply",
    )
    apply_metadata = apply_blueprint.get("metadata") or {}
    assert apply_metadata.get("audio_blueprint", {}).get("mode") == "apply"
    assert apply_metadata.get("audio", {}).get("music_mode") == "auto"

    apply_plan = engine.Compiler(apply_blueprint, library).compile()
    render_audio = (apply_plan.get("render_settings") or {}).get("audio") or {}
    assert render_audio.get("music_mode") == "auto"
    assert render_audio.get("music_path")
    assert render_audio.get("music_source") == "library"


def test_audio_blueprint_prefers_chapter_restart_for_long_photo_story() -> None:
    audio_a = Path("tests/tmp_vcs_audio_blueprint_long/a.m4a")
    audio_b = Path("tests/tmp_vcs_audio_blueprint_long/b.m4a")
    audio_a.parent.mkdir(parents=True, exist_ok=True)
    make_audio(audio_a, duration=36.0, frequency=420)
    make_audio(audio_b, duration=42.0, frequency=520)

    sections = []
    directory_nodes = [
        {
            "node_id": "dir_root",
            "name": "album",
            "relative_path": "",
            "depth": 0,
            "parent_id": None,
            "detected_type": "project_root",
            "confidence": 1.0,
            "reason": "root",
            "display_title": "album",
            "signals": {},
            "children": [],
            "title_style": None,
        }
    ]
    assets = [
        {
            "asset_id": "music_1",
            "type": "audio",
            "relative_path": audio_a.name,
            "absolute_path": str(audio_a.resolve()),
            "thumbnail_path": None,
            "file": {"name": audio_a.name, "extension": ".m4a", "size_bytes": audio_a.stat().st_size, "modified_time": "2025-05-01T10:00:00", "content_hash": "m1"},
            "media": {"duration_seconds": 36.0},
            "classification": {"directory_node_id": "dir_root"},
            "status": "ready",
        },
        {
            "asset_id": "music_2",
            "type": "audio",
            "relative_path": audio_b.name,
            "absolute_path": str(audio_b.resolve()),
            "thumbnail_path": None,
            "file": {"name": audio_b.name, "extension": ".m4a", "size_bytes": audio_b.stat().st_size, "modified_time": "2025-05-01T10:00:01", "content_hash": "m2"},
            "media": {"duration_seconds": 42.0},
            "classification": {"directory_node_id": "dir_root"},
            "status": "ready",
        },
    ]
    for chapter_index in range(3):
        section_node_id = f"dir_section_{chapter_index}"
        directory_nodes[0]["children"].append(section_node_id)
        directory_nodes.append(
            {
                "node_id": section_node_id,
                "name": f"章节{chapter_index + 1}",
                "relative_path": f"章节{chapter_index + 1}",
                "depth": 1,
                "parent_id": "dir_root",
                "detected_type": "chapter",
                "confidence": 0.9,
                "reason": "chapter",
                "display_title": f"章节{chapter_index + 1}",
                "signals": {"matched_theme_keywords": ["风景", "旅行"]},
                "children": [],
                "title_style": None,
            }
        )
        for image_index in range(40):
            assets.append(
                {
                    "asset_id": f"img_{chapter_index}_{image_index}",
                    "type": "image",
                    "relative_path": f"章节{chapter_index + 1}/{image_index}.jpg",
                    "absolute_path": f"D:/mock/chapter_{chapter_index}_{image_index}.jpg",
                    "thumbnail_path": None,
                    "file": {"name": f"{image_index}.jpg", "extension": ".jpg", "size_bytes": 1024, "modified_time": "2025-05-01T10:00:00", "content_hash": f"h{chapter_index}_{image_index}"},
                    "media": {"width": 1600, "height": 900},
                    "classification": {"directory_node_id": section_node_id},
                    "status": "ready",
                }
            )

    library = {
        "project": {"source_root": "D:/mock/long_album", "project_title": "长图文旅行"},
        "directory_nodes": directory_nodes,
        "assets": assets,
        "summary": {
            "total_assets": len(assets),
            "image_count": 120,
            "video_count": 0,
            "audio_count": 2,
            "skipped_count": 0,
            "error_count": 0,
        },
    }

    blueprint = engine.Planner(library).plan(
        template_mode="photo_story",
        music_blueprint_mode="recommend",
    )
    audio_blueprint = (blueprint.get("metadata") or {}).get("audio_blueprint") or {}
    settings = audio_blueprint.get("recommended_audio_settings") or {}
    assert audio_blueprint.get("template_id") == "photo_story"
    assert audio_blueprint.get("longform_project") is True
    assert settings.get("music_playlist_mode") == "chapter_restart"
    assert settings.get("music_chapter_restart") is True
    assert settings.get("music_fit_strategy") == "intro_loop_outro"


def test_renderer_prepares_chapter_restart_music_bed() -> None:
    root = Path("tests/tmp_vcs_audio_chapter_restart")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    audio_a = root / "a.m4a"
    audio_b = root / "b.m4a"
    make_audio(audio_a, duration=12.0, frequency=410)
    make_audio(audio_b, duration=12.0, frequency=510)

    plan = {
        "document_type": "render_plan",
        "total_duration": 6.0,
        "segments": [],
        "render_settings": {
            "aspect_ratio": "16:9",
            "fps": 12,
            "quality": "draft",
            "audio": {
                "music_mode": "manual",
                "music_path": str(audio_a.resolve()),
                "music_source": "manual",
                "music_playlist_mode": "chapter_restart",
                "music_playlist_paths": [str(audio_a.resolve()), str(audio_b.resolve())],
                "music_fit_strategy": "trim",
                "music_chapter_restart": True,
                "fade_in_seconds": 0.2,
                "fade_out_seconds": 0.2,
                "normalize_audio": False,
                "target_lufs": -16.0,
            },
            "audio_blueprint": {
                "timeline_cues": [
                    {"title": "A", "start_time": 0.0, "end_time": 2.0, "duration": 2.0},
                    {"title": "B", "start_time": 2.0, "end_time": 4.0, "duration": 2.0},
                    {"title": "C", "start_time": 4.0, "end_time": 6.0, "duration": 2.0},
                ]
            },
        },
    }
    renderer = engine.Renderer(plan, str(root / "dummy.mp4"), {"preview": True, "preview_height": 360})
    bed = renderer._prepare_music_bed(6.0)
    assert bed is not None
    assert bed.exists()
    bed_again = renderer._prepare_music_bed(6.0)
    assert bed_again == bed


if __name__ == "__main__":
    test_audio_blueprint_recommend_and_apply_modes()
    test_audio_blueprint_prefers_chapter_restart_for_long_photo_story()
    test_renderer_prepares_chapter_restart_music_bed()
    print("V5 audio blueprint smoke test passed")
