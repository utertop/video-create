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
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

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

SCHEMA_VERSION = "5.0"
ENGINE_VERSION = "video-create-engine-v5.0.1"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")
ALL_EXTS = IMAGE_EXTS + VIDEO_EXTS

CITY_KEYWORDS = [
    "北京", "上海", "广州", "深圳", "杭州", "泉州", "厦门", "福州", "南京", "苏州",
    "成都", "重庆", "西安", "东京", "京都", "巴黎", "伦敦", "纽约", "市", "州"
]
SPOT_KEYWORDS = [
    "寺", "庙", "园", "山", "桥", "塔", "宫", "馆", "街", "巷", "岛", "湖", "海",
    "湾", "西街", "开元寺", "鼓浪屿", "曾厝垵", "外滩"
]
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


def detect_directory_type(name: str, depth: int) -> Tuple[str, float, str]:
    normalized = name.strip()
    lower = normalized.lower()

    for pattern in DATE_PATTERNS:
        if pattern.search(lower):
            return "date", 0.96, "目录名匹配日期模式"

    for kw in CITY_KEYWORDS:
        if kw and kw in normalized:
            return "city", 0.92, f"目录名匹配城市关键词: {kw}"

    for kw in SPOT_KEYWORDS:
        if kw and kw in normalized:
            return "scenic_spot", 0.88, f"目录名匹配景点关键词: {kw}"

    if depth >= 2:
        return "scenic_spot", 0.60, "基于目录深度推断为景点/子章节"
    if depth == 1:
        return "chapter", 0.55, "一级目录默认识别为章节"
    return "unknown", 0.35, "根目录或未知目录"


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
    asset_count: int = 0
    children: List[str] = field(default_factory=list)
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
        dtype, confidence, reason = detect_directory_type(current.name, depth)
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
            "subtitle": "Travel Video",
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
        return StorySection(
            section_id=section_id,
            section_type=node.get("detected_type", "chapter"),
            title=node.get("display_title") or node.get("name", "章节"),
            subtitle=None,
            enabled=True,
            source_node_id=node["node_id"],
            asset_refs=asset_refs,
            children=children,
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
        self.time = 0.0
        self.segments: List[RenderSegment] = []

    def compile(self) -> Dict[str, Any]:
        emit_event("phase", phase="compile", message="编译渲染计划", percent=20)

        self._add(
            "title",
            duration=4.0,
            text=self.blueprint.get("title"),
            subtitle=self.blueprint.get("subtitle"),
        )

        for section in self.blueprint.get("sections", []):
            self._section(section)

        self._add("end", duration=3.0, text="To be continued!")

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
        if stype in {"city", "date", "scenic_spot", "chapter"}:
            self._add(
                "chapter",
                duration=2.5,
                text=section.get("title"),
                subtitle=section.get("subtitle"),
                section_id=section.get("section_id"),
            )

        for ref in section.get("asset_refs", []):
            if not ref.get("enabled", True):
                continue

            asset = self.assets.get(ref.get("asset_id"))
            if not asset or asset.get("status") == "error":
                continue

            duration = self._asset_duration(asset, ref)
            self._add(
                asset.get("type"),
                duration=duration,
                source_path=asset.get("absolute_path"),
                asset_id=asset.get("asset_id"),
                section_id=section.get("section_id"),
                keep_audio=bool(ref.get("keep_audio", True)),
            )

        for child in section.get("children", []):
            self._section(child)

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
    ) -> None:
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
            cache_key=safe_id(f"{seg_type}|{source_path}|{duration}|{text}|{ENGINE_VERSION}"),
        )
        self.segments.append(seg)
        self.time += duration


# =========================
# render -> final mp4
# =========================

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

            emit_event("phase", phase="render", message="Compositing final timeline", percent=91)
            final = concatenate_videoclips(clips, method="compose")

            if self.params.get("watermark"):
                emit_event("phase", phase="render", message="Adding watermark", percent=92)
                final = self._add_watermark(final, str(self.params.get("watermark")))

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

            emit_event("artifact", artifact="video", path=str(self.output_path), message="Final video is ready")
            emit_event("phase", phase="complete", message="Video exported successfully", percent=100)

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
            return self._text_card(
                seg.get("text") or "",
                seg.get("subtitle"),
                duration,
                main=(stype == "title"),
            )

        if stype == "image":
            return self._image_clip(Path(seg["source_path"]), duration)

        if stype == "video":
            return self._video_clip(
                Path(seg["source_path"]),
                duration,
                keep_audio=bool(seg.get("keep_audio", True)),
            )

        return None

    def _text_card(self, title: str, subtitle: Optional[str], duration: float, main: bool = False):
        w, h = self.target_size
        img = Image.new("RGB", self.target_size, (17, 31, 25))
        draw = ImageDraw.Draw(img)

        title_font = load_font(78 if main else 58)
        sub_font = load_font(34)

        tw, th = text_size(draw, title, title_font)
        draw.text(((w - tw) // 2, (h - th) // 2 - 40), title, font=title_font, fill=(255, 255, 255))

        if subtitle:
            sw, sh = text_size(draw, subtitle, sub_font)
            draw.text(((w - sw) // 2, (h - sh) // 2 + 55), subtitle, font=sub_font, fill=(52, 211, 153))

        return ImageClip(np.array(img)).set_duration(duration)

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
        cover = self.output_path.with_name(f"cover_{self.output_path.stem}.jpg")
        w, h = self.target_size
        img = Image.new("RGB", self.target_size, (18, 32, 26))
        draw = ImageDraw.Draw(img)

        title = str(self.params.get("title") or "Travel Video")
        subtitle = str(self.params.get("title_subtitle") or "Video Create Studio")

        title_font = load_font(72)
        sub_font = load_font(34)

        tw, th = text_size(draw, title, title_font)
        draw.text(((w - tw) // 2, h // 2 - 70), title, font=title_font, fill=(255, 255, 255))

        sw, sh = text_size(draw, subtitle, sub_font)
        draw.text(((w - sw) // 2, h // 2 + 30), subtitle, font=sub_font, fill=(52, 211, 153))

        img.save(cover, quality=92)
        emit_event("artifact", artifact="cover", path=str(cover), message="Cover generated")


# =========================
# CLI commands
# =========================

def command_scan(args: argparse.Namespace) -> None:
    scanner = Scanner(args.input_folder, recursive=args.recursive)
    result = scanner.scan()
    write_json(args.output, result)
    if args.output:
        emit_event("artifact", artifact="media_library", path=args.output, message="Media Library saved")


def command_plan(args: argparse.Namespace) -> None:
    result = Planner(read_json(args.library)).plan(strategy=args.strategy)
    write_json(args.output, result)
    if args.output:
        emit_event("artifact", artifact="story_blueprint", path=args.output, message="Story Blueprint saved")


def command_compile(args: argparse.Namespace) -> None:
    result = Compiler(read_json(args.blueprint), read_json(args.library)).compile()
    write_json(args.output, result)
    if args.output:
        emit_event("artifact", artifact="render_plan", path=args.output, message="Render Plan saved")


def command_render(args: argparse.Namespace) -> None:
    params = json.loads(args.params) if args.params else {}
    Renderer(read_json(args.plan), args.output, params).render()


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
