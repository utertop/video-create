from __future__ import annotations

import json
import shutil
import sys
from argparse import Namespace
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def make_image(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (960, 540), color)
    image.save(path, quality=92)


def test_low_res_preview_plan_and_render() -> None:
    root = Path("tests/tmp_vcs_low_res_preview")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    first = root / "first.jpg"
    second = root / "second.jpg"
    make_image(first, (42, 112, 82))
    make_image(second, (160, 92, 64))

    plan = {
        "document_type": "render_plan",
        "render_settings": {"fps": 24, "aspect_ratio": "16:9", "quality": "high"},
        "total_duration": 12.0,
        "segments": [
            {
                "segment_id": "seg_00001",
                "type": "image",
                "source_path": str(first),
                "duration": 6.0,
                "start_time": 0.0,
                "end_time": 6.0,
                "text": "Preview A",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
            {
                "segment_id": "seg_00002",
                "type": "image",
                "source_path": str(second),
                "duration": 6.0,
                "start_time": 6.0,
                "end_time": 12.0,
                "text": "Preview B",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "none"},
            },
        ],
    }

    preview = engine.build_low_res_preview_plan(plan, max_duration=3.0, max_segments=1)
    assert preview["total_duration"] == 3.0
    assert len(preview["segments"]) == 1
    assert preview["segments"][0]["duration"] == 3.0
    assert engine.get_preview_resolution("16:9", 360) == (640, 360)

    output = root / "preview.mp4"
    engine.Renderer(
        preview,
        str(output),
        {"preview": True, "preview_height": 360, "fps": 12, "quality": "draft"},
    ).render()
    ok, reason, duration = engine._v56_validate_video(output, min_size=512)
    assert ok, reason
    assert duration and 2.5 <= duration <= 3.5

    plan_path = root / "render_plan.json"
    cli_output = root / "preview_cli.mp4"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    engine.command_preview_render(
        Namespace(
            plan=str(plan_path),
            output=str(cli_output),
            params=json.dumps({"aspect_ratio": "16:9"}, ensure_ascii=False),
            height=360,
            fps=12,
            max_duration=3.0,
            max_segments=1,
        )
    )
    ok, reason, duration = engine._v56_validate_video(cli_output, min_size=512)
    assert ok, reason
    assert duration and 2.5 <= duration <= 3.5


if __name__ == "__main__":
    test_low_res_preview_plan_and_render()
    print("V5 low-res preview smoke test passed")
