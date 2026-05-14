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
        ColorClip,
        CompositeVideoClip,
        ImageClip,
        VideoFileClip,
        concatenate_videoclips,
    )

    HAS_MOVIEPY = True
except Exception:
    HAS_MOVIEPY = False


# =========================
# Constants
# =========================

SCHEMA_VERSION = "5.5"
ENGINE_VERSION = "video-create-engine-v5.6.0"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")
ALL_EXTS = IMAGE_EXTS + VIDEO_EXTS

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
    return 1920, 1080


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
    bbox = draw.textbbox((0, 0), text or "", font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


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


def close_clip(clip: Any) -> None:
    try:
        clip.close()
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
            return TitleStyle(preset="cinematic_bold", motion="fade_slide_up")

        # Category definitions: (preset, motion, keyword_weight_map)
        categories = {
            "playful": {
                "preset": "playful_pop", "motion": "pop_bounce",
                "keywords": {"猫": 2.0, "猫咪": 2.2, "狗": 2.0, "宠物": 2.0, "日常": 1.0, "萌": 1.5, "可爱": 1.5}
            },
            "romantic": {
                "preset": "romantic_soft", "motion": "slow_fade_zoom",
                "keywords": {"婚礼": 2.5, "浪漫": 2.0, "甜蜜": 2.0, "派对": 1.2, "生日": 1.5}
            },
            "tech": {
                "preset": "tech_future", "motion": "quick_zoom_punch",
                "keywords": {"科技": 2.0, "赛博": 2.5, "未来": 2.0, "办公": 1.0, "会议": 1.0, "学习": 1.0}
            },
            "nature": {
                "preset": "nature_documentary", "motion": "slow_fade_zoom",
                "keywords": {"登山": 1.5, "雪山": 2.0, "森林": 1.5, "风景": 1.0, "露营": 1.8, "自然": 1.2, "大海": 2.0, "湖泊": 1.5, "沙滩": 1.5}
            },
            "action": {
                "preset": "impact_flash", "motion": "quick_zoom_punch",
                "keywords": {"滑雪": 2.5, "运动": 1.5, "航拍": 1.5, "跑酷": 2.5, "极限": 2.0}
            },
            "travel": {
                "preset": "travel_postcard", "motion": "soft_zoom_in",
                "keywords": {"美食": 2.0, "街拍": 1.2, "古镇": 1.8, "旅行": 1.0, "探店": 2.0, "深夜": 1.5, "酒吧": 1.5}
            },
            "editorial": {
                "preset": "minimal_editorial", "motion": "fade_only",
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
            return TitleStyle(preset="cinematic_bold", motion="fade_slide_up")

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
        kind = "image" if ext in IMAGE_EXTS else "video"
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
            elif HAS_MOVIEPY:
                clip = VideoFileClip(str(path))
                media["duration_seconds"] = float(clip.duration or 0)
                media["width"], media["height"] = map(int, clip.size)
                media["orientation"] = orientation_from_size(clip.size)
                thumb = self._make_video_thumb(clip, asset_id, cache_key)
                clip.close()
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
            if asset.get("classification", {}).get("directory_node_id") == node_id:
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
        self.time = 0.0
        self.segments: List[RenderSegment] = []
        self.last_visual_source_path: Optional[str] = None
        self.single_auto_section_id: Optional[str] = None

    def compile(self) -> Dict[str, Any]:
        emit_event("phase", phase="compile", message="编译渲染计划", percent=20)

        self._add(
            "title",
            duration=4.0,
            text=self.blueprint.get("title"),
            subtitle=self.blueprint.get("subtitle"),
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
        self._add("end", duration=3.0, text=end_text)

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
            },
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
    ) -> None:
        if isinstance(title_style, TitleStyle):
            title_style = asdict(title_style)
        if isinstance(overlay_title_style, TitleStyle):
            overlay_title_style = asdict(overlay_title_style)

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
            cache_key=safe_id(f"{seg_type}|{source_path}|{duration}|{text}|{background_mode}|{ENGINE_VERSION}"),
        )
        self.segments.append(seg)
        if seg_type in {"image", "video"} and source_path:
            self.last_visual_source_path = source_path
        self.time += duration


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
            draw.text(((w - tw) // 2, by + 20), title, font=title_font, fill=(52, 211, 153, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw.text(((w - sw) // 2, by + 90), subtitle, font=sub_font, fill=(30, 41, 59, 200))

        elif preset == "travel_postcard":
            # Bordered card effect
            if is_full_card:
                draw.rectangle((40, 40, w - 40, h - 40), outline=(255, 255, 255, 180), width=3)
            title_font = load_font(72)
            sub_font = load_font(36)
            tw, th = text_size(draw, title, title_font)
            draw.text(((w - tw) // 2, (h - th) // 2 - 20), title, font=title_font, fill=(255, 255, 240, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw.text(((w - sw) // 2, (h - sh) // 2 + 60), subtitle, font=sub_font, fill=(251, 191, 36, 230))

        elif preset == "nature_documentary":
            # Minimal but elegant
            title_font = load_font(84)
            sub_font = load_font(32)
            tw, th = text_size(draw, title, title_font)
            draw.text(((w - tw) // 2, (h - th) // 2 - 30), title, font=title_font, fill=(255, 255, 255, 240))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw.text(((w - sw) // 2, (h - sh) // 2 + 70), subtitle, font=sub_font, fill=(167, 243, 208, 200))

        elif preset == "minimal_editorial":
            title_font = load_font(52)
            sub_font = load_font(28)
            tw, th = text_size(draw, title, title_font)
            draw.text(((w - tw) // 2, (h - th) // 2 - 10), title, font=title_font, fill=(255, 255, 255, 220))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw.text(((w - sw) // 2, (h - sh) // 2 + 50), subtitle, font=sub_font, fill=(255, 255, 255, 160))

        elif preset == "romantic_soft":
            # Pink/Warm theme with elegant font
            title_font = load_font(72)
            sub_font = load_font(34)
            tw, th = text_size(draw, title, title_font)
            # Subtle glow effect would be nice, but simple fill for now
            draw.text(((w - tw) // 2, (h - th) // 2 - 30), title, font=title_font, fill=(255, 192, 203, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw.text(((w - sw) // 2, (h - sh) // 2 + 65), subtitle, font=sub_font, fill=(255, 240, 245, 200))

        elif preset == "tech_future":
            # Cyan/Blue theme with blocky layout
            draw.rectangle((w // 2 - 150, h // 2 - 80, w // 2 + 150, h // 2 + 60), outline=(34, 211, 238, 180), width=2)
            title_font = load_font(68)
            sub_font = load_font(30)
            tw, th = text_size(draw, title, title_font)
            draw.text(((w - tw) // 2, (h - th) // 2 - 25), title, font=title_font, fill=(34, 211, 238, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw.text(((w - sw) // 2, (h - sh) // 2 + 55), subtitle, font=sub_font, fill=(255, 255, 255, 200))

        else: # cinematic_bold (default)
            title_font = load_font(78)
            sub_font = load_font(34)
            tw, th = text_size(draw, title, title_font)
            draw.text(((w - tw) // 2, (h - th) // 2 - 40), title, font=title_font, fill=(255, 255, 255, 255))
            if subtitle:
                sw, sh = text_size(draw, subtitle, sub_font)
                draw.text(((w - sw) // 2, (h - sh) // 2 + 55), subtitle, font=sub_font, fill=(52, 211, 153, 255))

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
        duration = max(float(duration or 0.1), 0.1)

        animated = clip

        if motion in {"soft_zoom_in", "slow_fade_zoom"}:
            animated = self._safe_resize(animated, lambda t: self._soft_zoom_scale(t, duration))
        elif motion == "pop_bounce":
            animated = self._safe_resize(animated, lambda t: self._pop_scale(t))
        elif motion == "quick_zoom_punch":
            animated = self._safe_resize(animated, lambda t: self._punch_scale(t))

        # Dynamic opacity must be mask-based, not set_opacity(lambda...).
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
        self.target_size = get_resolution(
            params.get("aspect_ratio") or settings.get("aspect_ratio") or "16:9"
        )
        self.temp_dir = Path(tempfile.mkdtemp(prefix="vcs_v5_render_"))
        self.first_visual_source = self._find_visual_source("first")
        self.last_visual_source = self._find_visual_source("last")
        self.renderer = TitleStyleRenderer(self.target_size)
        self.gpu_accel = params.get("gpu_accel", "none") # none, nvenc, qsv

    def render(self) -> None:
        if not HAS_MOVIEPY:
            raise RuntimeError(
                "MoviePy not installed. Please run: "
                "python -m pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg"
            )

        ensure_parent(self.output_path)
        clips: List[Any] = []
        final = None

        try:
            segments = self.plan.get("segments", [])
            total = max(1, len(segments))

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

            if not clips:
                raise RuntimeError("No valid clips generated")

            emit_event("phase", phase="render", message="正在合成最终时间线", percent=91)
            final = concatenate_videoclips(clips, method="compose")

            if self.params.get("watermark"):
                emit_event("phase", phase="render", message="正在添加水印", percent=92)
                final = self._add_watermark(final, str(self.params.get("watermark")))

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
                )

            return self._chapter_card(seg, duration)

        if stype == "image":
            clip = self._image_clip(Path(seg["source_path"]), duration)
            return self._apply_overlay_title(clip, seg)

        if stype == "video":
            clip = self._video_clip(
                Path(seg["source_path"]),
                duration,
                keep_audio=bool(seg.get("keep_audio", True)),
            )
            return self._apply_overlay_title(clip, seg)

        return None

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
        out = self.temp_dir / f"text_bg_{position}_{safe_id(str(source))}.jpg"
        if out.exists():
            return out

        try:
            if suffix in IMAGE_EXTS:
                with Image.open(source) as img:
                    img = ImageOps.exif_transpose(img).convert("RGB")
                    img.save(out, quality=94)
                return out

            if suffix in VIDEO_EXTS:
                clip = VideoFileClip(str(source))
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

        draw = ImageDraw.Draw(img)

        title_font = load_font(78 if main else 58)
        sub_font = load_font(34)

        tw, th = text_size(draw, title, title_font)
        draw.text(((w - tw) // 2, (h - th) // 2 - 40), title, font=title_font, fill=(255, 255, 255))

        if subtitle:
            sw, sh = text_size(draw, subtitle, sub_font)
            draw.text(((w - sw) // 2, (h - sh) // 2 + 55), subtitle, font=sub_font, fill=(52, 211, 153))

        return img

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

    def _image_clip(self, source: Path, duration: float):
        fixed = self.temp_dir / f"fixed_{safe_id(str(source))}.jpg"
        with Image.open(source) as img:
            img = ImageOps.exif_transpose(img).convert("RGB")
            img.save(fixed, quality=95)

        fg = ImageClip(str(fixed)).set_duration(duration)
        return self._compose_with_blur_bg(fg, duration, source_image=fixed)

    def _video_clip(self, source: Path, duration: float, keep_audio: bool = True):
        raw = VideoFileClip(str(source))
        if raw.duration and raw.duration > duration:
            raw = raw.subclip(0, duration)
        raw = raw.set_duration(min(duration, raw.duration or duration))

        frame_path: Optional[Path] = self.temp_dir / f"frame_{safe_id(str(source))}.jpg"
        try:
            raw.save_frame(str(frame_path), t=min(1.0, (raw.duration or 1.0) / 2))
        except Exception:
            frame_path = None

        final = self._compose_with_blur_bg(raw, raw.duration or duration, source_image=frame_path)
        if keep_audio and raw.audio is not None:
            final = final.set_audio(raw.audio)
        return final

    def _compose_with_blur_bg(self, clip: Any, duration: float, source_image: Optional[Path]):
        tw, th = self.target_size
        scale = min(tw / clip.w, th / clip.h)
        fg = clip.resize((max(1, int(clip.w * scale)), max(1, int(clip.h * scale))))

        if source_image and Path(source_image).exists():
            bg_path = self._blur_bg(Path(source_image))
            bg = ImageClip(str(bg_path)).set_duration(duration)
        else:
            bg = ColorClip(self.target_size, color=(0, 0, 0)).set_duration(duration)

        return CompositeVideoClip(
            [bg, fg.set_position("center")],
            size=self.target_size,
        ).set_duration(duration)

    def _blur_bg(self, source_image: Path) -> Path:
        out = self.temp_dir / f"bg_{source_image.stem}.jpg"
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
        draw.text((16, 10), text, font=font, fill=(255, 255, 255, 150))

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
        "aspect_ratio": params.get("aspect_ratio"),
        "fps": params.get("fps"),
        "quality": params.get("quality"),
    }
    return _v56_stable_json_hash(stable)


def _v56_build_chunk_groups(
    segments: List[Dict[str, Any]],
    chunk_seconds: float,
    params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    params = params or {}
    chunk_seconds = max(float(chunk_seconds or 240), 30.0)

    groups: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_duration = 0.0
    current_keys: List[str] = []

    for seg in segments:
        duration = float(seg.get("duration") or 0.0)
        if current and current_duration + duration > chunk_seconds:
            groups.append({
                "index": len(groups),
                "segments": current,
                "duration": round(current_duration, 3),
                "cache_key": _v56_stable_json_hash(current_keys),
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
            "-i", str(concat_list),
            "-c", "copy",
            str(tmp_output),
        ]
        emit_event("phase", phase="concat", message="使用 FFmpeg 快速拼接分段视频", percent=96)
        completed = subprocess.run(cmd, cwd=str(project_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0:
            return True
        emit_event("log", message=f"FFmpeg concat copy 失败，准备回退 MoviePy: {completed.stderr[-800:]}")
        return False
    except Exception as exc:
        emit_event("log", message=f"FFmpeg concat 不可用，准备回退 MoviePy: {exc}")
        return False


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


def _v56_write_chunk_video(
    renderer: Any,
    chunk: Dict[str, Any],
    chunk_path: Path,
    fps: int,
    params: Dict[str, Any],
) -> None:
    clips = []
    combined = None
    tmp_chunk = chunk_path.with_suffix(".rendering.tmp.mp4")

    try:
        for seg in chunk["segments"]:
            emit_event(
                "phase",
                phase="render",
                message=f"渲染分段 {chunk['index'] + 1}: {seg.get('type')} {seg.get('text') or ''}",
                percent=min(94, 10 + chunk["index"]),
            )
            clip = renderer._segment(seg)
            clips.append(clip)

        if not clips:
            raise RuntimeError(f"chunk_{chunk['index']:03d} 没有可渲染 clip")

        combined = concatenate_videoclips(clips, method="compose")
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
        self.chunk_seconds = float(self.params.get("chunk_seconds") or self.params.get("stable_chunk_seconds") or 240)

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

        segments = self.plan.get("segments", [])
        groups = _v56_build_chunk_groups(segments, self.chunk_seconds, self.params)
        manifest = self._load_manifest()
        manifest.setdefault("engine_version", ENGINE_VERSION)
        manifest.setdefault("chunks", {})

        emit_event(
            "phase",
            phase="render",
            message=f"启用 V5.6 长视频稳定模式：{len(groups)} 个分段，每段约 {int(self.chunk_seconds)} 秒",
            percent=8,
        )

        renderer = Renderer(self.plan, str(self.output), self.params)
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
                chunk_reports.append({"name": chunk_name, "status": "cached", "duration": duration, "cache_key": key})
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
                chunk_reports.append({"name": chunk_name, "status": "rendered", "duration": duration, "cache_key": key})
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
                    "created_at": datetime.now().isoformat(),
                })
                raise

        if not rendered_chunks:
            raise RuntimeError("没有成功渲染任何分段")

        concat_ok = _v56_concat_chunks_ffmpeg(rendered_chunks, tmp_output, self.project_dir)
        if not concat_ok:
            _v56_concat_chunks_moviepy(rendered_chunks, tmp_output, self.fps, self.params)

        ok, reason, final_duration = _v56_validate_video(tmp_output)
        if not ok:
            raise RuntimeError(f"最终视频校验失败，不覆盖旧文件: {reason}")

        _v56_atomic_replace(tmp_output, final_output)

        elapsed = (datetime.now() - started_at).total_seconds()
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



def command_render(args: argparse.Namespace) -> None:
    params = json.loads(args.params) if getattr(args, "params", None) else {}
    render_with_v56_stability(args.plan, args.output, params)


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
