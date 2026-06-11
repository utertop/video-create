import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def test_preview_and_final_cache_policy_are_isolated() -> None:
    root = Path("tests/tmp_vcs_preview_final_cache")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "image_01.jpg"
    engine.Image.new("RGB", (1280, 720), (78, 116, 166)).save(source, quality=92)
    segment = {
        "segment_id": "seg_cache_policy_01",
        "type": "image",
        "source_path": str(source),
        "duration": 2.0,
        "start_time": 0.0,
        "end_time": 2.0,
        "transition_config": {"type": "cut", "duration": 0},
        "motion_config": {"type": "gentle_push"},
    }
    preview_params = {
        "preview": True,
        "preview_height": 360,
        "fps": 12,
        "quality": "draft",
        "aspect_ratio": "16:9",
        "render_mode": "standard",
    }
    preview_540_params = dict(preview_params, preview_height=540)
    final_params = {
        "fps": 12,
        "quality": "draft",
        "aspect_ratio": "16:9",
        "render_mode": "standard",
    }

    preview_policy = engine._v56_render_cache_policy(preview_params)
    final_policy = engine._v56_render_cache_policy(final_params)

    assert preview_policy["render_intent"] == "preview"
    assert preview_policy["cache_namespace"] == "preview"
    assert preview_policy["allow_proxy"] is True
    assert preview_policy["uses_original_source"] is False
    assert final_policy["render_intent"] == "final"
    assert final_policy["cache_namespace"] == "final"
    assert final_policy["allow_proxy"] is False
    assert final_policy["uses_original_source"] is True
    assert final_policy["proxy_allowed_for_final"] is False

    preview_key = engine._v56_segment_cache_key(segment, preview_params)
    preview_540_key = engine._v56_segment_cache_key(segment, preview_540_params)
    final_key = engine._v56_segment_cache_key(segment, final_params)
    final_quality_key = engine._v56_segment_cache_key(segment, dict(final_params, quality="high"))

    assert preview_key != final_key
    assert preview_key != preview_540_key
    assert final_key != final_quality_key


if __name__ == "__main__":
    test_preview_and_final_cache_policy_are_isolated()
    print("V5 preview/final cache isolation smoke test passed")
