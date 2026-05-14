
# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "video_engine_v5.py"


def load_engine():
    spec = importlib.util.spec_from_file_location("video_engine_v5", ENGINE)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot import video_engine_v5.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["video_engine_v5"] = mod
    spec.loader.exec_module(mod)
    return mod


def make_segment(i: int, duration: float = 30.0) -> dict:
    return {
        "segment_id": f"seg_{i:03d}",
        "type": "image",
        "source_path": f"fake_{i}.jpg",
        "duration": duration,
        "text": None,
        "subtitle": None,
        "start_time": i * duration,
        "end_time": (i + 1) * duration,
        "cache_key": f"fake_{i}",
    }


def main() -> None:
    mod = load_engine()

    if not hasattr(mod, "_v56_build_chunk_groups"):
        raise AssertionError("_v56_build_chunk_groups not found")
    if not hasattr(mod, "_v56_should_use_stable_renderer"):
        raise AssertionError("_v56_should_use_stable_renderer not found")
    if not hasattr(mod, "V56StableRenderer"):
        raise AssertionError("V56StableRenderer not found")

    segments = [make_segment(i, 30.0) for i in range(20)]
    groups = mod._v56_build_chunk_groups(segments, 180, {"quality": "high", "fps": 30})
    if len(groups) < 3:
        raise AssertionError(f"expected at least 3 chunks, got {len(groups)}")

    for group in groups:
        if group["duration"] > 210:
            raise AssertionError(f"chunk too large: {group['duration']}")
        if not group.get("cache_key"):
            raise AssertionError("missing chunk cache_key")

    short_plan = {"total_duration": 120, "segments": segments[:3]}
    long_plan = {"total_duration": 1800, "segments": segments}
    if mod._v56_should_use_stable_renderer(short_plan, {"render_mode": "standard"}):
        raise AssertionError("standard mode should not use stable renderer")
    if not mod._v56_should_use_stable_renderer(long_plan, {"render_mode": "auto"}):
        raise AssertionError("long auto plan should use stable renderer")
    if not mod._v56_should_use_stable_renderer(short_plan, {"render_mode": "long_stable"}):
        raise AssertionError("explicit long_stable should use stable renderer")

    print("V5.6 long-video stability smoke test passed.")


if __name__ == "__main__":
    main()
