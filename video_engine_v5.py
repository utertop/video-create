# -*- coding: utf-8 -*-
"""
video_engine_v5.py

Video Create Studio V5 核心引擎
负责：scan, plan, compile, render 四阶段生命周期。

V5 核心改进：
1. 引入子命令架构。
2. 深度 EXIF 元数据提取。
3. 智能目录角色识别 (City - Date - Scenic Spot)。
4. 标准化 JSON 数据交互协议。
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageOps
# 修复新版 Pillow 移除 ANTIALIAS 导致的 MoviePy 崩溃
if not hasattr(Image, 'ANTIALIAS'):
    Image.ANTIALIAS = Image.LANCZOS

try:
    from moviepy.editor import (
        VideoFileClip, ImageClip, TextClip, CompositeVideoClip, 
        concatenate_videoclips, ColorClip
    )
    from moviepy.video.fx.all import resize, crop
    HAS_MOVIEPY = True
except ImportError:
    HAS_MOVIEPY = False

# =========================
# 常量与配置
# =========================

SCHEMA_VERSION = "5.0.0"
ENGINE_VERSION = "video-create-engine-v5"

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")
ALL_EXTS = IMAGE_EXTS + VIDEO_EXTS

# 简单的内置地理词典辅助识别 (可扩展)
CITY_KEYWORDS = ["市", "州", "盟", "泉州", "厦门", "杭州", "北京", "上海", "东京", "巴黎", "京都"]
SPOT_KEYWORDS = ["寺", "园", "山", "桥", "塔", "宫", "馆", "西街", "开元寺", "鼓浪屿", "外滩"]

# =========================
# 数据模型 (Schemas)
# =========================

@dataclass
class FileInfo:
    name: str
    extension: str
    size_bytes: int
    modified_time: str
    content_hash: Optional[str] = None

@dataclass
class MediaInfo:
    width: Optional[int] = None
    height: Optional[int] = None
    orientation: Optional[str] = None # landscape / portrait / square
    exif_orientation: Optional[int] = None
    duration_seconds: Optional[float] = None
    shooting_date: Optional[str] = None # 从 EXIF 提取

@dataclass
class AssetClassification:
    directory_node_id: str
    city: Optional[str] = None
    date: Optional[str] = None
    scenic_spot: Optional[str] = None
    detected_role: str = "normal"
    confidence: float = 0.0

@dataclass
class AssetRef:
    asset_id: str
    enabled: bool = True
    role: str = "normal" # opening / normal / highlight
    duration_policy: str = "auto"
    custom_duration: Optional[float] = None
    keep_audio: bool = True

@dataclass
class StorySection:
    section_id: str
    section_type: str # title / city / date / scenic_spot / chapter / end
    title: str
    subtitle: Optional[str] = None
    enabled: bool = True
    source_node_id: Optional[str] = None
    asset_refs: List[AssetRef] = field(default_factory=list)
    children: List['StorySection'] = field(default_factory=list)

@dataclass
class StoryBlueprint:
    schema_version: str = SCHEMA_VERSION
    document_type: str = "story_blueprint"
    title: str = "New Travel Video"
    subtitle: str = "Travel Memories"
    sections: List[StorySection] = field(default_factory=list)
    strategy: str = "city_date_spot"

@dataclass
class Asset:
    asset_id: str
    type: str # image / video
    relative_path: str
    absolute_path: str
    file: FileInfo
    media: MediaInfo
    classification: AssetClassification
    status: str = "supported"
    thumbnail_path: Optional[str] = None

@dataclass
class DirectoryNode:
    node_id: str
    name: str
    relative_path: str
    depth: int
    parent_id: Optional[str] = None
    detected_type: str = "unknown" # city / date / scenic_spot / chapter / unknown
    confidence: float = 0.0
    reason: str = ""
    display_title: str = ""
    asset_count: int = 0
    children: List[str] = field(default_factory=list)

@dataclass
class RenderSegment:
    segment_id: str
    type: str # title / chapter / video / image / end
    source_path: Optional[str] = None
    duration: float = 3.0
    text: Optional[str] = None
    subtitle: Optional[str] = None
    start_time: float = 0.0
    end_time: float = 0.0

@dataclass
class RenderPlan:
    schema_version: str = SCHEMA_VERSION
    document_type: str = "render_plan"
    output_path: str = ""
    total_duration: float = 0.0
    segments: List[RenderSegment] = field(default_factory=list)

# =========================
# 工具函数
# =========================

def emit_event(event_type: str, **payload):
    payload["type"] = event_type
    print(json.dumps(payload, ensure_ascii=False), flush=True)

def natural_sort_key(name: str):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", name)]

def get_exif_date(img: Image.Image) -> Optional[str]:
    """提取照片拍摄时间"""
    try:
        exif = img.getexif()
        if not exif:
            return None
        # 306 是 DateTime
        # 36867 是 DateTimeOriginal
        date_str = exif.get(36867) or exif.get(306)
        if date_str:
            # 格式通常是 YYYY:MM:DD HH:MM:SS
            dt = datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
            return dt.isoformat()
    except Exception:
        pass
    return None

def detect_directory_type(name: str, depth: int) -> Tuple[str, float, str]:
    """智能识别目录类型逻辑"""
    # 1. 日期识别 (Day X, YYYY-MM-DD, 20240511)
    if re.search(r"day\s*\d+|20\d{6}|20\d{2}[-.]\d{2}[-.]\d{2}", name.lower()):
        return "date", 0.95, "匹配日期模式"
    
    # 2. 城市识别
    for kw in CITY_KEYWORDS:
        if kw in name:
            return "city", 0.92, f"匹配城市关键词: {kw}"
    
    # 3. 景点识别
    for kw in SPOT_KEYWORDS:
        if kw in name:
            return "scenic_spot", 0.88, f"匹配景点关键词: {kw}"
    
    # 4. 深度推断 (如果是深度 2 且未识别出城市，可能是景点)
    if depth == 2:
        return "scenic_spot", 0.60, "基于目录深度推断"
    
    return "chapter", 0.50, "默认章节"

# =========================
# Scan 命令实现
# =========================

class Scanner:
    def __init__(self, input_root: str):
        self.root = Path(input_root).resolve()
        self.assets: List[Asset] = []
        self.nodes: Dict[str, DirectoryNode] = {}
        self.asset_counter = 0
        self.node_counter = 0
        self.thumb_dir = self.root / ".thumbnails"
        self.thumb_dir.mkdir(exist_ok=True)

    def generate_id(self, prefix: str, counter: int) -> str:
        return f"{prefix}_{counter:06d}"

    def scan(self, recursive: bool = True):
        emit_event("phase", phase="scan", message="Starting smart scan...")
        self._scan_recursive(self.root, depth=0, recursive=recursive)
        emit_event("phase", phase="scan", message="Scan complete", percent=100)

    def _scan_recursive(self, current_dir: Path, depth: int, recursive: bool = True, parent_node: Optional[DirectoryNode] = None):
        rel_path = str(current_dir.relative_to(self.root)).replace("\\", "/")
        if rel_path == ".":
            rel_path = ""

        # 创建目录节点
        node_id = self.generate_id("dir", self.node_counter)
        self.node_counter += 1
        
        dtype, conf, reason = detect_directory_type(current_dir.name, depth)
        node = DirectoryNode(
            node_id=node_id,
            name=current_dir.name,
            relative_path=rel_path,
            depth=depth,
            parent_id=parent_node.node_id if parent_node else None,
            detected_type=dtype,
            confidence=conf,
            reason=reason,
            display_title=current_dir.name
        )
        self.nodes[node_id] = node
        if parent_node:
            parent_node.children.append(node_id)

        # 扫描文件
        try:
            entries = sorted(os.listdir(current_dir), key=natural_sort_key)
        except PermissionError:
            return

        for entry in entries:
            p = current_dir / entry
            if p.is_dir():
                if recursive and not entry.startswith(".") and not entry.startswith("__"):
                    self._scan_recursive(p, depth + 1, recursive, node)
            elif p.is_file():
                if entry.lower().endswith(ALL_EXTS):
                    self._process_file(p, node)

    def _process_file(self, p: Path, node: DirectoryNode):
        self.asset_counter += 1
        rel_path = str(p.relative_to(self.root)).replace("\\", "/")
        ext = p.suffix.lower()
        kind = "image" if ext in IMAGE_EXTS else "video"
        
        st = p.stat()
        file_info = FileInfo(
            name=p.name,
            extension=ext,
            size_bytes=st.st_size,
            modified_time=datetime.fromtimestamp(st.st_mtime).isoformat()
        )

        media_info = MediaInfo()
        if kind == "image":
            try:
                with Image.open(p) as img:
                    media_info.width, media_info.height = img.size
                    media_info.orientation = "landscape" if media_info.width > media_info.height else "portrait"
                    media_info.shooting_date = get_exif_date(img)
            except Exception:
                pass
        
        thumb_path = None
        if kind == "video" and HAS_MOVIEPY:
            try:
                clip = VideoFileClip(str(p))
                media_info.duration_seconds = clip.duration
                media_info.width, media_info.height = clip.size
                media_info.orientation = "landscape" if media_info.width > media_info.height else "portrait"
                
                # 生成缩略图
                t_name = f"{self.generate_id('asset', self.asset_counter)}.jpg"
                t_path = self.thumb_dir / t_name
                if not t_path.exists():
                    # 抓取第 1 秒（或总长的一半）
                    frame_t = min(1.0, clip.duration / 2)
                    clip.save_frame(str(t_path), t=frame_t)
                
                thumb_path = str(t_path)
                clip.close()
            except Exception as e:
                emit_event("log", message=f"Failed to extract thumb for {p.name}: {str(e)}")
        
        # 资产分类信息
        classification = AssetClassification(
            directory_node_id=node.node_id,
            city=node.name if node.detected_type == "city" else None,
            scenic_spot=node.name if node.detected_type == "scenic_spot" else None,
            confidence=node.confidence
        )

        asset = Asset(
            asset_id=self.generate_id("asset", self.asset_counter),
            type=kind,
            relative_path=rel_path,
            absolute_path=str(p),
            file=file_info,
            media=media_info,
            classification=classification,
            thumbnail_path=thumb_path
        )
        self.assets.append(asset)
        node.asset_count += 1

    def to_json(self) -> Dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "document_type": "media_library",
            "engine_version": ENGINE_VERSION,
            "project": {
                "source_root": str(self.root),
                "scan_time": datetime.now().isoformat()
            },
            "directory_nodes": [asdict(n) for n in self.nodes.values()],
            "assets": [asdict(a) for a in self.assets],
            "summary": {
                "total_assets": len(self.assets),
                "image_count": sum(1 for a in self.assets if a.type == "image"),
                "video_count": sum(1 for a in self.assets if a.type == "video")
            }
        }

# =========================
# Plan 命令实现
# =========================

class Planner:
    def __init__(self, library: Dict):
        self.library = library
        self.nodes = {n["node_id"]: n for n in library["directory_nodes"]}
        self.assets = library["assets"]
        self.section_counter = 0

    def generate_id(self, prefix: str) -> str:
        self.section_counter += 1
        return f"{prefix}_{self.section_counter:04d}"

    def plan(self, strategy: str = "city_date_spot") -> Dict:
        emit_event("phase", phase="plan", message=f"Generating story blueprint using strategy: {strategy}")
        
        sections = []
        
        # 1. 找到所有根节点 (depth=0 或 parent_id=None)
        roots = [n for n in self.nodes.values() if n["parent_id"] is None]
        
        for root in roots:
            self._process_node_recursive(root, sections)

        # 2. 如果根节点下没素材也没子节点，清理空章节 (TBD)

        blueprint = StoryBlueprint(
            title=self.library["project"].get("title", "My Travel Vlog"),
            sections=sections,
            strategy=strategy
        )
        
        emit_event("phase", phase="plan", message="Blueprint generation complete", percent=100)
        return self._as_dict(blueprint)

    def _process_node_recursive(self, node: Dict, target_list: List[StorySection]):
        # 获取该节点下的素材
        node_assets = [a for a in self.assets if a["classification"]["directory_node_id"] == node["node_id"]]
        
        # 创建章节
        section = StorySection(
            section_id=self.generate_id("section"),
            section_type=node["detected_type"],
            title=node["display_title"],
            source_node_id=node["node_id"],
            asset_refs=[AssetRef(asset_id=a["asset_id"]) for a in node_assets]
        )
        
        # 递归处理子节点
        for child_id in node["children"]:
            child_node = self.nodes[child_id]
            self._process_node_recursive(child_node, section.children)
            
        # 优化建议：如果一个章节没有素材且只有一个子章节，考虑合并 (TBD)
        
        target_list.append(section)

    def _as_dict(self, obj):
        if isinstance(obj, list):
            return [self._as_dict(i) for i in obj]
        if hasattr(obj, "__dict__"):
            res = {}
            for k, v in asdict(obj).items():
                res[k] = self._as_dict(v)
            return res
        return obj

# =========================
# Compile 命令实现
# =========================

class Compiler:
    def __init__(self, blueprint: Dict, library: Dict):
        self.blueprint = blueprint
        self.library = library
        self.assets_map = {a["asset_id"]: a for a in library["assets"]}
        self.current_time = 0.0
        self.segments: List[RenderSegment] = []

    def compile(self) -> Dict:
        emit_event("phase", phase="compile", message="Compiling blueprint into render plan...")
        
        # 1. 片头
        self._add_segment("title", duration=4.0, text=self.blueprint["title"], subtitle=self.blueprint["subtitle"])
        
        # 2. 遍历章节
        for section in self.blueprint["sections"]:
            self._process_section(section)
            
        # 3. 片尾
        self._add_segment("end", duration=3.0, text="To be continued!")

        plan = RenderPlan(
            total_duration=self.current_time,
            segments=self.segments
        )
        
        emit_event("phase", phase="compile", message=f"Compilation complete. Total duration: {self.current_time:.2f}s", percent=100)
        return self._as_dict(plan)

    def _process_section(self, section: Dict):
        if not section.get("enabled", True):
            return

        # 如果是城市或日期章节，添加章节卡
        if section["section_type"] in ["city", "date", "scenic_spot"]:
            self._add_segment("chapter", duration=2.5, text=section["title"], subtitle=section.get("subtitle"))

        # 处理当前章节的素材
        for ref in section.get("asset_refs", []):
            if not ref.get("enabled", True):
                continue
            
            asset = self.assets_map.get(ref["asset_id"])
            if not asset:
                continue

            duration = 3.0
            if asset["type"] == "video":
                # 暂时假设视频时长，未来通过 ffprobe 获取
                duration = asset["media"].get("duration_seconds") or 5.0
            
            if ref.get("duration_policy") == "custom" and ref.get("custom_duration"):
                duration = ref["custom_duration"]

            self._add_segment(
                asset["type"], 
                duration=duration, 
                source_path=asset["absolute_path"]
            )

        # 递归处理子章节
        for child in section.get("children", []):
            self._process_section(child)

    def _add_segment(self, seg_type: str, duration: float, text: Optional[str] = None, subtitle: Optional[str] = None, source_path: Optional[str] = None):
        seg = RenderSegment(
            segment_id=f"seg_{len(self.segments):04d}",
            type=seg_type,
            duration=duration,
            text=text,
            subtitle=subtitle,
            source_path=source_path,
            start_time=self.current_time,
            end_time=self.current_time + duration
        )
        self.segments.append(seg)
        self.current_time += duration

    def _as_dict(self, obj):
        if isinstance(obj, list):
            return [self._as_dict(i) for i in obj]
        if hasattr(obj, "__dict__"):
            res = {}
            for k, v in asdict(obj).items():
                res[k] = self._as_dict(v)
            return res
        return obj

# =========================
# Render 命令实现
# =========================

class Renderer:
    def __init__(self, plan: Dict, output_path: str, params: Dict):
        self.plan = plan
        self.output_path = output_path
        self.params = params # title, title_subtitle, watermark, etc.
        self.target_size = (1920, 1080) if params.get("aspect_ratio") == "16:9" else (1080, 1920)

    def render(self):
        if not HAS_MOVIEPY:
            emit_event("error", message="MoviePy not found. Cannot render.")
            return

        try:
            emit_event("phase", phase="render", message="Initializing rendering engine...")
            
            clips = []
            segments = self.plan["segments"]
            total = len(segments)

            for i, seg in enumerate(segments):
                emit_event("phase", phase="render", 
                           message=f"Processing segment {i+1}/{total}: {seg['type']}", 
                           percent=int((i/total)*100))
                
                try:
                    clip = self._create_segment_clip(seg)
                    if clip:
                        clips.append(clip)
                except Exception as seg_err:
                    emit_event("log", message=f"Error in segment {i+1}: {str(seg_err)}")
                    raise seg_err

            if not clips:
                emit_event("error", message="No clips generated. Rendering aborted.")
                return

            emit_event("phase", phase="render", message="Compositing final video...", percent=95)
            
            final_video = concatenate_videoclips(clips, method="compose")
            
            # 添加水印 (如果需要)
            if self.params.get("watermark"):
                try:
                    watermark_txt = TextClip(self.params["watermark"], fontsize=30, color='white', opacity=0.5)
                    watermark_txt = watermark_txt.set_duration(final_video.duration).set_position(("right", "bottom"))
                    final_video = CompositeVideoClip([final_video, watermark_txt])
                except Exception as e:
                    emit_event("log", message=f"Warning: Failed to add watermark: {str(e)}")

            emit_event("phase", phase="render", message="Starting FFmpeg export. This may take a while...", percent=98)
            
            final_video.write_videofile(
                self.output_path, 
                fps=30, 
                codec="libx264", 
                audio_codec="aac",
                temp_audiofile="temp-audio.m4a",
                remove_temp=True
            )
            
            emit_event("phase", phase="render", message="Video exported successfully!", percent=100)
            emit_event("artifact", artifact="video", path=self.output_path, message="Final video is ready")
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            emit_event("error", message=f"Render failed: {str(e)}", details=error_details)
            # 把详细堆栈打到 stdout 以便 Rust 捕获
            print(f"FATAL_ERROR: {error_details}")
            sys.exit(1)

    def _create_segment_clip(self, seg):
        stype = seg["type"]
        duration = seg["duration"]
        
        if stype == "title" or stype == "chapter":
            return self._create_text_card(seg["text"], seg.get("subtitle"), duration, is_main=(stype=="title"))
        
        if stype == "image":
            clip = ImageClip(seg["source_path"]).set_duration(duration)
            clip = self._process_visual_clip(clip)
            # 添加简单的缩放动画 (Ken Burns)
            clip = clip.fx(resize, lambda t: 1.0 + 0.05 * t) 
            return clip
        
        if stype == "video":
            clip = VideoFileClip(seg["source_path"])
            # 如果视频长于片段时长，则裁剪；否则保持原样或循环
            if clip.duration > duration:
                clip = clip.subclip(0, duration)
            clip = self._process_visual_clip(clip)
            return clip

        if stype == "end":
            return self._create_text_card(seg["text"] or "To be continued", None, duration, is_main=False)
        
        return None

    def _create_text_card(self, title, subtitle, duration, is_main=False):
        bg = ColorClip(size=self.target_size, color=(20, 40, 32)).set_duration(duration)
        
        try:
            t_clip = TextClip(title or "", fontsize=70 if is_main else 50, color='white', font="Arial-Bold")
            t_clip = t_clip.set_duration(duration).set_position("center")
            
            elements = [bg, t_clip]
            
            if subtitle:
                s_clip = TextClip(subtitle, fontsize=30, color='#4ade80', font="Arial")
                s_clip = s_clip.set_duration(duration).set_position(("center", self.target_size[1]//2 + 60))
                elements.append(s_clip)
                
            return CompositeVideoClip(elements)
        except Exception as e:
            emit_event("log", message=f"Warning: TextClip failed (ImageMagick missing?): {str(e)}")
            return bg

    def _process_visual_clip(self, clip):
        # 统一缩放并裁剪到目标画幅
        w, h = clip.size
        target_w, target_h = self.target_size
        
        # 先按比例缩放，使得一边对齐
        ratio = max(target_w / w, target_h / h)
        new_w, new_h = int(w * ratio), int(h * ratio)
        clip = clip.resize(newsize=(new_w, new_h))
        
        # 再从中间裁剪
        clip = clip.crop(x_center=new_w/2, y_center=new_h/2, width=target_w, height=target_h)
        return clip

# =========================
# CLI 主程序
# =========================

def main():
    parser = argparse.ArgumentParser(description="Video Create Studio V5 Engine")
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")

    # Scan 命令
    scan_parser = subparsers.add_parser("scan", help="Scan input folder for assets")
    scan_parser.add_argument("--input_folder", required=True, help="Path to raw assets")
    scan_parser.add_argument("--output", help="Path to save media_library.json")
    scan_parser.add_argument("--recursive", action="store_true", default=True, help="Recursive scan")

    # Plan 命令
    plan_parser = subparsers.add_parser("plan", help="Plan story blueprint from library")
    plan_parser.add_argument("--library", required=True, help="Path to media_library.json")
    plan_parser.add_argument("--output", help="Path to save story_blueprint.json")
    plan_parser.add_argument("--strategy", default="city_date_spot", help="Story organization strategy")

    # 其他占位命令
    # Compile 命令
    compile_parser = subparsers.add_parser("compile", help="Compile render plan from blueprint")
    compile_parser.add_argument("--blueprint", required=True, help="Path to story_blueprint.json")
    compile_parser.add_argument("--library", required=True, help="Path to media_library.json")
    compile_parser.add_argument("--output", help="Path to save render_plan.json")

    # Render 命令
    render_parser = subparsers.add_parser("render", help="Execute rendering from plan")
    render_parser.add_argument("--plan", required=True, help="Path to render_plan.json")
    render_parser.add_argument("--output", required=True, help="Output video path")
    render_parser.add_argument("--params", help="JSON string of extra params (title, watermark, etc.)")

    args = parser.parse_args()

    if args.command == "scan":
        scanner = Scanner(args.input_folder)
        scanner.scan(recursive=args.recursive)
        result = scanner.to_json()
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            emit_event("artifact", artifact="media_library", path=args.output, message="Media Library saved")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
    
    elif args.command == "plan":
        with open(args.library, "r", encoding="utf-8") as f:
            lib = json.load(f)
        planner = Planner(lib)
        result = planner.plan(strategy=args.strategy)
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            emit_event("artifact", artifact="story_blueprint", path=args.output, message="Story Blueprint saved")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
            
    elif args.command == "compile":
        with open(args.blueprint, "r", encoding="utf-8") as f:
            bp = json.load(f)
        with open(args.library, "r", encoding="utf-8") as f:
            lib = json.load(f)
        compiler = Compiler(bp, lib)
        result = compiler.compile()
        
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            emit_event("artifact", artifact="render_plan", path=args.output, message="Render Plan saved")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "render":
        with open(args.plan, "r", encoding="utf-8") as f:
            plan = json.load(f)
        
        params = {}
        if args.params:
            params = json.loads(args.params)
            
        renderer = Renderer(plan, args.output, params)
        renderer.render()

    elif not args.command:
        parser.print_help()
    else:
        print(f"Command '{args.command}' is planned for V5 but not yet implemented in this draft.")

if __name__ == "__main__":
    main()
