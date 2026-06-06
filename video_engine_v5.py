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
import json
import math
import os
import re
import shutil
import sys
import subprocess
import tempfile
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
from video_engine import render_chunks as render_chunks_helpers
from video_engine import render_finalize as render_finalize_helpers
from video_engine import render_cards as render_cards_helpers
from video_engine import render_image_cache as render_image_cache_helpers
from video_engine import render_media_clips as render_media_clip_helpers
from video_engine import render_proxy as render_proxy_helpers
from video_engine import render_stable as render_stable_helpers
from video_engine import render_visual_base as render_visual_base_helpers
from video_engine import render_video_cache as render_video_cache_helpers
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
    return render_proxy_helpers.video_needs_display_normalization(source)


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
    return render_proxy_helpers.normalize_proxy_manifest(source)


def _load_proxy_manifest_from_library_path(library_path: Optional[str]) -> Dict[str, Dict[str, Any]]:
    return render_proxy_helpers.load_proxy_manifest_from_library_path(
        library_path,
        read_json_fn=read_json,
    )


def _guess_sibling_library_path(plan_path: Optional[str]) -> Optional[Path]:
    if not plan_path:
        return None
    plan_file = Path(str(plan_path))
    parent = plan_file.parent
    if not parent:
        return None
    candidate = parent / "media_library.json"
    return candidate if candidate.is_file() else None


class TitleStyleRenderer(render_cards_helpers.TitleStyleRenderer):
    def __init__(self, target_size: Tuple[int, int]):
        super().__init__(
            target_size,
            image_cls=Image,
            image_draw_mod=ImageDraw,
            image_filter_mod=ImageFilter,
            color_clip_cls=ColorClip,
            load_font_fn=load_font,
            text_size_fn=text_size,
            draw_text_with_emoji_fn=draw_text_with_emoji,
        )


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
        return render_image_cache_helpers.should_prerender_image_segment(self, duration, motion_config)

    def _ffmpeg_image_motion_cache_spec(self, motion_config: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        return render_image_cache_helpers.ffmpeg_image_motion_cache_spec(motion_config)

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
        return render_image_cache_helpers.prerender_image_segment(
            self,
            source,
            fixed,
            duration,
            motion_config,
            overlay_spec,
            emit_event_fn=emit_event,
            quality_to_crf_fn=quality_to_crf,
            validate_video_fn=_v56_validate_video,
            close_clip_fn=close_clip,
        )

    def _ffmpeg_prerender_image_segment(
        self,
        source: Path,
        fixed: Path,
        duration: float,
        motion_config: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        return render_image_cache_helpers.ffmpeg_prerender_image_segment(
            self,
            source,
            fixed,
            duration,
            motion_config,
            emit_event_fn=emit_event,
            quality_to_crf_fn=quality_to_crf,
            select_video_encoder_fn=select_ffmpeg_video_encoder,
            image_cls=Image,
        )

    def _photo_segment_cache_summary(self) -> Dict[str, int]:
        return render_image_cache_helpers.photo_segment_cache_summary(self)

    def _emit_photo_segment_cache_summary(self) -> None:
        render_image_cache_helpers.emit_photo_segment_cache_summary(self, emit_event_fn=emit_event)

    def _should_prerender_card_segment(self, seg: Dict[str, Any], duration: float) -> bool:
        return render_image_cache_helpers.should_prerender_card_segment(self, seg, duration)

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
        return render_image_cache_helpers.card_segment_cache_path(self, seg, duration)

    def _prerender_card_segment(self, seg: Dict[str, Any], duration: float) -> Optional[Path]:
        return render_image_cache_helpers.prerender_card_segment(
            self,
            seg,
            duration,
            emit_event_fn=emit_event,
            quality_to_crf_fn=quality_to_crf,
            validate_video_fn=_v56_validate_video,
            close_clip_fn=close_clip,
        )

    def _cached_card_segment(self, seg: Dict[str, Any], duration: float):
        return render_image_cache_helpers.cached_card_segment(
            self,
            seg,
            duration,
            video_file_clip_cls=VideoFileClip,
        )

    def _card_segment_cache_summary(self) -> Dict[str, int]:
        return render_image_cache_helpers.card_segment_cache_summary(self)

    def _emit_card_segment_cache_summary(self) -> None:
        render_image_cache_helpers.emit_card_segment_cache_summary(self, emit_event_fn=emit_event)

    def _standard_visual_cache_path(self) -> Path:
        return render_visual_base_helpers.standard_visual_cache_path(self)

    def _emit_visual_base_cache_summary(self) -> None:
        render_visual_base_helpers.emit_visual_base_cache_summary(self, emit_event_fn=emit_event)

    def _should_use_chunked_visual_base(self) -> bool:
        return render_visual_base_helpers.should_use_chunked_visual_base(self)

    def _is_safe_standard_visual_chunk_boundary(self, next_seg: Dict[str, Any]) -> bool:
        return render_visual_base_helpers.is_safe_standard_visual_chunk_boundary(next_seg)

    def _standard_visual_transition_influence(self, seg: Dict[str, Any]) -> Dict[str, Any]:
        return render_visual_base_helpers.standard_visual_transition_influence(seg)

    def _standard_visual_chunk_route_payload(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        return render_visual_base_helpers.standard_visual_chunk_route_payload(self, items)

    def _build_standard_visual_transition_units(self) -> List[List[Dict[str, Any]]]:
        return render_visual_base_helpers.build_standard_visual_transition_units(self)

    def _build_standard_visual_chunk_groups(self) -> List[Dict[str, Any]]:
        return render_visual_base_helpers.build_standard_visual_chunk_groups(self)

    def _render_visual_timeline_clip(self) -> Tuple[Any, List[Dict[str, Any]]]:
        return render_visual_base_helpers.render_visual_timeline_clip(self, emit_event_fn=emit_event)

    def _write_visual_base_video(self, output_path: Path) -> float:
        return render_visual_base_helpers.write_visual_base_video(
            self,
            output_path,
            logger_factory=lambda base_percent, span_percent: JsonMoviePyLogger(
                base_percent=base_percent,
                span_percent=span_percent,
            ),
            quality_to_crf_fn=quality_to_crf,
            close_clip_fn=close_clip,
            emit_event_fn=emit_event,
        )

    def _write_visual_base_video_from_chunks(self, output_path: Path) -> Optional[float]:
        return render_visual_base_helpers.write_visual_base_video_from_chunks(
            self,
            output_path,
            validate_video_fn=_v56_validate_video,
            write_chunk_video_fn=_v56_write_chunk_video,
            concat_chunks_ffmpeg_fn=_v56_concat_chunks_ffmpeg,
            concat_chunks_ffmpeg_reencode_fn=_v56_concat_chunks_ffmpeg_reencode,
            concat_chunks_moviepy_fn=_v56_concat_chunks_moviepy,
            atomic_replace_fn=_v56_atomic_replace,
            emit_event_fn=emit_event,
        )

    def _materialize_standard_visual_base(self) -> Tuple[Path, float]:
        return render_visual_base_helpers.materialize_standard_visual_base(
            self,
            validate_video_fn=_v56_validate_video,
            write_visual_base_video_fn=self._write_visual_base_video,
            write_visual_base_video_from_chunks_fn=self._write_visual_base_video_from_chunks,
            emit_event_fn=emit_event,
        )

    def _finalize_output_from_visual_base(self, visual_base_path: Path, output_path: Path, duration: float) -> float:
        return render_finalize_helpers.finalize_output_from_visual_base(
            self,
            visual_base_path,
            output_path,
            duration,
            apply_final_bgm_mix_fn=_v56_apply_final_bgm_mix,
            validate_video_fn=_v56_validate_video,
            atomic_replace_fn=_v56_atomic_replace,
        )

    def _video_segment_cache_summary(self) -> Dict[str, int]:
        return render_video_cache_helpers.video_segment_cache_summary(self)

    def _emit_video_segment_cache_summary(self) -> None:
        render_video_cache_helpers.emit_video_segment_cache_summary(self, emit_event_fn=emit_event)

    def _proxy_media_summary(self) -> Dict[str, int]:
        return render_proxy_helpers.proxy_media_summary(self)

    def _emit_proxy_media_summary(self) -> None:
        render_proxy_helpers.emit_proxy_media_summary(self, emit_event_fn=emit_event)

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
        return render_media_clip_helpers.find_visual_source(self, direction)

    def _source_frame_for_background(self, source_path: Optional[str], position: str) -> Optional[Path]:
        return render_media_clip_helpers.source_frame_for_background(
            self,
            source_path,
            position,
            emit_event_fn=emit_event,
            image_cls=Image,
            image_ops=ImageOps,
            video_file_clip_cls=VideoFileClip,
        )

    def _chapter_card(self, seg: Dict[str, Any], duration: float):
        return render_cards_helpers.chapter_card(
            self,
            seg,
            duration,
            np_module=np,
            image_clip_cls=ImageClip,
            composite_video_clip_cls=CompositeVideoClip,
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
        return render_cards_helpers.text_card(
            self,
            title,
            subtitle,
            duration,
            main=main,
            background_source=background_source,
            background_position=background_position,
            background_source_2=background_source_2,
            background_position_2=background_position_2,
            blend_sources=blend_sources,
            title_style=title_style,
            np_module=np,
            image_clip_cls=ImageClip,
            composite_video_clip_cls=CompositeVideoClip,
        )

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
        return render_cards_helpers.text_card_image(
            self,
            title,
            subtitle,
            main=main,
            background_source=background_source,
            background_position=background_position,
            background_source_2=background_source_2,
            background_position_2=background_position_2,
            blend_sources=blend_sources,
            title_style=title_style,
        )

    def _build_text_background(
        self,
        source_1: Optional[str],
        pos_1: str,
        source_2: Optional[str] = None,
        pos_2: str = "first",
        blend_sources: bool = False,
    ) -> Image.Image:
        return render_cards_helpers.build_text_background(
            self,
            source_1,
            pos_1,
            source_2,
            pos_2,
            blend_sources=blend_sources,
            image_cls=Image,
        )

    def _apply_overlay_title(self, clip: Any, seg: Dict[str, Any]):
        return render_cards_helpers.apply_overlay_title(
            self,
            clip,
            seg,
            composite_video_clip_cls=CompositeVideoClip,
            image_clip_cls=ImageClip,
            np_module=np,
        )

    def _overlay_title_clip(self, title: str, subtitle: Optional[str], duration: float, style: Optional[Dict[str, Any]] = None):
        return render_cards_helpers.overlay_title_clip(
            self,
            title,
            subtitle,
            duration,
            style=style,
            np_module=np,
            image_clip_cls=ImageClip,
        )

    def _image_overlay_cache_spec(self, seg: Dict[str, Any], duration: float) -> Optional[Dict[str, Any]]:
        return _v56_image_overlay_cache_spec(seg, duration)

    def _get_proxy_source(self, source: Path, is_video: bool) -> Path:
        return render_proxy_helpers.get_proxy_source(
            self,
            source,
            is_video,
            engine_version=ENGINE_VERSION,
            scan_proxy_profile=SCAN_PROXY_PROFILE,
            emit_event_fn=emit_event,
            image_cls=Image,
            image_ops=ImageOps,
        )

    def _image_clip(
        self,
        source: Path,
        duration: float,
        motion_config: Optional[Dict[str, Any]] = None,
        overlay_spec: Optional[Dict[str, Any]] = None,
    ):
        return render_media_clip_helpers.image_clip(
            self,
            source,
            duration,
            motion_config,
            overlay_spec,
            image_cls=Image,
            image_ops=ImageOps,
            video_file_clip_cls=VideoFileClip,
        )

    def _video_clip(
        self,
        source: Path,
        duration: float,
        keep_audio: bool = True,
        motion_config: Optional[Dict[str, Any]] = None,
        prefer_ffmpeg: bool = False,
    ):
        return render_media_clip_helpers.video_clip(
            self,
            source,
            duration,
            keep_audio=keep_audio,
            motion_config=motion_config,
            prefer_ffmpeg=prefer_ffmpeg,
            audio_file_clip_cls=AudioFileClip,
            color_clip_cls=ColorClip,
            composite_video_clip_cls=CompositeVideoClip,
            image_clip_cls=ImageClip,
            video_file_clip_cls=VideoFileClip,
        )

    def _normalize_video_display_geometry(self, source: Path) -> Path:
        return render_proxy_helpers.normalize_video_display_geometry(
            self,
            source,
            emit_event_fn=emit_event,
            needs_display_normalization_fn=video_needs_display_normalization,
        )

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
        return render_video_cache_helpers.ffmpeg_video_motion_cache_spec(motion_config)

    def _can_use_ffmpeg_fitted_video(self, seg: Dict[str, Any]) -> bool:
        return render_video_cache_helpers.can_use_ffmpeg_fitted_video(self, seg)

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
        return render_video_cache_helpers.ffmpeg_fit_video_segment(
            self,
            source,
            duration,
            keep_audio=keep_audio,
            force_audio_track=force_audio_track,
            track_stats=track_stats,
            emit_event_fn=emit_event,
            quality_to_crf_fn=quality_to_crf,
            select_video_encoder_fn=select_ffmpeg_video_encoder,
            video_has_audio_stream_fn=video_has_audio_stream,
        )

    def _ffmpeg_fit_motion_video_segment(
        self,
        source: Path,
        duration: float,
        motion_spec: Dict[str, Any],
        keep_audio: bool = True,
    ) -> Optional[Path]:
        return render_video_cache_helpers.ffmpeg_fit_motion_video_segment(
            self,
            source,
            duration,
            motion_spec,
            keep_audio=keep_audio,
            emit_event_fn=emit_event,
            quality_to_crf_fn=quality_to_crf,
            select_video_encoder_fn=select_ffmpeg_video_encoder,
            video_has_audio_stream_fn=video_has_audio_stream,
        )

    def _prerender_safe_video_overlay_segment(
        self,
        fitted_source: Path,
        seg: Dict[str, Any],
        duration: float,
    ) -> Optional[Path]:
        return render_video_cache_helpers.prerender_safe_video_overlay_segment(
            self,
            fitted_source,
            seg,
            duration,
            emit_event_fn=emit_event,
            quality_to_crf_fn=quality_to_crf,
            validate_video_fn=_v56_validate_video,
            close_clip_fn=close_clip,
            video_file_clip_cls=VideoFileClip,
        )

    def _compose_with_blur_bg(
        self,
        clip: Any,
        duration: float,
        source_image: Optional[Path],
        motion_config: Optional[Dict[str, Any]] = None,
    ):
        return render_media_clip_helpers.compose_with_blur_bg(
            self,
            clip,
            duration,
            source_image,
            motion_config,
            color_clip_cls=ColorClip,
            composite_video_clip_cls=CompositeVideoClip,
            image_cls=Image,
            image_filter_mod=ImageFilter,
            image_clip_cls=ImageClip,
        )

    def _apply_visual_motion(
        self,
        clip: Any,
        duration: float,
        motion_config: Optional[Dict[str, Any]],
    ):
        return render_media_clip_helpers.apply_visual_motion(self, clip, duration, motion_config)

    def _resize_clip_safe(self, clip: Any, scale_fn: Any):
        return render_media_clip_helpers.resize_clip_safe(clip, scale_fn)

    def _blur_bg(self, source_image: Path) -> Path:
        return render_media_clip_helpers.blur_bg(
            self,
            source_image,
            image_cls=Image,
            image_filter_mod=ImageFilter,
        )

    def _add_watermark(self, video: Any, text: str):
        return render_media_clip_helpers.add_watermark(
            video,
            text,
            np_module=np,
            image_cls=Image,
            image_draw_mod=ImageDraw,
            image_clip_cls=ImageClip,
            composite_video_clip_cls=CompositeVideoClip,
            load_font_fn=load_font,
            text_size_fn=text_size,
            draw_text_with_emoji_fn=draw_text_with_emoji,
        )

    def _create_cover(self) -> None:
        render_cards_helpers.create_cover(self, emit_event_fn=emit_event)


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
    return render_finalize_helpers.validate_video(
        path,
        min_size=min_size,
        has_moviepy=HAS_MOVIEPY,
        video_file_clip_cls=VideoFileClip,
        close_clip_fn=close_clip,
    )


def _v56_concat_chunks_ffmpeg(chunks: List[Path], tmp_output: Path, project_dir: Path) -> bool:
    return render_chunks_helpers._v56_concat_chunks_ffmpeg(
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
    return render_chunks_helpers._v56_concat_chunks_ffmpeg_reencode(
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
    return render_chunks_helpers._v56_concat_chunks_moviepy(
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
    return render_finalize_helpers.apply_final_bgm_mix(
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
    return render_chunks_helpers._v56_try_write_ffmpeg_direct_chunk(
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
    return render_chunks_helpers._v56_try_write_ffmpeg_image_chunk(
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
    return render_chunks_helpers._v56_try_write_ffmpeg_fitted_video_chunk(
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
    return render_chunks_helpers._v56_try_write_ffmpeg_card_chunk(
        renderer,
        chunk,
        tmp_chunk,
        params,
        emit_event_fn=emit_event,
        validate_video_fn=_v56_validate_video,
    )


def _v56_ensure_silent_audio_track(video_path: Path, duration: Optional[float] = None) -> bool:
    return render_chunks_helpers._v56_ensure_silent_audio_track(
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
    return render_finalize_helpers.safe_apply_final_bgm_mix(_v56_apply_final_bgm_mix, *args, **kwargs)


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
    return render_chunks_helpers._v56_write_chunk_video(
        renderer,
        chunk,
        chunk_path,
        fps,
        params,
        ensure_audio_track=ensure_audio_track,
        emit_event_fn=emit_event,
        quality_to_crf_fn=quality_to_crf,
        validate_video_fn=_v56_validate_video,
        ensure_silent_audio_track_fn=_v56_ensure_silent_audio_track,
        try_write_ffmpeg_direct_chunk_fn=_v56_try_write_ffmpeg_direct_chunk,
        try_write_ffmpeg_fitted_video_chunk_fn=_v56_try_write_ffmpeg_fitted_video_chunk,
        try_write_ffmpeg_card_chunk_fn=_v56_try_write_ffmpeg_card_chunk,
        try_write_ffmpeg_image_chunk_fn=_v56_try_write_ffmpeg_image_chunk,
        close_clip_fn=close_clip,
        logger_factory=lambda base_percent, span_percent: JsonMoviePyLogger(
            base_percent=base_percent,
            span_percent=span_percent,
        ),
    )


def _v56_should_use_stable_renderer(plan: Dict[str, Any], params: Dict[str, Any]) -> bool:
    return render_stable_helpers.should_use_stable_renderer(plan, params)


def _v56_resolve_render_backend_decision(plan: Dict[str, Any], params: Dict[str, Any]) -> BackendDecision:
    return render_stable_helpers.resolve_render_backend_decision(plan, params)


def _v56_resolve_render_backend(plan: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    return render_stable_helpers.resolve_render_backend(plan, params)


def _v56_backend_report_payload(
    decision: Optional[Any],
    fallback_used: Optional[str] = None,
    fallback_reason: Optional[str] = None,
) -> Dict[str, Any]:
    return render_stable_helpers.backend_report_payload(
        decision,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
    )


class V56StableRenderer(render_stable_helpers.V56StableRenderer):
    def __init__(self, plan: Dict[str, Any], output: str, params: Dict[str, Any], plan_path: Optional[str] = None):
        super().__init__(
            plan,
            output,
            params,
            plan_path=plan_path,
            renderer_cls=Renderer,
            has_moviepy=HAS_MOVIEPY,
            emit_event_fn=emit_event,
            stable_should_force_chunk_audio_track_fn=_v56_stable_should_force_chunk_audio_track,
            validate_video_fn=_v56_validate_video,
            write_chunk_video_fn=_v56_write_chunk_video,
            concat_chunks_ffmpeg_fn=_v56_concat_chunks_ffmpeg,
            concat_chunks_ffmpeg_reencode_fn=_v56_concat_chunks_ffmpeg_reencode,
            concat_chunks_moviepy_fn=_v56_concat_chunks_moviepy,
            safe_apply_final_bgm_mix_fn=_v56_safe_apply_final_bgm_mix,
            classify_render_failure_fn=_v56_classify_render_failure,
            build_recovery_summary_fn=_v56_build_recovery_summary,
            render_diagnostics_fn=_v56_render_diagnostics,
            report_summary_fields_fn=_v56_report_summary_fields,
            collect_segment_route_details_fn=_v56_collect_segment_route_details,
            collect_chunk_route_details_fn=_v56_collect_chunk_route_details,
        )


def _v56_run_render_backend(
    decision: Any,
    plan: Dict[str, Any],
    output: str,
    params: Dict[str, Any],
    plan_path: Optional[str] = None,
) -> BackendExecutionResult:
    return render_stable_helpers.run_render_backend(
        decision,
        plan,
        output,
        params,
        plan_path=plan_path,
        engine_module=sys.modules[__name__],
    )


def render_with_v56_stability(plan_path: str, output: str, params: Dict[str, Any]) -> None:
    return render_stable_helpers.render_with_v56_stability(
        plan_path,
        output,
        params,
        read_json_fn=read_json,
        engine_module=sys.modules[__name__],
    )

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
    return render_cards_helpers.preview_resolution(aspect_ratio)


def preview_background(size: Tuple[int, int], theme: str) -> Image.Image:
    return render_cards_helpers.preview_background(
        size,
        theme,
        image_cls=Image,
        image_draw_mod=ImageDraw,
        image_filter_mod=ImageFilter,
    )


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
