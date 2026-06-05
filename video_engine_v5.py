# -*- coding: utf-8 -*-
"""
Video Create Studio V5 Engine

Four-stage engine:
  scan    -> media_library.json
  plan    -> story_blueprint.json
  compile -> render_plan.json
  render  -> final mp4

Design goals:
  - schema_version on every JSON document
  - Media Library / Story Blueprint / Render Plan split
  - directory recognition with confidence and user-overridable metadata
  - complete-display rendering: no crop, no stretch
  - blurred background for portrait media in 16:9 output
  - JSON progress events for GUI, including MoviePy/FFmpeg export progress
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
import subprocess
import tempfile
import gc
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

ENGINE_ROOT = Path(__file__).resolve().parent
if str(ENGINE_ROOT) not in sys.path:
    sys.path.insert(0, str(ENGINE_ROOT))

from render_backends import (
    BackendDecision,
    BackendExecutionResult,
    build_backend_report_payload as backend_report_payload,
    coerce_backend_decision,
    coerce_backend_execution_result,
    merge_backend_reason_tags,
    resolve_render_backend as backend_selector_resolve_render_backend,
    run_ffmpeg_stable_backend,
    run_legacy_moviepy_backend,
    run_mlt_backend,
)
from video_engine.cache import CACHE_CLEANUP_DEFAULTS_MB, _cleanup_cache_buckets, file_hash_light, safe_id
from video_engine.constants import (
    ALL_EXTS,
    AUDIO_EXTS,
    ENGINE_VERSION,
    IGNORED_DIRS,
    IMAGE_EXTS,
    SCHEMA_VERSION,
    STABLE_RENDER_DEFAULTS,
    VIDEO_EXTS,
)
from video_engine.models import Asset, AssetRef, DirectoryNode, RenderSegment, StorySection, TitleStyle
from video_engine.scan_utils import (
    detect_directory_type,
    is_ignored_file,
    natural_sort_key,
    orientation_from_size,
    section_to_dict,
)
from video_engine.audio import (
    audio_asset_duration_seconds,
    build_chapter_restart_music_bed,
    build_music_bed_for_duration,
    prepare_cached_audio_for_mix,
    probe_audio_file,
    select_auto_music_asset,
    select_auto_music_assets,
    set_audio_event_emitter,
)
from video_engine.scan import SCAN_PROXY_PROFILE, Scanner, set_scan_event_emitter
from video_engine.plan import (
    AUDIO_BLUEPRINT_TEMPLATE_PROFILES,
    TEMPLATE_MATCHING_PROFILE_BY_ID,
    TEMPLATE_MATCHING_PROFILES,
    Planner,
    set_plan_event_emitter,
)
from video_engine.compile import Compiler, set_compile_event_emitter
from video_engine import render_diagnostics as render_diagnostics_helpers
from video_engine import render_ffmpeg as render_ffmpeg_helpers
from video_engine.render_routes import (
    _is_image_heavy_visual_mix,
    _should_auto_use_stable_renderer,
    _visual_segment_mix,
    _v56_chunk_route_family,
    _v56_image_overlay_cache_spec,
    _v56_is_ffmpeg_card_chunk_candidate,
    _v56_is_ffmpeg_fitted_video_chunk_route,
    _v56_is_ffmpeg_image_chunk_candidate,
    _v56_resolved_card_style,
)
from video_engine.render_cache import (
    _v56_atomic_replace,
    _v56_build_chunk_groups,
    _v56_chunk_visual_audio_payload,
    _v56_segment_cache_key,
    _v56_segment_source_fingerprints,
    _v56_source_fingerprint,
    _v56_stable_json_hash,
    _v56_write_build_report,
    set_render_cache_event_emitter,
)


# V5.3.2 early help guard
# Keep `python video_engine_v5.py --help` available even before optional media
# dependencies such as numpy/moviepy/pillow are installed. Real scan/render work
# still validates dependencies when the command continues past this point.
def _print_early_help_without_optional_deps() -> None:
    print("""Video Create Studio V5.6.2 Engine

usage:
  python video_engine_v5.py scan    --input_folder <folder> --output <media_library.json> [--recursive]
  python video_engine_v5.py plan    --library <media_library.json> --output <story_blueprint.json> [--template auto]
  python video_engine_v5.py compile --blueprint <story_blueprint.json> --library <media_library.json> --output <render_plan.json>
  python video_engine_v5.py render  --plan <render_plan.json> --output <video.mp4> [--params <json>]
  python video_engine_v5.py preview-render --plan <render_plan.json> --output <preview.mp4>
  python video_engine_v5.py preview-title --title <text> --style_json <json> --output <preview.mp4>

Pipeline:
  scan -> media_library.json -> plan -> story_blueprint.json -> compile -> render_plan.json -> render -> final mp4

Notes:
  - --help intentionally does not import heavy media dependencies.
  - scan/render require dependencies from requirements.txt.
""")


if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
    _print_early_help_without_optional_deps()
    raise SystemExit(0)


def _configure_utf8_stdio() -> None:
    """Force UTF-8 stdio on Windows/CI so JSON progress events can carry Chinese text safely."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


_configure_utf8_stdio()

try:
    from proglog import ProgressBarLogger
except Exception:  # pragma: no cover
    ProgressBarLogger = object  # type: ignore

try:
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
except Exception as exc:  # pragma: no cover
    print(f"Missing Python dependencies: {exc}", file=sys.stderr)
    raise

# Pillow 10+ compatibility for MoviePy 1.0.x
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

try:
    from moviepy.editor import (
        AudioFileClip,
        ColorClip,
        CompositeAudioClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        concatenate_audioclips,
        concatenate_videoclips,
    )
    try:
        from moviepy.audio.fx.all import audio_loop as moviepy_audio_loop
    except Exception:
        moviepy_audio_loop = None

    HAS_MOVIEPY = True
    MOVIEPY_IMPORT_ERROR = ""
except Exception as exc:
    HAS_MOVIEPY = False
    moviepy_audio_loop = None
    MOVIEPY_IMPORT_ERROR = str(exc)


# =========================
# Event / logging
# =========================

def emit_event(event_type: str, **payload: Any) -> None:
    """Emit one JSON event line for the Tauri GUI."""
    payload["type"] = event_type
    print(json.dumps(payload, ensure_ascii=False), flush=True)


set_audio_event_emitter(emit_event)
set_scan_event_emitter(emit_event)
set_plan_event_emitter(emit_event)
set_compile_event_emitter(emit_event)
set_render_cache_event_emitter(emit_event)


class JsonMoviePyLogger(ProgressBarLogger):  # type: ignore[misc]
    """
    Convert MoviePy/proglog progress into JSON events.

    Why:
      MoviePy enters FFmpeg export after segments are ready. Without this logger,
      the GUI often stays at 98% and looks frozen while FFmpeg is still writing.
    """

    def __init__(self, base_percent: int = 92, span_percent: int = 7):
        super().__init__()
        self.base_percent = base_percent
        self.span_percent = span_percent
        self.last_percent = -1
        self.last_message = ""

    def callback(self, **changes: Any) -> None:
        bars = getattr(self, "state", {}).get("bars", {})
        if not bars:
            return

        for bar_name, bar in bars.items():
            index = bar.get("index")
            total = bar.get("total")
            if not total or index is None:
                continue

            percent = int(self.base_percent + (float(index) / float(total)) * self.span_percent)
            percent = max(self.base_percent, min(99, percent))

            # Avoid flooding the frontend with too many identical events.
            message = f"Export progress {bar_name}: {index}/{total}"
            if percent != self.last_percent or message != self.last_message:
                self.last_percent = percent
                self.last_message = message
                emit_event("phase", phase="render", message=message, percent=percent)


# =========================
# Utility functions
# =========================

def get_resolution(aspect_ratio: str) -> Tuple[int, int]:
    if aspect_ratio == "9:16":
        return 1080, 1920
    if aspect_ratio == "1:1":
        return 1080, 1080
    if aspect_ratio == "16:9":
        return 1920, 1080
    return 1920, 1080


def get_preview_resolution(aspect_ratio: str, height: int = 540) -> Tuple[int, int]:
    height = max(240, min(int(height or 540), 720))
    if aspect_ratio == "9:16":
        width = int(round(height * 9 / 16))
    elif aspect_ratio == "1:1":
        width = height
    else:
        width = int(round(height * 16 / 9))
    return max(2, width // 2 * 2), max(2, height // 2 * 2)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        "/System/Library/Fonts/PingFang.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for item in candidates:
        if os.path.exists(item):
            try:
                return ImageFont.truetype(item, size)
            except Exception:
                pass
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    try:
        from pilmoji import Pilmoji
        with Pilmoji(draw._image, draw=draw) as pilmoji:
            return pilmoji.getsize(text or "", font=font)
    except ImportError:
        bbox = draw.textbbox((0, 0), text or "", font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

def draw_text_with_emoji(draw: ImageDraw.ImageDraw, xy: Tuple[int, int], text: str, font: ImageFont.ImageFont, fill: Any = None, **kwargs: Any) -> None:
    try:
        from pilmoji import Pilmoji
        with Pilmoji(draw._image, draw=draw) as pilmoji:
            pilmoji.text(xy, text, fill=fill, font=font, **kwargs)
    except ImportError:
        draw.text(xy, text, fill=fill, font=font, **kwargs)



def quality_to_crf(quality: Any) -> str:
    mapping = {
        "normal": "22",
        "draft": "24",
        "standard": "20",
        "high": "18",
        "ultra": "18",
    }
    return mapping.get(str(quality), "20")


def detect_ffmpeg_hardware_encoders() -> List[str]:
    """List available H.264 hardware encoders reported by the bundled FFmpeg."""
    candidates = ["h264_nvenc", "h264_qsv", "h264_amf", "h264_videotoolbox"]
    try:
        import imageio_ffmpeg

        completed = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        text = completed.stdout + completed.stderr
        return [encoder for encoder in candidates if encoder in text]
    except Exception:
        return []


def _should_default_to_hardware_encoding(params: Dict[str, Any]) -> bool:
    if bool(params.get("preview")):
        return False
    if bool(params.get("disable_default_hardware_encoding")):
        return False

    render_mode = str(params.get("render_mode") or params.get("long_video_mode") or "").lower()
    performance_mode = str(params.get("performance_mode") or "").lower()
    total_duration = float(params.get("total_duration") or 0.0)
    segment_count = int(params.get("segment_count") or 0)

    if render_mode in {"stable", "long", "long_stable"}:
        return True
    if performance_mode == "stable":
        return True
    if total_duration >= float(STABLE_RENDER_DEFAULTS["seconds"]):
        return True
    if segment_count >= int(STABLE_RENDER_DEFAULTS["segments"]):
        return True
    return False


def select_ffmpeg_video_encoder(params: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Choose an FFmpeg encoder.

    For low-risk acceleration, long/stable formal exports default to hardware
    auto-detection when the caller did not explicitly request CPU encoding.
    Some FFmpeg builds list an encoder even when the matching driver/device is
    unavailable, so callers still keep a libx264 fallback.
    """
    raw_requested = params.get("hardware_encoder")
    if raw_requested is None:
        raw_requested = params.get("hardware_encoding")
    requested = str(raw_requested or "").lower()
    if requested == "" and _should_default_to_hardware_encoding(params):
        requested = "auto"
    if requested in {"", "off", "false", "none", "libx264", "cpu"}:
        return "libx264", ["-preset", "veryfast"]

    available = detect_ffmpeg_hardware_encoders()
    aliases = {
        "auto": available[0] if available else "",
        "true": available[0] if available else "",
        "nvenc": "h264_nvenc",
        "qsv": "h264_qsv",
        "amf": "h264_amf",
        "videotoolbox": "h264_videotoolbox",
    }
    selected = aliases.get(requested, requested)
    if selected and selected in available:
        if selected == "h264_nvenc":
            return selected, ["-preset", "fast"]
        if selected == "h264_qsv":
            return selected, ["-preset", "veryfast"]
        if selected == "h264_amf":
            return selected, ["-quality", "quality"]
        return selected, []
    return "libx264", ["-preset", "veryfast"]


def close_clip(clip: Any) -> None:
    """Best-effort recursive close for MoviePy clips.

    MoviePy CompositeVideoClip/CompositeAudioClip may keep child clips, masks,
    audio clips and ffmpeg readers alive. Long photo timelines can therefore
    accumulate many readers/arrays unless we close the whole tree explicitly.
    """
    seen = set()

    def _close(obj: Any) -> None:
        if obj is None:
            return
        obj_id = id(obj)
        if obj_id in seen:
            return
        seen.add(obj_id)

        for child in list(getattr(obj, "clips", []) or []):
            _close(child)

        _close(getattr(obj, "mask", None))
        _close(getattr(obj, "audio", None))

        reader = getattr(obj, "reader", None)
        if reader is not None:
            try:
                reader.close()
            except Exception:
                pass

        try:
            obj.close()
        except Exception:
            pass

    _close(clip)


def video_needs_display_normalization(source: Path) -> bool:
    """Detect mp4 files whose encoded size differs from display geometry.

    MoviePy 1.0.x often trusts encoded width/height and can miss sample aspect
    ratio or rotation metadata. Those files need an FFmpeg normalization pass
    before composition, otherwise they can look stretched in the final timeline.
    """
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        probe_text = completed.stderr or ""
        lower = probe_text.lower()
        if "displaymatrix" in lower or "rotate" in lower or "rotation of" in lower:
            return True
        return bool(re.search(r"\bSAR\s+(?!1:1\b)\d+:\d+", probe_text))
    except Exception:
        return False


def video_has_audio_stream(source: Path) -> bool:
    """Return True when FFmpeg sees at least one audio stream in the source."""
    try:
        import imageio_ffmpeg

        completed = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return "Audio:" in (completed.stderr or "")
    except Exception:
        return False


def read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Optional[str], data: Dict[str, Any]) -> None:
    if not path:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    out = Path(path)
    ensure_parent(out)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _normalize_proxy_manifest(source: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(source, dict):
        return {}
    assets = source.get("assets")
    if not isinstance(assets, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for key, entry in assets.items():
        if not isinstance(entry, dict):
            continue
        abs_path = str(entry.get("source_path") or key or "")
        if not abs_path:
            continue
        normalized[abs_path] = entry
    return normalized


def _load_proxy_manifest_from_library_path(library_path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    if not library_path:
        return {}
    path = Path(str(library_path))
    if not path.is_file():
        return {}
    try:
        library = read_json(str(path))
    except Exception:
        return {}
    return _normalize_proxy_manifest(library.get("proxy_media_manifest"))


def _guess_sibling_library_path(plan_path: Optional[str]) -> Optional[Path]:
    if not plan_path:
        return None
    plan_file = Path(str(plan_path))
    parent = plan_file.parent
    if not parent:
        return None
    candidate = parent / "media_library.json"
    return candidate if candidate.is_file() else None


class TitleStyleRenderer:
    """V5.5 Template-driven Text Animation Engine."""

    def __init__(self, target_size: Tuple[int, int]):
        self.target_size = target_size

    def render_layer(
        self,
        title: str,
        subtitle: Optional[str],
        style: Dict[str, Any],
        is_full_card: bool = True
    ) -> Image.Image:
        w, h = self.target_size
        preset = style.get("preset", "cinematic_bold")
        preset_aliases = {
            "nature_documentary": "documentary_lower_third",
            "romantic_soft": "handwritten_note",
            "tech_future": "neon_night",
        }
        preset = preset_aliases.get(preset, preset)
        
        # Base transparent layer
        img = Image.new("RGBA", self.target_size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # Style definitions
        if preset == "playful_pop":
            # Round box + bright green text
            box_w = min(int(w * 0.5), 800)
            box_h = 160 if subtitle else 100
            bx, by = (w - box_w) // 2, (h - box_h) // 2
            draw.rounded_rectangle((bx, by, bx + box_w, by + box_h), radius=40, fill=(255, 255, 255, 200))
            title_font = load_font(64)
            sub_font = load_font(32)
            tw, th = text_size(draw, title, title_font)
            draw_text_with_emoji(draw, ((w - tw) // 2, by + 20), title, font=title_font, fill=(52, 211, 153, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw_text_with_emoji(draw, ((w - sw) // 2, by + 90), subtitle, font=sub_font, fill=(30, 41, 59, 200))

        elif preset == "travel_postcard":
            # Bordered card effect
            if is_full_card:
                draw.rectangle((40, 40, w - 40, h - 40), outline=(255, 255, 255, 180), width=3)
                draw.rectangle((56, 56, w - 56, h - 56), outline=(251, 191, 36, 120), width=2)
            title_font = load_font(72)
            sub_font = load_font(36)
            tw, th = text_size(draw, title, title_font)
            draw_text_with_emoji(draw, ((w - tw) // 2 + 3, (h - th) // 2 - 17), title, font=title_font, fill=(35, 24, 18, 190))
            draw_text_with_emoji(draw, ((w - tw) // 2, (h - th) // 2 - 20), title, font=title_font, fill=(255, 245, 210, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw_text_with_emoji(draw, ((w - sw) // 2, (h - sh) // 2 + 60), subtitle, font=sub_font, fill=(251, 191, 36, 230))

        elif preset == "impact_flash":
            title_font = load_font(92)
            sub_font = load_font(38)
            tw, th = text_size(draw, title, title_font)
            x, y = (w - tw) // 2, (h - th) // 2 - 26
            for offset in [(6, 6), (-5, 4), (4, -5), (-4, -4)]:
                draw_text_with_emoji(draw, (x + offset[0], y + offset[1]), title, font=title_font, fill=(17, 24, 39, 240))
            draw_text_with_emoji(draw, (x + 2, y + 2), title, font=title_font, fill=(239, 68, 68, 210))
            draw_text_with_emoji(draw, (x, y), title, font=title_font, fill=(255, 255, 255, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw.rounded_rectangle(((w - sw) // 2 - 18, y + th + 16, (w + sw) // 2 + 18, y + th + 62), radius=8, fill=(15, 23, 42, 210))
                draw_text_with_emoji(draw, ((w - sw) // 2, y + th + 22), subtitle, font=sub_font, fill=(255, 255, 255, 235))

        elif preset == "documentary_lower_third":
            band_h = 170 if subtitle else 126
            y0 = h - band_h - int(h * 0.08) if not is_full_card else int(h * 0.62)
            draw.rectangle((0, y0, w, y0 + band_h), fill=(10, 14, 12, 190))
            draw.rectangle((0, y0, 12, y0 + band_h), fill=(214, 182, 107, 255))
            title_font = load_font(60)
            sub_font = load_font(30)
            draw_text_with_emoji(draw, (56, y0 + 28), title, font=title_font, fill=(250, 246, 235, 255))
            if subtitle:
                draw_text_with_emoji(draw, (58, y0 + 98), subtitle, font=sub_font, fill=(214, 182, 107, 230))

        elif preset == "minimal_editorial":
            title_font = load_font(56)
            sub_font = load_font(28)
            tw, th = text_size(draw, title, title_font)
            x = int(w * 0.12) if is_full_card else int(w * 0.07)
            y = (h - th) // 2 - 10
            draw.rectangle((x, y - 28, x + 2, y + th + 80), fill=(255, 255, 255, 190))
            draw_text_with_emoji(draw, (x + 28, y), title, font=title_font, fill=(255, 255, 255, 235))
            if subtitle:
                draw_text_with_emoji(draw, (x + 30, y + th + 24), subtitle, font=sub_font, fill=(255, 255, 255, 170))

        elif preset == "handwritten_note":
            box_w = min(int(w * 0.62), 980)
            box_h = 190 if subtitle else 136
            bx, by = (w - box_w) // 2, (h - box_h) // 2
            draw.rounded_rectangle((bx, by, bx + box_w, by + box_h), radius=34, fill=(255, 251, 235, 225), outline=(255, 255, 255, 240), width=5)
            title_font = load_font(66)
            sub_font = load_font(32)
            tw, th = text_size(draw, title, title_font)
            draw_text_with_emoji(draw, ((w - tw) // 2 + 3, by + 28 + 3), title, font=title_font, fill=(14, 165, 233, 110))
            draw_text_with_emoji(draw, ((w - tw) // 2, by + 28), title, font=title_font, fill=(31, 41, 55, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw_text_with_emoji(draw, ((w - sw) // 2, by + 106), subtitle, font=sub_font, fill=(234, 88, 12, 220))

        elif preset == "neon_night":
            title_font = load_font(74)
            sub_font = load_font(32)
            tw, th = text_size(draw, title, title_font)
            x, y = (w - tw) // 2, (h - th) // 2 - 22
            for radius, alpha in [(10, 70), (5, 120), (2, 210)]:
                glow = Image.new("RGBA", self.target_size, (0, 0, 0, 0))
                glow_draw = ImageDraw.Draw(glow)
                draw_text_with_emoji(glow_draw, (x, y), title, font=title_font, fill=(244, 114, 182, alpha))
                img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius)))
            draw_text_with_emoji(draw, (x, y), title, font=title_font, fill=(255, 240, 252, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw_text_with_emoji(draw, ((w - sw) // 2, y + th + 32), subtitle, font=sub_font, fill=(125, 211, 252, 230))

        elif preset == "film_subtitle":
            title_font = load_font(56)
            sub_font = load_font(28)
            tw, th = text_size(draw, title, title_font)
            y = int(h * 0.68) if is_full_card else int(h * 0.72)
            draw.rectangle((0, y - 34, w, y + 116), fill=(0, 0, 0, 115))
            draw_text_with_emoji(draw, ((w - tw) // 2, y), title, font=title_font, fill=(248, 240, 220, 245))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw_text_with_emoji(draw, ((w - sw) // 2, y + 62), subtitle, font=sub_font, fill=(248, 240, 220, 190))
            if not is_full_card:
                draw.rectangle((28, 36, 30, h - 36), fill=(248, 240, 220, 42))

        elif preset == "route_marker":
            title_font = load_font(64)
            sub_font = load_font(30)
            x0, y0 = int(w * 0.22), int(h * 0.58)
            x1, y1 = int(w * 0.72), int(h * 0.38)
            draw.line((x0, y0, int(w * 0.44), y0 - 70, x1, y1), fill=(47, 111, 143, 220), width=5)
            draw.ellipse((x1 - 18, y1 - 18, x1 + 18, y1 + 18), fill=(37, 99, 235, 240))
            draw.ellipse((x1 - 7, y1 - 7, x1 + 7, y1 + 7), fill=(255, 255, 255, 240))
            tw, th = text_size(draw, title, title_font)
            draw.rounded_rectangle(((w - tw) // 2 - 32, y0 + 28, (w + tw) // 2 + 32, y0 + 118), radius=18, fill=(255, 251, 235, 220))
            draw_text_with_emoji(draw, ((w - tw) // 2, y0 + 42), title, font=title_font, fill=(23, 32, 26, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw_text_with_emoji(draw, ((w - sw) // 2, y0 + 112), subtitle, font=sub_font, fill=(47, 111, 143, 230))

        else: # cinematic_bold (default)
            title_font = load_font(78)
            sub_font = load_font(34)
            tw, th = text_size(draw, title, title_font)
            draw_text_with_emoji(draw, ((w - tw) // 2, (h - th) // 2 - 40), title, font=title_font, fill=(255, 255, 255, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw_text_with_emoji(draw, ((w - sw) // 2, (h - sh) // 2 + 55), subtitle, font=sub_font, fill=(52, 211, 153, 255))

        return img

    def _with_dynamic_opacity(self, clip: Any, opacity_fn: Any) -> Any:
        # Apply time-varying opacity using a MoviePy mask.
        # MoviePy 1.0.x set_opacity() only accepts numeric opacity.
        try:
            base_mask = getattr(clip, "mask", None)
            if base_mask is None:
                base_mask = ColorClip(clip.size, color=1, ismask=True).set_duration(clip.duration)

            def mask_filter(get_frame: Any, t: float) -> Any:
                try:
                    alpha = float(opacity_fn(t))
                except Exception:
                    alpha = 1.0
                alpha = max(0.0, min(1.0, alpha))
                return get_frame(t) * alpha

            return clip.set_mask(base_mask.fl(mask_filter))
        except Exception:
            return clip.set_opacity(1.0)

    def _safe_resize(self, clip: Any, scale_fn: Any) -> Any:
        try:
            return clip.resize(scale_fn)
        except Exception:
            return clip

    def _pop_scale(self, t: float) -> float:
        if t < 0.18:
            return 0.82 + (t / 0.18) * 0.28
        if t < 0.36:
            return 1.10 - ((t - 0.18) / 0.18) * 0.10
        return 1.0

    def _punch_scale(self, t: float) -> float:
        if t < 0.16:
            return 1.16 - (t / 0.16) * 0.16
        return 1.0

    def _soft_zoom_scale(self, t: float, duration: float) -> float:
        span = max(min(duration, 1.2), 0.4)
        ratio = max(0.0, min(1.0, t / span))
        return 0.96 + ratio * 0.04

    def animate(self, clip: Any, motion: str, duration: float) -> Any:
        motion = motion or "fade_slide_up"
        motion_aliases = {
            "fade_slide_up": "cinematic_reveal",
            "soft_zoom_in": "postcard_drift",
            "pop_bounce": "playful_bounce",
            "quick_zoom_punch": "impact_slam",
            "slow_fade_zoom": "film_burn",
            "fade_only": "editorial_fade",
        }
        motion = motion_aliases.get(motion, motion)
        duration = max(float(duration or 0.1), 0.1)

        animated = clip

        if motion == "static_hold":
            return animated.set_position(("center", "center"))

        if motion in {"soft_zoom_in", "slow_fade_zoom", "cinematic_reveal", "postcard_drift", "film_burn"}:
            animated = self._safe_resize(animated, lambda t: self._soft_zoom_scale(t, duration))
        elif motion in {"pop_bounce", "playful_bounce"}:
            animated = self._safe_resize(animated, lambda t: self._pop_scale(t))
        elif motion in {"quick_zoom_punch", "impact_slam"}:
            animated = self._safe_resize(animated, lambda t: self._punch_scale(t))

        # Dynamic opacity must be mask-based, not set_opacity(lambda...).
        if motion == "neon_flicker":
            animated = self._with_dynamic_opacity(animated, lambda t: self._neon_flicker_curve(t, duration))
        else:
            animated = self._with_dynamic_opacity(animated, lambda t: self._fade_curve(t, duration))

        try:
            return animated.set_position(("center", "center"))
        except Exception:
            return animated

    def _fade_curve(self, t: float, duration: float) -> float:
        in_t, out_t = 0.5, 0.4
        if t < in_t: return t / in_t
        if t > duration - out_t: return max(0, (duration - t) / out_t)
        return 1.0

    def _neon_flicker_curve(self, t: float, duration: float) -> float:
        if t < 0.08:
            return 0.25
        if t < 0.14:
            return 1.0
        if t < 0.20:
            return 0.48
        if t > duration - 0.35:
            return max(0.0, (duration - t) / 0.35)
        return 1.0

    def _slide_up(self, t: float, duration: float) -> int:
        h = self.target_size[1]
        center_y = h // 2
        offset = 20 * (1.0 - (t / duration))
        return int(center_y - offset)

    def _bounce(self, t: float, duration: float) -> float:
        if t < 0.2: return 0.8 + (t / 0.2) * 0.28 # 0.8 -> 1.08
        if t < 0.35: return 1.08 - ((t - 0.2) / 0.15) * 0.08 # 1.08 -> 1.0
        return 1.0


class Renderer:
    def __init__(self, plan: Dict[str, Any], output_path: str, params: Dict[str, Any]):
        self.plan = plan
        self.output_path = Path(output_path)
        self.params = params
        self.backend_decision = coerce_backend_decision(
            self.params.get("_backend_decision") or _v56_resolve_render_backend_decision(self.plan, self.params)
        )
        self.backend_execution = coerce_backend_execution_result(
            self.params.get("_backend_execution") or self.backend_decision
        )
        settings = plan.get("render_settings", {})
        aspect_ratio = params.get("aspect_ratio") or settings.get("aspect_ratio") or "16:9"
        if params.get("preview_height"):
            self.target_size = get_preview_resolution(aspect_ratio, int(params.get("preview_height") or 540))
        else:
            self.target_size = get_resolution(aspect_ratio)
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vcs_v5_render_"))
        self.render_cache_dir = self._init_render_cache_dir()
        self.audio_cache_dir = self._init_audio_cache_dir()
        self.first_visual_source = self._find_visual_source("first")
        self.last_visual_source = self._find_visual_source("last")
        self.renderer = TitleStyleRenderer(self.target_size)
        self.gpu_accel = params.get("gpu_accel", "none") # none, nvenc, qsv
        self.prefer_ffmpeg_segments = self._should_prefer_ffmpeg_segments(settings)
        self.audio_settings = self._resolve_audio_settings(settings)
        self._prepared_music_path: Optional[Path] = None
        self._prepared_music_paths: Optional[List[Path]] = None
        self._prepared_music_beds: Dict[str, Optional[Path]] = {}
        self._prepared_source_audio_paths: Dict[str, Optional[Path]] = {}
        self.photo_segment_cache_stats: Dict[str, int] = {
            "eligible": 0,
            "hit": 0,
            "created": 0,
            "fallback": 0,
            "overlay_eligible": 0,
            "overlay_hit": 0,
            "overlay_created": 0,
            "saved_live_composes": 0,
            "saved_render_seconds": 0,
        }
        self.card_segment_cache_stats: Dict[str, int] = {
            "eligible": 0,
            "hit": 0,
            "created": 0,
            "fallback": 0,
            "saved_live_composes": 0,
            "saved_render_seconds": 0,
        }
        self.visual_base_cache_stats: Dict[str, int] = {
            "eligible": 0,
            "hit": 0,
            "created": 0,
            "fallback": 0,
            "saved_render_seconds": 0,
            "chunk_groups": 0,
            "chunk_hit": 0,
            "chunk_created": 0,
        }
        self.video_segment_cache_stats: Dict[str, int] = {
            "eligible": 0,
            "hit": 0,
            "created": 0,
            "fallback": 0,
            "motion_eligible": 0,
            "motion_hit": 0,
            "motion_created": 0,
            "motion_fallback": 0,
            "saved_live_fits": 0,
            "saved_render_seconds": 0,
        }
        self.proxy_media_stats: Dict[str, int] = {
            "eligible": 0,
            "hit": 0,
            "manifest_hit": 0,
            "created": 0,
            "fallback": 0,
        }
        self.cache_cleanup_stats: Dict[str, Any] = {"enabled": True, "buckets": {}, "deleted_files": 0, "deleted_bytes": 0}
        self.last_render_timings: Dict[str, Any] = {}
        self.last_visual_finalize_summary: Dict[str, Any] = {}
        self.proxy_media_manifest = _normalize_proxy_manifest(self.params.get("proxy_media_manifest"))
        if not self.proxy_media_manifest:
            guessed_library_path = _guess_sibling_library_path(self.params.get("plan_path"))
            self.proxy_media_manifest = _load_proxy_manifest_from_library_path(str(guessed_library_path) if guessed_library_path else None)
        self.render_scheduler_summary: Dict[str, Any] = self._apply_runtime_render_scheduler()

    def _runtime_render_route_for_segment(self, seg: Dict[str, Any]) -> Tuple[str, str, List[str]]:
        stype = str(seg.get("type") or "")
        tags: List[str] = [stype]
        if stype in {"title", "chapter", "end"}:
            return "moviepy_required", "text_or_card_composite", tags + ["text", "timeline"]
        if stype == "image":
            if self._should_prerender_image_segment(float(seg.get("duration") or 0.0), seg.get("motion_config")):
                return "photo_prerender", "image_segment_cache_candidate", tags + ["cache", "prerender"]
            return "image_live_compose", "image_segment_needs_live_compose", tags + ["timeline", "image_compose"]
        if stype == "video":
            if self._can_use_ffmpeg_direct_chunk_segment(seg):
                return "direct_chunk_candidate", "lightweight_video_chunk_safe", tags + ["ffmpeg", "direct_chunk"]
            if self._can_use_ffmpeg_fitted_video(seg):
                if self._ffmpeg_video_motion_cache_spec(seg.get("motion_config")) is not None:
                    return "video_motion_fit", "simple_video_motion_cache_candidate", tags + ["ffmpeg", "video_cache", "motion_cache"]
                return "video_fit", "video_fit_cache_candidate", tags + ["ffmpeg", "video_cache"]
            return "moviepy_required", "video_segment_needs_timeline_processing", tags + ["timeline", "composite"]
        return "moviepy_required", "unknown_segment_type", tags + ["timeline"]

    def _apply_runtime_render_scheduler(self) -> Dict[str, Any]:
        route_counts: Dict[str, int] = {}
        segments = self.plan.get("segments", []) or []
        for seg in segments:
            route, reason, tags = self._runtime_render_route_for_segment(seg)
            seg["runtime_render_route"] = route
            seg["runtime_render_route_reason"] = reason
            seg["runtime_render_route_tags"] = tags
            route_counts[route] = route_counts.get(route, 0) + 1
        return {
            "strategy_version": "runtime_segment_rules_v1",
            "route_counts": route_counts,
            "total_segments": len(segments),
            "prefer_ffmpeg_segments": bool(self.prefer_ffmpeg_segments),
        }

    def _emit_render_scheduler_summary(self) -> None:
        summary = dict(self.render_scheduler_summary or {})
        route_counts = dict(summary.get("route_counts") or {})
        if not route_counts:
            return
        compact = ", ".join(f"{key}={value}" for key, value in sorted(route_counts.items()))
        emit_event("log", message=f"Render scheduler summary: {compact}")

    def _init_render_cache_dir(self) -> Path:
        configured = self.params.get("cache_root") or self.params.get("render_cache_root")
        cache_dir = Path(configured) if configured else self.output_path.parent / ".video_create_project" / "render_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _init_audio_cache_dir(self) -> Path:
        configured = self.params.get("audio_cache_root")
        if configured:
            cache_dir = Path(configured)
        else:
            project_dir = self.render_cache_dir.parent if self.render_cache_dir.name == "render_cache" else self.output_path.parent / ".video_create_project"
            cache_dir = project_dir / "audio_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def _project_cache_root(self) -> Path:
        if self.render_cache_dir.name == "render_cache":
            return self.render_cache_dir.parent
        return self.output_path.parent / ".video_create_project"

    def _cleanup_project_cache_dirs(self) -> Dict[str, Any]:
        project_root = self._project_cache_root()
        summary = _cleanup_cache_buckets(
            [
                ("render_cache", self.render_cache_dir, CACHE_CLEANUP_DEFAULTS_MB["render_cache"]),
                ("audio_cache", self.audio_cache_dir, CACHE_CLEANUP_DEFAULTS_MB["audio_cache"]),
                ("proxies", project_root / "proxies", CACHE_CLEANUP_DEFAULTS_MB["proxies"]),
                ("chunks", project_root / "chunks", CACHE_CLEANUP_DEFAULTS_MB["chunks"]),
            ],
            self.params,
        )
        deleted_files = int(summary.get("deleted_files") or 0)
        deleted_bytes = int(summary.get("deleted_bytes") or 0)
        if deleted_files > 0:
            emit_event(
                "log",
                message=f"Project cache cleanup: deleted_files={deleted_files}, deleted_bytes={deleted_bytes}",
            )
        self.cache_cleanup_stats = summary
        return summary

    def _cache_path(self, kind: str, source: Path, suffix: str, extra: str = "") -> Path:
        bucket = self.render_cache_dir / kind
        bucket.mkdir(parents=True, exist_ok=True)
        key_extra = f"{extra}|target={self.target_size[0]}x{self.target_size[1]}"
        key = file_hash_light(source, key_extra) if source.exists() else safe_id(f"{source}|{key_extra}")
        return bucket / f"{key}{suffix}"

    def _cache_bucket_path(self, kind: str, suffix: str, key: str) -> Path:
        bucket = self.render_cache_dir / kind
        bucket.mkdir(parents=True, exist_ok=True)
        return bucket / f"{safe_id(key)}{suffix}"

    def _cache_identity_for_source(self, source_path: Optional[str], role: str) -> str:
        if not source_path:
            return f"{role}:none"
        source = Path(str(source_path))
        if not source.exists():
            return f"{role}:missing:{source}"
        return f"{role}:{file_hash_light(source, role)}"

    def _visual_stage_audio_cache_payload(self) -> Dict[str, Any]:
        return {
            "keep_source_audio": bool(self.audio_settings.get("keep_source_audio", True)),
            "source_audio_volume": float(self.audio_settings.get("source_audio_volume", 1.0)),
            "normalize_audio": bool(self.audio_settings.get("normalize_audio", False)),
            "target_lufs": float(self.audio_settings.get("target_lufs", -16.0)),
        }

    def _should_prerender_image_segment(self, duration: float, motion_config: Optional[Dict[str, Any]] = None) -> bool:
        performance_mode = str(self.params.get("performance_mode") or self.plan.get("render_settings", {}).get("performance_mode") or "").lower()
        render_mode = str(self.params.get("render_mode") or self.plan.get("render_settings", {}).get("render_mode") or "").lower()
        total_duration = float(self.plan.get("total_duration") or 0.0)
        segments = list(self.plan.get("segments", []) or [])
        segment_count = len(segments)
        motion_type = str((motion_config or {}).get("type") or "none")
        if motion_type not in {"none", "still_hold", "gentle_push", "slow_push", "ken_burns", "subtle_ken_burns", "punch_zoom", "micro_zoom"}:
            return False
        large_project = (
            performance_mode == "stable"
            or render_mode == "long_stable"
            or _should_auto_use_stable_renderer(total_duration, segments, self.params)
        )
        medium_project = (
            performance_mode in {"balanced", "quality"}
            and (
                total_duration >= float(STABLE_RENDER_DEFAULTS["image_heavy_seconds"])
                or segment_count >= int(STABLE_RENDER_DEFAULTS["image_heavy_segments"])
            )
        )
        return (
            large_project
            or medium_project
        ) and float(duration or 0.0) > 0.1

    def _ffmpeg_image_motion_cache_spec(self, motion_config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        motion_type = str((motion_config or {}).get("type") or "none")
        if motion_type in {"none", "still_hold"}:
            return {"type": motion_type, "amount": 0.0}
        if motion_type == "gentle_push":
            return {"type": motion_type, "amount": 0.018}
        if motion_type == "slow_push":
            return {"type": motion_type, "amount": 0.015}
        return None

    def _can_use_ffmpeg_image_chunk_segment(self, seg: Dict[str, Any]) -> bool:
        return _v56_is_ffmpeg_image_chunk_candidate(seg, self.params)

    def _can_use_ffmpeg_card_chunk_segment(self, seg: Dict[str, Any]) -> bool:
        return _v56_is_ffmpeg_card_chunk_candidate(seg, self.params)

    def _build_image_visual_clip(self, fixed: Path, duration: float, motion_config: Optional[Dict[str, Any]] = None):
        fg = ImageClip(str(fixed)).set_duration(duration)
        return self._compose_with_blur_bg(fg, duration, source_image=fixed, motion_config=motion_config)

    def _build_image_segment_clip(
        self,
        fixed: Path,
        duration: float,
        motion_config: Optional[Dict[str, Any]] = None,
        overlay_spec: Optional[Dict[str, Any]] = None,
    ):
        clip = self._build_image_visual_clip(fixed, duration, motion_config)
        if overlay_spec and overlay_spec.get("text"):
            clip = self._apply_overlay_title(
                clip,
                {
                    "overlay_text": overlay_spec.get("text"),
                    "overlay_subtitle": overlay_spec.get("subtitle"),
                    "overlay_duration": overlay_spec.get("duration"),
                    "overlay_title_style": overlay_spec.get("style"),
                },
            )
        return clip

    def _prerender_image_segment(
        self,
        source: Path,
        fixed: Path,
        duration: float,
        motion_config: Optional[Dict[str, Any]] = None,
        overlay_spec: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        motion_key = json.dumps(motion_config or {}, ensure_ascii=False, sort_keys=True)
        overlay_key = json.dumps(overlay_spec or {}, ensure_ascii=False, sort_keys=True)
        has_overlay = bool((overlay_spec or {}).get("text"))
        out = self._cache_path(
            "photo_segments",
            source,
            ".mp4",
            f"photo_seg_v4|duration={round(float(duration or 0.0), 3)}|fps={fps}|motion={motion_key}|overlay={overlay_key}",
        )
        if out.exists() and out.stat().st_size > 1024:
            self.photo_segment_cache_stats["hit"] += 1
            self.photo_segment_cache_stats["saved_live_composes"] += 1
            self.photo_segment_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
            if has_overlay:
                self.photo_segment_cache_stats["overlay_hit"] += 1
            emit_event("log", message=f"Photo segment cache hit: {out.name}")
            return out

        clip = None
        try:
            clip = self._build_image_segment_clip(fixed, duration, motion_config, overlay_spec=overlay_spec)
            clip.write_videofile(
                str(out),
                fps=fps,
                codec="libx264",
                audio=False,
                preset="veryfast",
                threads=1,
                verbose=False,
                logger=None,
                ffmpeg_params=[
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-crf",
                    quality_to_crf(self.params.get("python_quality") or self.params.get("quality") or "standard"),
                ],
            )
            ok, _reason, _duration = _v56_validate_video(out, min_size=512)
            if ok:
                self.photo_segment_cache_stats["created"] += 1
                if has_overlay:
                    self.photo_segment_cache_stats["overlay_created"] += 1
                emit_event("log", message=f"Photo segment cache created: {out.name}")
                return out
        except Exception as exc:
            self.photo_segment_cache_stats["fallback"] += 1
            emit_event("log", message=f"Photo segment prerender fallback to live compose: {source.name}: {exc}")
        finally:
            if clip is not None:
                close_clip(clip)
            clip = None
            try:
                gc.collect()
            except Exception:
                pass

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return None

    def _ffmpeg_prerender_image_segment(
        self,
        source: Path,
        fixed: Path,
        duration: float,
        motion_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        motion_spec = self._ffmpeg_image_motion_cache_spec(motion_config)
        if motion_spec is None:
            return None

        fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        motion_key = json.dumps(motion_spec, ensure_ascii=False, sort_keys=True)
        out = self._cache_path(
            "photo_segments_ffmpeg",
            source,
            ".mp4",
            f"photo_seg_ffmpeg_v1|duration={round(float(duration or 0.0), 3)}|fps={fps}|motion={motion_key}",
        )
        if out.exists() and out.stat().st_size > 1024:
            emit_event("log", message=f"FFmpeg image segment cache hit: {out.name}")
            return out

        bg_path = self._blur_bg(fixed)
        segment_duration = max(float(duration or 0.1), 0.1)
        tw, th = self.target_size

        try:
            with Image.open(fixed) as img:
                iw, ih = img.size
        except Exception:
            return None

        base_scale = min(float(tw) / float(max(1, iw)), float(th) / float(max(1, ih)))
        base_w = max(2, int(round((iw * base_scale) / 2.0)) * 2)
        base_h = max(2, int(round((ih * base_scale) / 2.0)) * 2)
        amount = float(motion_spec.get("amount") or 0.0)

        fg_filter = f"[1:v]scale={base_w}:{base_h}[fg]"
        if amount > 0:
            zoom_expr = f"(1+{amount:.6f}*t/{segment_duration:.6f})"
            fg_filter = (
                "[1:v]"
                f"scale='max(2,trunc({base_w}*{zoom_expr}/2)*2)':"
                f"'max(2,trunc({base_h}*{zoom_expr}/2)*2)':eval=frame"
                "[fg]"
            )
        filter_complex = ";".join(
            [
                f"[0:v]scale={tw}:{th},setsar=1[bg]",
                fg_filter,
                "[bg][fg]overlay=(W-w)/2:(H-h)/2:eval=frame,format=yuv420p[outv]",
            ]
        )

        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            selected_encoder, encoder_args = select_ffmpeg_video_encoder(self.params)

            def build_cmd(video_encoder: str, video_encoder_args: List[str]) -> List[str]:
                cmd = [
                    ffmpeg,
                    "-y",
                    "-loop",
                    "1",
                    "-framerate",
                    str(fps),
                    "-t",
                    f"{segment_duration:.6f}",
                    "-i",
                    str(bg_path),
                    "-loop",
                    "1",
                    "-framerate",
                    str(fps),
                    "-t",
                    f"{segment_duration:.6f}",
                    "-i",
                    str(fixed),
                    "-filter_complex",
                    filter_complex,
                    "-map",
                    "[outv]",
                    "-r",
                    str(fps),
                    "-an",
                    "-c:v",
                    video_encoder,
                ]
                cmd += video_encoder_args
                if video_encoder == "libx264":
                    cmd += ["-crf", quality_to_crf(self.params.get("python_quality") or self.params.get("quality") or "standard")]
                else:
                    cmd += ["-b:v", "8M"]
                cmd += ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
                return cmd

            completed = subprocess.run(build_cmd(selected_encoder, encoder_args), capture_output=True, text=True, encoding="utf-8", errors="replace")
            if completed.returncode != 0 and selected_encoder != "libx264":
                emit_event("log", message=f"FFmpeg image segment {selected_encoder} fallback to libx264: {completed.stderr[-600:]}")
                completed = subprocess.run(
                    build_cmd("libx264", ["-preset", "veryfast"]),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            if completed.returncode == 0 and out.exists() and out.stat().st_size > 1024:
                emit_event("log", message=f"FFmpeg image segment cache created: {out.name}")
                return out
            emit_event("log", message=f"FFmpeg image segment fallback to MoviePy: {source.name}: {completed.stderr[-600:]}")
        except Exception as exc:
            emit_event("log", message=f"FFmpeg image segment raised, fallback to MoviePy: {source.name}: {exc}")

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return None

    def _photo_segment_cache_summary(self) -> Dict[str, int]:
        return dict(self.photo_segment_cache_stats)

    def _emit_photo_segment_cache_summary(self) -> None:
        photo_cache = self._photo_segment_cache_summary()
        if photo_cache["eligible"] <= 0:
            return
        emit_event(
            "log",
            message=(
                "Photo segment cache summary: "
                f"eligible={photo_cache['eligible']}, "
                f"hit={photo_cache['hit']}, "
                f"created={photo_cache['created']}, "
                f"fallback={photo_cache['fallback']}, "
                f"overlay_hit={photo_cache['overlay_hit']}, "
                f"saved_live_composes={photo_cache['saved_live_composes']}, "
                f"saved_render_seconds={photo_cache['saved_render_seconds']}"
            ),
        )
        emit_event("photo_cache", **photo_cache)

    def _should_prerender_card_segment(self, seg: Dict[str, Any], duration: float) -> bool:
        return str(seg.get("type") or "") in {"title", "chapter", "end"} and float(duration or 0.0) > 0.1

    def _build_card_segment_clip(self, seg: Dict[str, Any], duration: float):
        stype = str(seg.get("type") or "")
        if stype == "title":
            background_source = self.params.get("title_background_path") or self.first_visual_source
            return self._text_card(
                seg.get("text") or "",
                seg.get("subtitle"),
                duration,
                main=True,
                background_source=background_source,
                background_position="first",
                title_style=self.params.get("title_style") or seg.get("title_style"),
            )
        if stype == "end":
            background_source = self.params.get("end_background_path") or self.last_visual_source
            return self._text_card(
                seg.get("text") or "",
                seg.get("subtitle"),
                duration,
                main=False,
                background_source=background_source,
                background_position="last",
                title_style=self.params.get("end_title_style") or seg.get("title_style"),
            )
        return self._chapter_card(seg, duration)

    def _card_segment_cache_path(self, seg: Dict[str, Any], duration: float) -> Path:
        stype = str(seg.get("type") or "")
        if stype == "title":
            background_source = self.params.get("title_background_path") or self.first_visual_source
            background_position = "first"
            background_source_2 = None
            background_position_2 = "first"
            blend_sources = False
            title_style = self.params.get("title_style") or seg.get("title_style")
            main = True
        elif stype == "end":
            background_source = self.params.get("end_background_path") or self.last_visual_source
            background_position = "last"
            background_source_2 = None
            background_position_2 = "first"
            blend_sources = False
            title_style = self.params.get("end_title_style") or seg.get("title_style")
            main = False
        else:
            background_source = seg.get("background_source_path")
            background_position = seg.get("background_source_position") or "first"
            background_source_2 = seg.get("background_source_path_2")
            background_position_2 = seg.get("background_source_position_2") or "first"
            blend_sources = bool((seg.get("background_mode") or "bridge_blur") == "bridge_blur")
            title_style = seg.get("title_style")
            main = False

        fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        key_payload = {
            "version": "card_seg_v1",
            "segment_id": seg.get("segment_id"),
            "segment_type": stype,
            "duration": round(float(duration or 0.0), 3),
            "text": seg.get("text"),
            "subtitle": seg.get("subtitle"),
            "title_style": title_style or {},
            "main": main,
            "background_mode": seg.get("background_mode"),
            "background_position": background_position,
            "background_position_2": background_position_2,
            "blend_sources": blend_sources,
            "fps": fps,
            "target_size": list(self.target_size),
            "source_1": self._cache_identity_for_source(background_source, "source_1"),
            "source_2": self._cache_identity_for_source(background_source_2, "source_2"),
        }
        return self._cache_bucket_path(
            "card_segments",
            ".mp4",
            json.dumps(key_payload, ensure_ascii=False, sort_keys=True),
        )

    def _prerender_card_segment(self, seg: Dict[str, Any], duration: float) -> Optional[Path]:
        stype = str(seg.get("type") or "")
        out = self._card_segment_cache_path(seg, duration)
        if out.exists() and out.stat().st_size > 1024:
            self.card_segment_cache_stats["hit"] += 1
            self.card_segment_cache_stats["saved_live_composes"] += 1
            self.card_segment_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
            emit_event("log", message=f"Card segment cache hit: {out.name}")
            return out

        clip = None
        fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        try:
            clip = self._build_card_segment_clip(seg, duration)
            clip.write_videofile(
                str(out),
                fps=fps,
                codec="libx264",
                audio=False,
                preset="veryfast",
                threads=1,
                verbose=False,
                logger=None,
                ffmpeg_params=[
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-crf",
                    quality_to_crf(self.params.get("python_quality") or self.params.get("quality") or "standard"),
                ],
            )
            ok, _reason, _duration = _v56_validate_video(out, min_size=512)
            if ok:
                self.card_segment_cache_stats["created"] += 1
                emit_event("log", message=f"Card segment cache created: {out.name}")
                return out
        except Exception as exc:
            self.card_segment_cache_stats["fallback"] += 1
            emit_event("log", message=f"Card segment prerender fallback to live compose: {seg.get('segment_id') or stype}: {exc}")
        finally:
            if clip is not None:
                close_clip(clip)
            clip = None
            try:
                gc.collect()
            except Exception:
                pass

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return None

    def _cached_card_segment(self, seg: Dict[str, Any], duration: float):
        if not self._should_prerender_card_segment(seg, duration):
            return self._build_card_segment_clip(seg, duration)
        self.card_segment_cache_stats["eligible"] += 1
        cached = self._prerender_card_segment(seg, duration)
        if cached is not None and cached.exists():
            return VideoFileClip(str(cached))
        return self._build_card_segment_clip(seg, duration)

    def _card_segment_cache_summary(self) -> Dict[str, int]:
        return dict(self.card_segment_cache_stats)

    def _emit_card_segment_cache_summary(self) -> None:
        card_cache = self._card_segment_cache_summary()
        if card_cache["eligible"] <= 0:
            return
        emit_event(
            "log",
            message=(
                "Card segment cache summary: "
                f"eligible={card_cache['eligible']}, "
                f"hit={card_cache['hit']}, "
                f"created={card_cache['created']}, "
                f"fallback={card_cache['fallback']}, "
                f"saved_live_composes={card_cache['saved_live_composes']}, "
                f"saved_render_seconds={card_cache['saved_render_seconds']}"
            ),
        )
        emit_event("card_cache", **card_cache)

    def _standard_visual_cache_path(self) -> Path:
        fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        key_payload = {
            "version": "standard_visual_base_v1",
            "engine_version": ENGINE_VERSION,
            "segments": self.plan.get("segments", []) or [],
            "aspect_ratio": self.params.get("aspect_ratio") or self.plan.get("render_settings", {}).get("aspect_ratio"),
            "fps": fps,
            "quality": self.params.get("quality") or self.plan.get("render_settings", {}).get("quality"),
            "python_quality": self.params.get("python_quality"),
            "preview": bool(self.params.get("preview")),
            "preview_height": self.params.get("preview_height"),
            "watermark": self.params.get("watermark"),
            "target_size": list(self.target_size),
            "audio_visual": self._visual_stage_audio_cache_payload(),
        }
        return self._cache_bucket_path(
            "final_video_bases",
            ".mp4",
            json.dumps(key_payload, ensure_ascii=False, sort_keys=True),
        )

    def _emit_visual_base_cache_summary(self) -> None:
        stats = dict(self.visual_base_cache_stats)
        if stats["eligible"] <= 0:
            return
        emit_event(
            "log",
            message=(
                "Visual base cache summary: "
                f"eligible={stats['eligible']}, "
                f"hit={stats['hit']}, "
                f"created={stats['created']}, "
                f"fallback={stats['fallback']}, "
                f"chunk_groups={stats['chunk_groups']}, "
                f"chunk_hit={stats['chunk_hit']}, "
                f"chunk_created={stats['chunk_created']}, "
                f"saved_render_seconds={stats['saved_render_seconds']}"
            ),
        )
        emit_event("visual_base_cache", **stats)

    def _should_use_chunked_visual_base(self) -> bool:
        if self.params.get("watermark"):
            return False
        segments = list(self.plan.get("segments") or [])
        if len(segments) < 2:
            return False
        enabled = self.params.get("visual_base_chunk_cache")
        if enabled is None:
            enabled = True
        return bool(enabled)

    def _is_safe_standard_visual_chunk_boundary(self, next_seg: Dict[str, Any]) -> bool:
        transition = next_seg.get("transition_config") or {}
        transition_type = str(transition.get("type") or next_seg.get("transition") or "none")
        transition_duration = float(transition.get("duration") or 0.0)
        return transition_type in {"none", "cut"} and transition_duration <= 0.05

    def _standard_visual_transition_influence(self, seg: Dict[str, Any]) -> Dict[str, Any]:
        transition = seg.get("transition_config") or {}
        transition_type = str(transition.get("type") or seg.get("transition") or "none")
        transition_duration = float(transition.get("duration") or 0.0)
        if transition_type in {"none", "cut"} and transition_duration <= 0.05:
            return {"type": transition_type, "backward": 0, "forward": 0, "safe_split": True}

        transition_influence_map = {
            "soft_crossfade": {"backward": 1, "forward": 0, "safe_split": False},
            "quick_zoom": {"backward": 1, "forward": 0, "safe_split": False},
            "flash_cut": {"backward": 1, "forward": 0, "safe_split": False},
            "fade_through_dark": {"backward": 1, "forward": 1, "safe_split": False},
            "fade_through_white": {"backward": 1, "forward": 1, "safe_split": False},
        }
        influence = transition_influence_map.get(
            transition_type,
            {"backward": 1, "forward": 1, "safe_split": False},
        )
        return {"type": transition_type, **influence}

    def _standard_visual_chunk_route_payload(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        routes = [str(seg.get("runtime_render_route") or seg.get("render_route") or "moviepy_required") for seg in items]
        route_counts: Dict[str, int] = {}
        for route in routes:
            route_counts[route] = route_counts.get(route, 0) + 1
        if items and all(route == "direct_chunk_candidate" for route in routes):
            return {
                "runtime_chunk_route": "ffmpeg_direct_chunk",
                "runtime_chunk_route_reason": "all_segments_direct_chunk_safe",
                "runtime_chunk_route_tags": ["ffmpeg", "chunk", "direct", "visual_base"],
                "runtime_chunk_route_counts": route_counts,
            }
        if items and all(_v56_is_ffmpeg_fitted_video_chunk_route(route) for route in routes):
            return {
                "runtime_chunk_route": "ffmpeg_fitted_video_chunk",
                "runtime_chunk_route_reason": "all_segments_ffmpeg_fitted_video_safe",
                "runtime_chunk_route_tags": ["ffmpeg", "chunk", "video_fit", "visual_base"],
                "runtime_chunk_route_counts": route_counts,
            }
        if items and all(self._can_use_ffmpeg_card_chunk_segment(seg) for seg in items):
            return {
                "runtime_chunk_route": "ffmpeg_card_chunk",
                "runtime_chunk_route_reason": "all_segments_ffmpeg_card_chunk_safe",
                "runtime_chunk_route_tags": ["ffmpeg", "chunk", "card", "visual_base"],
                "runtime_chunk_route_counts": route_counts,
            }
        if items and all(self._can_use_ffmpeg_image_chunk_segment(seg) for seg in items):
            return {
                "runtime_chunk_route": "ffmpeg_image_chunk",
                "runtime_chunk_route_reason": "all_segments_ffmpeg_image_chunk_safe",
                "runtime_chunk_route_tags": ["ffmpeg", "chunk", "image", "visual_base"],
                "runtime_chunk_route_counts": route_counts,
            }
        return {
            "runtime_chunk_route": "moviepy_chunk",
            "runtime_chunk_route_reason": "safe_cut_boundary_visual_chunk",
            "runtime_chunk_route_tags": ["moviepy", "chunk", "timeline", "visual_base"],
            "runtime_chunk_route_counts": route_counts,
        }

    def _build_standard_visual_transition_units(self) -> List[List[Dict[str, Any]]]:
        segments = list(self.plan.get("segments") or [])
        if not segments:
            return []
        ranges: List[Tuple[int, int]] = []
        for idx, seg in enumerate(segments):
            influence = self._standard_visual_transition_influence(seg)
            if influence.get("safe_split"):
                continue
            start = max(0, idx - int(influence.get("backward") or 0))
            end = min(len(segments) - 1, idx + int(influence.get("forward") or 0))
            ranges.append((start, end))

        merged_ranges: List[Tuple[int, int]] = []
        for start, end in ranges:
            if not merged_ranges or start > merged_ranges[-1][1] + 1:
                merged_ranges.append((start, end))
            else:
                prev_start, prev_end = merged_ranges[-1]
                merged_ranges[-1] = (prev_start, max(prev_end, end))

        units: List[List[Dict[str, Any]]] = []
        cursor = 0
        for start, end in merged_ranges:
            while cursor < start:
                units.append([segments[cursor]])
                cursor += 1
            units.append(segments[start:end + 1])
            cursor = end + 1
        while cursor < len(segments):
            units.append([segments[cursor]])
            cursor += 1
        return units

    def _build_standard_visual_chunk_groups(self) -> List[Dict[str, Any]]:
        units = self._build_standard_visual_transition_units()
        if not units:
            return []
        max_segments = max(2, int(self.params.get("visual_base_chunk_max_segments") or 6))
        max_seconds = max(4.0, float(self.params.get("visual_base_chunk_seconds") or 20.0))
        groups: List[Dict[str, Any]] = []
        current: List[Dict[str, Any]] = []
        current_duration = 0.0
        current_keys: List[str] = []
        current_segment_count = 0
        current_family: Optional[str] = None

        def flush() -> None:
            nonlocal current, current_duration, current_keys, current_segment_count, current_family
            if not current:
                return
            groups.append({
                "index": len(groups),
                "segments": list(current),
                "duration": round(current_duration, 3),
                "cache_key": _v56_stable_json_hash(current_keys),
                **self._standard_visual_chunk_route_payload(current),
            })
            current = []
            current_duration = 0.0
            current_keys = []
            current_segment_count = 0
            current_family = None

        for unit in units:
            unit_duration = sum(float(seg.get("duration") or 0.0) for seg in unit)
            unit_segment_count = len(unit)
            unit_family = "timeline"
            if unit and all(_v56_chunk_route_family(seg, self.params) == "direct" for seg in unit):
                unit_family = "direct"
            elif unit and all(_v56_chunk_route_family(seg, self.params) == "card" for seg in unit):
                unit_family = "card"
            elif unit and all(_v56_chunk_route_family(seg, self.params) == "image" for seg in unit):
                unit_family = "image"
            if current:
                count_exceeded = (current_segment_count + unit_segment_count) > max_segments
                time_exceeded = (current_duration + unit_duration) > max_seconds
                family_changed = current_family != unit_family
                if count_exceeded or time_exceeded or family_changed:
                    flush()
            current.extend(unit)
            current_duration += unit_duration
            current_segment_count += unit_segment_count
            current_family = unit_family
            for seg in unit:
                current_keys.append(_v56_segment_cache_key(seg, self.params))

        flush()
        return groups

    def _render_visual_timeline_clip(self) -> Tuple[Any, List[Dict[str, Any]]]:
        clips: List[Any] = []
        rendered_segments: List[Dict[str, Any]] = []
        segments = self.plan.get("segments", [])
        total = max(1, len(segments))
        self._emit_render_scheduler_summary()

        for idx, seg in enumerate(segments, 1):
            emit_event(
                "phase",
                phase="render",
                message=f"Processing segment {idx}/{total}: {seg.get('type')}",
                percent=min(90, int(idx / total * 90)),
            )
            clip = self._segment(seg)
            if clip is not None:
                clips.append(clip)
                rendered_segments.append(seg)

        if not clips:
            raise RuntimeError("No valid clips generated")

        emit_event("phase", phase="render", message="Composing final video timeline", percent=91)
        final = self._compose_timeline(clips, rendered_segments)

        if self.params.get("watermark"):
            emit_event("phase", phase="render", message="Applying watermark", percent=92)
            final = self._add_watermark(final, str(self.params.get("watermark")))

        return final, rendered_segments

    def _write_visual_base_video(self, output_path: Path) -> float:
        final = None
        duration = 0.0
        try:
            final, _rendered_segments = self._render_visual_timeline_clip()
            duration = float(getattr(final, "duration", 0.0) or 0.0)
            logger = JsonMoviePyLogger(base_percent=92, span_percent=7)
            final.write_videofile(
                str(output_path),
                fps=int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30),
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                threads=4,
                temp_audiofile=str(self.temp_dir / "temp_audio.m4a"),
                remove_temp=True,
                ffmpeg_params=[
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-crf",
                    quality_to_crf(self.params.get("python_quality") or self.params.get("quality")),
                ],
                logger=logger,
            )
            return duration
        finally:
            if final is not None:
                close_clip(final)

    def _write_visual_base_video_from_chunks(self, output_path: Path) -> Optional[float]:
        if not self._should_use_chunked_visual_base():
            return None
        groups = self._build_standard_visual_chunk_groups()
        if len(groups) < 2:
            return None

        self.visual_base_cache_stats["chunk_groups"] = max(
            int(self.visual_base_cache_stats.get("chunk_groups") or 0),
            len(groups),
        )
        chunk_bucket = self.render_cache_dir / "visual_base_chunks"
        chunk_bucket.mkdir(parents=True, exist_ok=True)
        chunk_work_dir = self.render_cache_dir / "visual_base_chunk_work"
        chunk_work_dir.mkdir(parents=True, exist_ok=True)

        rendered_chunks: List[Path] = []
        for group in groups:
            chunk_path = chunk_bucket / f"{group['cache_key']}.mp4"
            ok, _reason, _duration = _v56_validate_video(chunk_path, min_size=512)
            if ok:
                self.visual_base_cache_stats["chunk_hit"] += 1
                rendered_chunks.append(chunk_path)
                emit_event("log", message=f"Visual base chunk cache hit: {chunk_path.name}")
                continue
            _v56_write_chunk_video(
                self,
                group,
                chunk_path,
                int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30),
                self.params,
                ensure_audio_track=False,
            )
            ok, reason, _duration = _v56_validate_video(chunk_path, min_size=512)
            if not ok:
                raise RuntimeError(f"visual base chunk validation failed: {reason}")
            self.visual_base_cache_stats["chunk_created"] += 1
            rendered_chunks.append(chunk_path)
            emit_event("log", message=f"Visual base chunk cache created: {chunk_path.name}")

        tmp_output = output_path.with_suffix(".assembling.tmp.mp4")
        try:
            if tmp_output.exists():
                tmp_output.unlink()
        except Exception:
            pass

        concat_ok = _v56_concat_chunks_ffmpeg(rendered_chunks, tmp_output, chunk_work_dir)
        if not concat_ok:
            concat_ok = _v56_concat_chunks_ffmpeg_reencode(
                rendered_chunks,
                tmp_output,
                chunk_work_dir,
                int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30),
                self.params,
            )
        if not concat_ok:
            _v56_concat_chunks_moviepy(
                rendered_chunks,
                tmp_output,
                int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30),
                self.params,
            )

        ok, reason, duration = _v56_validate_video(tmp_output, min_size=512)
        if not ok:
            raise RuntimeError(f"visual base chunk concat failed: {reason}")
        _v56_atomic_replace(tmp_output, output_path)
        return float(duration or 0.0)

    def _materialize_standard_visual_base(self) -> Tuple[Path, float]:
        self.visual_base_cache_stats["eligible"] += 1
        out = self._standard_visual_cache_path()
        ok, _reason, duration = _v56_validate_video(out, min_size=512)
        if ok:
            self.visual_base_cache_stats["hit"] += 1
            self.visual_base_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
            emit_event("log", message=f"Visual base cache hit: {out.name}")
            return out, float(duration or 0.0)

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass

        try:
            duration = self._write_visual_base_video_from_chunks(out)
            if duration is None:
                duration = self._write_visual_base_video(out)
            ok, _reason, validated_duration = _v56_validate_video(out, min_size=512)
            if ok:
                self.visual_base_cache_stats["created"] += 1
                emit_event("log", message=f"Visual base cache created: {out.name}")
                return out, float(validated_duration or duration or 0.0)
        except Exception:
            self.visual_base_cache_stats["fallback"] += 1
            raise

        self.visual_base_cache_stats["fallback"] += 1
        raise RuntimeError("Failed to materialize standard visual base video")

    def _finalize_output_from_visual_base(self, visual_base_path: Path, output_path: Path, duration: float) -> float:
        mixed_output = output_path.with_suffix(".audio.tmp.mp4")
        finalize_started = perf_counter()
        try:
            if mixed_output.exists():
                mixed_output.unlink()
        except Exception:
            pass

        final_duration = float(duration or 0.0)
        finalize_summary = {
            "audio_mix_attempted": False,
            "audio_mix_applied": False,
            "copy_through_used": False,
            "audio_mix_seconds": 0.0,
            "copy_through_seconds": 0.0,
            "total_finalize_seconds": 0.0,
        }
        audio_mix_started = perf_counter()
        if _v56_apply_final_bgm_mix(
            visual_base_path,
            mixed_output,
            self.audio_settings,
            final_duration,
            prepared_bgm_path=self._prepare_music_bed(final_duration) or self._prepare_music_path(),
            prepared_bgm_is_bed=True,
        ):
            finalize_summary["audio_mix_attempted"] = True
            finalize_summary["audio_mix_applied"] = True
            finalize_summary["audio_mix_seconds"] = round(perf_counter() - audio_mix_started, 4)
            ok, reason, validated_duration = _v56_validate_video(mixed_output, min_size=512)
            if not ok:
                raise RuntimeError(f"visual base validation failed: {reason}")
            _v56_atomic_replace(mixed_output, output_path)
            finalize_summary["total_finalize_seconds"] = round(perf_counter() - finalize_started, 4)
            self.last_visual_finalize_summary = finalize_summary
            return float(validated_duration or final_duration)

        finalize_summary["audio_mix_attempted"] = True
        finalize_summary["audio_mix_seconds"] = round(perf_counter() - audio_mix_started, 4)
        copy_started = perf_counter()
        ensure_parent(output_path)
        if output_path.exists():
            output_path.unlink()
        shutil.copy2(visual_base_path, output_path)
        finalize_summary["copy_through_used"] = True
        finalize_summary["copy_through_seconds"] = round(perf_counter() - copy_started, 4)
        ok, reason, validated_duration = _v56_validate_video(output_path, min_size=512)
        if not ok:
            raise RuntimeError(f"visual base final validation failed: {reason}")
        finalize_summary["total_finalize_seconds"] = round(perf_counter() - finalize_started, 4)
        self.last_visual_finalize_summary = finalize_summary
        return float(validated_duration or final_duration)

    def _video_segment_cache_summary(self) -> Dict[str, int]:
        return dict(self.video_segment_cache_stats)

    def _emit_video_segment_cache_summary(self) -> None:
        video_cache = self._video_segment_cache_summary()
        if video_cache["eligible"] <= 0:
            return
        emit_event(
            "log",
            message=(
                "Video segment cache summary: "
                f"eligible={video_cache['eligible']}, "
                f"hit={video_cache['hit']}, "
                f"created={video_cache['created']}, "
                f"fallback={video_cache['fallback']}, "
                f"motion_hit={video_cache['motion_hit']}, "
                f"saved_live_fits={video_cache['saved_live_fits']}, "
                f"saved_render_seconds={video_cache['saved_render_seconds']}"
            ),
        )
        emit_event("video_cache", **video_cache)

    def _proxy_media_summary(self) -> Dict[str, int]:
        return dict(self.proxy_media_stats)

    def _emit_proxy_media_summary(self) -> None:
        proxy_cache = self._proxy_media_summary()
        if proxy_cache["eligible"] <= 0:
            return
        emit_event(
            "log",
            message=(
                "Proxy media summary: "
                f"eligible={proxy_cache['eligible']}, "
                f"hit={proxy_cache['hit']}, "
                f"manifest_hit={proxy_cache['manifest_hit']}, "
                f"created={proxy_cache['created']}, "
                f"fallback={proxy_cache['fallback']}"
            ),
        )
        emit_event("proxy_cache", **proxy_cache)

    def _prepare_music_path(self) -> Optional[Path]:
        paths = self._prepare_music_paths()
        return paths[0] if paths else None

    def _prepare_music_paths(self) -> List[Path]:
        if self._prepared_music_paths:
            return [path for path in self._prepared_music_paths if path.exists()]

        raw_paths: List[str] = []
        playlist_paths = self.audio_settings.get("music_playlist_paths")
        if isinstance(playlist_paths, list):
            raw_paths.extend(str(item) for item in playlist_paths if item)

        music_path = self.audio_settings.get("music_path")
        if music_path and str(music_path) not in raw_paths:
            raw_paths.insert(0, str(music_path))

        prepared: List[Path] = []
        for raw in raw_paths:
            source = Path(str(raw))
            if not source.exists():
                continue
            try:
                prepared.append(prepare_cached_audio_for_mix(
                    source,
                    self.audio_cache_dir,
                    normalize_audio=bool(self.audio_settings.get("normalize_audio", False)),
                    target_lufs=float(self.audio_settings.get("target_lufs", -16.0) or -16.0),
                ))
            except Exception as exc:
                emit_event("log", message=f"Audio cache fallback to source: {exc}")
                prepared.append(source)
        self._prepared_music_paths = prepared
        return [path for path in prepared if path.exists()]

    def _prepare_music_bed(self, duration: float) -> Optional[Path]:
        duration = max(0.1, float(duration or 0.0))
        audio_blueprint = self.plan.get("render_settings", {}).get("audio_blueprint") or {}
        chapter_cues = audio_blueprint.get("timeline_cues") if isinstance(audio_blueprint, dict) else None
        cache_key = f"{duration:.3f}|{json.dumps({'audio': {k: self.audio_settings.get(k) for k in ('music_fit_strategy', 'music_playlist_mode', 'music_playlist_paths', 'music_path', 'fade_in_seconds', 'fade_out_seconds', 'music_chapter_restart')}, 'chapter_cues': chapter_cues}, ensure_ascii=False, sort_keys=True)}"
        if cache_key in self._prepared_music_beds:
            prepared = self._prepared_music_beds[cache_key]
            if prepared is None or prepared.exists():
                return prepared

        prepared_tracks = self._prepare_music_paths()
        if not prepared_tracks:
            self._prepared_music_beds[cache_key] = None
            return None

        playlist_mode = str(self.audio_settings.get("music_playlist_mode") or "single").lower()
        chapter_restart_enabled = bool(self.audio_settings.get("music_chapter_restart", False)) or playlist_mode == "chapter_restart"
        if chapter_restart_enabled and isinstance(chapter_cues, list) and chapter_cues:
            music_bed = build_chapter_restart_music_bed(
                prepared_tracks,
                chapter_cues,
                duration,
                self.audio_cache_dir,
                playlist_mode=playlist_mode,
                fit_strategy=str(self.audio_settings.get("music_fit_strategy") or "auto"),
                fade_in=float(self.audio_settings.get("fade_in_seconds", 0.0) or 0.0),
                fade_out=float(self.audio_settings.get("fade_out_seconds", 0.0) or 0.0),
            )
            self._prepared_music_beds[cache_key] = music_bed
            return music_bed

        music_bed = build_music_bed_for_duration(
            prepared_tracks,
            duration,
            self.audio_cache_dir,
            fit_strategy=str(self.audio_settings.get("music_fit_strategy") or "auto"),
            fade_in=float(self.audio_settings.get("fade_in_seconds", 0.0) or 0.0),
            fade_out=float(self.audio_settings.get("fade_out_seconds", 0.0) or 0.0),
        )
        self._prepared_music_beds[cache_key] = music_bed
        return music_bed

    def _prepare_source_audio_path(self, source: Path) -> Optional[Path]:
        cache_key = str(source.resolve()) if source.exists() else str(source)
        if cache_key in self._prepared_source_audio_paths:
            prepared = self._prepared_source_audio_paths[cache_key]
            if prepared is None or prepared.exists():
                return prepared

        if not source.exists() or not video_has_audio_stream(source):
            self._prepared_source_audio_paths[cache_key] = None
            return None

        try:
            # Normalize embedded source audio into the same cache contract so
            # stable-mode optimizations do not flatten or silently drop it.
            prepared = prepare_cached_audio_for_mix(
                source,
                self.audio_cache_dir,
                normalize_audio=bool(self.audio_settings.get("normalize_audio", False)),
                target_lufs=float(self.audio_settings.get("target_lufs", -16.0) or -16.0),
            )
        except Exception as exc:
            emit_event("log", message=f"Source audio cache fallback to embedded track: {exc}")
            prepared = None
        self._prepared_source_audio_paths[cache_key] = prepared
        return prepared

    def _should_prefer_ffmpeg_segments(self, settings: Dict[str, Any]) -> bool:
        performance_mode = str(self.params.get("performance_mode") or settings.get("performance_mode") or "").lower()
        edit_strategy = str(self.params.get("edit_strategy") or settings.get("edit_strategy") or "").lower()
        engine = str(self.params.get("engine") or settings.get("engine") or "").lower()
        return performance_mode == "stable" or edit_strategy in {"fast_assembly", "long_stable"} or engine == "ffmpeg_concat"

    def _resolve_audio_settings(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        params_audio = self.params.get("audio")
        settings_audio = settings.get("audio")
        base_audio = settings_audio if isinstance(settings_audio, dict) else {}
        override_audio = params_audio if isinstance(params_audio, dict) else {}
        audio = dict(base_audio)
        audio.update({key: value for key, value in override_audio.items() if value is not None})

        def num(name: str, default: float, minimum: float, maximum: float) -> float:
            try:
                value = float(audio.get(name, default))
            except Exception:
                value = default
            if not math.isfinite(value):
                value = default
            return max(minimum, min(maximum, value))

        music_mode = str(audio.get("music_mode") or "off").lower()
        if music_mode not in {"off", "auto", "manual"}:
            music_mode = "off"
        playlist_mode = str(audio.get("music_playlist_mode") or "single").lower()
        if playlist_mode not in {"single", "auto_playlist", "manual_playlist", "chapter_restart"}:
            playlist_mode = "single"
        fit_strategy = str(audio.get("music_fit_strategy") or "auto").lower()
        if fit_strategy not in {"auto", "loop", "trim", "intro_loop_outro", "once"}:
            fit_strategy = "auto"
        playlist_paths = audio.get("music_playlist_paths")
        if not isinstance(playlist_paths, list):
            playlist_paths = []
        playlist_paths = [str(item) for item in playlist_paths if item]

        estimated_video_duration = 0.0
        try:
            estimated_video_duration = float(audio.get("estimated_video_duration") or self.plan.get("total_duration") or 0.0)
        except Exception:
            estimated_video_duration = 0.0

        if music_mode == "auto":
            if not playlist_paths and isinstance(base_audio, dict):
                base_playlist = base_audio.get("music_playlist_paths")
                if isinstance(base_playlist, list):
                    playlist_paths = [str(item) for item in base_playlist if item]
            if playlist_paths and not audio.get("music_path"):
                audio["music_path"] = playlist_paths[0]
                audio["music_source"] = "library"
            elif not audio.get("music_path") and isinstance(base_audio, dict):
                audio["music_path"] = base_audio.get("music_path")
                audio["music_source"] = base_audio.get("music_source") or "library"

        return {
            "music_mode": music_mode,
            "music_path": audio.get("music_path"),
            "music_playlist_mode": playlist_mode,
            "music_playlist_paths": playlist_paths,
            "music_fit_strategy": fit_strategy,
            "music_chapter_restart": bool(audio.get("music_chapter_restart", False) or playlist_mode == "chapter_restart"),
            "music_source": audio.get("music_source") or ("manual" if music_mode == "manual" else "library" if music_mode == "auto" and audio.get("music_path") else "none"),
            "bgm_volume": num("bgm_volume", 0.28, 0.0, 1.0),
            "source_audio_volume": num("source_audio_volume", 1.0, 0.0, 1.0),
            "keep_source_audio": bool(audio.get("keep_source_audio", True)),
            "auto_ducking": bool(audio.get("auto_ducking", True)),
            "fade_in_seconds": num("fade_in_seconds", 1.5, 0.0, 10.0),
            "fade_out_seconds": num("fade_out_seconds", 3.0, 0.0, 20.0),
            "duck_bgm_volume": num("duck_bgm_volume", 0.16, 0.0, 1.0),
            "normalize_audio": bool(audio.get("normalize_audio", False)),
            "target_lufs": num("target_lufs", -16.0, -30.0, -8.0),
        }

    def _segment_keep_audio(self, seg: Dict[str, Any]) -> bool:
        return bool(self.audio_settings.get("keep_source_audio", True)) and bool(seg.get("keep_audio", True))

    def render(self) -> None:
        if not HAS_MOVIEPY:
            detail = f" Import failed: {MOVIEPY_IMPORT_ERROR}" if MOVIEPY_IMPORT_ERROR else ""
            raise RuntimeError(
                "MoviePy not installed. Please run: "
                "python -m pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg"
                + detail
            )

        ensure_parent(self.output_path)
        return self._render_with_visual_cache()
        clips: List[Any] = []
        rendered_segments: List[Dict[str, Any]] = []
        final = None

        try:
            segments = self.plan.get("segments", [])
            total = max(1, len(segments))
            self._emit_render_scheduler_summary()

            for idx, seg in enumerate(segments, 1):
                emit_event(
                    "phase",
                    phase="render",
                    message=f"Processing segment {idx}/{total}: {seg.get('type')}",
                    percent=min(90, int(idx / total * 90)),
                )
                clip = self._segment(seg)
                if clip is not None:
                    clips.append(clip)
                    rendered_segments.append(seg)

            if not clips:
                raise RuntimeError("No valid clips generated")

            emit_event("phase", phase="render", message="Composing final video timeline", percent=91)
            final = self._compose_timeline(clips, rendered_segments)

            if self.params.get("watermark"):
                emit_event("phase", phase="render", message="Applying watermark", percent=92)
                final = self._add_watermark(final, str(self.params.get("watermark")))

            final = self._apply_audio_mix(final)

            emit_event("phase", phase="render", message="Exporting final video", percent=92)

            logger = JsonMoviePyLogger(base_percent=92, span_percent=7)
            final.write_videofile(
                str(self.output_path),
                fps=int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30),
                codec="libx264",
                audio_codec="aac",
                preset="medium",
                threads=4,
                temp_audiofile=str(self.temp_dir / "temp_audio.m4a"),
                remove_temp=True,
                ffmpeg_params=[
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-crf",
                    quality_to_crf(self.params.get("python_quality") or self.params.get("quality")),
                ],
                logger=logger,
            )

            if self.params.get("cover"):
                self._create_cover()

            self._emit_photo_segment_cache_summary()
            self._emit_card_segment_cache_summary()
            self._emit_video_segment_cache_summary()
            self._emit_proxy_media_summary()
            self._cleanup_project_cache_dirs()

            try:
                project_dir = self._project_cache_root()
                backend_payload = _v56_backend_report_payload(self.backend_execution)
                diagnostics = _v56_render_diagnostics(self, [], [], False, self.last_render_timings)
                _v56_write_build_report(project_dir / "build_report.json", {
                    "engine_version": ENGINE_VERSION,
                    "status": "done",
                    "render_mode": "v5_standard",
                    "output_path": str(self.output_path),
                    "selected_backend": self.backend_execution.selected_backend_name,
                    "backend": backend_payload,
                    "output_size_bytes": self.output_path.stat().st_size if self.output_path.exists() else None,
                    "duration_seconds": float(getattr(final, "duration", 0.0) or 0.0),
                    "photo_segment_cache": self._photo_segment_cache_summary(),
                    "card_segment_cache": self._card_segment_cache_summary(),
                    "video_segment_cache": self._video_segment_cache_summary(),
                    "proxy_media": self._proxy_media_summary(),
                    "cache_cleanup": self.cache_cleanup_stats,
                    "render_scheduler": self.render_scheduler_summary,
                    "segment_routes": _v56_collect_segment_route_details(self.plan.get("segments", []) or []),
                    "timings": dict(self.last_render_timings),
                    "diagnostics": diagnostics,
                    **_v56_report_summary_fields(backend_payload, diagnostics, render_intent="final"),
                    "created_at": datetime.now().isoformat(),
                })
            except Exception as exc:
                emit_event("log", message=f"build_report write skipped for standard render: {exc}")

            emit_event("artifact", artifact="video", path=str(self.output_path), message="video exported")
            emit_event("phase", phase="complete", message="Render complete", percent=100)

        finally:
            if final is not None:
                close_clip(final)
            for clip in clips:
                close_clip(clip)
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _render_with_visual_cache(self) -> None:
        final_duration = 0.0
        render_started = perf_counter()
        timings: Dict[str, Any] = {}
        try:
            visual_started = perf_counter()
            visual_base_path, visual_duration = self._materialize_standard_visual_base()
            timings["visual_base_materialize_seconds"] = round(perf_counter() - visual_started, 4)

            finalize_started = perf_counter()
            final_duration = self._finalize_output_from_visual_base(
                visual_base_path,
                self.output_path,
                visual_duration,
            )
            timings["finalize_seconds"] = round(perf_counter() - finalize_started, 4)
            timings["total_render_seconds"] = round(perf_counter() - render_started, 4)
            if self.last_visual_finalize_summary:
                timings["finalize"] = dict(self.last_visual_finalize_summary)
            self.last_render_timings = dict(timings)

            if self.params.get("cover"):
                self._create_cover()

            self._emit_visual_base_cache_summary()
            self._emit_photo_segment_cache_summary()
            self._emit_card_segment_cache_summary()
            self._emit_video_segment_cache_summary()
            self._emit_proxy_media_summary()
            self._cleanup_project_cache_dirs()

            try:
                project_dir = self._project_cache_root()
                backend_payload = _v56_backend_report_payload(self.backend_execution)
                diagnostics = _v56_render_diagnostics(self, [], [], False, self.last_render_timings)
                _v56_write_build_report(project_dir / "build_report.json", {
                    "engine_version": ENGINE_VERSION,
                    "status": "done",
                    "render_mode": "v5_standard",
                    "output_path": str(self.output_path),
                    "selected_backend": self.backend_execution.selected_backend_name,
                    "backend": backend_payload,
                    "output_size_bytes": self.output_path.stat().st_size if self.output_path.exists() else None,
                    "duration_seconds": final_duration,
                    "visual_base_cache": dict(self.visual_base_cache_stats),
                    "photo_segment_cache": self._photo_segment_cache_summary(),
                    "card_segment_cache": self._card_segment_cache_summary(),
                    "video_segment_cache": self._video_segment_cache_summary(),
                    "proxy_media": self._proxy_media_summary(),
                    "cache_cleanup": self.cache_cleanup_stats,
                    "render_scheduler": self.render_scheduler_summary,
                    "segment_routes": _v56_collect_segment_route_details(self.plan.get("segments", []) or []),
                    "timings": dict(self.last_render_timings),
                    "diagnostics": diagnostics,
                    **_v56_report_summary_fields(backend_payload, diagnostics, render_intent="final"),
                    "created_at": datetime.now().isoformat(),
                })
            except Exception as exc:
                emit_event("log", message=f"build_report write skipped for standard render: {exc}")

            emit_event("artifact", artifact="video", path=str(self.output_path), message="video exported")
            emit_event("phase", phase="complete", message="Render complete", percent=100)
        finally:
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _segment(self, seg: Dict[str, Any]):
        stype = seg.get("type")
        duration = float(seg.get("duration") or 3.0)

        if stype in {"title", "chapter", "end"}:
            return self._cached_card_segment(seg, duration)

        if stype == "image":
            overlay_spec = self._image_overlay_cache_spec(seg, duration)
            clip = self._image_clip(Path(seg["source_path"]), duration, seg.get("motion_config"), overlay_spec=overlay_spec)
            if overlay_spec is not None:
                return clip
            return self._apply_overlay_title(clip, seg)

        if stype == "video":
            route = str(seg.get("runtime_render_route") or seg.get("render_route") or "")
            clip = self._video_clip(
                Path(seg["source_path"]),
                duration,
                keep_audio=self._segment_keep_audio(seg),
                motion_config=seg.get("motion_config"),
                prefer_ffmpeg=route in {"video_fit", "video_motion_fit", "direct_chunk_candidate"} or self._can_use_ffmpeg_fitted_video(seg),
            )
            return self._apply_overlay_title(clip, seg)

        return None

    def _compose_timeline(self, clips: List[Any], segments: List[Dict[str, Any]]):
        timeline = []
        cursor = 0.0
        max_end = 0.0

        for idx, clip in enumerate(clips):
            seg = segments[idx] if idx < len(segments) else {}
            transition_config = seg.get("transition_config") or {}
            transition_type = str(transition_config.get("type") or seg.get("transition") or "none")
            transition_duration = self._effective_transition_duration(
                clip,
                transition_config,
                seg.get("rhythm_config") or {},
            )

            start = cursor
            if idx > 0 and transition_duration > 0:
                start = max(0.0, cursor - transition_duration)
                clip = self._apply_transition_in(clip, transition_type, transition_duration)

            timeline.append(clip.set_start(start))
            max_end = max(max_end, start + float(clip.duration or 0.0))
            cursor = max_end

        if len(timeline) == 1:
            return timeline[0]
        return CompositeVideoClip(timeline, size=self.target_size).set_duration(max_end)

    def _apply_audio_mix(self, video: Any):
        settings = self.audio_settings
        duration = max(0.0, float(getattr(video, "duration", None) or self.plan.get("total_duration") or 0.0))
        if duration <= 0:
            return video

        source_audio = getattr(video, "audio", None) if settings.get("keep_source_audio", True) else None
        if source_audio is not None:
            source_volume = float(settings.get("source_audio_volume", 1.0))
            if source_volume <= 0:
                source_audio = None

        music_mode = str(settings.get("music_mode") or "off")
        music_path = settings.get("music_path")
        if music_mode == "off" or not music_path:
            if source_audio is not getattr(video, "audio", None):
                return video.set_audio(source_audio)
            return video

        path = self._prepare_music_bed(duration) or self._prepare_music_path() or Path(str(music_path))
        if not path.exists():
            emit_event("log", message=f"BGM file missing, skipped: {path}")
            return video.set_audio(source_audio) if source_audio is not getattr(video, "audio", None) else video

        bgm = None
        try:
            emit_event("phase", phase="audio", message="Finalizing audio mix", percent=92)
            bgm = AudioFileClip(str(path))
            if float(getattr(bgm, "duration", 0.0) or 0.0) < duration:
                bgm = self._loop_audio_to_duration(bgm, duration)
            bgm = bgm.set_duration(min(duration, float(getattr(bgm, "duration", duration) or duration)))

            bgm_volume = float(settings.get("bgm_volume", 0.28))
            if settings.get("auto_ducking", True) and source_audio is not None:
                bgm_volume = min(bgm_volume, float(settings.get("duck_bgm_volume", 0.16)))

            if bgm_volume <= 0:
                close_clip(bgm)
                return video.set_audio(source_audio)

            bgm = bgm.volumex(bgm_volume)
            fade_in = min(float(settings.get("fade_in_seconds", 0.0)), duration / 2.0)
            fade_out = min(float(settings.get("fade_out_seconds", 0.0)), duration / 2.0)
            if fade_in > 0:
                bgm = bgm.audio_fadein(fade_in)
            if fade_out > 0:
                bgm = bgm.audio_fadeout(fade_out)

            if source_audio is not None:
                return video.set_audio(CompositeAudioClip([source_audio, bgm.set_start(0)]).set_duration(duration))
            return video.set_audio(bgm)
        except Exception as exc:
            if bgm is not None:
                close_clip(bgm)
            emit_event("log", message=f"BGM preparation failed: {exc}")
            return video.set_audio(source_audio) if source_audio is not None else video

    def _loop_audio_to_duration(self, audio: Any, duration: float):
        source_duration = float(getattr(audio, "duration", None) or 0.0)
        if source_duration <= 0:
            return audio.set_duration(duration)
        if source_duration >= duration:
            return audio.subclip(0, duration)

        if moviepy_audio_loop is not None:
            try:
                return moviepy_audio_loop(audio, duration=duration)
            except Exception:
                pass

        clips = []
        remaining = duration
        while remaining > 0:
            take = min(source_duration, remaining)
            clips.append(audio.subclip(0, take))
            remaining -= take
        if len(clips) == 1:
            return clips[0].set_duration(duration)
        return concatenate_audioclips(clips).set_duration(duration)

    def _effective_transition_duration(
        self,
        clip: Any,
        transition_config: Dict[str, Any],
        rhythm_config: Dict[str, Any],
    ) -> float:
        transition_type = str(transition_config.get("type") or "none")
        if transition_type in {"none", "cut"}:
            return 0.0

        duration = float(transition_config.get("duration") or 0.0)
        pace = str(rhythm_config.get("pace") or "")
        if pace in {"fast_punchy", "fast_review"}:
            duration *= 0.72
        elif pace in {"medium_soft", "auto"}:
            duration *= 1.0
        elif pace in {"steady_story", "long_consistent"}:
            duration *= 0.82

        clip_duration = float(getattr(clip, "duration", None) or 0.0)
        if clip_duration <= 0:
            return 0.0
        return max(0.0, min(duration, clip_duration * 0.35, 0.8))

    def _apply_transition_in(self, clip: Any, transition_type: str, duration: float):
        if duration <= 0:
            return clip

        if transition_type in {"quick_zoom", "flash_cut"}:
            clip = self._resize_clip_safe(
                clip,
                lambda t: 1.08 - 0.08 * min(max(t / max(duration, 0.01), 0.0), 1.0),
            )

        try:
            return clip.crossfadein(duration)
        except Exception:
            try:
                return clip.fadein(duration)
            except Exception:
                return clip

    def _find_visual_source(self, direction: str) -> Optional[str]:
        """Find first/last image or video source from render_plan for title/end backgrounds."""
        segments = self.plan.get("segments", [])
        ordered = segments if direction == "first" else list(reversed(segments))
        for seg in ordered:
            if seg.get("type") in {"image", "video"} and seg.get("source_path"):
                return str(seg.get("source_path"))
        return None

    def _source_frame_for_background(self, source_path: Optional[str], position: str) -> Optional[Path]:
        """Return a temporary image frame that can be blurred as a text-card background.

        Image source: EXIF-transposed image.
        Video source: first frame for opening title, last frame for ending card.
        """
        if not source_path:
            return None

        source = Path(str(source_path))
        if not source.exists():
            emit_event("log", message=f"Preview background source missing, using fallback: {source}")
            return None

        suffix = source.suffix.lower()
        out = self._cache_path("text_frames", source, ".jpg", f"text_bg|position={position}")
        if out.exists():
            return out

        try:
            if suffix in IMAGE_EXTS:
                with Image.open(source) as img:
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    img.save(out, quality=94)
                return out

            if suffix in VIDEO_EXTS:
                render_source = self._normalize_video_display_geometry(source)
                clip = VideoFileClip(str(render_source))
                try:
                    duration = float(clip.duration or 0)
                    if position == "last":
                        t = max(0.0, duration - 0.08) if duration else 0.0
                    elif position == "middle":
                        t = max(0.0, duration / 2.0) if duration else 0.0
                    else:
                        t = 0.05 if duration > 0.1 else 0.0
                    clip.save_frame(str(out), t=t)
                    return out
                finally:
                    clip.close()
        except Exception as exc:
            emit_event("log", message=f"Fixed image cache failed for {source.name}: {exc}")

        return None

    def _chapter_card(self, seg: Dict[str, Any], duration: float):
        mode = seg.get("background_mode") or "bridge_blur"
        title_style = seg.get("title_style")

        if mode == "plain":
            return self._text_card(
                seg.get("text") or "",
                seg.get("subtitle"),
                duration,
                main=False,
                background_source=None,
                background_position="first",
                title_style=title_style,
            )

        if mode == "bridge_blur":
            return self._text_card(
                seg.get("text") or "",
                seg.get("subtitle"),
                duration,
                main=False,
                background_source=seg.get("background_source_path"),
                background_position=seg.get("background_source_position") or "last",
                background_source_2=seg.get("background_source_path_2"),
                background_position_2=seg.get("background_source_position_2") or "first",
                blend_sources=True,
                title_style=title_style,
            )

        return self._text_card(
            seg.get("text") or "",
            seg.get("subtitle"),
            duration,
            main=False,
            background_source=seg.get("background_source_path"),
            background_position=seg.get("background_source_position") or "first",
            title_style=title_style,
        )

    def _text_card(
        self,
        title: str,
        subtitle: Optional[str],
        duration: float,
        main: bool = False,
        background_source: Optional[str] = None,
        background_position: str = "first",
        background_source_2: Optional[str] = None,
        background_position_2: str = "first",
        blend_sources: bool = False,
        title_style: Optional[Dict[str, Any]] = None,
    ):
        bg = self._build_text_background(
            background_source,
            background_position,
            background_source_2,
            background_position_2,
            blend_sources=blend_sources,
        )
        bg_clip = ImageClip(np.array(bg)).set_duration(duration)
        
        style = title_style or {"preset": "cinematic_bold" if main else "cinematic_bold", "motion": "fade_slide_up"}
        text_img = self.renderer.render_layer(title, subtitle, style, is_full_card=True)
        text_clip = ImageClip(np.array(text_img), ismask=False).set_duration(duration)
        text_clip = self.renderer.animate(text_clip, style.get("motion", "fade_slide_up"), duration)

        return CompositeVideoClip([bg_clip, text_clip], size=self.target_size)

    def _text_card_image(
        self,
        title: str,
        subtitle: Optional[str],
        main: bool = False,
        background_source: Optional[str] = None,
        background_position: str = "first",
        background_source_2: Optional[str] = None,
        background_position_2: str = "first",
        blend_sources: bool = False,
        title_style: Optional[Dict[str, Any]] = None,
    ) -> Image.Image:
        """Build the exact PIL frame used by title/chapter/end cards.

        Cover generation calls this helper too, so the exported
        cover image is visually consistent with the first video frame.
        """
        w, h = self.target_size
        img = self._build_text_background(
            background_source,
            background_position,
            background_source_2,
            background_position_2,
            blend_sources=blend_sources,
        )

        style = title_style or {"preset": "cinematic_bold" if main else "film_subtitle", "motion": "static_hold"}
        text_img = self.renderer.render_layer(title, subtitle, style, is_full_card=True)
        composed = img.convert("RGBA")
        composed.alpha_composite(text_img)
        return composed.convert("RGB")

    def _build_text_background(
        self,
        source_1: Optional[str],
        pos_1: str,
        source_2: Optional[str] = None,
        pos_2: str = "first",
        blend_sources: bool = False,
    ) -> Image.Image:
        frame_1 = self._source_frame_for_background(source_1, pos_1)
        frame_2 = self._source_frame_for_background(source_2, pos_2) if source_2 else None

        if frame_1 and frame_1.exists():
            img_1 = Image.open(self._blur_bg(frame_1)).convert("RGB")
            if blend_sources and frame_2 and frame_2.exists():
                img_2 = Image.open(self._blur_bg(frame_2)).convert("RGB")
                img = Image.blend(img_1, img_2, 0.50)
            else:
                img = img_1
            return Image.blend(img, Image.new("RGB", self.target_size, (0, 0, 0)), 0.20)

        if frame_2 and frame_2.exists():
            img = Image.open(self._blur_bg(frame_2)).convert("RGB")
            return Image.blend(img, Image.new("RGB", self.target_size, (0, 0, 0)), 0.20)

        return Image.new("RGB", self.target_size, (17, 31, 25))

    def _apply_overlay_title(self, clip: Any, seg: Dict[str, Any]):
        text = seg.get("overlay_text")
        if not text:
            return clip
        subtitle = seg.get("overlay_subtitle")
        duration = min(float(seg.get("overlay_duration") or 1.8), float(clip.duration or 1.8))
        style = seg.get("overlay_title_style")
        overlay = self._overlay_title_clip(str(text), subtitle, duration, style=style)
        return CompositeVideoClip([clip, overlay], size=clip.size).set_duration(clip.duration)

    def _overlay_title_clip(self, title: str, subtitle: Optional[str], duration: float, style: Optional[Dict[str, Any]] = None):
        if not style:
            style = {"preset": "cinematic_bold", "motion": "fade_slide_up", "position": "lower_left"}
        
        text_img = self.renderer.render_layer(title, subtitle, style, is_full_card=False)
        text_clip = ImageClip(np.array(text_img), ismask=False).set_duration(duration)
        text_clip = self.renderer.animate(text_clip, style.get("motion", "fade_slide_up"), duration)

        # Handle positioning for overlays
        pos = style.get("position", "lower_left")
        w, h = self.target_size
        if pos == "lower_left":
            text_clip = text_clip.set_position((int(w * 0.05), int(h * 0.70)))
        elif pos == "lower_center":
            text_clip = text_clip.set_position(("center", int(h * 0.75)))
        else:
            text_clip = text_clip.set_position("center")

        return text_clip

    def _image_overlay_cache_spec(self, seg: Dict[str, Any], duration: float) -> Optional[Dict[str, Any]]:
        return _v56_image_overlay_cache_spec(seg, duration)

    def _get_proxy_source(self, source: Path, is_video: bool) -> Path:
        use_proxy = bool(
            self.params.get("preview")
            or self.params.get("proxy_media")
            or self.params.get("use_proxy_media")
            or self.params.get("optimized_media") == "proxy"
        )
        if not use_proxy:
            return source

        proxy_dir = self.render_cache_dir.parent / "proxies"
        proxy_dir.mkdir(parents=True, exist_ok=True)

        tw, th = self.target_size
        self.proxy_media_stats["eligible"] += 1
        manifest_entry = self.proxy_media_manifest.get(str(source.resolve())) or self.proxy_media_manifest.get(str(source))
        if manifest_entry:
            profiles = manifest_entry.get("profiles") or {}
            profile = profiles.get(str(SCAN_PROXY_PROFILE["name"])) if isinstance(profiles, dict) else None
            proxy_path_value = profile.get("path") if isinstance(profile, dict) else None
            if proxy_path_value:
                manifest_proxy_path = Path(str(proxy_path_value))
                if manifest_proxy_path.is_file():
                    self.proxy_media_stats["manifest_hit"] += 1
                    self.proxy_media_stats["hit"] += 1
                    return manifest_proxy_path

        proxy_key = f"{ENGINE_VERSION}|{source.resolve()}|{source.stat().st_mtime_ns}|{source.stat().st_size}|{tw}x{th}|video={is_video}"
        proxy_hash = hashlib.md5(proxy_key.encode()).hexdigest()

        ext = ".mp4" if is_video else ".jpg"
        proxy_path = proxy_dir / f"proxy_{proxy_hash}{ext}"

        if proxy_path.exists():
            self.proxy_media_stats["hit"] += 1
            return proxy_path

        emit_event("log", message=f"Creating preview proxy: {source.name}")
        try:
            if is_video:
                import imageio_ffmpeg

                cmd = [
                    imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(source),
                    "-vf", f"scale='min({tw},iw)':'min({th},ih)':force_original_aspect_ratio=decrease",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                    "-c:a", "copy",
                    str(proxy_path)
                ]
                subprocess.run(cmd, check=True, capture_output=True)
            else:
                with Image.open(source) as img:
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    img.thumbnail((tw, th), Image.Resampling.LANCZOS)
                    img.save(proxy_path, quality=85)
            self.proxy_media_stats["created"] += 1
            return proxy_path
        except Exception as e:
            self.proxy_media_stats["fallback"] += 1
            emit_event("log", message=f"Display normalization probe failed: {e}")
            return source

    def _image_clip(
        self,
        source: Path,
        duration: float,
        motion_config: Optional[Dict[str, Any]] = None,
        overlay_spec: Optional[Dict[str, Any]] = None,
    ):
        source = self._get_proxy_source(source, is_video=False)
        fixed = self._cache_path("fixed_images", source, ".jpg", "exif_rgb_v1")
        if not fixed.exists():
            with Image.open(source) as img:
                img = ImageOps.exif_transpose(img).convert("RGB")
                img.save(fixed, quality=95)

        if self._should_prerender_image_segment(duration, motion_config):
            self.photo_segment_cache_stats["eligible"] += 1
            if overlay_spec:
                self.photo_segment_cache_stats["overlay_eligible"] += 1
            prerendered = self._prerender_image_segment(source, fixed, duration, motion_config, overlay_spec=overlay_spec)
            if prerendered is not None and prerendered.exists():
                return VideoFileClip(str(prerendered)).set_duration(duration)

        return self._build_image_segment_clip(fixed, duration, motion_config, overlay_spec=overlay_spec)

    def _video_clip(
        self,
        source: Path,
        duration: float,
        keep_audio: bool = True,
        motion_config: Optional[Dict[str, Any]] = None,
        prefer_ffmpeg: bool = False,
    ):
        source = self._get_proxy_source(source, is_video=True)
        if prefer_ffmpeg:
            self.video_segment_cache_stats["eligible"] += 1
            motion_spec = self._ffmpeg_video_motion_cache_spec(motion_config)
            if motion_spec is not None:
                self.video_segment_cache_stats["motion_eligible"] += 1
                motion_fitted = self._ffmpeg_fit_motion_video_segment(
                    source,
                    duration,
                    motion_spec,
                    keep_audio=keep_audio,
                )
                if motion_fitted:
                    return VideoFileClip(str(motion_fitted))
            else:
                fitted = self._ffmpeg_fit_video_segment(source, duration, keep_audio=keep_audio)
                if fitted:
                    return VideoFileClip(str(fitted))

        render_source = self._normalize_video_display_geometry(source)
        raw = VideoFileClip(str(render_source))
        if raw.duration and raw.duration > duration:
            raw = raw.subclip(0, duration)
        raw = raw.set_duration(min(duration, raw.duration or duration))

        frame_path: Optional[Path] = self._cache_path("video_frames", source, ".jpg", "middle_frame_v1")
        try:
            if not frame_path.exists():
                raw.save_frame(str(frame_path), t=min(1.0, (raw.duration or 1.0) / 2))
        except Exception:
            frame_path = None

        final = self._compose_with_blur_bg(
            raw,
            raw.duration or duration,
            source_image=frame_path,
            motion_config=motion_config,
        )
        prepared_source_audio = self._prepare_source_audio_path(source) if keep_audio else None
        if keep_audio and prepared_source_audio is not None:
            source_volume = float(self.audio_settings.get("source_audio_volume", 1.0))
            if source_volume > 0:
                source_audio = AudioFileClip(str(prepared_source_audio))
                source_audio_duration = float(getattr(source_audio, "duration", None) or 0.0)
                if source_audio_duration > 0:
                    source_audio = source_audio.subclip(0, min(source_audio_duration, raw.duration or duration))
                if abs(source_volume - 1.0) > 0.001:
                    source_audio = source_audio.volumex(source_volume)
                final = final.set_audio(source_audio)
        elif keep_audio and raw.audio is not None:
            source_volume = float(self.audio_settings.get("source_audio_volume", 1.0))
            if source_volume > 0:
                source_audio = raw.audio
                if abs(source_volume - 1.0) > 0.001:
                    source_audio = source_audio.volumex(source_volume)
                final = final.set_audio(source_audio)
        return final

    def _normalize_video_display_geometry(self, source: Path) -> Path:
        if not video_needs_display_normalization(source):
            return source

        normalized = self._cache_path("normalized_videos", source, ".mp4", "display_geometry_v1")
        if normalized.exists():
            return normalized

        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            cmd = [
                ffmpeg,
                "-y",
                "-i",
                str(source),
                "-vf",
                "scale=trunc(iw*sar/2)*2:trunc(ih/2)*2,setsar=1",
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(normalized),
            ]
            emit_event("log", message=f"Display normalization required; creating normalized proxy: {source.name}")
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if completed.returncode == 0 and normalized.exists() and normalized.stat().st_size > 1024:
                return normalized
            emit_event("log", message=f"FFmpeg display normalization failed, falling back to source: {source.name}: {completed.stderr[-600:]}")
        except Exception as exc:
            emit_event("log", message=f"FFmpeg display normalization raised, falling back to source: {source.name}: {exc}")

        return source

    def _video_overlay_fitted_safe(self, seg: Dict[str, Any]) -> bool:
        text = seg.get("overlay_text")
        if not text:
            return True
        subtitle = seg.get("overlay_subtitle")
        overlay_duration = float(seg.get("overlay_duration") or 1.8)
        style = dict(seg.get("overlay_title_style") or {})
        motion = str(style.get("motion") or "fade_slide_up")
        position = str(style.get("position") or "lower_left")
        if motion not in {
            "fade_slide_up",
            "editorial_fade",
            "static_hold",
            "lower_third_slide",
            "cinematic_reveal",
            "postcard_drift",
        }:
            return False
        if position not in {"lower_left", "lower_center", "center"}:
            return False
        if len(str(text)) > 42 or len(str(subtitle or "")) > 64:
            return False
        return overlay_duration <= 3.2

    def _ffmpeg_video_motion_cache_spec(self, motion_config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        motion_type = str((motion_config or {}).get("type") or "none")
        if motion_type in {"none", "still_hold"}:
            return None
        if motion_type == "gentle_push":
            return {"type": motion_type, "mode": "progressive_zoom", "amount": 0.018}
        if motion_type == "slow_push":
            return {"type": motion_type, "mode": "progressive_zoom", "amount": 0.015}
        if motion_type == "micro_zoom":
            return {"type": motion_type, "mode": "progressive_zoom", "amount": 0.024}
        if motion_type == "subtle_ken_burns":
            return {"type": motion_type, "mode": "progressive_zoom", "amount": 0.012}
        return None

    def _can_use_ffmpeg_fitted_video(self, seg: Dict[str, Any]) -> bool:
        if not self.prefer_ffmpeg_segments:
            return False
        if seg.get("type") != "video":
            return False

        transition = seg.get("transition_config") or {}
        transition_type = str(transition.get("type") or seg.get("transition") or "none")
        transition_duration = float(transition.get("duration") or 0.0)
        if transition_type not in {
            "none",
            "cut",
            "soft_crossfade",
            "fade_through_dark",
            "fade_through_white",
            "quick_zoom",
            "flash_cut",
        }:
            return False
        if transition_type in {"none", "cut"}:
            if transition_duration > 0.05:
                return False
        elif transition_duration > 0.8:
            return False

        motion_type = str((seg.get("motion_config") or {}).get("type") or "none")
        if motion_type not in {"none", "still_hold"} and self._ffmpeg_video_motion_cache_spec(seg.get("motion_config")) is None:
            return False
        return self._video_overlay_fitted_safe(seg)

    def _can_use_ffmpeg_direct_chunk_segment(self, seg: Dict[str, Any]) -> bool:
        if self.params.get("preview"):
            return False
        if seg.get("type") != "video" or seg.get("overlay_text"):
            return False

        transition = seg.get("transition_config") or {}
        transition_type = str(transition.get("type") or seg.get("transition") or "none")
        transition_duration = float(transition.get("duration") or 0.0)
        if transition_type not in {"none", "cut"} or transition_duration > 0.05:
            return False

        motion = seg.get("motion_config") or {}
        motion_type = str(motion.get("type") or "none")
        return motion_type in {"none", "still_hold"}

    def _ffmpeg_fit_video_segment(
        self,
        source: Path,
        duration: float,
        keep_audio: bool = True,
        force_audio_track: bool = False,
        track_stats: bool = True,
    ) -> Optional[Path]:
        fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        audio_mode = "source" if keep_audio else "silent" if force_audio_track else "none"
        extra = f"fit_v3|duration={round(float(duration or 0), 3)}|audio={audio_mode}|fps={fps}"
        out = self._cache_path("fitted_videos", source, ".mp4", extra)
        if out.exists() and out.stat().st_size > 1024:
            if track_stats:
                self.video_segment_cache_stats["hit"] += 1
                self.video_segment_cache_stats["saved_live_fits"] += 1
                self.video_segment_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
                emit_event("log", message=f"Video segment cache hit: {out.name}")
            return out

        render_source = self._normalize_video_display_geometry(source)
        segment_duration = max(float(duration or 0.1), 0.1)
        prepared_source_audio = self._prepare_source_audio_path(source) if keep_audio else None
        use_cached_source_audio = prepared_source_audio is not None and prepared_source_audio.exists()
        fallback_source_audio = bool(keep_audio and video_has_audio_stream(render_source))
        use_source_audio = bool(use_cached_source_audio or fallback_source_audio)
        needs_audio_track = bool(keep_audio or force_audio_track)
        source_volume = float(self.audio_settings.get("source_audio_volume", 1.0))
        tw, th = self.target_size
        vf = (
            f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
            f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps},format=yuv420p"
        )

        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            selected_encoder, encoder_args = select_ffmpeg_video_encoder(self.params)

            def build_cmd(video_encoder: str, video_encoder_args: List[str]) -> List[str]:
                cmd = [ffmpeg, "-y", "-i", str(render_source)]
                if use_cached_source_audio:
                    cmd += ["-i", str(prepared_source_audio)]
                elif needs_audio_track and not use_source_audio:
                    cmd += [
                        "-f",
                        "lavfi",
                        "-t",
                        str(segment_duration),
                        "-i",
                        "anullsrc=channel_layout=stereo:sample_rate=48000",
                    ]
                cmd += ["-t", str(segment_duration), "-vf", vf, "-map", "0:v:0"]
                if needs_audio_track:
                    if use_cached_source_audio:
                        audio_map = "1:a:0"
                    elif use_source_audio:
                        audio_map = "0:a:0"
                    else:
                        audio_map = "1:a:0"
                    cmd += ["-map", audio_map]
                    audio_filters = []
                    if abs(source_volume - 1.0) > 0.001 and (use_source_audio or use_cached_source_audio):
                        audio_filters.append(f"volume={source_volume:.4f}")
                    audio_filters.extend(["aresample=48000", "apad"])
                    cmd += [
                        "-af",
                        ",".join(audio_filters),
                        "-ac",
                        "2",
                        "-ar",
                        "48000",
                        "-shortest",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "160k",
                    ]
                else:
                    cmd += ["-an"]
                cmd += ["-c:v", video_encoder]
                cmd += video_encoder_args
                if video_encoder == "libx264":
                    cmd += ["-crf", quality_to_crf(self.params.get("python_quality") or self.params.get("quality") or "standard")]
                else:
                    cmd += ["-b:v", "8M"]
                cmd += ["-movflags", "+faststart", str(out)]
                return cmd

            completed = subprocess.run(build_cmd(selected_encoder, encoder_args), capture_output=True, text=True, encoding="utf-8", errors="replace")
            if completed.returncode != 0 and selected_encoder != "libx264":
                emit_event("log", message=f"Selected encoder {selected_encoder} failed, falling back to libx264: {completed.stderr[-600:]}")
                completed = subprocess.run(
                    build_cmd("libx264", ["-preset", "veryfast"]),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            if completed.returncode == 0 and out.exists() and out.stat().st_size > 1024:
                if track_stats:
                    self.video_segment_cache_stats["created"] += 1
                    emit_event("log", message=f"Video segment cache created: {out.name}")
                return out
            if track_stats:
                self.video_segment_cache_stats["fallback"] += 1
                emit_event("log", message=f"FFmpeg fitted segment failed, falling back to MoviePy: {source.name}: {completed.stderr[-600:]}")
        except Exception as exc:
            if track_stats:
                self.video_segment_cache_stats["fallback"] += 1
                emit_event("log", message=f"FFmpeg fitted segment raised, falling back to MoviePy: {source.name}: {exc}")

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return None

    def _ffmpeg_fit_motion_video_segment(
        self,
        source: Path,
        duration: float,
        motion_spec: Dict[str, Any],
        keep_audio: bool = True,
    ) -> Optional[Path]:
        fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        audio_mode = "source" if keep_audio else "none"
        motion_key = json.dumps(motion_spec or {}, ensure_ascii=False, sort_keys=True)
        out = self._cache_path(
            "motion_fitted_videos",
            source,
            ".mp4",
            f"motion_fit_v1|duration={round(float(duration or 0), 3)}|audio={audio_mode}|fps={fps}|motion={motion_key}",
        )
        if out.exists() and out.stat().st_size > 1024:
            self.video_segment_cache_stats["hit"] += 1
            self.video_segment_cache_stats["motion_hit"] += 1
            self.video_segment_cache_stats["saved_live_fits"] += 1
            self.video_segment_cache_stats["saved_render_seconds"] += int(round(float(duration or 0.0)))
            emit_event("log", message=f"Video motion cache hit: {out.name}")
            return out

        base = self._ffmpeg_fit_video_segment(source, duration, keep_audio=keep_audio, track_stats=False)
        if not base or not base.exists():
            self.video_segment_cache_stats["fallback"] += 1
            self.video_segment_cache_stats["motion_fallback"] += 1
            emit_event("log", message=f"FFmpeg motion fit fallback to MoviePy: {source.name}: base fit unavailable")
            return None

        tw, th = self.target_size
        segment_duration = max(float(duration or 0.1), 0.1)
        amount = float(motion_spec.get("amount") or 0.0)
        frame_budget = max(int(round(segment_duration * fps)), 1)
        zoom_expr = f"(1+{amount:.6f}*on/{frame_budget})"
        vf = (
            f"zoompan=z='{zoom_expr}':"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"d=1:s={tw}x{th}:fps={fps},"
            f"setsar=1,format=yuv420p"
        )

        try:
            import imageio_ffmpeg

            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
            selected_encoder, encoder_args = select_ffmpeg_video_encoder(self.params)
            has_audio = bool(keep_audio and video_has_audio_stream(base))

            def build_cmd(video_encoder: str, video_encoder_args: List[str]) -> List[str]:
                cmd = [ffmpeg, "-y", "-i", str(base), "-t", str(segment_duration), "-vf", vf, "-map", "0:v:0"]
                if has_audio:
                    cmd += ["-map", "0:a:0", "-c:a", "copy", "-shortest"]
                else:
                    cmd += ["-an"]
                cmd += ["-c:v", video_encoder]
                cmd += video_encoder_args
                if video_encoder == "libx264":
                    cmd += ["-crf", quality_to_crf(self.params.get("python_quality") or self.params.get("quality") or "standard")]
                else:
                    cmd += ["-b:v", "8M"]
                cmd += ["-movflags", "+faststart", str(out)]
                return cmd

            completed = subprocess.run(build_cmd(selected_encoder, encoder_args), capture_output=True, text=True, encoding="utf-8", errors="replace")
            if completed.returncode != 0 and selected_encoder != "libx264":
                emit_event("log", message=f"FFmpeg video motion {selected_encoder} fallback to libx264: {completed.stderr[-600:]}")
                completed = subprocess.run(
                    build_cmd("libx264", ["-preset", "veryfast"]),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
            if completed.returncode == 0 and out.exists() and out.stat().st_size > 1024:
                self.video_segment_cache_stats["created"] += 1
                self.video_segment_cache_stats["motion_created"] += 1
                emit_event("log", message=f"Video motion cache created: {out.name}")
                return out
            self.video_segment_cache_stats["fallback"] += 1
            self.video_segment_cache_stats["motion_fallback"] += 1
            emit_event("log", message=f"FFmpeg motion fit failed, falling back to MoviePy: {source.name}: {completed.stderr[-600:]}")
        except Exception as exc:
            self.video_segment_cache_stats["fallback"] += 1
            self.video_segment_cache_stats["motion_fallback"] += 1
            emit_event("log", message=f"FFmpeg motion fit raised, falling back to MoviePy: {source.name}: {exc}")

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return None

    def _prerender_safe_video_overlay_segment(
        self,
        fitted_source: Path,
        seg: Dict[str, Any],
        duration: float,
    ) -> Optional[Path]:
        overlay_spec = self._image_overlay_cache_spec(seg, duration)
        if overlay_spec is None:
            return fitted_source

        overlay_key = json.dumps(overlay_spec, ensure_ascii=False, sort_keys=True)
        out = self._cache_path(
            "overlay_fitted_videos",
            fitted_source,
            ".mp4",
            f"overlay_fit_v1|duration={round(float(duration or 0.0), 3)}|overlay={overlay_key}",
        )
        if out.exists() and out.stat().st_size > 1024:
            emit_event("log", message=f"Video overlay cache hit: {out.name}")
            return out

        clip = None
        final = None
        try:
            clip = VideoFileClip(str(fitted_source)).set_duration(duration)
            final = self._apply_overlay_title(clip, seg)
            has_audio = getattr(final, "audio", None) is not None
            final.write_videofile(
                str(out),
                fps=int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30),
                codec="libx264",
                audio=has_audio,
                audio_codec="aac" if has_audio else None,
                preset="veryfast",
                threads=1,
                verbose=False,
                logger=None,
                ffmpeg_params=[
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    "-crf",
                    quality_to_crf(self.params.get("python_quality") or self.params.get("quality") or "standard"),
                ],
            )
            ok, _reason, _duration = _v56_validate_video(out, min_size=512)
            if ok:
                emit_event("log", message=f"Video overlay cache created: {out.name}")
                return out
        except Exception as exc:
            emit_event("log", message=f"Video overlay prerender fallback: {exc}")
        finally:
            if final is not None:
                close_clip(final)
            if clip is not None:
                close_clip(clip)
            try:
                gc.collect()
            except Exception:
                pass

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return None

    def _compose_with_blur_bg(
        self,
        clip: Any,
        duration: float,
        source_image: Optional[Path],
        motion_config: Optional[Dict[str, Any]] = None,
    ):
        tw, th = self.target_size
        scale = min(tw / clip.w, th / clip.h)
        fg = clip.resize((max(1, int(clip.w * scale)), max(1, int(clip.h * scale))))
        fg = self._apply_visual_motion(fg, duration, motion_config)

        if source_image and Path(source_image).exists():
            bg_path = self._blur_bg(Path(source_image))
            bg = ImageClip(str(bg_path)).set_duration(duration)
        else:
            bg = ColorClip(self.target_size, color=(0, 0, 0)).set_duration(duration)

        return CompositeVideoClip(
            [bg, fg.set_position("center")],
            size=self.target_size,
        ).set_duration(duration)

    def _apply_visual_motion(
        self,
        clip: Any,
        duration: float,
        motion_config: Optional[Dict[str, Any]],
    ):
        motion_type = str((motion_config or {}).get("type") or "none")
        if motion_type in {"none", "still_hold"}:
            return clip

        duration = max(float(duration or 0.1), 0.1)

        if motion_type in {"gentle_push", "slow_push"}:
            amount = 0.018 if motion_type == "gentle_push" else 0.015
            return self._resize_clip_safe(clip, lambda t: 1.0 + amount * min(max(t / duration, 0.0), 1.0))

        if motion_type in {"ken_burns", "subtle_ken_burns"}:
            amount = 0.022 if motion_type == "ken_burns" else 0.012
            return self._resize_clip_safe(clip, lambda t: 1.0 + amount * min(max(t / duration, 0.0), 1.0))

        if motion_type in {"punch_zoom", "micro_zoom"}:
            amount = 0.035 if motion_type == "punch_zoom" else 0.025
            return self._resize_clip_safe(
                clip,
                lambda t: 1.0 + amount * max(0.0, 1.0 - min(max(t / 0.42, 0.0), 1.0)),
            )

        return clip

    def _resize_clip_safe(self, clip: Any, scale_fn: Any):
        try:
            return clip.resize(scale_fn)
        except Exception:
            return clip

    def _blur_bg(self, source_image: Path) -> Path:
        out = self._cache_path("blur_backgrounds", source_image, ".jpg", "blur30_dark28_v1")
        if out.exists():
            return out

        tw, th = self.target_size
        img = None
        bg = None
        try:
            with Image.open(source_image) as raw_img:
                img = raw_img.convert("RGB")
            scale = max(tw / img.width, th / img.height)
            bg = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)

            left = max(0, (bg.width - tw) // 2)
            top = max(0, (bg.height - th) // 2)
            bg = bg.crop((left, top, left + tw, top + th)).filter(ImageFilter.GaussianBlur(30))
            bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.28)
            bg.save(out, quality=90)
            return out
        finally:
            for image in (bg, img):
                try:
                    if image is not None:
                        image.close()
                except Exception:
                    pass

    def _add_watermark(self, video: Any, text: str):
        font = load_font(30)
        temp = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(temp)
        tw, th = text_size(draw, text, font)

        img = Image.new("RGBA", (tw + 32, th + 24), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw_text_with_emoji(draw, (16, 10), text, font=font, fill=(255, 255, 255, 150))

        wm = ImageClip(np.array(img)).set_duration(video.duration).set_position(("right", "bottom"))
        return CompositeVideoClip([video, wm], size=video.size)

    def _create_cover(self) -> None:
        """Create the upload cover from the same visual recipe as the opening title card.

        Priority:
          1. params.title_background_path selected in GUI
          2. first visual segment from render_plan
          3. plain brand background fallback

        This keeps cover_travel_video.jpg, the first video frame, and the
        user-selected opening background visually consistent.
        """
        cover = self.output_path.with_name(f"cover_{self.output_path.stem}.jpg")
        title = str(self.params.get("title") or "Travel Video")
        subtitle = str(self.params.get("title_subtitle") or "Video Create Studio")
        background_source = self.params.get("title_background_path") or self.first_visual_source

        img = self._text_card_image(
            title=title,
            subtitle=subtitle,
            main=True,
            background_source=background_source,
            background_position="first",
            title_style=self.params.get("title_style") or {"preset": "cinematic_bold", "motion": "static_hold"},
        )

        img.save(cover, quality=92)
        emit_event(
            "artifact",
            artifact="cover",
            path=str(cover),
            message="Cover generated from opening title card background",
        )


# =========================
# CLI commands
# =========================

def command_scan(args: argparse.Namespace) -> None:
    scanner = Scanner(args.input_folder, recursive=args.recursive)
    result = scanner.scan()
    write_json(args.output, result)
    if args.output:
        emit_event("artifact", artifact="media_library", path=args.output, message="media library generated")


def command_plan(args: argparse.Namespace) -> None:
    result = Planner(read_json(args.library)).plan(
        strategy=args.strategy,
        template_mode=getattr(args, "template", "auto"),
        music_blueprint_mode=getattr(args, "music_blueprint", "recommend"),
    )
    write_json(args.output, result)
    if args.output:
        emit_event("artifact", artifact="story_blueprint", path=args.output, message="story blueprint generated")


def command_compile(args: argparse.Namespace) -> None:
    result = Compiler(read_json(args.blueprint), read_json(args.library)).compile()
    write_json(args.output, result)
    if args.output:
        emit_event("artifact", artifact="render_plan", path=args.output, message="render plan generated")



# =========================
# V5.6 long-video stability renderer
# =========================

def _v56_validate_video(path: Path, min_size: int = 1024) -> Tuple[bool, str, Optional[float]]:
    if not path.exists():
        return False, "video file does not exist", None
    if path.stat().st_size < min_size:
        return False, f"video file is too small: {path.stat().st_size} bytes", None

    if not HAS_MOVIEPY:
        return True, "MoviePy unavailable; size check passed", None

    clip = None
    try:
        clip = VideoFileClip(str(path))
        duration = float(clip.duration or 0.0)
        if duration <= 0:
            return False, "video duration is invalid", duration
        return True, "validation passed", duration
    except Exception as exc:
        return False, f"video validation failed: {exc}", None
    finally:
        if clip is not None:
            close_clip(clip)


def _v56_concat_chunks_ffmpeg(chunks: List[Path], tmp_output: Path, project_dir: Path) -> bool:
    return render_ffmpeg_helpers._v56_concat_chunks_ffmpeg(
        chunks,
        tmp_output,
        project_dir,
        emit_event_fn=emit_event,
    )


def _v56_concat_chunks_ffmpeg_reencode(
    chunks: List[Path],
    tmp_output: Path,
    project_dir: Path,
    fps: int,
    params: Dict[str, Any],
) -> bool:
    return render_ffmpeg_helpers._v56_concat_chunks_ffmpeg_reencode(
        chunks,
        tmp_output,
        project_dir,
        fps,
        params,
        emit_event_fn=emit_event,
        quality_to_crf_fn=quality_to_crf,
        select_video_encoder_fn=select_ffmpeg_video_encoder,
    )


def _v56_concat_chunks_moviepy(chunks: List[Path], tmp_output: Path, fps: int, params: Dict[str, Any]) -> None:
    return render_ffmpeg_helpers._v56_concat_chunks_moviepy(
        chunks,
        tmp_output,
        fps,
        params,
        emit_event_fn=emit_event,
        quality_to_crf_fn=quality_to_crf,
        close_clip_fn=close_clip,
        video_file_clip_cls=VideoFileClip,
        concatenate_videoclips_fn=concatenate_videoclips,
        logger_factory=lambda base_percent, span_percent: JsonMoviePyLogger(
            base_percent=base_percent,
            span_percent=span_percent,
        ),
    )


def _v56_apply_final_bgm_mix(
    input_video: Path,
    output_video: Path,
    audio_settings: Dict[str, Any],
    duration: Optional[float],
    prepared_bgm_path: Optional[Path] = None,
    prepared_bgm_is_bed: bool = False,
) -> bool:
    return render_ffmpeg_helpers._v56_apply_final_bgm_mix(
        input_video,
        output_video,
        audio_settings,
        duration,
        prepared_bgm_path=prepared_bgm_path,
        prepared_bgm_is_bed=prepared_bgm_is_bed,
        emit_event_fn=emit_event,
        video_has_audio_stream_fn=video_has_audio_stream,
    )


def _v56_try_write_ffmpeg_direct_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
) -> bool:
    return render_ffmpeg_helpers._v56_try_write_ffmpeg_direct_chunk(
        renderer,
        chunk,
        tmp_chunk,
        params,
        emit_event_fn=emit_event,
        validate_video_fn=_v56_validate_video,
    )


def _v56_try_write_ffmpeg_image_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
) -> bool:
    return render_ffmpeg_helpers._v56_try_write_ffmpeg_image_chunk(
        renderer,
        chunk,
        tmp_chunk,
        params,
        emit_event_fn=emit_event,
        validate_video_fn=_v56_validate_video,
        image_cls=Image,
        image_ops=ImageOps,
    )


def _v56_try_write_ffmpeg_fitted_video_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
) -> bool:
    return render_ffmpeg_helpers._v56_try_write_ffmpeg_fitted_video_chunk(
        renderer,
        chunk,
        tmp_chunk,
        params,
        emit_event_fn=emit_event,
        validate_video_fn=_v56_validate_video,
    )


def _v56_try_write_ffmpeg_card_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
) -> bool:
    return render_ffmpeg_helpers._v56_try_write_ffmpeg_card_chunk(
        renderer,
        chunk,
        tmp_chunk,
        params,
        emit_event_fn=emit_event,
        validate_video_fn=_v56_validate_video,
    )


def _v56_ensure_silent_audio_track(video_path: Path, duration: Optional[float] = None) -> bool:
    return render_ffmpeg_helpers._v56_ensure_silent_audio_track(
        video_path,
        duration,
        emit_event_fn=emit_event,
        video_has_audio_stream_fn=video_has_audio_stream,
    )

def _v56_stable_should_force_chunk_audio_track(renderer: Any, segments: List[Dict[str, Any]]) -> bool:
    return render_diagnostics_helpers._v56_stable_should_force_chunk_audio_track(
        renderer,
        segments,
        video_has_audio_stream_fn=video_has_audio_stream,
    )


def _v56_collect_segment_route_details(segments: List[Dict[str, Any]], limit: int = 200) -> List[Dict[str, Any]]:
    return render_diagnostics_helpers._v56_collect_segment_route_details(segments, limit=limit)


def _v56_collect_chunk_route_details(
    groups: List[Dict[str, Any]],
    chunk_reports: List[Dict[str, Any]],
    limit: int = 200,
) -> List[Dict[str, Any]]:
    return render_diagnostics_helpers._v56_collect_chunk_route_details(groups, chunk_reports, limit=limit)


def _v56_route_reason_summary(items: List[Dict[str, Any]], route_key: str, reason_key: str) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_route_reason_summary(items, route_key, reason_key)


def _v56_top_named_counts(counts: Dict[str, int], limit: int = 5) -> List[Dict[str, Any]]:
    return render_diagnostics_helpers._v56_top_named_counts(counts, limit=limit)


def _v56_timing_highlights(timings: Optional[Dict[str, Any]], limit: int = 3) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_timing_highlights(timings, limit=limit)


def _v56_cache_efficiency_entry(
    stats: Optional[Dict[str, Any]],
    *,
    hit_keys: Tuple[str, ...] = ("hit",),
    created_keys: Tuple[str, ...] = ("created",),
    fallback_keys: Tuple[str, ...] = ("fallback",),
) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_cache_efficiency_entry(
        stats,
        hit_keys=hit_keys,
        created_keys=created_keys,
        fallback_keys=fallback_keys,
    )


def _v56_fast_path_coverage(
    items: List[Dict[str, Any]],
    *,
    fast_routes: Tuple[str, ...],
    route_key: str = "route",
    reason_key: str = "reason",
    limit: int = 5,
) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_fast_path_coverage(
        items,
        fast_routes=fast_routes,
        route_key=route_key,
        reason_key=reason_key,
        limit=limit,
    )


def _v56_route_difference_summary(items: List[Dict[str, Any]], limit: int = 5) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_route_difference_summary(items, limit=limit)


def _v56_observability_summary(
    renderer: Any,
    *,
    segment_route_details: List[Dict[str, Any]],
    chunk_route_details: List[Dict[str, Any]],
    timings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_observability_summary(
        renderer,
        segment_route_details=segment_route_details,
        chunk_route_details=chunk_route_details,
        timings=timings,
    )


def _v56_report_summary_fields(
    backend_payload: Dict[str, Any],
    diagnostics: Dict[str, Any],
    *,
    render_intent: str,
) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_report_summary_fields(
        backend_payload,
        diagnostics,
        render_intent=render_intent,
    )


def _v56_classify_render_failure(error: Any, stage: str) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_classify_render_failure(error, stage)


def _v56_build_recovery_summary(
    manifest: Optional[Dict[str, Any]],
    *,
    chunk_reports: List[Dict[str, Any]],
    failed_chunk: Optional[str] = None,
    failure: Optional[Dict[str, Any]] = None,
    manifest_path: Optional[Path] = None,
    resumed_from_manifest: bool = False,
    reused_chunk_count: int = 0,
) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_build_recovery_summary(
        manifest,
        chunk_reports=chunk_reports,
        failed_chunk=failed_chunk,
        failure=failure,
        manifest_path=manifest_path,
        resumed_from_manifest=resumed_from_manifest,
        reused_chunk_count=reused_chunk_count,
    )

def _v56_safe_apply_final_bgm_mix(*args: Any, **kwargs: Any) -> Tuple[bool, Optional[Exception]]:
    try:
        return bool(_v56_apply_final_bgm_mix(*args, **kwargs)), None
    except Exception as exc:
        return False, exc


def _v56_render_diagnostics(
    renderer: Any,
    groups: List[Dict[str, Any]],
    chunk_reports: List[Dict[str, Any]],
    force_chunk_audio_track: bool,
    timings: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_render_diagnostics(
        renderer,
        groups,
        chunk_reports,
        force_chunk_audio_track,
        timings,
        select_video_encoder_fn=select_ffmpeg_video_encoder,
        should_default_to_hardware_encoding_fn=_should_default_to_hardware_encoding,
    )

def _v56_write_chunk_video(
    renderer: Any,
    chunk: Dict[str, Any],
    chunk_path: Path,
    fps: int,
    params: Dict[str, Any],
    ensure_audio_track: bool = False,
) -> None:
    clips = []
    rendered_segments = []
    combined = None
    tmp_chunk = chunk_path.with_suffix(".rendering.tmp.mp4")

    try:
        chunk_route = str(chunk.get("runtime_chunk_route") or "")
        if chunk_route == "ffmpeg_direct_chunk" and _v56_try_write_ffmpeg_direct_chunk(renderer, chunk, tmp_chunk, params):
            if ensure_audio_track:
                ok, _reason, duration = _v56_validate_video(tmp_chunk)
                if ok and not _v56_ensure_silent_audio_track(tmp_chunk, duration):
                    raise RuntimeError("failed to ensure audio-ready stable chunk")
            _v56_atomic_replace(tmp_chunk, chunk_path)
            return
        if chunk_route == "ffmpeg_fitted_video_chunk" and _v56_try_write_ffmpeg_fitted_video_chunk(renderer, chunk, tmp_chunk, params):
            if ensure_audio_track:
                ok, _reason, duration = _v56_validate_video(tmp_chunk)
                if ok and not _v56_ensure_silent_audio_track(tmp_chunk, duration):
                    raise RuntimeError("failed to ensure audio-ready stable chunk")
            _v56_atomic_replace(tmp_chunk, chunk_path)
            return
        if chunk_route == "ffmpeg_card_chunk" and _v56_try_write_ffmpeg_card_chunk(renderer, chunk, tmp_chunk, params):
            if ensure_audio_track:
                ok, _reason, duration = _v56_validate_video(tmp_chunk)
                if ok and not _v56_ensure_silent_audio_track(tmp_chunk, duration):
                    raise RuntimeError("failed to ensure audio-ready stable chunk")
            _v56_atomic_replace(tmp_chunk, chunk_path)
            return
        if chunk_route == "ffmpeg_image_chunk" and _v56_try_write_ffmpeg_image_chunk(renderer, chunk, tmp_chunk, params):
            if ensure_audio_track:
                ok, _reason, duration = _v56_validate_video(tmp_chunk)
                if ok and not _v56_ensure_silent_audio_track(tmp_chunk, duration):
                    raise RuntimeError("failed to ensure audio-ready stable chunk")
            _v56_atomic_replace(tmp_chunk, chunk_path)
            return

        for seg in chunk["segments"]:
            emit_event(
                "phase",
                phase="render",
                message=f"Rendering chunk {chunk['index'] + 1}: {seg.get('type')} {seg.get('text') or ''}",
                percent=min(94, 10 + chunk["index"]),
            )
            clip = renderer._segment(seg)
            if clip is not None:
                clips.append(clip)
                rendered_segments.append(seg)

        if not clips:
            raise RuntimeError(f"chunk_{chunk['index']:03d} has no renderable clip")

        combined = renderer._compose_timeline(clips, rendered_segments)
        crf = quality_to_crf(params.get("quality") or params.get("python_quality") or "high")
        combined.write_videofile(
            str(tmp_chunk),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            ffmpeg_params=["-crf", crf, "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=JsonMoviePyLogger(base_percent=20, span_percent=70),
        )

        ok, reason, _duration = _v56_validate_video(tmp_chunk)
        if not ok:
            raise RuntimeError(f"chunk validation failed: {reason}")

        if ensure_audio_track and not _v56_ensure_silent_audio_track(tmp_chunk, _duration):
            raise RuntimeError("failed to ensure audio-ready stable chunk")

        _v56_atomic_replace(tmp_chunk, chunk_path)
    finally:
        if combined is not None:
            close_clip(combined)
        for clip in clips:
            close_clip(clip)
        if tmp_chunk.exists():
            try:
                tmp_chunk.unlink()
            except Exception:
                pass
        try:
            gc.collect()
        except Exception:
            pass


def _v56_should_use_stable_renderer(plan: Dict[str, Any], params: Dict[str, Any]) -> bool:
    performance_mode = str(params.get("performance_mode") or plan.get("render_settings", {}).get("performance_mode") or "").lower()
    mode = str(params.get("render_mode") or params.get("long_video_mode") or "auto").lower()

    # Explicit render mode has the highest priority.
    if mode in {"stable", "long", "long_stable", "true", "1", "yes"}:
        return True
    if mode in {"standard", "classic", "moviepy"}:
        return False

    if performance_mode == "stable":
        return True

    # "quality" means keep higher visual quality, not force the unsafe monolithic
    # MoviePy timeline. Large projects still need chunked stable rendering.
    total_duration = float(plan.get("total_duration") or 0.0)
    segments = list(plan.get("segments", []) or [])
    return _should_auto_use_stable_renderer(total_duration, segments, params)


def _v56_resolve_render_backend_decision(plan: Dict[str, Any], params: Dict[str, Any]) -> BackendDecision:
    return backend_selector_resolve_render_backend(plan, params, _v56_should_use_stable_renderer)


def _v56_resolve_render_backend(plan: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    return _v56_resolve_render_backend_decision(plan, params).to_dict()


def _v56_backend_report_payload(
    decision: Optional[Any],
    fallback_used: Optional[str] = None,
    fallback_reason: Optional[str] = None,
) -> Dict[str, Any]:
    return render_diagnostics_helpers._v56_backend_report_payload(
        decision,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )


class V56StableRenderer:
    def __init__(self, plan: Dict[str, Any], output: str, params: Dict[str, Any], plan_path: Optional[str] = None):
        self.plan = plan
        self.output = Path(output)
        self.params = params or {}
        self.backend_decision = coerce_backend_decision(
            self.params.get("_backend_decision") or _v56_resolve_render_backend_decision(self.plan, self.params)
        )
        self.backend_execution = coerce_backend_execution_result(
            self.params.get("_backend_execution") or self.backend_decision
        )
        self.plan_path = Path(plan_path).resolve() if plan_path else None

        if self.plan_path:
            self.project_dir = self.plan_path.parent
        else:
            self.project_dir = self.output.parent / ".video_create_project"

        self.chunk_dir = self.project_dir / "chunks" / self.output.stem
        self.chunk_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.chunk_dir / "chunk_manifest.json"
        self.report_path = self.project_dir / "build_report.json"

        self.fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        self.chunk_seconds = float(self.params.get("chunk_seconds") or self.params.get("stable_chunk_seconds") or 120)

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            try:
                with self.manifest_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"chunks": {}}
        return {"chunks": {}}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        ensure_parent(self.manifest_path)
        with self.manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def _write_failure_report(
        self,
        *,
        renderer: Renderer,
        manifest: Dict[str, Any],
        groups: List[Dict[str, Any]],
        chunk_reports: List[Dict[str, Any]],
        chunk_route_counts: Dict[str, int],
        timings: Dict[str, Any],
        force_chunk_audio_track: bool,
        final_output: Path,
        error: Any,
        stage: str,
        failed_chunk: Optional[str] = None,
        resumed_from_manifest: bool = False,
        reused_chunk_count: int = 0,
    ) -> None:
        failure = _v56_classify_render_failure(error, stage)
        segment_routes = _v56_collect_segment_route_details(self.plan.get("segments", []) or [])
        chunk_routes = _v56_collect_chunk_route_details(groups, chunk_reports)
        backend_payload = _v56_backend_report_payload(self.backend_execution)
        diagnostics = _v56_render_diagnostics(renderer, groups, chunk_reports, force_chunk_audio_track, timings)
        report = {
            "engine_version": ENGINE_VERSION,
            "status": "failed",
            "failed_chunk": failed_chunk,
            "failed_stage": stage,
            "error": str(error),
            "failure": failure,
            "output_path": str(final_output),
            "selected_backend": self.backend_execution.selected_backend_name,
            "backend": backend_payload,
            "chunk_dir": str(self.chunk_dir),
            "chunks": chunk_reports,
            "photo_segment_cache": renderer._photo_segment_cache_summary(),
            "card_segment_cache": renderer._card_segment_cache_summary(),
            "video_segment_cache": renderer._video_segment_cache_summary(),
            "proxy_media": renderer._proxy_media_summary(),
            "cache_cleanup": renderer.cache_cleanup_stats,
            "render_scheduler": renderer.render_scheduler_summary,
            "segment_routes": segment_routes,
            "chunk_routes": chunk_routes,
            "timings": dict(timings),
            "recovery": _v56_build_recovery_summary(
                manifest,
                chunk_reports=chunk_reports,
                failed_chunk=failed_chunk,
                failure=failure,
                manifest_path=self.manifest_path,
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            ),
            "chunk_scheduler": {
                "strategy_version": "chunk_rules_v1",
                "route_counts": chunk_route_counts,
                "total_chunks": len(groups),
            },
            "diagnostics": diagnostics,
            **_v56_report_summary_fields(backend_payload, diagnostics, render_intent="final"),
            "created_at": datetime.now().isoformat(),
        }
        _v56_write_build_report(self.report_path, report)

    def render(self) -> None:
        if not HAS_MOVIEPY:
            raise RuntimeError("MoviePy unavailable; stable renderer cannot render video")

        started_at = datetime.now()
        tmp_output = self.output.with_suffix(".rendering.tmp.mp4")
        final_output = self.output

        if tmp_output.exists():
            try:
                tmp_output.unlink()
            except Exception:
                pass

        renderer = Renderer(self.plan, str(self.output), self.params)
        segments = self.plan.get("segments", [])
        force_chunk_audio_track = _v56_stable_should_force_chunk_audio_track(renderer, segments)
        groups = _v56_build_chunk_groups(segments, self.chunk_seconds, self.params)
        timings: Dict[str, Any] = {"total_render_seconds": 0.0}
        chunk_route_counts: Dict[str, int] = {}
        for group in groups:
            route = str(group.get("runtime_chunk_route") or "moviepy_chunk")
            chunk_route_counts[route] = chunk_route_counts.get(route, 0) + 1
        manifest = self._load_manifest()
        manifest.setdefault("engine_version", ENGINE_VERSION)
        manifest.setdefault("chunks", {})
        manifest.setdefault("render_attempts", 0)
        manifest["render_attempts"] = int(manifest.get("render_attempts") or 0) + 1
        manifest["last_started_at"] = datetime.now().isoformat()
        resumed_from_manifest = any(
            isinstance(item, dict) and item.get("status") in {"done", "failed"}
            for item in (manifest.get("chunks") or {}).values()
        )
        reused_chunk_count = 0
        self._save_manifest(manifest)
        if chunk_route_counts:
            compact = ", ".join(f"{key}={value}" for key, value in sorted(chunk_route_counts.items()))
            emit_event("log", message=f"Chunk scheduler summary: {compact}")

        emit_event(
            "phase",
            phase="render",
            message=f"Using V5.6 stable render mode: {len(groups)} chunks, {int(self.chunk_seconds)} seconds each",
            percent=8,
        )

        rendered_chunks: List[Path] = []
        chunk_reports: List[Dict[str, Any]] = []
        chunk_render_started = perf_counter()

        for group in groups:
            idx = int(group["index"])
            chunk_name = f"chunk_{idx:03d}.mp4"
            chunk_path = self.chunk_dir / chunk_name
            key = str(group["cache_key"])
            existing = manifest.get("chunks", {}).get(chunk_name, {})

            ok, reason, duration = _v56_validate_video(chunk_path)
            if existing.get("cache_key") == key and existing.get("status") == "done" and ok:
                reused_chunk_count += 1
                emit_event("phase", phase="render", message=f"Reusing cached chunk {chunk_name}", percent=min(94, 10 + int((idx / max(len(groups), 1)) * 80)))
                rendered_chunks.append(chunk_path)
                chunk_reports.append({
                    "name": chunk_name,
                    "status": "cached",
                    "duration": duration,
                    "cache_key": key,
                    "runtime_chunk_route": group.get("runtime_chunk_route"),
                    "runtime_chunk_route_reason": group.get("runtime_chunk_route_reason"),
                })
                continue

            try:
                _v56_write_chunk_video(
                    renderer,
                    group,
                    chunk_path,
                    self.fps,
                    self.params,
                    ensure_audio_track=force_chunk_audio_track,
                )
                ok, reason, duration = _v56_validate_video(chunk_path)
                if not ok:
                    raise RuntimeError(reason)

                manifest["chunks"][chunk_name] = {
                    "status": "done",
                    "cache_key": key,
                    "path": str(chunk_path),
                    "duration": duration,
                    "attempt_count": int(existing.get("attempt_count") or 0) + 1,
                    "runtime_chunk_route": group.get("runtime_chunk_route"),
                    "runtime_chunk_route_reason": group.get("runtime_chunk_route_reason"),
                    "updated_at": datetime.now().isoformat(),
                }
                manifest["last_completed_chunk"] = chunk_name
                self._save_manifest(manifest)
                rendered_chunks.append(chunk_path)
                chunk_reports.append({
                    "name": chunk_name,
                    "status": "rendered",
                    "duration": duration,
                    "cache_key": key,
                    "runtime_chunk_route": group.get("runtime_chunk_route"),
                    "runtime_chunk_route_reason": group.get("runtime_chunk_route_reason"),
                })
            except Exception as exc:
                failure = _v56_classify_render_failure(exc, "chunk_render")
                manifest["chunks"][chunk_name] = {
                    "status": "failed",
                    "cache_key": key,
                    "path": str(chunk_path),
                    "error": str(exc),
                    "attempt_count": int(existing.get("attempt_count") or 0) + 1,
                    "failure": failure,
                    "runtime_chunk_route": group.get("runtime_chunk_route"),
                    "runtime_chunk_route_reason": group.get("runtime_chunk_route_reason"),
                    "updated_at": datetime.now().isoformat(),
                }
                manifest["last_failed_chunk"] = chunk_name
                manifest["last_failure"] = failure
                self._save_manifest(manifest)
                self._write_failure_report(
                    renderer=renderer,
                    manifest=manifest,
                    groups=groups,
                    chunk_reports=chunk_reports,
                    chunk_route_counts=chunk_route_counts,
                    timings=timings,
                    force_chunk_audio_track=force_chunk_audio_track,
                    final_output=final_output,
                    error=exc,
                    stage="chunk_render",
                    failed_chunk=chunk_name,
                    resumed_from_manifest=resumed_from_manifest,
                    reused_chunk_count=reused_chunk_count,
                )
                raise

        if False and not rendered_chunks:
            raise RuntimeError("stable render produced no successful chunks")

        if not rendered_chunks:
            exc = RuntimeError("stable render produced no successful chunks")
            manifest["last_failure"] = _v56_classify_render_failure(exc, "chunk_render")
            self._save_manifest(manifest)
            self._write_failure_report(
                renderer=renderer,
                manifest=manifest,
                groups=groups,
                chunk_reports=chunk_reports,
                chunk_route_counts=chunk_route_counts,
                timings=timings,
                force_chunk_audio_track=force_chunk_audio_track,
                final_output=final_output,
                error=exc,
                stage="chunk_render",
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            )
            raise exc

        timings["chunk_render_seconds"] = round(perf_counter() - chunk_render_started, 4)
        concat_started = perf_counter()
        concat_strategy = "ffmpeg_copy"
        concat_ok = _v56_concat_chunks_ffmpeg(rendered_chunks, tmp_output, self.project_dir)
        if not concat_ok:
            concat_strategy = "ffmpeg_reencode"
            concat_ok = _v56_concat_chunks_ffmpeg_reencode(rendered_chunks, tmp_output, self.project_dir, self.fps, self.params)
        if not concat_ok:
            concat_strategy = "moviepy_fallback"
            try:
                _v56_concat_chunks_moviepy(rendered_chunks, tmp_output, self.fps, self.params)
            except Exception as exc:
                manifest["last_failure"] = _v56_classify_render_failure(exc, "concat")
                self._save_manifest(manifest)
                self._write_failure_report(
                    renderer=renderer,
                    manifest=manifest,
                    groups=groups,
                    chunk_reports=chunk_reports,
                    chunk_route_counts=chunk_route_counts,
                    timings=timings,
                    force_chunk_audio_track=force_chunk_audio_track,
                    final_output=final_output,
                    error=exc,
                    stage="concat",
                    resumed_from_manifest=resumed_from_manifest,
                    reused_chunk_count=reused_chunk_count,
                )
                raise
        timings["concat_seconds"] = round(perf_counter() - concat_started, 4)
        timings["concat_strategy"] = concat_strategy

        ok, reason, final_duration = _v56_validate_video(tmp_output)
        if not ok:
            exc = RuntimeError(f"final stable output validation failed: {reason}")
            manifest["last_failure"] = _v56_classify_render_failure(exc, "output_validate")
            self._save_manifest(manifest)
            self._write_failure_report(
                renderer=renderer,
                manifest=manifest,
                groups=groups,
                chunk_reports=chunk_reports,
                chunk_route_counts=chunk_route_counts,
                timings=timings,
                force_chunk_audio_track=force_chunk_audio_track,
                final_output=final_output,
                error=exc,
                stage="output_validate",
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            )
            raise exc
            raise RuntimeError(f"chunk validation failed after render: {reason}")

        mixed_output = tmp_output.with_suffix(".audio.tmp.mp4")
        final_mix_started = perf_counter()
        audio_mix_applied = False
        mix_ok, mix_error = _v56_safe_apply_final_bgm_mix(
            tmp_output,
            mixed_output,
            renderer.audio_settings,
            final_duration,
            prepared_bgm_path=renderer._prepare_music_bed(final_duration) or renderer._prepare_music_path(),
            prepared_bgm_is_bed=True,
        )
        if mix_error is not None:
            manifest["last_failure"] = _v56_classify_render_failure(mix_error, "audio_mix")
            self._save_manifest(manifest)
            self._write_failure_report(
                renderer=renderer,
                manifest=manifest,
                groups=groups,
                chunk_reports=chunk_reports,
                chunk_route_counts=chunk_route_counts,
                timings=timings,
                force_chunk_audio_track=force_chunk_audio_track,
                final_output=final_output,
                error=mix_error,
                stage="audio_mix",
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            )
            raise mix_error
        if mix_ok:
            audio_mix_applied = True
            try:
                tmp_output.unlink()
            except Exception:
                pass
            os.replace(str(mixed_output), str(tmp_output))
            ok, reason, final_duration = _v56_validate_video(tmp_output)
            if not ok:
                exc = RuntimeError(f"final audio mix validation failed: {reason}")
                manifest["last_failure"] = _v56_classify_render_failure(exc, "audio_mix")
                self._save_manifest(manifest)
                self._write_failure_report(
                    renderer=renderer,
                    manifest=manifest,
                    groups=groups,
                    chunk_reports=chunk_reports,
                    chunk_route_counts=chunk_route_counts,
                    timings=timings,
                    force_chunk_audio_track=force_chunk_audio_track,
                    final_output=final_output,
                    error=exc,
                    stage="audio_mix",
                    resumed_from_manifest=resumed_from_manifest,
                    reused_chunk_count=reused_chunk_count,
                )
                raise exc
                raise RuntimeError(f"final output validation failed after concat: {reason}")

        timings["final_audio_mix_seconds"] = round(perf_counter() - final_mix_started, 4)
        timings["final_audio_mix_applied"] = audio_mix_applied
        _v56_atomic_replace(tmp_output, final_output)

        elapsed = (datetime.now() - started_at).total_seconds()
        timings["total_render_seconds"] = round(elapsed, 4)
        renderer.last_render_timings = dict(timings)
        renderer._emit_photo_segment_cache_summary()
        renderer._emit_card_segment_cache_summary()
        renderer._emit_video_segment_cache_summary()
        renderer._emit_proxy_media_summary()
        renderer._cleanup_project_cache_dirs()
        manifest["last_completed_at"] = datetime.now().isoformat()
        manifest["last_failure"] = None
        self._save_manifest(manifest)
        backend_payload = _v56_backend_report_payload(self.backend_execution)
        diagnostics = _v56_render_diagnostics(renderer, groups, chunk_reports, force_chunk_audio_track, timings)
        report = {
            "engine_version": ENGINE_VERSION,
            "status": "done",
            "render_mode": "v5.6_long_video_stable",
            "output_path": str(final_output),
            "selected_backend": self.backend_execution.selected_backend_name,
            "backend": backend_payload,
            "output_size_bytes": final_output.stat().st_size if final_output.exists() else None,
            "duration_seconds": final_duration,
            "elapsed_seconds": elapsed,
            "chunk_seconds": self.chunk_seconds,
            "chunk_count": len(rendered_chunks),
            "chunk_dir": str(self.chunk_dir),
            "chunks": chunk_reports,
            "photo_segment_cache": renderer._photo_segment_cache_summary(),
            "card_segment_cache": renderer._card_segment_cache_summary(),
            "video_segment_cache": renderer._video_segment_cache_summary(),
            "proxy_media": renderer._proxy_media_summary(),
            "cache_cleanup": renderer.cache_cleanup_stats,
            "render_scheduler": renderer.render_scheduler_summary,
            "segment_routes": _v56_collect_segment_route_details(segments),
            "chunk_routes": _v56_collect_chunk_route_details(groups, chunk_reports),
            "timings": dict(timings),
            "recovery": _v56_build_recovery_summary(
                manifest,
                chunk_reports=chunk_reports,
                manifest_path=self.manifest_path,
                resumed_from_manifest=resumed_from_manifest,
                reused_chunk_count=reused_chunk_count,
            ),
            "chunk_scheduler": {
                "strategy_version": "chunk_rules_v1",
                "route_counts": chunk_route_counts,
                "total_chunks": len(groups),
            },
            "diagnostics": diagnostics,
            **_v56_report_summary_fields(backend_payload, diagnostics, render_intent="final"),
            "created_at": datetime.now().isoformat(),
        }
        _v56_write_build_report(self.report_path, report)
        emit_event("phase", phase="done", message="Stable render complete", percent=100)


def _v56_run_render_backend(
    decision: Any,
    plan: Dict[str, Any],
    output: str,
    params: Dict[str, Any],
    plan_path: Optional[str] = None,
) -> BackendExecutionResult:
    resolved_decision = coerce_backend_decision(decision)
    fallback_chain = list(resolved_decision.fallback_chain or [resolved_decision.backend_name])
    ordered_candidates: List[str] = []
    for backend_name in [resolved_decision.backend_name, *fallback_chain]:
        normalized = str(backend_name or "").strip()
        if normalized and normalized not in ordered_candidates:
            ordered_candidates.append(normalized)

    failed_reasons: List[str] = []
    last_error: Optional[Exception] = None
    for backend_name in ordered_candidates:
        initial_execution = BackendExecutionResult.from_decision(
            resolved_decision,
            fallback_used=(backend_name if backend_name != resolved_decision.backend_name else None),
            fallback_reason=merge_backend_reason_tags(failed_reasons) if failed_reasons else None,
        )
        effective_params = dict(params or {})
        effective_params["_backend_decision"] = resolved_decision.to_dict()
        effective_params["_backend_execution"] = initial_execution.to_dict()

        try:
            if backend_name == "ffmpeg_stable_backend":
                result = run_ffmpeg_stable_backend(
                    sys.modules[__name__],
                    resolved_decision,
                    plan,
                    output,
                    effective_params,
                    plan_path=plan_path,
                )
            elif backend_name == "legacy_moviepy_backend":
                result = run_legacy_moviepy_backend(
                    sys.modules[__name__],
                    resolved_decision,
                    plan,
                    output,
                    effective_params,
                )
            elif backend_name == "mlt_backend":
                result = run_mlt_backend(
                    sys.modules[__name__],
                    resolved_decision,
                    plan,
                    output,
                    effective_params,
                    plan_path=plan_path,
                )
            else:
                raise RuntimeError(f"Unknown render backend: {backend_name}")
        except Exception as exc:
            last_error = exc
            failed_reasons.append(
                str(
                    getattr(exc, "reason", None)
                    or str(exc)
                    or backend_name
                    or exc.__class__.__name__
                )
            )
            continue

        if backend_name == resolved_decision.backend_name:
            return result
        return BackendExecutionResult.from_decision(
            resolved_decision,
            actual_backend_name=result.actual_backend_name,
            fallback_used=result.actual_backend_name,
            fallback_reason=merge_backend_reason_tags(failed_reasons) if failed_reasons else None,
        )

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"Unable to execute render backend: {resolved_decision.backend_name}")


def render_with_v56_stability(plan_path: str, output: str, params: Dict[str, Any]) -> None:
    plan = read_json(plan_path)
    decision = _v56_resolve_render_backend_decision(plan, params)
    _v56_run_render_backend(decision, plan, output, params, plan_path=plan_path)


def build_low_res_preview_plan(
    plan: Dict[str, Any],
    max_duration: float = 20.0,
    max_segments: int = 8,
) -> Dict[str, Any]:
    """Create a short render-plan sample for real low-res previews."""
    preview_plan = dict(plan)
    source_segments = list(plan.get("segments") or [])
    remaining = max(1.0, float(max_duration or 20.0))
    limit = max(1, int(max_segments or 8))
    cursor = 0.0
    segments: List[Dict[str, Any]] = []

    for source in source_segments:
        if len(segments) >= limit or remaining <= 0:
            break
        duration = max(0.1, float(source.get("duration") or 0.1))
        used_duration = min(duration, remaining)
        seg = dict(source)
        seg["duration"] = used_duration
        seg["start_time"] = cursor
        seg["end_time"] = cursor + used_duration
        segments.append(seg)
        cursor += used_duration
        remaining -= used_duration

    if not segments and source_segments:
        seg = dict(source_segments[0])
        used_duration = min(max(0.1, float(seg.get("duration") or 0.1)), max_duration)
        seg["duration"] = used_duration
        seg["start_time"] = 0.0
        seg["end_time"] = used_duration
        segments.append(seg)
        cursor = used_duration

    preview_plan["segments"] = segments
    preview_plan["total_duration"] = cursor
    preview_settings = dict(plan.get("render_settings") or {})
    preview_settings["preview"] = True
    preview_settings["fps"] = min(int(preview_settings.get("fps") or 24), 15)
    preview_settings["quality"] = "draft"
    preview_settings["python_quality"] = "draft"
    preview_settings["render_mode"] = "standard"
    preview_settings["performance_mode"] = "balanced"
    preview_plan["render_settings"] = preview_settings
    return preview_plan


def command_preview_render(args: argparse.Namespace) -> None:
    plan = read_json(args.plan)
    params = json.loads(args.params) if getattr(args, "params", None) else {}
    sibling_library_path = _guess_sibling_library_path(args.plan)
    if sibling_library_path and "proxy_media_manifest" not in params:
        params["proxy_media_manifest"] = read_json(str(sibling_library_path)).get("proxy_media_manifest", {})
    params["plan_path"] = str(args.plan)
    aspect_ratio = params.get("aspect_ratio") or plan.get("render_settings", {}).get("aspect_ratio") or "16:9"
    params.update({
        "aspect_ratio": aspect_ratio,
        "preview": True,
        "preview_height": int(args.height or 540),
        "fps": int(args.fps or 15),
        "quality": "draft",
        "python_quality": "draft",
        "render_mode": "standard",
        "performance_mode": "balanced",
        "cover": False,
    })
    preview_plan = build_low_res_preview_plan(
        plan,
        max_duration=float(args.max_duration or 20.0),
        max_segments=int(args.max_segments or 8),
    )
    emit_event(
        "phase",
        phase="preview",
        message=f"Generating low-res preview: {len(preview_plan.get('segments', []))} segments",
        percent=5,
    )
    Renderer(preview_plan, args.output, params).render()



def command_render(args: argparse.Namespace) -> None:
    params = json.loads(args.params) if getattr(args, "params", None) else {}
    render_with_v56_stability(args.plan, args.output, params)


def preview_resolution(aspect_ratio: str) -> Tuple[int, int]:
    if aspect_ratio == "9:16":
        return 360, 640
    if aspect_ratio == "1:1":
        return 480, 480
    return 640, 360


def preview_background(size: Tuple[int, int], theme: str) -> Image.Image:
    palettes = {
        "nature": ((18, 54, 38), (106, 142, 69), (211, 238, 174)),
        "city": ((7, 12, 28), (43, 63, 88), (47, 157, 210)),
        "clean": ((248, 250, 252), (205, 220, 232), (164, 220, 190)),
        "travel": ((40, 62, 57), (129, 171, 159), (201, 132, 87)),
    }
    c1, c2, c3 = palettes.get(theme, palettes["travel"])
    w, h = size
    img = Image.new("RGB", size, c1)
    draw = ImageDraw.Draw(img)
    for y in range(h):
        ratio = y / max(h - 1, 1)
        if ratio < 0.55:
            local = ratio / 0.55
            color = tuple(int(c1[i] + (c2[i] - c1[i]) * local) for i in range(3))
        else:
            local = (ratio - 0.55) / 0.45
            color = tuple(int(c2[i] + (c3[i] - c2[i]) * local) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)
    draw.ellipse((int(w * 0.08), int(h * 0.12), int(w * 0.42), int(h * 0.68)), fill=(*c3[:3],))
    overlay = Image.new("RGB", size, (8, 18, 14))
    return Image.blend(img.filter(ImageFilter.GaussianBlur(radius=10)), overlay, 0.18)


def command_preview_title(args: argparse.Namespace) -> None:
    if not HAS_MOVIEPY:
        raise RuntimeError(
            "MoviePy not installed. Please run: "
            "python -m pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg"
        )

    output_path = Path(args.output)
    ensure_parent(output_path)
    duration = max(1.0, min(float(args.duration or 3.0), 6.0))
    aspect_ratio = args.aspect_ratio or "16:9"
    target_size = preview_resolution(aspect_ratio)
    style = json.loads(args.style_json) if args.style_json else {}
    style.setdefault("preset", "cinematic_bold")
    style.setdefault("motion", "fade_slide_up")

    renderer = TitleStyleRenderer(target_size)
    bg = preview_background(target_size, args.background or "travel")
    text_img = renderer.render_layer(args.title or "Title preview", args.subtitle or None, style, is_full_card=True)
    bg_clip = ImageClip(np.array(bg)).set_duration(duration)
    text_clip = ImageClip(np.array(text_img), ismask=False).set_duration(duration)
    text_clip = renderer.animate(text_clip, style.get("motion", "fade_slide_up"), duration)
    final = CompositeVideoClip([bg_clip, text_clip], size=target_size).set_duration(duration)
    try:
        final.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio=False,
            preset="veryfast",
            threads=2,
            ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-crf", "28"],
            logger=None,
        )
    finally:
        for clip in (text_clip, bg_clip, final):
            try:
                clip.close()
            except Exception:
                pass

    print(json.dumps({
        "ok": True,
        "output_path": str(output_path),
        "duration": duration,
        "width": target_size[0],
        "height": target_size[1],
    }, ensure_ascii=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Video Create Studio V5 Engine")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("scan", help="Scan input folder and generate media_library.json")
    p.add_argument("--input_folder", required=True)
    p.add_argument("--output")
    p.add_argument("--recursive", action="store_true", default=True)
    p.set_defaults(func=command_scan)

    p = sub.add_parser("plan", help="Generate story_blueprint.json from media_library.json")
    p.add_argument("--library", required=True)
    p.add_argument("--output")
    p.add_argument("--strategy", default="city_date_spot")
    p.add_argument("--template", default="auto", help="Template mode: auto, off, or a template id such as travel_postcard")
    p.add_argument("--music_blueprint", default="recommend", help="Music blueprint mode: recommend, apply, or off")
    p.set_defaults(func=command_plan)

    p = sub.add_parser("compile", help="Compile render_plan.json from story_blueprint.json")
    p.add_argument("--blueprint", required=True)
    p.add_argument("--library", required=True)
    p.add_argument("--output")
    p.set_defaults(func=command_compile)

    p = sub.add_parser("render", help="Render final MP4 from render_plan.json")
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--params")
    p.set_defaults(func=command_render)

    p = sub.add_parser("preview-render", help="Render a real low-resolution preview from render_plan.json")
    p.add_argument("--plan", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--params")
    p.add_argument("--height", type=int, default=540)
    p.add_argument("--fps", type=int, default=15)
    p.add_argument("--max_duration", type=float, default=20.0)
    p.add_argument("--max_segments", type=int, default=8)
    p.set_defaults(func=command_preview_render)

    p = sub.add_parser("preview-title", help="Render a low-resolution title-style preview MP4")
    p.add_argument("--title", required=True)
    p.add_argument("--subtitle", default="")
    p.add_argument("--style_json", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--aspect_ratio", default="16:9")
    p.add_argument("--background", default="travel")
    p.add_argument("--duration", default="3.0")
    p.set_defaults(func=command_preview_title)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        raise SystemExit(2)

    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        import traceback

        emit_event("error", message=str(exc), details=traceback.format_exc())
        raise
