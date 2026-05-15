import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

import video_engine_v5 as engine


def make_image(path: Path) -> None:
    image = Image.new("RGB", (960, 540), (36, 98, 78))
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), "CACHE", fill=(255, 255, 255))
    image.save(path, quality=92)


def render_once(root: Path, image_path: Path, output_name: str) -> None:
    plan = {
        "render_settings": {"fps": 12, "aspect_ratio": "16:9"},
        "segments": [
            {
                "segment_id": "seg_00000",
                "type": "image",
                "source_path": str(image_path),
                "duration": 0.8,
                "text": None,
                "subtitle": None,
                "start_time": 0,
                "end_time": 0.8,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "still_hold"},
                "rhythm_config": {"pace": "fast_review", "role": "visual"},
                "keep_audio": False,
            }
        ],
    }
    engine.Renderer(plan, str(root / output_name), {"fps": 12, "quality": "draft"}).render()


def test_render_preprocess_cache_reuse() -> None:
    root = Path("tests/tmp_vcs_render_cache")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    image_path = root / "source.jpg"
    make_image(image_path)

    render_once(root, image_path, "first.mp4")
    cache_root = root / ".video_create_project" / "render_cache"
    cached_files = sorted(path for path in cache_root.rglob("*") if path.is_file())
    assert cached_files, "expected preprocessing cache files"
    mtimes_before = {path: path.stat().st_mtime for path in cached_files}

    render_once(root, image_path, "second.mp4")
    cached_files_after = sorted(path for path in cache_root.rglob("*") if path.is_file())
    mtimes_after = {path: path.stat().st_mtime for path in cached_files_after}

    assert set(mtimes_before) == set(mtimes_after)
    assert mtimes_before == mtimes_after


if __name__ == "__main__":
    test_render_preprocess_cache_reuse()
    print("V5 render preprocess cache smoke test passed")
