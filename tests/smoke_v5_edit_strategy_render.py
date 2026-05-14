import shutil
import sys
from pathlib import Path
from typing import Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

import video_engine_v5 as engine


def build_mock_image(path: Path, color: Tuple[int, int, int], text: str) -> None:
    image = Image.new("RGB", (960, 540), color)
    draw = ImageDraw.Draw(image)
    draw.text((80, 80), text, fill=(255, 255, 255))
    image.save(path, quality=92)


def test_edit_strategy_render_consumes_transition_and_motion() -> None:
    root = Path("tests/tmp_vcs_p3_render_smoke")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    image_one = root / "one.jpg"
    image_two = root / "two.jpg"
    output = root / "p3_smoke.mp4"

    build_mock_image(image_one, (32, 96, 80), "ONE")
    build_mock_image(image_two, (160, 72, 54), "TWO")

    plan = {
        "render_settings": {"fps": 12, "aspect_ratio": "16:9", "edit_strategy": "travel_soft"},
        "segments": [
            {
                "segment_id": "seg_00000",
                "type": "image",
                "source_path": str(image_one),
                "duration": 1.2,
                "text": None,
                "subtitle": None,
                "start_time": 0,
                "end_time": 1.2,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0, "strategy": "travel_soft"},
                "motion_config": {"type": "gentle_push", "intensity": "soft"},
                "rhythm_config": {"pace": "medium_soft", "role": "visual"},
                "keep_audio": False,
            },
            {
                "segment_id": "seg_00001",
                "type": "image",
                "source_path": str(image_two),
                "duration": 1.2,
                "text": None,
                "subtitle": None,
                "start_time": 1.2,
                "end_time": 2.4,
                "transition": "soft_crossfade",
                "transition_config": {"type": "soft_crossfade", "duration": 0.35, "strategy": "travel_soft"},
                "motion_config": {"type": "gentle_push", "intensity": "soft"},
                "rhythm_config": {"pace": "medium_soft", "role": "visual"},
                "keep_audio": False,
            },
        ],
    }

    engine.Renderer(plan, str(output), {"fps": 12, "quality": "draft"}).render()
    ok, reason, duration = engine._v56_validate_video(output, min_size=512)

    assert ok, reason
    assert duration and 1.8 <= duration <= 2.3, duration


if __name__ == "__main__":
    test_edit_strategy_render_consumes_transition_and_motion()
    print("V5 edit strategy render smoke test passed")
