# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "video_engine_v5.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("video_engine_v5", ENGINE)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot import video_engine_v5.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["video_engine_v5"] = mod
    spec.loader.exec_module(mod)

    renderer = mod.TitleStyleRenderer((320, 180))
    img = mod.Image.new("RGBA", (320, 180), (0, 0, 0, 0))
    clip = mod.ImageClip(mod.np.array(img)).set_duration(1.2)

    for motion in [
        "fade_only",
        "fade_slide_up",
        "soft_zoom_in",
        "pop_bounce",
        "quick_zoom_punch",
        "slow_fade_zoom",
    ]:
        animated = renderer.animate(clip, motion, 1.2)
        frame = animated.get_frame(0.3)
        if frame is None:
            raise AssertionError(f"{motion}: empty frame")

    print("V5.5.1 MoviePy opacity smoke test passed.")


if __name__ == "__main__":
    main()
