from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections import Counter
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .audio import probe_audio_file
from .cache import CACHE_CLEANUP_DEFAULTS_MB, _cleanup_cache_buckets, file_hash_light, safe_id
from .constants import ALL_EXTS, ENGINE_VERSION, IGNORED_DIRS, IMAGE_EXTS, SCHEMA_VERSION, VIDEO_EXTS
from .models import Asset, DirectoryNode, TitleStyle
from .scan_utils import (
    detect_directory_type,
    is_ignored_file,
    natural_sort_key,
    orientation_from_size,
)

SCAN_PROXY_PROFILE = {
    "name": "preview_540p",
    "max_width": 960,
    "max_height": 540,
    "video_crf": 28,
    "image_quality": 85,
}

_emit_event: Callable[..., None] = lambda _event_type, **_payload: None


def set_scan_event_emitter(callback: Callable[..., None]) -> None:
    global _emit_event
    _emit_event = callback


def emit_event(event_type: str, **payload: Any) -> None:
    _emit_event(event_type, **payload)


def _image_deps() -> Tuple[Any, Any]:
    from PIL import Image, ImageOps

    return Image, ImageOps


def _video_file_clip_class() -> Optional[Any]:
    try:
        from moviepy.editor import VideoFileClip

        return VideoFileClip
    except Exception:
        return None


def get_exif_date(img: Any) -> Optional[str]:
    try:
        exif = img.getexif()
        date_str = exif.get(36867) or exif.get(306)
        if date_str:
            return datetime.strptime(str(date_str), "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        return None
    return None


class Scanner:
    def __init__(self, input_root: str, recursive: bool = True):
        self.root = Path(input_root).resolve()
        self.recursive = recursive
        self.nodes: Dict[str, DirectoryNode] = {}
        self.assets: List[Asset] = []
        self.cache_root = self.root / ".cache_video_create_v5"
        self.thumb_dir = self.cache_root / "thumbnails"
        self.proxy_dir = self.cache_root / "proxies"
        self.metadata_dir = self.cache_root / "metadata"
        self.thumb_dir.mkdir(parents=True, exist_ok=True)
        self.proxy_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.proxy_manifest: Dict[str, Any] = {
            "version": 1,
            "profile": dict(SCAN_PROXY_PROFILE),
            "generated_at": None,
            "assets": {},
            "summary": {
                "eligible": 0,
                "ready": 0,
                "error": 0,
            },
        }
        self.cache_cleanup_stats: Dict[str, Any] = {"enabled": True, "buckets": {}, "deleted_files": 0, "deleted_bytes": 0}
        self.metadata_cache_stats: Dict[str, int] = {"hit": 0, "miss": 0, "error": 0}
        self.skipped_count = 0

    def scan(self) -> Dict[str, Any]:
        if not self.root.exists() or not self.root.is_dir():
            raise FileNotFoundError(f"输入目录不存在或不是目录: {self.root}")

        emit_event("phase", phase="scan", message="开始扫描素材", percent=5)
        self._scan_dir(self.root, depth=0, parent_id=None, inherited={})
        self._normalize_directory_nodes()
        self._refresh_asset_classification_context()
        self.proxy_manifest["generated_at"] = datetime.now().isoformat()
        self.cache_cleanup_stats = self._cleanup_scan_cache_dirs()
        if self.metadata_cache_stats["hit"] > 0:
            emit_event(
                "log",
                message=(
                    "Scan metadata cache summary: "
                    f"hit={self.metadata_cache_stats['hit']}, "
                    f"miss={self.metadata_cache_stats['miss']}, "
                    f"error={self.metadata_cache_stats['error']}"
                ),
            )
        emit_event("phase", phase="scan", message="素材扫描完成", percent=100)
        content_profile = self._build_scan_content_profile()

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
            "proxy_media_manifest": self.proxy_manifest,
            "scan_metadata_cache": dict(self.metadata_cache_stats),
            "cache_cleanup": self.cache_cleanup_stats,
            "summary": {
                "total_assets": len(self.assets),
                "image_count": sum(1 for a in self.assets if a.type == "image"),
                "video_count": sum(1 for a in self.assets if a.type == "video"),
                "audio_count": sum(1 for a in self.assets if a.type == "audio"),
                "skipped_count": self.skipped_count,
                "error_count": sum(1 for a in self.assets if a.status == "error"),
                "content_profile": content_profile,
            },
        }

    def _build_scan_content_profile(self) -> Dict[str, Any]:
        visual_assets = [a for a in self.assets if a.type in {"image", "video"}]
        visual_count = len(visual_assets)
        image_count = sum(1 for a in self.assets if a.type == "image")
        video_count = sum(1 for a in self.assets if a.type == "video")
        audio_count = sum(1 for a in self.assets if a.type == "audio")
        orientation_counts: Counter[str] = Counter()
        video_durations: List[float] = []
        keyword_counts: Counter[str] = Counter()
        node_type_counts: Counter[str] = Counter()

        for node in self.nodes.values():
            node_type_counts[str(node.detected_type or "unknown")] += 1
            signals = node.signals or {}
            for keyword in signals.get("matched_theme_keywords") or []:
                keyword_counts[str(keyword)] += 2
            for keyword in signals.get("matched_event_keywords") or []:
                keyword_counts[str(keyword)] += 2

        for asset in visual_assets:
            media = asset.media or {}
            width = int(media.get("width") or 0)
            height = int(media.get("height") or 0)
            if width > 0 and height > 0:
                orientation_counts[orientation_from_size((width, height))] += 1
            if asset.type == "video":
                duration = float(media.get("duration_seconds") or 0.0)
                if duration > 0:
                    video_durations.append(duration)

        image_ratio = (image_count / visual_count) if visual_count else 0.0
        video_ratio = (video_count / visual_count) if visual_count else 0.0
        portrait_ratio = (orientation_counts.get("portrait", 0) / visual_count) if visual_count else 0.0
        landscape_ratio = (orientation_counts.get("landscape", 0) / visual_count) if visual_count else 0.0
        square_ratio = (orientation_counts.get("square", 0) / visual_count) if visual_count else 0.0

        dominant_media_type = "mixed"
        if visual_count == 0:
            dominant_media_type = "unknown"
        elif image_ratio >= 0.72:
            dominant_media_type = "image"
        elif video_ratio >= 0.72:
            dominant_media_type = "video"

        return {
            "visual_asset_count": visual_count,
            "image_count": image_count,
            "video_count": video_count,
            "audio_count": audio_count,
            "image_ratio": round(image_ratio, 3),
            "video_ratio": round(video_ratio, 3),
            "portrait_ratio": round(portrait_ratio, 3),
            "landscape_ratio": round(landscape_ratio, 3),
            "square_ratio": round(square_ratio, 3),
            "dominant_media_type": dominant_media_type,
            "mixed_media": visual_count > 0 and image_count > 0 and video_count > 0,
            "total_video_duration_seconds": round(sum(video_durations), 3),
            "avg_video_duration_seconds": round(sum(video_durations) / len(video_durations), 3) if video_durations else 0.0,
            "top_level_section_count": sum(1 for node in self.nodes.values() if int(node.depth or 0) == 1),
            "chapter_node_count": int(node_type_counts.get("chapter", 0)),
            "city_node_count": int(node_type_counts.get("city", 0)),
            "date_node_count": int(node_type_counts.get("date", 0)),
            "scenic_spot_node_count": int(node_type_counts.get("scenic_spot", 0)),
            "top_keywords": [
                {"keyword": keyword, "count": int(count)}
                for keyword, count in keyword_counts.most_common(6)
            ],
        }

    def _cleanup_scan_cache_dirs(self) -> Dict[str, Any]:
        summary = _cleanup_cache_buckets(
            [
                ("scan_proxies", self.proxy_dir, CACHE_CLEANUP_DEFAULTS_MB["scan_proxies"]),
                ("thumbnails", self.thumb_dir, CACHE_CLEANUP_DEFAULTS_MB["thumbnails"]),
                ("scan_metadata", self.metadata_dir, 128),
            ],
            {},
        )
        deleted_files = int(summary.get("deleted_files") or 0)
        deleted_bytes = int(summary.get("deleted_bytes") or 0)
        if deleted_files > 0:
            emit_event(
                "log",
                message=f"Scan cache cleanup: deleted_files={deleted_files}, deleted_bytes={deleted_bytes}",
            )
        return summary

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


    def _metadata_cache_path(self, asset_id: str, cache_key: str) -> Path:
        return self.metadata_dir / f"{asset_id}_{cache_key[:12]}.json"

    def _load_scan_metadata_cache(self, asset_id: str, cache_key: str, kind: str) -> Optional[Dict[str, Any]]:
        cache_path = self._metadata_cache_path(asset_id, cache_key)
        if not cache_path.exists():
            self.metadata_cache_stats["miss"] += 1
            return None

        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if cached.get("engine_version") != ENGINE_VERSION:
                self.metadata_cache_stats["miss"] += 1
                return None
            if cached.get("cache_key") != cache_key or cached.get("kind") != kind:
                self.metadata_cache_stats["miss"] += 1
                return None
            thumb = cached.get("thumbnail_path")
            if kind in {"image", "video"} and (not thumb or not Path(str(thumb)).exists()):
                self.metadata_cache_stats["miss"] += 1
                return None
            media = cached.get("media")
            if not isinstance(media, dict):
                self.metadata_cache_stats["miss"] += 1
                return None
            self.metadata_cache_stats["hit"] += 1
            return cached
        except Exception:
            self.metadata_cache_stats["error"] += 1
            return None

    def _write_scan_metadata_cache(
        self,
        asset_id: str,
        cache_key: str,
        kind: str,
        media: Dict[str, Any],
        thumbnail_path: Optional[str],
        status: str,
    ) -> None:
        if status != "ready":
            return
        cache_path = self._metadata_cache_path(asset_id, cache_key)
        payload = {
            "version": 1,
            "engine_version": ENGINE_VERSION,
            "cache_key": cache_key,
            "kind": kind,
            "media": media,
            "thumbnail_path": thumbnail_path,
            "generated_at": datetime.now().isoformat(),
        }
        try:
            tmp_path = cache_path.with_suffix(".tmp.json")
            tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(str(tmp_path), str(cache_path))
        except Exception:
            self.metadata_cache_stats["error"] += 1

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
        cached = self._load_scan_metadata_cache(asset_id, cache_key, kind)
        if cached:
            media.update(dict(cached.get("media") or {}))
            thumb = cached.get("thumbnail_path") or None
            proxy_entry = self._build_scan_proxy_entry(path, kind, media, cache_key)
            if proxy_entry:
                self.proxy_manifest["assets"][str(path)] = proxy_entry
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
                    "proxy_profiles": proxy_entry.get("profiles") if proxy_entry else {},
                    "generated_at": datetime.now().isoformat(),
                    "metadata_cache": "hit",
                },
            )

        try:
            if kind == "image":
                image_mod, image_ops = _image_deps()
                with image_mod.open(path) as img:
                    img = image_ops.exif_transpose(img)
                    img = img.convert("RGB")
                    media["width"], media["height"] = img.size
                    media["orientation"] = orientation_from_size(img.size)
                    media["shooting_date"] = get_exif_date(img)
                    thumb = self._make_image_thumb(img, asset_id, cache_key)
            elif kind == "video":
                video_file_clip = _video_file_clip_class()
                if video_file_clip is not None:
                    clip = video_file_clip(str(path))
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

        self._write_scan_metadata_cache(asset_id, cache_key, kind, media, thumb, status)
        proxy_entry = self._build_scan_proxy_entry(path, kind, media, cache_key)
        if proxy_entry:
            self.proxy_manifest["assets"][str(path)] = proxy_entry

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
                "proxy_profiles": proxy_entry.get("profiles") if proxy_entry else {},
                "generated_at": datetime.now().isoformat(),
            },
        )

    def _build_scan_proxy_entry(
        self,
        path: Path,
        kind: str,
        media: Dict[str, Any],
        cache_key: str,
    ) -> Optional[Dict[str, Any]]:
        if kind not in {"image", "video"}:
            return None

        summary = self.proxy_manifest["summary"]
        summary["eligible"] = int(summary.get("eligible") or 0) + 1

        profile = dict(SCAN_PROXY_PROFILE)
        max_w = int(profile["max_width"])
        max_h = int(profile["max_height"])
        stat = path.stat()
        rel = path.relative_to(self.root).as_posix()
        proxy_hash = hashlib.md5(
            f"{ENGINE_VERSION}|scan_proxy|{path.resolve()}|{stat.st_mtime_ns}|{stat.st_size}|{kind}|{max_w}x{max_h}".encode("utf-8")
        ).hexdigest()
        ext = ".mp4" if kind == "video" else ".jpg"
        proxy_path = self.proxy_dir / f"proxy_{proxy_hash}{ext}"
        source_width = int(media.get("width") or 0)
        source_height = int(media.get("height") or 0)

        try:
            if not proxy_path.exists():
                self._materialize_scan_proxy(path, proxy_path, kind, max_w, max_h, profile)
            width, height = self._probe_scan_proxy_dimensions(proxy_path, kind, fallback=(source_width, source_height))
            summary["ready"] = int(summary.get("ready") or 0) + 1
            return {
                "asset_id": "asset_" + safe_id(rel),
                "source_path": str(path),
                "kind": kind,
                "profiles": {
                    str(profile["name"]): {
                        "path": str(proxy_path),
                        "width": width,
                        "height": height,
                        "status": "ready",
                        "cache_key": cache_key,
                        "generated_at": datetime.now().isoformat(),
                    }
                },
            }
        except Exception as exc:
            summary["error"] = int(summary.get("error") or 0) + 1
            emit_event("log", message=f"扫描期代理素材生成失败，预览将回退到运行时代理: {path.name}: {exc}")
            return {
                "asset_id": "asset_" + safe_id(rel),
                "source_path": str(path),
                "kind": kind,
                "profiles": {
                    str(profile["name"]): {
                        "path": str(proxy_path),
                        "width": source_width or None,
                        "height": source_height or None,
                        "status": "error",
                        "error": str(exc),
                    }
                },
            }

    def _materialize_scan_proxy(
        self,
        source: Path,
        proxy_path: Path,
        kind: str,
        max_width: int,
        max_height: int,
        profile: Dict[str, Any],
    ) -> None:
        if kind == "video":
            import imageio_ffmpeg

            cmd = [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-i",
                str(source),
                "-vf",
                f"scale='min({max_width},iw)':'min({max_height},ih)':force_original_aspect_ratio=decrease",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                str(profile.get("video_crf") or 28),
                "-c:a",
                "aac",
                "-b:a",
                "96k",
                str(proxy_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            return

        image_mod, image_ops = _image_deps()
        with image_mod.open(source) as img:
            img = image_ops.exif_transpose(img).convert("RGB")
            img.thumbnail((max_width, max_height), image_mod.Resampling.LANCZOS)
            img.save(proxy_path, quality=int(profile.get("image_quality") or 85))

    def _probe_scan_proxy_dimensions(
        self,
        proxy_path: Path,
        kind: str,
        fallback: Tuple[int, int],
    ) -> Tuple[Optional[int], Optional[int]]:
        if kind == "image":
            image_mod, _image_ops = _image_deps()
            with image_mod.open(proxy_path) as img:
                return int(img.width), int(img.height)
        width, height = fallback
        return (int(width) or None, int(height) or None)

    def _make_image_thumb(self, img: Any, asset_id: str, cache_key: str) -> str:
        out = self.thumb_dir / f"{asset_id}_{cache_key[:8]}.jpg"
        if not out.exists():
            image_mod, _image_ops = _image_deps()
            thumb = img.convert("RGB")
            thumb.thumbnail((480, 270))
            canvas = image_mod.new("RGB", (480, 270), (20, 24, 22))
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
