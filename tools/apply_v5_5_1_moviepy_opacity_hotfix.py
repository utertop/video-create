# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
ENGINE_PY = ROOT / "video_engine_v5.py"

SAFE_ANIMATION_BLOCK = '    def _with_dynamic_opacity(self, clip: Any, opacity_fn: Any) -> Any:\n        # Apply time-varying opacity using a MoviePy mask.\n        # MoviePy 1.0.x set_opacity() only accepts numeric opacity.\n        try:\n            base_mask = getattr(clip, "mask", None)\n            if base_mask is None:\n                base_mask = ColorClip(clip.size, color=1, ismask=True).set_duration(clip.duration)\n\n            def mask_filter(get_frame: Any, t: float) -> Any:\n                try:\n                    alpha = float(opacity_fn(t))\n                except Exception:\n                    alpha = 1.0\n                alpha = max(0.0, min(1.0, alpha))\n                return get_frame(t) * alpha\n\n            return clip.set_mask(base_mask.fl(mask_filter))\n        except Exception:\n            return clip.set_opacity(1.0)\n\n    def _safe_resize(self, clip: Any, scale_fn: Any) -> Any:\n        try:\n            return clip.resize(scale_fn)\n        except Exception:\n            return clip\n\n    def _pop_scale(self, t: float) -> float:\n        if t < 0.18:\n            return 0.82 + (t / 0.18) * 0.28\n        if t < 0.36:\n            return 1.10 - ((t - 0.18) / 0.18) * 0.10\n        return 1.0\n\n    def _punch_scale(self, t: float) -> float:\n        if t < 0.16:\n            return 1.16 - (t / 0.16) * 0.16\n        return 1.0\n\n    def _soft_zoom_scale(self, t: float, duration: float) -> float:\n        span = max(min(duration, 1.2), 0.4)\n        ratio = max(0.0, min(1.0, t / span))\n        return 0.96 + ratio * 0.04\n\n    def animate(self, clip: Any, motion: str, duration: float) -> Any:\n        motion = motion or "fade_slide_up"\n        duration = max(float(duration or 0.1), 0.1)\n\n        animated = clip\n\n        if motion in {"soft_zoom_in", "slow_fade_zoom"}:\n            animated = self._safe_resize(animated, lambda t: self._soft_zoom_scale(t, duration))\n        elif motion == "pop_bounce":\n            animated = self._safe_resize(animated, lambda t: self._pop_scale(t))\n        elif motion == "quick_zoom_punch":\n            animated = self._safe_resize(animated, lambda t: self._punch_scale(t))\n\n        # Dynamic opacity must be mask-based, not set_opacity(lambda...).\n        animated = self._with_dynamic_opacity(animated, lambda t: self._fade_curve(t, duration))\n\n        try:\n            return animated.set_position(("center", "center"))\n        except Exception:\n            return animated\n\n'


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def backup(path: Path, suffix: str) -> None:
    bak = path.with_suffix(path.suffix + suffix)
    if path.exists() and not bak.exists():
        bak.write_text(read(path), encoding="utf-8")


def patch_engine() -> None:
    if not ENGINE_PY.exists():
        raise FileNotFoundError(ENGINE_PY)

    backup(ENGINE_PY, ".v551_moviepy_opacity.bak")
    text = read(ENGINE_PY)

    if "def _with_dynamic_opacity(self, clip: Any, opacity_fn: Any)" in text:
        print("[SKIP] video_engine_v5.py already contains V5.5.1 dynamic opacity fix.")
        return

    start = text.find("    def animate(self, clip:")
    if start < 0:
        start = text.find("    def animate(self, clip")
    if start < 0:
        raise RuntimeError("Could not find TitleStyleRenderer.animate() in video_engine_v5.py")

    end = text.find("    def _fade_curve", start)
    if end < 0:
        raise RuntimeError("Could not find def _fade_curve after animate() in video_engine_v5.py")

    patched = text[:start] + SAFE_ANIMATION_BLOCK + text[end:]
    patched = patched.replace(
        'ENGINE_VERSION = "video-create-engine-v5.5.0"',
        'ENGINE_VERSION = "video-create-engine-v5.5.1"',
    )
    patched = patched.replace("Video Create Studio V5.5.0 Engine", "Video Create Studio V5.5.1 Engine")

    write(ENGINE_PY, patched)
    print("[OK] patched video_engine_v5.py with MoviePy-safe dynamic opacity.")


def main() -> None:
    if not (ROOT / "package.json").exists():
        raise SystemExit("Please run from project root, for example: cd D:\\Automatic\\video_create")
    patch_engine()
    print()
    print("V5.5.1 MoviePy opacity hotfix applied.")
    print(r"Run: python -m py_compile .\video_engine_v5.py")
    print(r"Run: python .\tests\smoke_v5_5_1_moviepy_opacity.py")
    print(r"If Tauri still uses old engine: Remove-Item .\src-tauri\target\debug\video_engine_v5.py -Force")


if __name__ == "__main__":
    main()
