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
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# V5.3.2 early help guard
# Keep `python video_engine_v5.py --help` available even before optional media
# dependencies such as numpy/moviepy/pillow are installed. Real scan/render work
# still validates dependencies when the command continues past this point.
def _print_early_help_without_optional_deps() -> None:
    print("""Video Create Studio V5.6.0 Engine

usage:
  python video_engine_v5.py scan    --input_folder <folder> --output <media_library.json> [--recursive]
  python video_engine_v5.py plan    --library <media_library.json> --output <story_blueprint.json>
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
except Exception:
    HAS_MOVIEPY = False
    moviepy_audio_loop = None


# =========================
# Constants
# =========================

SCHEMA_VERSION = "5.5"
ENGINE_VERSION = "video-create-engine-v5.6.0"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg")
ALL_EXTS = IMAGE_EXTS + VIDEO_EXTS + AUDIO_EXTS

AUDIO_PREFERRED_EXT_SCORE = {
    ".wav": 6,
    ".m4a": 5,
    ".mp3": 4,
    ".flac": 4,
    ".aac": 3,
    ".ogg": 2,
}

AUDIO_MUSIC_HINTS = ("bgm", "music", "soundtrack", "instrumental", "score", "theme", "配乐", "音乐", "伴奏", "纯音乐", "背景音乐")
AUDIO_EFFECT_HINTS = ("effect", "sfx", "音效", "提示音", "转场音")

CITY_KEYWORDS = [
    "北京", "上海", "广州", "深圳", "杭州", "泉州", "厦门", "福州", "南京", "苏州",
    "成都", "重庆", "西安", "东京", "京都", "巴黎", "伦敦", "纽约",
]

# V5.4.2 directory recognition strategy:
# - Strong spot names can identify scenic spots when there is travel context.
# - Suffix keywords are useful under city/date/chapter parents, but should not override
#   first-level content categories by themselves.
# - Weak one-character keywords such as "山" or "桥" are only signals, not decisions.
SPOT_STRONG_KEYWORDS = [
    "开元寺", "西街", "鼓浪屿", "曾厝垵", "清源山", "武夷山", "黄山", "泰山",
    "外滩", "故宫", "天坛", "颐和园", "兵马俑", "环球影城", "迪士尼",
]

SPOT_SUFFIX_KEYWORDS = [
    "寺", "庙", "宫", "塔", "岛", "湖", "海", "湾", "街", "巷", "馆", "园",
    "古城", "古镇", "公园", "博物馆", "美术馆", "植物园", "动物园",
]

SPOT_WEAK_KEYWORDS = [
    "山", "桥", "路", "村", "城", "港", "江", "河",
]

THEME_KEYWORDS = [
    "猫", "猫咪", "狗", "宠物", "美食", "登山", "徒步", "滑雪", "雪山", "雪崩", "日常", "人物",
    "人像", "运动", "露营", "航拍", "街拍", "风景", "自然", "森林", "湖泊", "大海", "沙滩",
    "城市", "建筑", "科技", "赛博", "深夜", "酒吧", "展览", "博物馆", "艺术", "学习", "办公",
]

EVENT_KEYWORDS = [
    "婚礼", "生日", "聚会", "毕业", "演出", "旅行", "团建", "年会", "派对", "探店", "浪漫",
]

# Backward-compatible alias for old code/comments.
SPOT_KEYWORDS = SPOT_STRONG_KEYWORDS + SPOT_SUFFIX_KEYWORDS + SPOT_WEAK_KEYWORDS

DATE_PATTERNS = [
    re.compile(r"^20\d{2}[-_.年]\d{1,2}[-_.月]\d{1,2}日?$"),
    re.compile(r"^\d{4}[-_.]\d{1,2}[-_.]\d{1,2}$"),
    re.compile(r"^day\s*\d+$", re.I),
    re.compile(r"^第?\d+天$"),
]

IGNORED_DIRS = {
    "__pycache__",
    "node_modules",
    "dist",
    "target",
    "output",
    "outputs",
    ".git",
    ".cache_video_create_v5",
    ".thumbnails",
}
IGNORED_FILES = {"thumbs.db", ".ds_store"}


# =========================
# Event / logging
# =========================

def emit_event(event_type: str, **payload: Any) -> None:
    """Emit one JSON event line for the Tauri GUI."""
    payload["type"] = event_type
    print(json.dumps(payload, ensure_ascii=False), flush=True)


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
            message = f"正在导出最终视频 {bar_name}: {index}/{total}"
            if percent != self.last_percent or message != self.last_message:
                self.last_percent = percent
                self.last_message = message
                emit_event("phase", phase="render", message=message, percent=percent)


# =========================
# Utility functions
# =========================

def natural_sort_key(value: str) -> List[Any]:
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", value)]


def safe_id(text: str) -> str:
    normalized = text.replace("\\", "/")
    return hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()[:12]


def file_hash_light(path: Path, extra: str = "") -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}|{ENGINE_VERSION}|{extra}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


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



def is_ignored_file(path: Path) -> bool:
    lower = path.name.lower()
    if lower in IGNORED_FILES:
        return True
    if lower.endswith("副本.jpg") or lower.endswith("副本.jpeg"):
        return True
    return False


def match_keywords(name: str, keywords: Iterable[str]) -> List[str]:
    return [kw for kw in keywords if kw and kw in name]


def detect_directory_type(
    name: str,
    depth: int,
    parent_type: str = "project_root",
    sibling_names: Optional[List[str]] = None,
) -> Tuple[str, float, str, Dict[str, Any], str]:
    """
    V5.4.2 hierarchy-aware directory recognition.

    Return:
      detected_type, confidence, reason, signals, raw_detected_type

    Important rules:
      - First-level folders under project root default to chapter.
      - scenic_spot requires travel context such as city/date parent, or a strong spot name.
      - Weak single-character spot keywords never decide scenic_spot by themselves.
      - Sibling normalization runs later in Scanner._normalize_directory_nodes().
    """
    normalized = name.strip()
    lower = normalized.lower()
    parent_type = parent_type or "project_root"

    matched_city = match_keywords(normalized, CITY_KEYWORDS)
    matched_spot_strong = match_keywords(normalized, SPOT_STRONG_KEYWORDS)
    matched_spot_suffix = match_keywords(normalized, SPOT_SUFFIX_KEYWORDS)
    matched_spot_weak = match_keywords(normalized, SPOT_WEAK_KEYWORDS)
    matched_theme = match_keywords(normalized, THEME_KEYWORDS)
    matched_event = match_keywords(normalized, EVENT_KEYWORDS)

    signals: Dict[str, Any] = {
        "parent_detected_type": parent_type,
        "depth": depth,
        "matched_city_keywords": matched_city,
        "matched_spot_strong_keywords": matched_spot_strong,
        "matched_spot_suffix_keywords": matched_spot_suffix,
        "matched_spot_weak_keywords": matched_spot_weak,
        "matched_theme_keywords": matched_theme,
        "matched_event_keywords": matched_event,
        "date_pattern_matched": False,
        "sibling_names": sibling_names or [],
    }

    if depth == 0:
        return "unknown", 0.35, "项目根目录，不作为叙事章节类型", signals, "project_root"

    for pattern in DATE_PATTERNS:
        if pattern.search(lower):
            signals["date_pattern_matched"] = True
            return "date", 0.96, "目录名匹配日期模式", signals, "date"

    if matched_city:
        return "city", 0.90, f"目录名匹配城市关键词: {matched_city[0]}", signals, "city"

    has_travel_parent = parent_type in {"city", "date"}
    has_story_parent = parent_type in {"chapter", "theme", "event"}
    strong_spot = bool(matched_spot_strong)
    suffix_spot = bool(matched_spot_suffix)
    weak_only_spot = bool(matched_spot_weak) and not strong_spot and not suffix_spot

    if has_travel_parent and (strong_spot or suffix_spot):
        kw = (matched_spot_strong or matched_spot_suffix)[0]
        return "scenic_spot", 0.88, f"父目录为 {parent_type}，且命中景点特征: {kw}", signals, "scenic_spot"

    if has_travel_parent and depth >= 2 and not (matched_theme or matched_event):
        return "scenic_spot", 0.64, "父目录为城市/日期，深层目录默认按景点候选处理", signals, "scenic_spot_candidate"

    if strong_spot and depth >= 2:
        kw = matched_spot_strong[0]
        return "scenic_spot", 0.78, f"深层目录命中强景点名: {kw}", signals, "scenic_spot"

    if depth == 1:
        if matched_theme:
            return "chapter", 0.74, f"一级目录默认作为内容章节；主题关键词: {matched_theme[0]}", signals, "theme"
        if matched_event:
            return "chapter", 0.74, f"一级目录默认作为内容章节；事件关键词: {matched_event[0]}", signals, "event"
        if weak_only_spot:
            return "chapter", 0.70, f"一级目录命中弱景点关键词 {matched_spot_weak[0]}，不足以判定为景点，按内容章节处理", signals, "scenic_spot_candidate"
        if suffix_spot and not has_travel_parent:
            return "chapter", 0.68, f"一级目录命中景点后缀 {matched_spot_suffix[0]}，但缺少城市/日期父级上下文，按章节处理", signals, "scenic_spot_candidate"
        return "chapter", 0.65, "一级目录默认识别为内容章节", signals, "chapter"

    if has_story_parent and (strong_spot or suffix_spot):
        kw = (matched_spot_strong or matched_spot_suffix)[0]
        return "scenic_spot", 0.72, f"章节下子目录命中景点特征: {kw}", signals, "scenic_spot"

    if matched_theme:
        return "chapter", 0.66, f"目录命中主题关键词: {matched_theme[0]}，按章节处理", signals, "theme"

    if weak_only_spot:
        return "chapter", 0.58, f"仅命中弱景点关键词 {matched_spot_weak[0]}，按章节处理", signals, "scenic_spot_candidate"

    if depth >= 2:
        return "chapter", 0.56, "深层目录未命中明确景点特征，按子章节处理", signals, "chapter"

    return "unknown", 0.35, "未知目录类型", signals, "unknown"



def get_exif_date(img: Image.Image) -> Optional[str]:
    try:
        exif = img.getexif()
        date_str = exif.get(36867) or exif.get(306)
        if date_str:
            return datetime.strptime(str(date_str), "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        return None
    return None


def orientation_from_size(size: Iterable[int]) -> str:
    w, h = list(size)[:2]
    if w > h:
        return "landscape"
    if h > w:
        return "portrait"
    return "square"


def section_to_dict(section: "StorySection") -> Dict[str, Any]:
    data = asdict(section)
    data["asset_refs"] = [asdict(ref) for ref in section.asset_refs]
    data["children"] = [section_to_dict(child) for child in section.children]
    return data


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


def select_ffmpeg_video_encoder(params: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Choose an FFmpeg encoder.

    Hardware encoding is opt-in for now. Some FFmpeg builds list an encoder even
    when the matching driver/device is unavailable, so callers still keep a
    libx264 fallback.
    """
    requested = str(params.get("hardware_encoder") or params.get("hardware_encoding") or "off").lower()
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
            return selected, ["-preset", "p4"]
        if selected == "h264_qsv":
            return selected, ["-preset", "veryfast"]
        if selected == "h264_amf":
            return selected, ["-quality", "speed"]
        return selected, []
    return "libx264", ["-preset", "veryfast"]


def close_clip(clip: Any) -> None:
    try:
        clip.close()
    except Exception:
        pass


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


def probe_audio_file(source: Path) -> Dict[str, Any]:
    """Probe audio metadata using FFmpeg stderr, without requiring ffprobe."""
    media = {
        "width": None,
        "height": None,
        "orientation": None,
        "shooting_date": None,
        "duration_seconds": None,
        "sample_rate": None,
        "channels": None,
        "audio_codec": None,
    }
    try:
        import imageio_ffmpeg

        completed = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        probe_text = completed.stderr or ""

        duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe_text)
        if duration_match:
            hours = int(duration_match.group(1))
            minutes = int(duration_match.group(2))
            seconds = float(duration_match.group(3))
            media["duration_seconds"] = round(hours * 3600 + minutes * 60 + seconds, 3)

        audio_line = None
        for line in probe_text.splitlines():
            if "Audio:" in line:
                audio_line = line
                break

        if audio_line:
            codec_match = re.search(r"Audio:\s*([^,]+)", audio_line)
            if codec_match:
                media["audio_codec"] = codec_match.group(1).strip().lower()

            sample_rate_match = re.search(r"(\d+)\s*Hz", audio_line)
            if sample_rate_match:
                media["sample_rate"] = int(sample_rate_match.group(1))

            if "stereo" in audio_line.lower():
                media["channels"] = 2
            elif "mono" in audio_line.lower():
                media["channels"] = 1
            else:
                channels_match = re.search(r"(\d+(?:\.\d+)?)\s*channels?", audio_line.lower())
                if channels_match:
                    media["channels"] = int(float(channels_match.group(1)))
    except Exception:
        pass

    return media


def prepare_cached_audio_for_mix(source: Path, cache_root: Path) -> Path:
    """Normalize audio once and reuse it across renders."""
    if not source.exists():
        raise FileNotFoundError(f"Audio source not found: {source}")

    bucket = cache_root / "normalized"
    bucket.mkdir(parents=True, exist_ok=True)
    cache_path = bucket / f"{file_hash_light(source, 'audio_mix_aac_48k_stereo_v1')}.m4a"
    if cache_path.exists() and cache_path.stat().st_size > 1024:
        emit_event("log", message=f"Audio cache hit: {cache_path.name}")
        return cache_path

    tmp_path = cache_path.with_suffix(".tmp.m4a")
    try:
        import imageio_ffmpeg

        completed = subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-i",
                str(source),
                "-vn",
                "-ac",
                "2",
                "-ar",
                "48000",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-movflags",
                "+faststart",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "unknown ffmpeg error")[-800:])
        if not tmp_path.exists() or tmp_path.stat().st_size <= 1024:
            raise RuntimeError("normalized audio cache output is empty")
        os.replace(str(tmp_path), str(cache_path))
        emit_event("log", message=f"Audio cache created: {cache_path.name}")
        return cache_path
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def audio_asset_duration_seconds(asset: Dict[str, Any]) -> float:
    media = asset.get("media", {}) if isinstance(asset, dict) else {}
    return float(media.get("duration_seconds") or media.get("duration") or 0.0)


def auto_music_score(asset: Dict[str, Any]) -> float:
    if asset.get("type") != "audio":
        return 0.0

    duration = audio_asset_duration_seconds(asset)
    if duration < 15:
        return 0.0

    file_info = asset.get("file", {}) if isinstance(asset, dict) else {}
    name = str(file_info.get("name") or "")
    rel_path = str(asset.get("relative_path") or "")
    haystack_lower = f"{name} {rel_path}".lower()
    haystack = f"{name} {rel_path}"
    ext = str(file_info.get("extension") or "").lower()

    score = 12.0 if duration >= 45 else 6.0
    if any(hint in haystack_lower for hint in AUDIO_MUSIC_HINTS[:6]) or any(hint in haystack for hint in AUDIO_MUSIC_HINTS[6:]):
        score += 40.0
    if any(hint in haystack_lower for hint in AUDIO_EFFECT_HINTS[:2]) or any(hint in haystack for hint in AUDIO_EFFECT_HINTS[2:]):
        score -= 25.0

    if duration >= 90:
        score += 18.0
    elif duration >= 45:
        score += 10.0
    elif duration >= 25:
        score += 4.0

    score += float(AUDIO_PREFERRED_EXT_SCORE.get(ext, 0))
    return score


def select_auto_music_asset(assets: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    ranked = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        status = asset.get("status")
        if status == "error" or (isinstance(status, dict) and status.get("state") == "error"):
            continue
        score = auto_music_score(asset)
        if score <= 0:
            continue
        ranked.append((score, audio_asset_duration_seconds(asset), str(asset.get("relative_path") or ""), asset))

    if not ranked:
        return None

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return ranked[0][3]


def select_auto_music_assets(assets: Iterable[Dict[str, Any]], target_duration: float = 0.0) -> List[Dict[str, Any]]:
    ranked: List[Tuple[float, float, str, Dict[str, Any]]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        status = asset.get("status")
        if status == "error" or (isinstance(status, dict) and status.get("state") == "error"):
            continue
        score = auto_music_score(asset)
        if score <= 0:
            continue
        ranked.append((score, audio_asset_duration_seconds(asset), str(asset.get("relative_path") or ""), asset))

    if not ranked:
        return []

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    ordered = [item[3] for item in ranked]
    if target_duration <= 0:
        return ordered[:1]
    if target_duration < 600:
        return ordered[:1]

    selected: List[Dict[str, Any]] = []
    total_duration = 0.0
    for asset in ordered:
        selected.append(asset)
        total_duration += audio_asset_duration_seconds(asset)
        if len(selected) >= 4 or total_duration >= target_duration * 0.72:
            break
    return selected or ordered[:1]


def build_music_bed_for_duration(
    prepared_tracks: List[Path],
    duration: float,
    cache_root: Path,
    fit_strategy: str = "auto",
    fade_in: float = 0.0,
    fade_out: float = 0.0,
) -> Optional[Path]:
    if not prepared_tracks:
        return None

    duration = max(0.1, float(duration or 0.0))
    fit_strategy = str(fit_strategy or "auto").lower()
    if fit_strategy not in {"auto", "loop", "trim", "intro_loop_outro", "once"}:
        fit_strategy = "auto"

    bucket = cache_root / "beds"
    bucket.mkdir(parents=True, exist_ok=True)
    key = json.dumps(
        {
            "tracks": [str(path.resolve()) for path in prepared_tracks if path.exists()],
            "duration": round(duration, 3),
            "fit_strategy": fit_strategy,
            "fade_in": round(float(fade_in or 0.0), 3),
            "fade_out": round(float(fade_out or 0.0), 3),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    cache_path = bucket / f"{safe_id(key)}.m4a"
    if cache_path.exists() and cache_path.stat().st_size > 1024:
        emit_event("log", message=f"Music bed cache hit: {cache_path.name}")
        return cache_path

    tmp_path = cache_path.with_suffix(".tmp.m4a")
    clips: List[Any] = []
    try:
        if not HAS_MOVIEPY:
            raise RuntimeError("MoviePy is required for music bed generation")

        source_clips = [AudioFileClip(str(path)) for path in prepared_tracks if path.exists()]
        clips.extend(source_clips)
        if not source_clips:
            return None

        if len(source_clips) > 1:
            assembled: List[Any] = []
            remaining = duration
            index = 0
            while remaining > 0 and source_clips:
                source = source_clips[index % len(source_clips)]
                source_duration = float(getattr(source, "duration", 0.0) or 0.0)
                take = min(max(source_duration, 0.1), remaining)
                assembled.append(source.subclip(0, take))
                remaining -= take
                index += 1
            music_clip = concatenate_audioclips(assembled).set_duration(duration)
        else:
            source = source_clips[0]
            source_duration = float(getattr(source, "duration", 0.0) or 0.0)
            effective_strategy = fit_strategy
            if effective_strategy == "auto":
                if source_duration <= 0:
                    effective_strategy = "once"
                elif duration <= source_duration * 1.2:
                    effective_strategy = "trim"
                elif duration <= source_duration * 3.0:
                    effective_strategy = "intro_loop_outro"
                else:
                    effective_strategy = "loop"

            if source_duration <= 0:
                music_clip = source.set_duration(duration)
            elif effective_strategy in {"once", "trim"}:
                music_clip = source.subclip(0, min(duration, source_duration)).set_duration(min(duration, source_duration))
            elif effective_strategy == "intro_loop_outro" and source_duration > 18 and duration > source_duration:
                intro = min(max(6.0, source_duration * 0.18), 18.0)
                outro = min(max(8.0, source_duration * 0.18), 20.0)
                middle_start = min(intro, max(0.0, source_duration - 10.0))
                middle_end = max(middle_start + 4.0, source_duration - outro)
                if middle_end <= middle_start + 1.0:
                    music_clip = moviepy_audio_loop(source, duration=duration) if moviepy_audio_loop is not None else concatenate_audioclips([source] * int(math.ceil(duration / source_duration))).subclip(0, duration)
                else:
                    intro_clip = source.subclip(0, min(intro, duration))
                    outro_len = min(outro, max(0.0, duration - float(getattr(intro_clip, "duration", 0.0) or 0.0)))
                    body_target = max(0.0, duration - float(getattr(intro_clip, "duration", 0.0) or 0.0) - outro_len)
                    middle_clip = source.subclip(middle_start, middle_end)
                    if body_target > 0 and moviepy_audio_loop is not None:
                        body_clip = moviepy_audio_loop(middle_clip, duration=body_target)
                    elif body_target > 0:
                        body_segments: List[Any] = []
                        remaining = body_target
                        middle_duration = float(getattr(middle_clip, "duration", 0.0) or 0.0)
                        while remaining > 0 and middle_duration > 0:
                            take = min(middle_duration, remaining)
                            body_segments.append(middle_clip.subclip(0, take))
                            remaining -= take
                        body_clip = concatenate_audioclips(body_segments).set_duration(body_target) if body_segments else None
                    else:
                        body_clip = None
                    outro_clip = source.subclip(max(0.0, source_duration - outro_len), source_duration) if outro_len > 0 else None
                    parts = [clip for clip in [intro_clip, body_clip, outro_clip] if clip is not None]
                    music_clip = concatenate_audioclips(parts).set_duration(duration)
            else:
                if moviepy_audio_loop is not None:
                    music_clip = moviepy_audio_loop(source, duration=duration)
                else:
                    loops = max(1, int(math.ceil(duration / source_duration)))
                    music_clip = concatenate_audioclips([source] * loops).subclip(0, duration)

        actual_duration = min(duration, float(getattr(music_clip, "duration", duration) or duration))
        if fade_in > 0:
            music_clip = music_clip.audio_fadein(min(float(fade_in), actual_duration / 2.0))
        if fade_out > 0:
            music_clip = music_clip.audio_fadeout(min(float(fade_out), actual_duration / 2.0))

        music_clip.write_audiofile(
            str(tmp_path),
            fps=48000,
            codec="aac",
            bitrate="160k",
            ffmpeg_params=["-movflags", "+faststart"],
            verbose=False,
            logger=None,
        )
        if not tmp_path.exists() or tmp_path.stat().st_size <= 1024:
            raise RuntimeError("music bed output is empty")
        os.replace(str(tmp_path), str(cache_path))
        emit_event("log", message=f"Music bed cache created: {cache_path.name}")
        return cache_path
    finally:
        for clip in clips:
            close_clip(clip)
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


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


# =========================
# Data models
# =========================

@dataclass
class TitleStyle:
    preset: str = "cinematic_bold"
    motion: str = "fade_slide_up"
    color_theme: str = "auto"
    position: str = "center"
    user_overridden: bool = False


@dataclass
class DirectoryNode:
    node_id: str
    name: str
    relative_path: str
    depth: int
    parent_id: Optional[str]
    detected_type: str
    confidence: float
    reason: str
    display_title: str
    raw_detected_type: Optional[str] = None
    signals: Dict[str, Any] = field(default_factory=dict)
    user_override_fields: List[str] = field(default_factory=list)
    asset_count: int = 0
    children: List[str] = field(default_factory=list)
    title_style: Optional[TitleStyle] = None
    auto_detected: bool = True
    user_overridden: bool = False


@dataclass
class Asset:
    asset_id: str
    type: str
    relative_path: str
    absolute_path: str
    thumbnail_path: Optional[str]
    file: Dict[str, Any]
    media: Dict[str, Any]
    classification: Dict[str, Any]
    status: str = "ready"
    cache: Optional[Dict[str, Any]] = None


@dataclass
class AssetRef:
    asset_id: str
    enabled: bool = True
    role: str = "normal"
    duration_policy: str = "auto"
    custom_duration: Optional[float] = None
    keep_audio: bool = True
    user_overridden: bool = False


@dataclass
class StorySection:
    section_id: str
    section_type: str
    title: str
    subtitle: Optional[str]
    enabled: bool
    source_node_id: Optional[str]
    asset_refs: List[AssetRef]
    children: List["StorySection"]
    auto_detected: bool = True
    user_overridden: bool = False
    rhythm: str = "standard"
    title_mode: str = "full_card"
    background: Optional[Dict[str, Any]] = None
    title_style: Optional[TitleStyle] = None


@dataclass
class RenderSegment:
    segment_id: str
    type: str
    source_path: Optional[str]
    duration: float
    text: Optional[str]
    subtitle: Optional[str]
    start_time: float
    end_time: float
    section_id: Optional[str] = None
    asset_id: Optional[str] = None
    transition: str = "none"
    transition_config: Optional[Dict[str, Any]] = None
    motion_config: Optional[Dict[str, Any]] = None
    rhythm_config: Optional[Dict[str, Any]] = None
    background: str = "blur"
    background_mode: Optional[str] = None
    background_source_path: Optional[str] = None
    background_source_position: Optional[str] = None
    background_source_path_2: Optional[str] = None
    background_source_position_2: Optional[str] = None
    overlay_text: Optional[str] = None
    overlay_subtitle: Optional[str] = None
    overlay_duration: Optional[float] = None
    overlay_title_style: Optional[Dict[str, Any]] = None
    title_style: Optional[Dict[str, Any]] = None
    keep_audio: bool = True
    cache_key: Optional[str] = None
    render_route: Optional[str] = None
    render_route_reason: Optional[str] = None
    render_route_tags: Optional[List[str]] = None


# =========================
# scan -> media_library.json
# =========================

class Scanner:
    def __init__(self, input_root: str, recursive: bool = True):
        self.root = Path(input_root).resolve()
        self.recursive = recursive
        self.nodes: Dict[str, DirectoryNode] = {}
        self.assets: List[Asset] = []
        self.cache_root = self.root / ".cache_video_create_v5"
        self.thumb_dir = self.cache_root / "thumbnails"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.skipped_count = 0

    def scan(self) -> Dict[str, Any]:
        if not self.root.exists() or not self.root.is_dir():
            raise FileNotFoundError(f"输入目录不存在或不是目录: {self.root}")

        emit_event("phase", phase="scan", message="开始扫描素材", percent=5)
        self._scan_dir(self.root, depth=0, parent_id=None, inherited={})
        self._normalize_directory_nodes()
        self._refresh_asset_classification_context()
        emit_event("phase", phase="scan", message="素材扫描完成", percent=100)

        return {
            "schema_version": SCHEMA_VERSION,
            "document_type": "media_library",
            "engine_version": ENGINE_VERSION,
            "project": {
                "source_root": str(self.root),
                "scan_time": datetime.now().isoformat(),
            },
            "directory_nodes": [asdict(x) for x in self.nodes.values()],
            "assets": [asdict(x) for x in self.assets],
            "summary": {
                "total_assets": len(self.assets),
                "image_count": sum(1 for a in self.assets if a.type == "image"),
                "video_count": sum(1 for a in self.assets if a.type == "video"),
                "audio_count": sum(1 for a in self.assets if a.type == "audio"),
                "skipped_count": self.skipped_count,
                "error_count": sum(1 for a in self.assets if a.status == "error"),
            },
        }

    def _scan_dir(
        self,
        current: Path,
        depth: int,
        parent_id: Optional[str],
        inherited: Dict[str, Optional[str]],
    ) -> str:
        rel = "" if current == self.root else current.relative_to(self.root).as_posix()
        parent_type = self.nodes[parent_id].detected_type if parent_id and parent_id in self.nodes else "project_root"
        sibling_names: List[str] = []
        try:
            sibling_names = [p.name for p in current.parent.iterdir() if p.is_dir()] if current.parent else []
        except Exception:
            sibling_names = []
        dtype, confidence, reason, signals, raw_type = detect_directory_type(current.name, depth, parent_type, sibling_names)
        node_id = "dir_" + safe_id(rel or current.name)
        node = DirectoryNode(
            node_id=node_id,
            name=current.name,
            relative_path=rel,
            depth=depth,
            parent_id=parent_id,
            detected_type=dtype,
            confidence=confidence,
            reason=reason,
            display_title=current.name,
            raw_detected_type=raw_type,
            signals=signals,
            title_style=self._recommend_title_style(signals),
        )
        self.nodes[node_id] = node

        if parent_id and parent_id in self.nodes:
            self.nodes[parent_id].children.append(node_id)

        context = dict(inherited)
        if dtype == "city":
            context["city"] = current.name
        elif dtype == "date":
            context["date"] = current.name
        elif dtype == "scenic_spot":
            context["scenic_spot"] = current.name

        try:
            entries = sorted(current.iterdir(), key=lambda p: natural_sort_key(p.name))
        except PermissionError:
            emit_event("log", message=f"无权限访问目录，已跳过: {current}")
            return node_id

        for path in entries:
            if path.is_dir():
                if path.name.startswith(".") or path.name in IGNORED_DIRS:
                    continue
                if self.recursive:
                    self._scan_dir(path, depth + 1, node_id, context)
            elif path.is_file():
                if is_ignored_file(path):
                    self.skipped_count += 1
                    continue
                if path.suffix.lower() in ALL_EXTS:
                    asset = self._scan_asset(path, node_id, context)
                    self.assets.append(asset)
                    node.asset_count += 1
                    if asset.type in {"image", "video"}:
                        emit_event(
                            "media",
                            item_kind=asset.type,
                            rel_path=asset.relative_path,
                            display_name=asset.file["name"],
                            path=asset.absolute_path,
                            thumbnail=asset.thumbnail_path,
                            width=asset.media.get("width"),
                            height=asset.media.get("height"),
                            duration=asset.media.get("duration_seconds"),
                            chapter=current.name,
                            mtime=path.stat().st_mtime,
                        )

        return node_id

    def _recommend_title_style(self, signals: Dict[str, Any]) -> TitleStyle:
        """V5.5 Weighted Tag System for Title Style Recommendation.
        
        Calculates a score for each category based on keyword matches and weights.
        """
        themes = signals.get("matched_theme_keywords") or []
        events = signals.get("matched_event_keywords") or []
        all_keywords = list(set(themes + events))

        if not all_keywords:
            return TitleStyle(preset="cinematic_bold", motion="cinematic_reveal")

        # Category definitions: (preset, motion, keyword_weight_map)
        categories = {
            "playful": {
                "preset": "playful_pop", "motion": "playful_bounce",
                "keywords": {"猫": 2.0, "猫咪": 2.2, "狗": 2.0, "宠物": 2.0, "日常": 1.0, "萌": 1.5, "可爱": 1.5}
            },
            "romantic": {
                "preset": "handwritten_note", "motion": "handwritten_draw",
                "keywords": {"婚礼": 2.5, "浪漫": 2.0, "甜蜜": 2.0, "派对": 1.2, "生日": 1.5}
            },
            "tech": {
                "preset": "neon_night", "motion": "neon_flicker",
                "keywords": {"科技": 2.0, "赛博": 2.5, "未来": 2.0, "办公": 1.0, "会议": 1.0, "学习": 1.0}
            },
            "nature": {
                "preset": "documentary_lower_third", "motion": "lower_third_slide",
                "keywords": {"登山": 1.5, "雪山": 2.0, "森林": 1.5, "风景": 1.0, "露营": 1.8, "自然": 1.2, "大海": 2.0, "湖泊": 1.5, "沙滩": 1.5}
            },
            "action": {
                "preset": "impact_flash", "motion": "impact_slam",
                "keywords": {"滑雪": 2.5, "运动": 1.5, "航拍": 1.5, "跑酷": 2.5, "极限": 2.0}
            },
            "travel": {
                "preset": "travel_postcard", "motion": "postcard_drift",
                "keywords": {"美食": 2.0, "街拍": 1.2, "古镇": 1.8, "旅行": 1.0, "探店": 2.0, "深夜": 1.5, "酒吧": 1.5}
            },
            "editorial": {
                "preset": "minimal_editorial", "motion": "editorial_fade",
                "keywords": {"人物": 1.5, "人像": 1.5, "展览": 1.8, "博物馆": 1.8, "艺术": 1.5, "建筑": 1.2, "城市": 1.0}
            }
        }

        scores: Dict[str, float] = {}
        for cat_name, config in categories.items():
            score = 0.0
            kw_map = config["keywords"]
            for kw in all_keywords:
                if kw in kw_map:
                    score += kw_map[kw]
            if score > 0:
                scores[cat_name] = score

        if not scores:
            return TitleStyle(preset="cinematic_bold", motion="cinematic_reveal")

        # Pick the category with the highest score
        best_cat = max(scores.items(), key=lambda x: x[1])[0]
        winner = categories[best_cat]
        
        return TitleStyle(preset=winner["preset"], motion=winner["motion"])

    def _normalize_directory_nodes(self) -> None:
        """Second-pass normalization for sibling consistency and weak keyword false positives."""
        for parent in list(self.nodes.values()):
            children = [self.nodes[cid] for cid in parent.children if cid in self.nodes]
            if not children:
                continue

            counts: Dict[str, int] = {}
            for child in children:
                counts[child.detected_type] = counts.get(child.detected_type, 0) + 1
            majority_type = max(counts.items(), key=lambda item: item[1])[0] if counts else None
            parent_type = parent.detected_type or "project_root"
            parent_is_travel = parent_type in {"city", "date"}

            for child in children:
                if child.user_overridden:
                    continue

                signals = child.signals or {}
                signals["sibling_majority_type"] = majority_type
                signals["sibling_type_counts"] = counts
                signals["parent_detected_type"] = parent_type

                weak_only = bool(signals.get("matched_spot_weak_keywords")) and not signals.get("matched_spot_strong_keywords") and not signals.get("matched_spot_suffix_keywords")
                no_strong_spot = not signals.get("matched_spot_strong_keywords")
                first_level_under_root = parent.parent_id is None and child.depth == 1

                if (
                    child.detected_type == "scenic_spot"
                    and not parent_is_travel
                    and (first_level_under_root or majority_type == "chapter" or weak_only or no_strong_spot)
                ):
                    original = child.detected_type
                    child.raw_detected_type = child.raw_detected_type or original
                    child.detected_type = "chapter"
                    child.confidence = max(float(child.confidence or 0), 0.72)
                    child.reason = (
                        "同级目录一致性修正：父目录不是城市/日期，"
                        "弱景点关键词或单个景点候选不足以单独判定 scenic_spot，按章节处理"
                    )
                    signals["normalized_from"] = original
                    signals["normalization_rule"] = "sibling_context_consistency"

                if first_level_under_root and child.detected_type not in {"city", "date", "chapter"}:
                    original = child.detected_type
                    child.raw_detected_type = child.raw_detected_type or original
                    child.detected_type = "chapter"
                    child.confidence = max(float(child.confidence or 0), 0.70)
                    child.reason = "一级同级素材目录统一作为内容章节，避免目录类型混杂"
                    signals["normalized_from"] = original
                    signals["normalization_rule"] = "first_level_content_chapter"

                child.signals = signals

    def _context_for_node(self, node_id: str) -> Dict[str, Optional[str]]:
        city = None
        date = None
        scenic_spot = None
        current = self.nodes.get(node_id)

        while current:
            if current.detected_type == "city" and city is None:
                city = current.name
            elif current.detected_type == "date" and date is None:
                date = current.name
            elif current.detected_type == "scenic_spot" and scenic_spot is None:
                scenic_spot = current.name

            if not current.parent_id:
                break
            current = self.nodes.get(current.parent_id)

        return {"city": city, "date": date, "scenic_spot": scenic_spot}

    def _refresh_asset_classification_context(self) -> None:
        """Refresh asset city/date/scenic_spot after directory normalization."""
        for asset in self.assets:
            node_id = asset.classification.get("directory_node_id")
            if not node_id:
                continue
            context = self._context_for_node(node_id)
            asset.classification["city"] = context.get("city")
            asset.classification["date"] = context.get("date")
            asset.classification["scenic_spot"] = context.get("scenic_spot")


    def _scan_asset(self, path: Path, node_id: str, context: Dict[str, Optional[str]]) -> Asset:
        ext = path.suffix.lower()
        if ext in IMAGE_EXTS:
            kind = "image"
        elif ext in VIDEO_EXTS:
            kind = "video"
        else:
            kind = "audio"
        stat = path.stat()
        rel = path.relative_to(self.root).as_posix()
        asset_id = "asset_" + safe_id(rel)
        cache_key = file_hash_light(path)
        media: Dict[str, Any] = {
            "width": None,
            "height": None,
            "orientation": None,
            "shooting_date": None,
            "duration_seconds": None,
            "sample_rate": None,
            "channels": None,
            "audio_codec": None,
        }
        thumb: Optional[str] = None
        status = "ready"

        try:
            if kind == "image":
                with Image.open(path) as img:
                    img = ImageOps.exif_transpose(img)
                    img = img.convert("RGB")
                    media["width"], media["height"] = img.size
                    media["orientation"] = orientation_from_size(img.size)
                    media["shooting_date"] = get_exif_date(img)
                    thumb = self._make_image_thumb(img, asset_id, cache_key)
            elif kind == "video" and HAS_MOVIEPY:
                clip = VideoFileClip(str(path))
                media["duration_seconds"] = float(clip.duration or 0)
                media["width"], media["height"] = map(int, clip.size)
                media["orientation"] = orientation_from_size(clip.size)
                thumb = self._make_video_thumb(clip, asset_id, cache_key)
                clip.close()
            elif kind == "audio":
                media.update(probe_audio_file(path))
        except Exception as exc:
            status = "error"
            emit_event("log", message=f"素材分析失败: {path.name}: {exc}")

        return Asset(
            asset_id=asset_id,
            type=kind,
            relative_path=rel,
            absolute_path=str(path),
            thumbnail_path=thumb,
            file={
                "name": path.name,
                "extension": ext,
                "size_bytes": stat.st_size,
                "modified_time": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "content_hash": cache_key,
            },
            media=media,
            classification={
                "directory_node_id": node_id,
                "city": context.get("city"),
                "date": context.get("date"),
                "scenic_spot": context.get("scenic_spot"),
                "detected_role": "normal",
                "confidence": 0.85,
            },
            status=status,
            cache={
                "cache_key": cache_key,
                "thumbnail_path": thumb,
                "generated_at": datetime.now().isoformat(),
            },
        )

    def _make_image_thumb(self, img: Image.Image, asset_id: str, cache_key: str) -> str:
        out = self.thumb_dir / f"{asset_id}_{cache_key[:8]}.jpg"
        if not out.exists():
            thumb = img.convert("RGB")
            thumb.thumbnail((480, 270))
            canvas = Image.new("RGB", (480, 270), (20, 24, 22))
            canvas.paste(thumb, ((480 - thumb.width) // 2, (270 - thumb.height) // 2))
            canvas.save(out, quality=85)
        return str(out)

    def _make_video_thumb(self, clip: Any, asset_id: str, cache_key: str) -> str:
        out = self.thumb_dir / f"{asset_id}_{cache_key[:8]}.jpg"
        if not out.exists():
            frame_t = min(1.0, max(0.0, (clip.duration or 0) / 2))
            clip.save_frame(str(out), t=frame_t)
        return str(out)


# =========================
# plan -> story_blueprint.json
# =========================

class Planner:
    def __init__(self, library: Dict[str, Any]):
        self.library = library
        self.nodes = {n["node_id"]: n for n in library.get("directory_nodes", [])}
        self.assets = library.get("assets", [])

    def plan(self, strategy: str = "city_date_spot") -> Dict[str, Any]:
        emit_event("phase", phase="plan", message="生成故事蓝图", percent=20)

        roots = [n for n in self.nodes.values() if n.get("parent_id") is None]
        sections: List[StorySection] = []

        for root in roots:
            for child_id in root.get("children", []):
                section = self._section_from_node(self.nodes[child_id])
                if section:
                    sections.append(section)

            loose = self._asset_refs_for_node(root["node_id"])
            if loose:
                sections.insert(
                    0,
                    StorySection(
                        section_id="section_root",
                        section_type="chapter",
                        title=root.get("display_title") or "素材",
                        subtitle=None,
                        enabled=True,
                        source_node_id=root["node_id"],
                        asset_refs=loose,
                        children=[],
                    ),
                )

        emit_event("phase", phase="plan", message="故事蓝图完成", percent=100)
        return {
            "schema_version": SCHEMA_VERSION,
            "document_type": "story_blueprint",
            "title": self.library.get("project", {}).get("project_title") or "My Travel Vlog",
            "subtitle": "",
            "strategy": strategy,
            "sections": [section_to_dict(s) for s in sections],
            "metadata": {"created_at": datetime.now().isoformat()},
        }

    def _section_from_node(self, node: Dict[str, Any]) -> Optional[StorySection]:
        asset_refs = self._asset_refs_for_node(node["node_id"])
        children = []

        for child_id in node.get("children", []):
            child = self._section_from_node(self.nodes[child_id])
            if child:
                children.append(child)

        if not asset_refs and not children:
            return None

        section_id = "section_" + safe_id(node.get("relative_path") or node.get("name", "section"))
        section_type = node.get("detected_type", "chapter")
        return StorySection(
            section_id=section_id,
            section_type=section_type,
            title=node.get("display_title") or node.get("name", "章节"),
            subtitle=None,
            enabled=True,
            source_node_id=node["node_id"],
            asset_refs=asset_refs,
            children=children,
            title_mode="overlay" if section_type == "scenic_spot" else "full_card",
            background={
                "mode": "auto_bridge",
                "custom_asset_id": None,
                "custom_path": None,
                "user_overridden": False,
            },
            title_style=node.get("title_style"),
        )

    def _asset_refs_for_node(self, node_id: str) -> List[AssetRef]:
        refs: List[AssetRef] = []
        for asset in self.assets:
            if asset.get("classification", {}).get("directory_node_id") == node_id and asset.get("type") in {"image", "video"}:
                refs.append(AssetRef(asset_id=asset["asset_id"], keep_audio=asset.get("type") == "video"))
        return refs


# =========================
# compile -> render_plan.json
# =========================

class Compiler:
    def __init__(self, blueprint: Dict[str, Any], library: Dict[str, Any]):
        self.blueprint = blueprint
        self.library = library
        self.assets = {a["asset_id"]: a for a in library.get("assets", [])}
        self.blueprint_metadata = blueprint.get("metadata", {}) or {}
        self.default_chapter_background_mode = self.blueprint_metadata.get("chapter_background_mode", "auto_bridge")
        self.scenic_spot_title_mode = self.blueprint_metadata.get("scenic_spot_title_mode", "overlay")
        self.edit_strategy = self.blueprint_metadata.get("edit_strategy", "smart_director")
        self.transition_profile = self.blueprint_metadata.get("transition_profile", "auto")
        self.rhythm_profile = self.blueprint_metadata.get("rhythm_profile", "auto")
        self.performance_mode = self.blueprint_metadata.get("performance_mode", "balanced")
        self.audio_settings = self._resolve_render_audio_settings()
        self.time = 0.0
        self.segments: List[RenderSegment] = []
        self.last_visual_source_path: Optional[str] = None
        self.single_auto_section_id: Optional[str] = None

    def _resolve_render_audio_settings(self) -> Optional[Dict[str, Any]]:
        audio = self.blueprint_metadata.get("audio")
        if not isinstance(audio, dict):
            return None

        resolved = dict(audio)
        music_mode = str(resolved.get("music_mode") or "off").lower()
        if music_mode not in {"off", "auto", "manual"}:
            music_mode = "off"
        resolved["music_mode"] = music_mode

        if music_mode == "auto":
            selected = select_auto_music_asset(self.library.get("assets", []))
            if selected:
                resolved["music_path"] = selected.get("absolute_path")
                resolved["music_source"] = "library"
                resolved["selected_asset_id"] = selected.get("asset_id")
                emit_event("log", message=f"自动音乐模式已选择候选 BGM: {selected.get('relative_path')}")
            else:
                resolved["music_path"] = None
                resolved["music_source"] = "none"
                emit_event("log", message="自动音乐模式未找到合适的 BGM 候选，后续渲染将按无音乐处理")
        elif music_mode == "manual":
            resolved["music_source"] = "manual" if resolved.get("music_path") else "none"
        else:
            resolved["music_path"] = None
            resolved["music_source"] = "none"

        return resolved

    def _compile_video_overlay_safe(self, seg: RenderSegment) -> bool:
        text = seg.overlay_text
        if not text:
            return True
        subtitle = seg.overlay_subtitle
        overlay_duration = float(seg.overlay_duration or 1.8)
        style = dict(seg.overlay_title_style or {})
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

    def _compile_video_motion_fit_candidate(self, seg: RenderSegment) -> bool:
        motion_type = str((seg.motion_config or {}).get("type") or "none")
        return motion_type in {"gentle_push", "slow_push"}

    def _compile_video_fitted_candidate(self, seg: RenderSegment) -> bool:
        if seg.type != "video":
            return False
        transition = seg.transition_config or {}
        transition_type = str(transition.get("type") or seg.transition or "none")
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
        motion_type = str((seg.motion_config or {}).get("type") or "none")
        if motion_type not in {"none", "still_hold"} and not self._compile_video_motion_fit_candidate(seg):
            return False
        return self._compile_video_overlay_safe(seg)

    def _compile_direct_chunk_candidate(self, seg: RenderSegment) -> bool:
        if seg.type != "video" or seg.overlay_text:
            return False
        transition = seg.transition_config or {}
        transition_type = str(transition.get("type") or seg.transition or "none")
        transition_duration = float(transition.get("duration") or 0.0)
        if transition_type not in {"none", "cut"} or transition_duration > 0.05:
            return False
        motion_type = str((seg.motion_config or {}).get("type") or "none")
        return motion_type in {"none", "still_hold"}

    def _compile_should_hint_photo_prerender(self, seg: RenderSegment, total_duration: float, segment_count: int) -> bool:
        if seg.type != "image":
            return False
        motion_type = str((seg.motion_config or {}).get("type") or "none")
        if motion_type not in {"none", "still_hold", "gentle_push", "slow_push", "ken_burns", "subtle_ken_burns", "punch_zoom", "micro_zoom"}:
            return False
        performance_mode = str(self.performance_mode or "").lower()
        render_mode = str(self.blueprint_metadata.get("render_mode", "auto") or "").lower()
        large_project = performance_mode == "stable" or render_mode == "long_stable" or total_duration >= 600.0 or segment_count >= 80
        medium_project = performance_mode in {"balanced", "quality"} and (total_duration >= 240.0 or segment_count >= 30)
        return (large_project or medium_project) and float(seg.duration or 0.0) > 0.1

    def _assign_render_scheduler_hints(self) -> Dict[str, Any]:
        total_duration = float(self.time or 0.0)
        segment_count = len(self.segments)
        route_counts: Dict[str, int] = {}
        for seg in self.segments:
            tags: List[str] = [str(seg.type)]
            route = "moviepy_required"
            reason = "timeline_composite_required"
            if seg.type in {"title", "chapter", "end"}:
                route = "moviepy_required"
                reason = "text_or_card_composite"
                tags.extend(["text", "timeline"])
            elif seg.type == "image":
                if self._compile_should_hint_photo_prerender(seg, total_duration, segment_count):
                    route = "photo_prerender"
                    reason = "image_segment_cache_candidate"
                    tags.extend(["cache", "prerender"])
                else:
                    route = "image_live_compose"
                    reason = "image_segment_needs_live_compose"
                    tags.extend(["image_compose", "timeline"])
            elif seg.type == "video":
                if self._compile_direct_chunk_candidate(seg):
                    route = "direct_chunk_candidate"
                    reason = "lightweight_video_chunk_safe"
                    tags.extend(["ffmpeg", "direct_chunk"])
                elif self._compile_video_fitted_candidate(seg):
                    if self._compile_video_motion_fit_candidate(seg):
                        route = "video_motion_fit"
                        reason = "simple_video_motion_cache_candidate"
                        tags.extend(["ffmpeg", "video_cache", "motion_cache"])
                    else:
                        route = "video_fit"
                        reason = "video_fit_cache_candidate"
                        tags.extend(["ffmpeg", "video_cache"])
                else:
                    route = "moviepy_required"
                    reason = "video_segment_needs_timeline_processing"
                    tags.extend(["timeline", "composite"])
            seg.render_route = route
            seg.render_route_reason = reason
            seg.render_route_tags = tags
            route_counts[route] = route_counts.get(route, 0) + 1
        return {
            "strategy_version": "segment_rules_v1",
            "route_counts": route_counts,
            "total_segments": segment_count,
            "total_duration": round(total_duration, 3),
        }

    def compile(self) -> Dict[str, Any]:
        emit_event("phase", phase="compile", message="编译渲染计划", percent=20)

        self._add(
            "title",
            duration=4.0,
            text=self.blueprint.get("title"),
            subtitle=self.blueprint.get("subtitle"),
            title_style=self.blueprint_metadata.get("title_style"),
        )

        enabled_top_sections = [
            section for section in self.blueprint.get("sections", [])
            if section.get("enabled", True)
        ]
        if len(enabled_top_sections) == 1:
            only_section = enabled_top_sections[0]
            if (
                only_section.get("auto_detected", True)
                and not only_section.get("user_overridden", False)
                and self.blueprint_metadata.get("single_section_chapter_card", "auto") == "auto"
            ):
                # Single automatic folder chapters, such as a one-off folder named "haha",
                # are usually just containers. Suppress the extra chapter card to avoid
                # confusing it with the opening title card.
                self.single_auto_section_id = only_section.get("section_id")

        for section in self.blueprint.get("sections", []):
            self._section(section)

        end_text = (
            self.blueprint.get("end_text")
            or self.blueprint_metadata.get("end_text")
            or "To be continued!"
        )
        self._add(
            "end",
            duration=3.0,
            text=end_text,
            title_style=self.blueprint_metadata.get("end_title_style"),
        )

        render_scheduler = self._assign_render_scheduler_hints()

        emit_event("phase", phase="compile", message="渲染计划完成", percent=100)
        return {
            "schema_version": SCHEMA_VERSION,
            "document_type": "render_plan",
            "output_path": "",
            "total_duration": round(self.time, 3),
            "segments": [asdict(s) for s in self.segments],
            "render_settings": {
                "aspect_ratio": "16:9",
                "quality": "high",
                "python_quality": "ultra",
                "fps": 30,
                "engine": "moviepy_crossfade",
                "edit_strategy": self.edit_strategy,
                "transition_profile": self.transition_profile,
                "rhythm_profile": self.rhythm_profile,
                "performance_mode": self.performance_mode,
                "render_mode": self.blueprint_metadata.get("render_mode", "auto"),
                "chunk_seconds": self.blueprint_metadata.get("chunk_seconds"),
                "audio": self.audio_settings,
            },
            "render_scheduler": render_scheduler,
            "cache_policy": {
                "enabled": True,
                "invalidation_keys": [
                    "file_path",
                    "file_size",
                    "mtime",
                    "render_params",
                    "engine_version",
                ],
            },
            "metadata": {"generated_at": datetime.now().isoformat()},
        }

    def _section(self, section: Dict[str, Any]) -> None:
        if not section.get("enabled", True):
            return

        stype = section.get("section_type", "chapter")
        background = section.get("background") or {}
        has_custom_background = bool(background.get("user_overridden") and background.get("custom_path"))
        use_overlay_title = stype == "scenic_spot" and not has_custom_background and self.scenic_spot_title_mode == "overlay"
        suppress_section_title = section.get("section_id") == self.single_auto_section_id

        pending_overlay_text = None
        pending_overlay_subtitle = None
        pending_overlay_title_style = None

        if suppress_section_title:
            # Only one automatic top-level section exists. Do not insert a chapter card
            # and do not overlay the folder name. The opening title already introduces the video.
            pass
        elif stype in {"city", "date", "chapter"} or (stype == "scenic_spot" and not use_overlay_title):
            bg_info = self._chapter_background_info(section)
            self._add(
                "chapter",
                duration=2.5,
                text=section.get("title"),
                subtitle=section.get("subtitle"),
                section_id=section.get("section_id"),
                title_style=section.get("title_style"),
                section_type=stype,
                **bg_info,
            )
        elif use_overlay_title:
            pending_overlay_text = section.get("title")
            pending_overlay_subtitle = section.get("subtitle")
            pending_overlay_title_style = section.get("title_style")

        overlay_consumed = False
        for ref in section.get("asset_refs", []):
            if not ref.get("enabled", True):
                continue

            asset = self.assets.get(ref.get("asset_id"))
            if not asset or asset.get("status") == "error":
                continue

            duration = self._asset_duration(asset, ref)
            overlay_text = None
            overlay_subtitle = None
            if pending_overlay_text and not overlay_consumed:
                overlay_text = pending_overlay_text
                overlay_subtitle = pending_overlay_subtitle
                overlay_consumed = True

            self._add(
                asset.get("type"),
                duration=duration,
                source_path=asset.get("absolute_path"),
                asset_id=asset.get("asset_id"),
                section_id=section.get("section_id"),
                keep_audio=bool(ref.get("keep_audio", True)),
                overlay_text=overlay_text,
                overlay_subtitle=overlay_subtitle,
                overlay_duration=1.8 if overlay_text else None,
                overlay_title_style=pending_overlay_title_style if overlay_text else None,
                section_type=stype,
            )

        for child in section.get("children", []):
            self._section(child)

    def _chapter_background_info(self, section: Dict[str, Any]) -> Dict[str, Optional[str]]:
        background = section.get("background") or {}
        mode = background.get("mode") or self.default_chapter_background_mode
        custom_path = background.get("custom_path")

        if background.get("user_overridden") and custom_path:
            return {
                "background_mode": "custom_blur",
                "background_source_path": custom_path,
                "background_source_position": "middle",
                "background_source_path_2": None,
                "background_source_position_2": None,
            }

        first_visual = self._first_visual_source_in_section(section)

        if mode == "plain":
            return {
                "background_mode": "plain",
                "background_source_path": None,
                "background_source_position": None,
                "background_source_path_2": None,
                "background_source_position_2": None,
            }

        if mode == "auto_first_asset":
            return {
                "background_mode": "auto_first_asset",
                "background_source_path": first_visual,
                "background_source_position": "first",
                "background_source_path_2": None,
                "background_source_position_2": None,
            }

        # Default: bridge background blends previous visual tail with current section first visual.
        return {
            "background_mode": "bridge_blur",
            "background_source_path": self.last_visual_source_path or first_visual,
            "background_source_position": "last" if self.last_visual_source_path else "first",
            "background_source_path_2": first_visual,
            "background_source_position_2": "first",
        }

    def _first_visual_source_in_section(self, section: Dict[str, Any]) -> Optional[str]:
        for ref in section.get("asset_refs", []):
            if not ref.get("enabled", True):
                continue
            asset = self.assets.get(ref.get("asset_id"))
            if asset and asset.get("status") != "error" and asset.get("type") in {"image", "video"}:
                return asset.get("absolute_path")
        for child in section.get("children", []):
            found = self._first_visual_source_in_section(child)
            if found:
                return found
        return None

    def _asset_duration(self, asset: Dict[str, Any], ref: Dict[str, Any]) -> float:
        if ref.get("duration_policy") == "custom" and ref.get("custom_duration"):
            return float(ref["custom_duration"])

        if asset.get("type") == "video":
            return float(asset.get("media", {}).get("duration_seconds") or asset.get("media", {}).get("duration") or 5.0)

        orientation = asset.get("media", {}).get("orientation")
        if orientation == "landscape":
            return 3.6
        if orientation == "portrait":
            return 3.0
        return 3.2

    def _add(
        self,
        seg_type: str,
        duration: float,
        text: Optional[str] = None,
        subtitle: Optional[str] = None,
        source_path: Optional[str] = None,
        section_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        keep_audio: bool = True,
        background_mode: Optional[str] = None,
        background_source_path: Optional[str] = None,
        background_source_position: Optional[str] = None,
        background_source_path_2: Optional[str] = None,
        background_source_position_2: Optional[str] = None,
        overlay_text: Optional[str] = None,
        overlay_subtitle: Optional[str] = None,
        overlay_duration: Optional[float] = None,
        overlay_title_style: Optional[Dict[str, Any]] = None,
        title_style: Optional[Dict[str, Any]] = None,
        section_type: Optional[str] = None,
    ) -> None:
        if isinstance(title_style, TitleStyle):
            title_style = asdict(title_style)
        if isinstance(overlay_title_style, TitleStyle):
            overlay_title_style = asdict(overlay_title_style)

        transition_config, motion_config, rhythm_config = self._creative_segment_config(
            seg_type=seg_type,
            duration=float(duration),
            section_type=section_type,
            has_overlay=bool(overlay_text),
        )
        creative_cache_key = json.dumps(
            {
                "strategy": self.edit_strategy,
                "transition": transition_config,
                "motion": motion_config,
                "rhythm": rhythm_config,
            },
            ensure_ascii=False,
            sort_keys=True,
        )

        seg = RenderSegment(
            segment_id=f"seg_{len(self.segments):05d}",
            type=seg_type,
            source_path=source_path,
            duration=float(duration),
            text=text,
            subtitle=subtitle,
            start_time=round(self.time, 3),
            end_time=round(self.time + duration, 3),
            section_id=section_id,
            asset_id=asset_id,
            transition=transition_config.get("type", "none"),
            transition_config=transition_config,
            motion_config=motion_config,
            rhythm_config=rhythm_config,
            keep_audio=keep_audio,
            background_mode=background_mode,
            background_source_path=background_source_path,
            background_source_position=background_source_position,
            background_source_path_2=background_source_path_2,
            background_source_position_2=background_source_position_2,
            overlay_text=overlay_text,
            overlay_subtitle=overlay_subtitle,
            overlay_duration=overlay_duration,
            overlay_title_style=overlay_title_style,
            title_style=title_style,
            cache_key=safe_id(
                f"{seg_type}|{source_path}|{duration}|{text}|{background_mode}|{creative_cache_key}|{ENGINE_VERSION}"
            ),
        )
        self.segments.append(seg)
        if seg_type in {"image", "video"} and source_path:
            self.last_visual_source_path = source_path
        self.time += duration

    def _creative_segment_config(
        self,
        seg_type: str,
        duration: float,
        section_type: Optional[str],
        has_overlay: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        strategy = str(self.edit_strategy or "smart_director")
        if strategy not in {
            "smart_director",
            "fast_assembly",
            "travel_soft",
            "beat_cut",
            "documentary",
            "long_stable",
        }:
            strategy = "smart_director"

        section_type = section_type or "global"
        is_boundary = seg_type in {"title", "chapter", "end"}
        is_video = seg_type == "video"
        is_image = seg_type == "image"

        def transition(kind: str, seconds: float, reason: str) -> Dict[str, Any]:
            if kind in {"none", "cut"}:
                seconds = 0.0
            else:
                seconds = min(max(seconds, 0.0), max(duration * 0.28, 0.0), 0.8)
            return {
                "type": kind,
                "duration": round(seconds, 3),
                "profile": self.transition_profile,
                "strategy": strategy,
                "scope": "boundary" if is_boundary else "asset",
                "reason": reason,
            }

        def motion(kind: str, intensity: str, reason: str) -> Dict[str, Any]:
            return {
                "type": kind,
                "intensity": intensity,
                "strategy": strategy,
                "apply_to": seg_type,
                "overlay_safe": has_overlay,
                "reason": reason,
            }

        def rhythm(role: str, pace: str, importance: float) -> Dict[str, Any]:
            return {
                "role": role,
                "pace": pace,
                "importance": round(importance, 2),
                "profile": self.rhythm_profile,
                "strategy": strategy,
                "section_type": section_type,
            }

        if is_boundary:
            if strategy == "beat_cut":
                return (
                    transition("flash_cut", 0.16, "章节边界用短促闪切，强化卡点感"),
                    motion("title_style", "medium", "章节文字动效主导画面运动"),
                    rhythm("chapter_boundary", "fast_punchy", 0.9),
                )
            if strategy == "travel_soft":
                return (
                    transition("fade_through_white", 0.46, "旅拍章节用亮调柔化过渡"),
                    motion("title_style", "soft", "保留章节文字动效，避免背景抢戏"),
                    rhythm("chapter_boundary", "medium_soft", 0.86),
                )
            if strategy == "documentary":
                return (
                    transition("fade_through_dark", 0.34, "纪录叙事用稳重暗场分段"),
                    motion("title_style", "low", "边界段保持信息清晰"),
                    rhythm("chapter_boundary", "steady_story", 0.9),
                )
            if strategy == "long_stable":
                return (
                    transition("fade_through_dark", 0.24, "长片减少高频转场刺激"),
                    motion("title_style", "low", "长片章节牌以低运动量为主"),
                    rhythm("chapter_boundary", "long_consistent", 0.82),
                )
            if strategy == "fast_assembly":
                return (
                    transition("cut", 0.0, "快速成片优先效率和稳定"),
                    motion("title_style", "low", "减少额外运动计算"),
                    rhythm("chapter_boundary", "fast_review", 0.74),
                )
            return (
                transition("fade_through_dark", 0.32, "智能导演默认用清晰章节分隔"),
                motion("title_style", "medium", "章节文字动效承担主要表现"),
                rhythm("chapter_boundary", "auto", 0.86),
            )

        if strategy == "fast_assembly":
            return (
                transition("cut", 0.0, "素材快速直切，适合批量审片和极速出片"),
                motion("none" if is_video else "still_hold", "none", "快速成片减少逐段运动处理"),
                rhythm("footage" if is_video else "visual", "fast_review", 0.62),
            )
        if strategy == "travel_soft":
            return (
                transition("soft_crossfade", 0.45, "旅拍素材用柔和交叉淡化保持流动感"),
                motion("none" if is_video else "gentle_push", "soft", "轻推镜头增加旅行感但不抢主体"),
                rhythm("footage" if is_video else "visual", "medium_soft", 0.72),
            )
        if strategy == "beat_cut":
            return (
                transition("quick_zoom" if is_image else "cut", 0.18, "节奏型剪辑用短促冲击转场"),
                motion("micro_zoom" if is_video else "punch_zoom", "high", "增加卡点冲击和画面能量"),
                rhythm("beat_asset", "fast_punchy", 0.82),
            )
        if strategy == "documentary":
            return (
                transition("soft_crossfade" if is_image else "cut", 0.28, "纪录叙事保持克制连贯"),
                motion("none" if is_video else "slow_push", "low", "慢推帮助观众阅读画面信息"),
                rhythm("story_asset", "steady_story", 0.78),
            )
        if strategy == "long_stable":
            return (
                transition("cut" if is_video else "soft_crossfade", 0.2, "长片降低转场复杂度，保证稳定输出"),
                motion("none" if is_video else "subtle_ken_burns", "low", "长片保留轻微变化避免疲劳"),
                rhythm("longform_asset", "long_consistent", 0.68),
            )

        if section_type in {"city", "date"}:
            transition_type = "bridge_blur"
            reason = "智能导演识别城市/日期段落，用桥接模糊增强段落感"
        elif has_overlay:
            transition_type = "soft_crossfade"
            reason = "首个景点素材含标题叠加，使用柔和过渡保护文字可读性"
        else:
            transition_type = "soft_crossfade" if is_image else "cut"
            reason = "智能导演根据素材类型选择默认连贯剪辑"

        return (
            transition(transition_type, 0.34, reason),
            motion("none" if is_video else "ken_burns", "medium", "智能导演为静态图补充轻微镜头运动"),
            rhythm("footage" if is_video else "visual", "auto", 0.72),
        )


# =========================
# render -> final mp4
# =========================

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
            for i in range(8):
                yy = 40 + i * 52
                draw.rectangle((32, yy, 48, yy + 20), outline=(248, 240, 220, 80), width=1)

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

    def _cache_path(self, kind: str, source: Path, suffix: str, extra: str = "") -> Path:
        bucket = self.render_cache_dir / kind
        bucket.mkdir(parents=True, exist_ok=True)
        key_extra = f"{extra}|target={self.target_size[0]}x{self.target_size[1]}"
        key = file_hash_light(source, key_extra) if source.exists() else safe_id(f"{source}|{key_extra}")
        return bucket / f"{key}{suffix}"

    def _should_prerender_image_segment(self, duration: float, motion_config: Optional[Dict[str, Any]] = None) -> bool:
        performance_mode = str(self.params.get("performance_mode") or self.plan.get("render_settings", {}).get("performance_mode") or "").lower()
        render_mode = str(self.params.get("render_mode") or self.plan.get("render_settings", {}).get("render_mode") or "").lower()
        total_duration = float(self.plan.get("total_duration") or 0.0)
        segment_count = len(self.plan.get("segments", []) or [])
        motion_type = str((motion_config or {}).get("type") or "none")
        if motion_type not in {"none", "still_hold", "gentle_push", "slow_push", "ken_burns", "subtle_ken_burns", "punch_zoom", "micro_zoom"}:
            return False
        large_project = (
            performance_mode == "stable"
            or render_mode == "long_stable"
            or total_duration >= 600.0
            or segment_count >= 80
        )
        medium_project = (
            performance_mode in {"balanced", "quality"}
            and (total_duration >= 240.0 or segment_count >= 30)
        )
        return (
            large_project
            or medium_project
        ) and float(duration or 0.0) > 0.1

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
            f"photo_seg_v3|duration={round(float(duration or 0.0), 3)}|fps={fps}|motion={motion_key}|overlay={overlay_key}",
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
                prepared.append(prepare_cached_audio_for_mix(source, self.audio_cache_dir))
            except Exception as exc:
                emit_event("log", message=f"Audio cache fallback to source: {exc}")
                prepared.append(source)
        self._prepared_music_paths = prepared
        return [path for path in prepared if path.exists()]

    def _prepare_music_bed(self, duration: float) -> Optional[Path]:
        duration = max(0.1, float(duration or 0.0))
        cache_key = f"{duration:.3f}|{json.dumps({k: self.audio_settings.get(k) for k in ('music_fit_strategy', 'music_playlist_mode', 'music_playlist_paths', 'music_path', 'fade_in_seconds', 'fade_out_seconds')}, ensure_ascii=False, sort_keys=True)}"
        if cache_key in self._prepared_music_beds:
            prepared = self._prepared_music_beds[cache_key]
            if prepared is None or prepared.exists():
                return prepared

        prepared_tracks = self._prepare_music_paths()
        if not prepared_tracks:
            self._prepared_music_beds[cache_key] = None
            return None

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
            prepared = prepare_cached_audio_for_mix(source, self.audio_cache_dir)
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
        if playlist_mode not in {"single", "auto_playlist", "manual_playlist"}:
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
            "music_source": audio.get("music_source") or ("manual" if music_mode == "manual" else "library" if music_mode == "auto" and audio.get("music_path") else "none"),
            "bgm_volume": num("bgm_volume", 0.28, 0.0, 1.0),
            "source_audio_volume": num("source_audio_volume", 1.0, 0.0, 1.0),
            "keep_source_audio": bool(audio.get("keep_source_audio", True)),
            "auto_ducking": bool(audio.get("auto_ducking", True)),
            "fade_in_seconds": num("fade_in_seconds", 1.5, 0.0, 10.0),
            "fade_out_seconds": num("fade_out_seconds", 3.0, 0.0, 20.0),
            "duck_bgm_volume": num("duck_bgm_volume", 0.16, 0.0, 1.0),
        }

    def _segment_keep_audio(self, seg: Dict[str, Any]) -> bool:
        return bool(self.audio_settings.get("keep_source_audio", True)) and bool(seg.get("keep_audio", True))

    def render(self) -> None:
        if not HAS_MOVIEPY:
            raise RuntimeError(
                "MoviePy not installed. Please run: "
                "python -m pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg"
            )

        ensure_parent(self.output_path)
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

            emit_event("phase", phase="render", message="正在合成最终时间线", percent=91)
            final = self._compose_timeline(clips, rendered_segments)

            if self.params.get("watermark"):
                emit_event("phase", phase="render", message="正在添加水印", percent=92)
                final = self._add_watermark(final, str(self.params.get("watermark")))

            final = self._apply_audio_mix(final)

            emit_event("phase", phase="render", message="正在导出最终视频", percent=92)

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
            self._emit_video_segment_cache_summary()

            emit_event("artifact", artifact="video", path=str(self.output_path), message="最终视频已生成")
            emit_event("phase", phase="complete", message="视频导出成功", percent=100)

        finally:
            if final is not None:
                close_clip(final)
            for clip in clips:
                close_clip(clip)
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _segment(self, seg: Dict[str, Any]):
        stype = seg.get("type")
        duration = float(seg.get("duration") or 3.0)

        if stype in {"title", "chapter", "end"}:
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
            emit_event("log", message=f"BGM 文件不存在，已跳过背景音乐: {path}")
            return video.set_audio(source_audio) if source_audio is not getattr(video, "audio", None) else video

        bgm = None
        try:
            emit_event("phase", phase="audio", message="正在混合背景音乐与视频原声", percent=92)
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
            emit_event("log", message=f"BGM 混音失败，已保留视频原声继续渲染: {exc}")
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
            emit_event("log", message=f"文案背景源不存在，已回退为纯色背景: {source}")
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
            emit_event("log", message=f"生成文案背景帧失败，已回退为纯色背景: {source.name}: {exc}")

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
        text = seg.get("overlay_text")
        if not text:
            return None
        subtitle = seg.get("overlay_subtitle")
        overlay_duration = min(float(seg.get("overlay_duration") or 1.8), float(duration or 1.8))
        style = dict(seg.get("overlay_title_style") or {})
        motion = str(style.get("motion") or "fade_slide_up")
        position = str(style.get("position") or "lower_left")
        if motion not in {"fade_slide_up", "editorial_fade", "static_hold", "lower_third_slide", "cinematic_reveal", "postcard_drift"}:
            return None
        if position not in {"lower_left", "lower_center", "center"}:
            return None
        if len(str(text)) > 42 or len(str(subtitle or "")) > 64:
            return None
        if overlay_duration > min(3.2, float(duration or 0.0)):
            return None
        return {
            "text": str(text),
            "subtitle": str(subtitle) if subtitle else None,
            "duration": round(overlay_duration, 3),
            "style": style,
        }

    def _get_proxy_source(self, source: Path, is_video: bool) -> Path:
        if not self.params.get("preview"):
            return source
            
        proxy_dir = self.render_cache_dir.parent / "proxies"
        proxy_dir.mkdir(parents=True, exist_ok=True)
        
        tw, th = self.target_size
        proxy_key = f"{source.stat().st_mtime}_{source.stat().st_size}_{tw}x{th}"
        proxy_hash = hashlib.md5(proxy_key.encode()).hexdigest()
        
        ext = ".mp4" if is_video else ".jpg"
        proxy_path = proxy_dir / f"proxy_{proxy_hash}{ext}"
        
        if proxy_path.exists():
            return proxy_path
            
        emit_event("log", message=f"正在生成极速预览代理: {source.name}")
        try:
            if is_video:
                cmd = [
                    "ffmpeg", "-y", "-i", str(source),
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
            return proxy_path
        except Exception as e:
            emit_event("log", message=f"预览代理生成失败，回退原图: {e}")
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
            emit_event("log", message=f"检测到视频显示比例元数据，正在归一化以避免画面拉伸: {source.name}")
            completed = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if completed.returncode == 0 and normalized.exists() and normalized.stat().st_size > 1024:
                return normalized
            emit_event("log", message=f"视频显示比例归一化失败，回退原始文件: {source.name}: {completed.stderr[-600:]}")
        except Exception as exc:
            emit_event("log", message=f"视频显示比例归一化异常，回退原始文件: {source.name}: {exc}")

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
                emit_event("log", message=f"硬件编码 {selected_encoder} 不可用，回退 libx264: {completed.stderr[-600:]}")
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
                emit_event("log", message=f"FFmpeg 视频段预适配失败，回退 MoviePy: {source.name}: {completed.stderr[-600:]}")
        except Exception as exc:
            if track_stats:
                self.video_segment_cache_stats["fallback"] += 1
                emit_event("log", message=f"FFmpeg 视频段预适配异常，回退 MoviePy: {source.name}: {exc}")

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
            emit_event("log", message=f"FFmpeg 视频 motion 预适配失败，回退 MoviePy: {source.name}: base fit unavailable")
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
            emit_event("log", message=f"FFmpeg 视频 motion 预适配失败，回退 MoviePy: {source.name}: {completed.stderr[-600:]}")
        except Exception as exc:
            self.video_segment_cache_stats["fallback"] += 1
            self.video_segment_cache_stats["motion_fallback"] += 1
            emit_event("log", message=f"FFmpeg 视频 motion 预适配异常，回退 MoviePy: {source.name}: {exc}")

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
        img = Image.open(source_image).convert("RGB")
        scale = max(tw / img.width, th / img.height)
        bg = img.resize((int(img.width * scale), int(img.height * scale)), Image.Resampling.LANCZOS)

        left = max(0, (bg.width - tw) // 2)
        top = max(0, (bg.height - th) // 2)
        bg = bg.crop((left, top, left + tw, top + th)).filter(ImageFilter.GaussianBlur(30))
        bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.28)
        bg.save(out, quality=90)
        return out

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
        emit_event("artifact", artifact="media_library", path=args.output, message="素材库已保存")


def command_plan(args: argparse.Namespace) -> None:
    result = Planner(read_json(args.library)).plan(strategy=args.strategy)
    write_json(args.output, result)
    if args.output:
        emit_event("artifact", artifact="story_blueprint", path=args.output, message="故事蓝图已保存")


def command_compile(args: argparse.Namespace) -> None:
    result = Compiler(read_json(args.blueprint), read_json(args.library)).compile()
    write_json(args.output, result)
    if args.output:
        emit_event("artifact", artifact="render_plan", path=args.output, message="渲染计划已保存")



# =========================
# V5.6 long-video stability renderer
# =========================

def _v56_stable_json_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def _v56_segment_cache_key(seg: Dict[str, Any], params: Dict[str, Any]) -> str:
    stable = {
        "engine_version": ENGINE_VERSION,
        "segment_id": seg.get("segment_id"),
        "type": seg.get("type"),
        "source_path": seg.get("source_path"),
        "asset_id": seg.get("asset_id"),
        "duration": seg.get("duration"),
        "text": seg.get("text"),
        "subtitle": seg.get("subtitle"),
        "background_mode": seg.get("background_mode"),
        "background_source_path": seg.get("background_source_path"),
        "background_source_path_2": seg.get("background_source_path_2"),
        "overlay_text": seg.get("overlay_text"),
        "title_style": seg.get("title_style"),
        "overlay_title_style": seg.get("overlay_title_style"),
        "params_title_style": params.get("title_style") if seg.get("type") == "title" else None,
        "params_end_title_style": params.get("end_title_style") if seg.get("type") == "end" else None,
        "transition_config": seg.get("transition_config"),
        "motion_config": seg.get("motion_config"),
        "rhythm_config": seg.get("rhythm_config"),
        "keep_audio": seg.get("keep_audio"),
        "audio": params.get("audio"),
        "aspect_ratio": params.get("aspect_ratio"),
        "fps": params.get("fps"),
        "quality": params.get("quality"),
        "python_quality": params.get("python_quality"),
    }
    return _v56_stable_json_hash(stable)


def _v56_build_chunk_groups(
    segments: List[Dict[str, Any]],
    chunk_seconds: float,
    params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    params = params or {}
    chunk_seconds = max(float(chunk_seconds or 120), 30.0)

    groups: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_duration = 0.0
    current_keys: List[str] = []

    def chunk_route_payload(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        routes = [str(seg.get("runtime_render_route") or seg.get("render_route") or "moviepy_required") for seg in items]
        route_counts: Dict[str, int] = {}
        for route in routes:
            route_counts[route] = route_counts.get(route, 0) + 1
        if items and all(route == "direct_chunk_candidate" for route in routes):
            return {
                "runtime_chunk_route": "ffmpeg_direct_chunk",
                "runtime_chunk_route_reason": "all_segments_direct_chunk_safe",
                "runtime_chunk_route_tags": ["ffmpeg", "chunk", "direct"],
                "runtime_chunk_route_counts": route_counts,
            }
        if any(route in {"moviepy_required", "image_live_compose", "photo_prerender"} for route in routes):
            reason = "contains_timeline_or_image_segments"
        elif any(route in {"video_fit", "video_motion_fit"} for route in routes):
            reason = "contains_video_timeline_segments"
        else:
            reason = "default_timeline_chunk"
        return {
            "runtime_chunk_route": "moviepy_chunk",
            "runtime_chunk_route_reason": reason,
            "runtime_chunk_route_tags": ["moviepy", "chunk", "timeline"],
            "runtime_chunk_route_counts": route_counts,
        }

    for seg in segments:
        duration = float(seg.get("duration") or 0.0)
        route = str(seg.get("runtime_render_route") or seg.get("render_route") or "moviepy_required")
        is_direct = (route == "direct_chunk_candidate")
        
        if current:
            # Check if current group is direct
            current_routes = [str(s.get("runtime_render_route") or s.get("render_route") or "moviepy_required") for s in current]
            current_is_direct = all(r == "direct_chunk_candidate" for r in current_routes)
            
            time_exceeded = (current_duration + duration > chunk_seconds)
            route_changed = (current_is_direct != is_direct)
            
            if time_exceeded or route_changed:
                groups.append({
                    "index": len(groups),
                    "segments": current,
                    "duration": round(current_duration, 3),
                    "cache_key": _v56_stable_json_hash(current_keys),
                    **chunk_route_payload(current),
                })
                current = []
                current_duration = 0.0
                current_keys = []

        current.append(seg)
        current_duration += duration
        current_keys.append(_v56_segment_cache_key(seg, params))

    if current:
        groups.append({
            "index": len(groups),
            "segments": current,
            "duration": round(current_duration, 3),
            "cache_key": _v56_stable_json_hash(current_keys),
            **chunk_route_payload(current),
        })

    return groups


def _v56_validate_video(path: Path, min_size: int = 1024) -> Tuple[bool, str, Optional[float]]:
    if not path.exists():
        return False, "文件不存在", None
    if path.stat().st_size < min_size:
        return False, f"文件过小: {path.stat().st_size} bytes", None

    if not HAS_MOVIEPY:
        return True, "MoviePy 不可用，仅完成大小校验", None

    clip = None
    try:
        clip = VideoFileClip(str(path))
        duration = float(clip.duration or 0.0)
        if duration <= 0:
            return False, "视频时长无效", duration
        return True, "校验通过", duration
    except Exception as exc:
        return False, f"视频读取校验失败: {exc}", None
    finally:
        if clip is not None:
            close_clip(clip)


def _v56_atomic_replace(tmp_path: Path, final_path: Path) -> None:
    ensure_parent(final_path)
    if final_path.exists():
        final_path.unlink()
    os.replace(str(tmp_path), str(final_path))


def _v56_write_build_report(report_path: Path, report: Dict[str, Any]) -> None:
    try:
        ensure_parent(report_path)
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        emit_event("log", message=f"写入 build_report.json 失败: {exc}")


def _v56_concat_chunks_ffmpeg(chunks: List[Path], tmp_output: Path, project_dir: Path) -> bool:
    if not chunks:
        raise RuntimeError("没有可拼接的 chunk 文件")

    concat_list = project_dir / "concat_list.txt"
    resolved_output = tmp_output.resolve()
    with concat_list.open("w", encoding="utf-8", newline="\n") as f:
        for chunk in chunks:
            escaped = chunk.resolve().as_posix().replace("'", r"'\''")
            f.write(f"file '{escaped}'\n")

    try:
        import subprocess
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list.resolve()),
            "-c", "copy",
            str(resolved_output),
        ]
        emit_event("phase", phase="concat", message="使用 FFmpeg 快速拼接分段视频", percent=96)
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0 and resolved_output.exists() and resolved_output.stat().st_size > 1024:
            return True
        emit_event("log", message=f"FFmpeg concat copy 失败，准备回退 MoviePy: {completed.stderr[-800:]}")
        return False
    except Exception as exc:
        emit_event("log", message=f"FFmpeg concat 不可用，准备回退 MoviePy: {exc}")
        return False


def _v56_concat_chunks_ffmpeg_reencode(
    chunks: List[Path],
    tmp_output: Path,
    project_dir: Path,
    fps: int,
    params: Dict[str, Any],
) -> bool:
    if not chunks:
        raise RuntimeError("missing chunks for ffmpeg reencode concat")

    concat_list = project_dir / "concat_reencode_list.txt"
    resolved_output = tmp_output.resolve()
    with concat_list.open("w", encoding="utf-8", newline="\n") as f:
        for chunk in chunks:
            escaped = chunk.resolve().as_posix().replace("'", r"'\''")
            f.write(f"file '{escaped}'\n")

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        selected_encoder, encoder_args = select_ffmpeg_video_encoder(params)
        cmd = [
            ffmpeg,
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list.resolve()),
            "-r",
            str(int(fps or 30)),
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-c:v",
            selected_encoder,
        ]
        cmd += encoder_args
        if selected_encoder == "libx264":
            cmd += ["-crf", quality_to_crf(params.get("quality") or params.get("python_quality") or "high")]
        else:
            cmd += ["-b:v", "8M"]
        cmd += [
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "48000",
            "-ac",
            "2",
            str(resolved_output),
        ]
        emit_event("phase", phase="concat", message="ä½¿ç”¨ FFmpeg é‡ç¼–ç åˆå¹¶åˆ†æ®µè§†é¢‘", percent=96)
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0 and resolved_output.exists() and resolved_output.stat().st_size > 1024:
            return True
        emit_event("log", message=f"FFmpeg concat reencode failed, fallback to MoviePy: {completed.stderr[-800:]}")
        return False
    except Exception as exc:
        emit_event("log", message=f"FFmpeg concat reencode raised, fallback to MoviePy: {exc}")
        return False
    finally:
        try:
            if concat_list.exists():
                concat_list.unlink()
        except Exception:
            pass


def _v56_concat_chunks_moviepy(chunks: List[Path], tmp_output: Path, fps: int, params: Dict[str, Any]) -> None:
    emit_event("phase", phase="concat", message="使用 MoviePy 回退拼接分段视频", percent=96)
    clips = []
    final = None
    try:
        for chunk in chunks:
            clips.append(VideoFileClip(str(chunk)))
        final = concatenate_videoclips(clips, method="compose")
        crf = quality_to_crf(params.get("quality") or params.get("python_quality") or "high")
        final.write_videofile(
            str(tmp_output),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            ffmpeg_params=["-crf", crf, "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=JsonMoviePyLogger(base_percent=96, span_percent=3),
        )
    finally:
        if final is not None:
            close_clip(final)
        for clip in clips:
            close_clip(clip)


def _v56_apply_final_bgm_mix(
    input_video: Path,
    output_video: Path,
    audio_settings: Dict[str, Any],
    duration: Optional[float],
    prepared_bgm_path: Optional[Path] = None,
    prepared_bgm_is_bed: bool = False,
) -> bool:
    music_mode = str(audio_settings.get("music_mode") or "off")
    music_path = audio_settings.get("music_path")
    if music_mode == "off" or not music_path:
        return False

    bgm_path = prepared_bgm_path or Path(str(music_path))
    if not bgm_path.exists():
        emit_event("log", message=f"BGM 文件不存在，稳定模式已跳过背景音乐: {bgm_path}")
        return False

    video_duration = max(0.1, float(duration or 0.0))
    bgm_volume = float(audio_settings.get("bgm_volume", 0.28))
    if bgm_volume <= 0:
        return False

    keep_source = bool(audio_settings.get("keep_source_audio", True))
    source_has_audio = keep_source and video_has_audio_stream(input_video)
    if bool(audio_settings.get("auto_ducking", True)) and source_has_audio:
        bgm_volume = min(bgm_volume, float(audio_settings.get("duck_bgm_volume", 0.16)))

    fade_in = min(float(audio_settings.get("fade_in_seconds", 0.0)), video_duration / 2.0)
    fade_out = min(float(audio_settings.get("fade_out_seconds", 0.0)), video_duration / 2.0)

    bgm_filters = [f"volume={bgm_volume:.4f}"]
    if fade_in > 0:
        bgm_filters.append(f"afade=t=in:st=0:d={fade_in:.3f}")
    if fade_out > 0:
        fade_start = max(0.0, video_duration - fade_out)
        bgm_filters.append(f"afade=t=out:st={fade_start:.3f}:d={fade_out:.3f}")
    bgm_filters.extend([
        "aresample=48000",
        f"atrim=0:{video_duration:.3f}",
        "asetpts=N/SR/TB",
    ])

    if source_has_audio:
        filter_complex = (
            f"[1:a]{','.join(bgm_filters)}[bgm];"
            "[0:a:0]aresample=48000[src];"
            "[src][bgm]amix=inputs=2:duration=first:dropout_transition=0[mix]"
        )
    else:
        filter_complex = f"[1:a]{','.join(bgm_filters)}[mix]"

    try:
        import imageio_ffmpeg

        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-i",
            str(input_video),
        ]
        if not prepared_bgm_is_bed:
            cmd.extend(["-stream_loop", "-1"])
        cmd.extend([
            "-i",
            str(bgm_path),
            "-filter_complex",
            filter_complex,
            "-map",
            "0:v:0",
            "-map",
            "[mix]",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(output_video),
        ])
        emit_event("phase", phase="audio", message="稳定模式：使用 FFmpeg 流式混合背景音乐", percent=97)
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0 and output_video.exists() and output_video.stat().st_size > 1024:
            return True
        emit_event("log", message=f"稳定模式 BGM 混音失败，保留无 BGM 结果: {completed.stderr[-800:]}")
    except Exception as exc:
        emit_event("log", message=f"稳定模式 BGM 混音异常，保留无 BGM 结果: {exc}")

    try:
        if output_video.exists():
            output_video.unlink()
    except Exception:
        pass
    return False


def _v56_try_write_ffmpeg_direct_chunk(
    renderer: Any,
    chunk: Dict[str, Any],
    tmp_chunk: Path,
    params: Dict[str, Any],
) -> bool:
    segments = chunk.get("segments") or []
    if not segments:
        return False
    if str(chunk.get("runtime_chunk_route") or "") not in {"", "ffmpeg_direct_chunk"}:
        return False

    sources: List[Path] = []
    for seg in segments:
        source_path = seg.get("source_path")
        if not source_path:
            return False
        source = Path(source_path)
        seg_route = str(seg.get("runtime_render_route") or seg.get("render_route") or "")
        if seg_route and seg_route != "direct_chunk_candidate":
            return False
        if not source.exists() or not renderer._can_use_ffmpeg_direct_chunk_segment(seg):
            return False
        sources.append(source)

    if hasattr(renderer, "_segment_keep_audio"):
        keep_audio_flags = [bool(renderer._segment_keep_audio(seg)) for seg in segments]
    else:
        keep_audio_flags = [bool(seg.get("keep_audio", True)) for seg in segments]
    needs_audio_track = any(keep_audio_flags)
    fitted_segments: List[Path] = []
    for seg, source, keep_audio in zip(segments, sources, keep_audio_flags):
        fitted = renderer._ffmpeg_fit_video_segment(
            source,
            float(seg.get("duration") or 0.1),
            keep_audio=keep_audio,
            force_audio_track=needs_audio_track,
        )
        if not fitted or not fitted.exists():
            return False
        fitted_segments.append(fitted)

    concat_list = tmp_chunk.with_suffix(".concat.txt")
    try:
        with concat_list.open("w", encoding="utf-8", newline="\n") as f:
            for fitted in fitted_segments:
                escaped = fitted.resolve().as_posix().replace("'", r"'\''")
                f.write(f"file '{escaped}'\n")

        import imageio_ffmpeg

        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(tmp_chunk),
        ]
        emit_event("phase", phase="render", message=f"使用 FFmpeg 直出轻量分段 {chunk['index'] + 1}", percent=min(94, 10 + chunk["index"]))
        completed = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode != 0:
            emit_event("log", message=f"FFmpeg chunk 直出失败，回退 MoviePy: {completed.stderr[-800:]}")
            return False
        ok, reason, _duration = _v56_validate_video(tmp_chunk)
        if not ok:
            emit_event("log", message=f"FFmpeg chunk 直出校验失败，回退 MoviePy: {reason}")
            return False
        return True
    except Exception as exc:
        emit_event("log", message=f"FFmpeg chunk 直出异常，回退 MoviePy: {exc}")
        return False
    finally:
        try:
            if concat_list.exists():
                concat_list.unlink()
        except Exception:
            pass


def _v56_write_chunk_video(
    renderer: Any,
    chunk: Dict[str, Any],
    chunk_path: Path,
    fps: int,
    params: Dict[str, Any],
) -> None:
    clips = []
    rendered_segments = []
    combined = None
    tmp_chunk = chunk_path.with_suffix(".rendering.tmp.mp4")

    try:
        chunk_route = str(chunk.get("runtime_chunk_route") or "")
        if chunk_route == "ffmpeg_direct_chunk" and _v56_try_write_ffmpeg_direct_chunk(renderer, chunk, tmp_chunk, params):
            _v56_atomic_replace(tmp_chunk, chunk_path)
            return

        for seg in chunk["segments"]:
            emit_event(
                "phase",
                phase="render",
                message=f"渲染分段 {chunk['index'] + 1}: {seg.get('type')} {seg.get('text') or ''}",
                percent=min(94, 10 + chunk["index"]),
            )
            clip = renderer._segment(seg)
            if clip is not None:
                clips.append(clip)
                rendered_segments.append(seg)

        if not clips:
            raise RuntimeError(f"chunk_{chunk['index']:03d} 没有可渲染 clip")

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
            raise RuntimeError(f"chunk 校验失败: {reason}")

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
    if performance_mode == "stable":
        return True
    if performance_mode == "quality":
        return False

    mode = str(params.get("render_mode") or params.get("long_video_mode") or "auto").lower()
    if mode in {"stable", "long", "long_stable", "true", "1", "yes"}:
        return True
    if mode in {"standard", "classic", "moviepy"}:
        return False

    total_duration = float(plan.get("total_duration") or 0.0)
    segments = plan.get("segments", [])
    return total_duration >= float(params.get("stable_threshold_seconds", 600)) or len(segments) >= int(params.get("stable_threshold_segments", 80))


class V56StableRenderer:
    def __init__(self, plan: Dict[str, Any], output: str, params: Dict[str, Any], plan_path: Optional[str] = None):
        self.plan = plan
        self.output = Path(output)
        self.params = params or {}
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

    def render(self) -> None:
        if not HAS_MOVIEPY:
            raise RuntimeError("MoviePy 不可用，无法渲染视频")

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
        groups = _v56_build_chunk_groups(segments, self.chunk_seconds, self.params)
        chunk_route_counts: Dict[str, int] = {}
        for group in groups:
            route = str(group.get("runtime_chunk_route") or "moviepy_chunk")
            chunk_route_counts[route] = chunk_route_counts.get(route, 0) + 1
        manifest = self._load_manifest()
        manifest.setdefault("engine_version", ENGINE_VERSION)
        manifest.setdefault("chunks", {})
        if chunk_route_counts:
            compact = ", ".join(f"{key}={value}" for key, value in sorted(chunk_route_counts.items()))
            emit_event("log", message=f"Chunk scheduler summary: {compact}")

        emit_event(
            "phase",
            phase="render",
            message=f"启用 V5.6 长视频稳定模式：{len(groups)} 个分段，每段约 {int(self.chunk_seconds)} 秒",
            percent=8,
        )

        rendered_chunks: List[Path] = []
        chunk_reports: List[Dict[str, Any]] = []

        for group in groups:
            idx = int(group["index"])
            chunk_name = f"chunk_{idx:03d}.mp4"
            chunk_path = self.chunk_dir / chunk_name
            key = str(group["cache_key"])
            existing = manifest.get("chunks", {}).get(chunk_name, {})

            ok, reason, duration = _v56_validate_video(chunk_path)
            if existing.get("cache_key") == key and existing.get("status") == "done" and ok:
                emit_event("phase", phase="render", message=f"复用已完成分段 {chunk_name}", percent=min(94, 10 + int((idx / max(len(groups), 1)) * 80)))
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
                _v56_write_chunk_video(renderer, group, chunk_path, self.fps, self.params)
                ok, reason, duration = _v56_validate_video(chunk_path)
                if not ok:
                    raise RuntimeError(reason)

                manifest["chunks"][chunk_name] = {
                    "status": "done",
                    "cache_key": key,
                    "path": str(chunk_path),
                    "duration": duration,
                    "updated_at": datetime.now().isoformat(),
                }
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
                manifest["chunks"][chunk_name] = {
                    "status": "failed",
                    "cache_key": key,
                    "path": str(chunk_path),
                    "error": str(exc),
                    "updated_at": datetime.now().isoformat(),
                }
                self._save_manifest(manifest)
                _v56_write_build_report(self.report_path, {
                    "engine_version": ENGINE_VERSION,
                    "status": "failed",
                    "failed_chunk": chunk_name,
                    "error": str(exc),
                    "output_path": str(final_output),
                    "chunk_dir": str(self.chunk_dir),
                    "chunks": chunk_reports,
                    "photo_segment_cache": renderer._photo_segment_cache_summary(),
                    "video_segment_cache": renderer._video_segment_cache_summary(),
                    "render_scheduler": renderer.render_scheduler_summary,
                    "chunk_scheduler": {
                        "strategy_version": "chunk_rules_v1",
                        "route_counts": chunk_route_counts,
                        "total_chunks": len(groups),
                    },
                    "created_at": datetime.now().isoformat(),
                })
                raise

        if not rendered_chunks:
            raise RuntimeError("没有成功渲染任何分段")

        concat_ok = _v56_concat_chunks_ffmpeg(rendered_chunks, tmp_output, self.project_dir)
        if not concat_ok:
            concat_ok = _v56_concat_chunks_ffmpeg_reencode(rendered_chunks, tmp_output, self.project_dir, self.fps, self.params)
        if not concat_ok:
            _v56_concat_chunks_moviepy(rendered_chunks, tmp_output, self.fps, self.params)

        ok, reason, final_duration = _v56_validate_video(tmp_output)
        if not ok:
            raise RuntimeError(f"最终视频校验失败，不覆盖旧文件: {reason}")

        mixed_output = tmp_output.with_suffix(".audio.tmp.mp4")
        if _v56_apply_final_bgm_mix(
            tmp_output,
            mixed_output,
            renderer.audio_settings,
            final_duration,
            prepared_bgm_path=renderer._prepare_music_bed(final_duration) or renderer._prepare_music_path(),
            prepared_bgm_is_bed=True,
        ):
            try:
                tmp_output.unlink()
            except Exception:
                pass
            os.replace(str(mixed_output), str(tmp_output))
            ok, reason, final_duration = _v56_validate_video(tmp_output)
            if not ok:
                raise RuntimeError(f"最终视频音频混合后校验失败，不覆盖旧文件: {reason}")

        _v56_atomic_replace(tmp_output, final_output)

        elapsed = (datetime.now() - started_at).total_seconds()
        renderer._emit_photo_segment_cache_summary()
        renderer._emit_video_segment_cache_summary()
        report = {
            "engine_version": ENGINE_VERSION,
            "status": "done",
            "render_mode": "v5.6_long_video_stable",
            "output_path": str(final_output),
            "output_size_bytes": final_output.stat().st_size if final_output.exists() else None,
            "duration_seconds": final_duration,
            "elapsed_seconds": elapsed,
            "chunk_seconds": self.chunk_seconds,
            "chunk_count": len(rendered_chunks),
            "chunk_dir": str(self.chunk_dir),
            "chunks": chunk_reports,
            "photo_segment_cache": renderer._photo_segment_cache_summary(),
            "video_segment_cache": renderer._video_segment_cache_summary(),
            "render_scheduler": renderer.render_scheduler_summary,
            "chunk_scheduler": {
                "strategy_version": "chunk_rules_v1",
                "route_counts": chunk_route_counts,
                "total_chunks": len(groups),
            },
            "created_at": datetime.now().isoformat(),
        }
        _v56_write_build_report(self.report_path, report)
        emit_event("phase", phase="done", message="长视频稳定渲染完成", percent=100)


def render_with_v56_stability(plan_path: str, output: str, params: Dict[str, Any]) -> None:
    plan = read_json(plan_path)
    if _v56_should_use_stable_renderer(plan, params):
        V56StableRenderer(plan, output, params, plan_path=plan_path).render()
    else:
        final_output = Path(output)
        tmp_output = final_output.with_suffix(".rendering.tmp.mp4")
        if tmp_output.exists():
            try:
                tmp_output.unlink()
            except Exception:
                pass

        Renderer(plan, str(tmp_output), params).render()
        ok, reason, _duration = _v56_validate_video(tmp_output)
        if not ok:
            raise RuntimeError(f"标准渲染结果校验失败，不覆盖旧文件: {reason}")
        _v56_atomic_replace(tmp_output, final_output)


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
    text_img = renderer.render_layer(args.title or "章节标题", args.subtitle or None, style, is_full_card=True)
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
