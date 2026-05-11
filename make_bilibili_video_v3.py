# -*- coding: utf-8 -*-
"""
make_bilibili_video_v3.py

B站 / YouTube 横屏旅行视频生成器 V3

定位：
    面向 Lumix / 相机照片 + mp4 视频素材，批量生成 16:9 横屏旅行相册视频。

V3 重点能力：
    1. 默认 1920x1080 / 16:9，适合 B站横屏。
    2. 照片自动修正 EXIF 方向，避免竖拍照片横过来或倒置。
    3. 照片完整显示，不裁剪、不拉伸；两侧/上下使用同图模糊背景。
    4. 视频完整显示，不裁剪、不拉伸；竖屏视频也支持模糊背景。
    5. 默认保留原视频声音；照片、片头、章节、片尾自动补静音音轨，方便后续拼接。
    6. 支持缓存：EXIF 修正图、模糊背景、视频首帧、标准化片段 mp4。
    7. 支持递归目录：--recursive，并可按子目录自动生成章节标题卡。
    8. 支持智能照片时长：按横竖图、全景、亮度、画面复杂度估算展示时间。
    9. 支持水印 / 角标：--watermark "PangBo Travel"。
    10. 支持自动生成 B站封面图：--cover。
    11. 支持 build_report.txt 构建报告。
    12. 支持两种最终合成引擎：
        - moviepy_crossfade：效果更好，有交叉淡化，适合素材中等规模。
        - ffmpeg_concat：速度更快，适合大批量素材，转场为片段自身淡入淡出。
        - auto：素材较少用 crossfade，素材较多用 ffmpeg_concat。

推荐安装：
    python -m pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg

推荐运行：
    python make_bilibili_video_v3.py --input_folder "E:\\Lumix\\泉州-厦门\\hh" --recursive --chapters_from_dirs --title "福建-泉州-厦门" --end "To be continued!" --watermark "PangBo Travel" --cover --quality high --output_name "quanzhou_xiamen"
"""

import argparse
import hashlib
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# 兼容 Pillow 10+，修复 moviepy 1.x 内部使用 Image.ANTIALIAS 的问题
if not hasattr(Image, "ANTIALIAS"):
    Image.ANTIALIAS = Image.Resampling.LANCZOS

from moviepy.editor import (
    AudioClip,
    ColorClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
    concatenate_videoclips,
)

try:
    import imageio_ffmpeg
except Exception:
    imageio_ffmpeg = None


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp")
VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".m4v")
ALL_EXTS = IMAGE_EXTS + VIDEO_EXTS


def emit_event(event_type: str, **payload):
    payload["type"] = event_type
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def emit_log(message: str, **payload):
    emit_event("log", message=message, **payload)


def emit_phase(phase: str, message: Optional[str] = None, percent: Optional[int] = None, **payload):
    data = {"phase": phase}
    if message is not None:
        data["message"] = message
    if percent is not None:
        data["percent"] = percent
    data.update(payload)
    emit_event("phase", **data)


def emit_progress(current: int, total: int, phase: str, message: str, **payload):
    percent = 0 if total <= 0 else max(0, min(100, round(current / total * 90)))
    emit_event(
        "progress",
        current=current,
        total=total,
        percent=percent,
        phase=phase,
        message=message,
        **payload,
    )


@dataclass
class MediaItem:
    kind: str              # image / video / title / chapter / end
    path: Optional[str]
    rel_path: str
    display_name: str
    chapter: Optional[str] = None
    duration: Optional[float] = None
    source_mtime: Optional[float] = None
    source_size: Optional[int] = None
    cached_segment: Optional[str] = None
    status: str = "pending"
    error: Optional[str] = None


def natural_sort_key(name: str):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", name)]


def get_resolution(ratio: str) -> Tuple[int, int]:
    if ratio == "16:9":
        return 1920, 1080
    if ratio == "9:16":
        return 1080, 1920
    if ratio == "1:1":
        return 1080, 1080
    return 1920, 1080


def get_quality_params(quality: str) -> Tuple[str, str]:
    # CRF 越小画质越高、文件越大
    if quality == "normal":
        return "22", "medium"
    if quality == "high":
        return "20", "medium"
    if quality == "ultra":
        return "18", "slow"
    return "20", "medium"


def get_ffmpeg_exe() -> str:
    if imageio_ffmpeg is not None:
        try:
            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            pass
    return "ffmpeg"


def safe_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r"[^\w\u4e00-\u9fff.-]+", "_", name, flags=re.UNICODE)
    name = name.strip("._ ")
    return name[:max_len] if name else "unnamed"


def is_ignored_file(filename: str) -> bool:
    lower = filename.lower()
    base = os.path.basename(filename)
    if base.startswith(".") or base.startswith("~"):
        return True
    if base.startswith("_temp") or base.startswith("._"):
        return True
    if lower.endswith("副本.jpg") or lower.endswith("副本.jpeg"):
        return True
    if lower in ("thumbs.db", ".ds_store"):
        return True
    return False


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def file_signature(path: str) -> Dict[str, object]:
    st = os.stat(path)
    return {
        "path": os.path.abspath(path),
        "size": st.st_size,
        "mtime": int(st.st_mtime),
    }


def stable_hash(data: Dict[str, object]) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:20]


def get_font_path() -> Optional[str]:
    candidates = [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        r"C:\Windows\Fonts\simsun.ttc",
        r"C:\Windows\Fonts\arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return None


def make_silent_audio(duration: float, fps: int = 44100):
    def make_frame(t):
        if isinstance(t, np.ndarray):
            return np.zeros((len(t), 2))
        return np.array([0.0, 0.0])
    return AudioClip(make_frame, duration=duration, fps=fps)


def write_clip(clip, output_path: str, fps: int, quality: str, with_audio: bool = True):
    crf, preset = get_quality_params(quality)
    kwargs = dict(
        fps=fps,
        codec="libx264",
        preset=preset,
        threads=4,
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart", "-crf", crf],
        verbose=False,
        logger=None,
    )
    if with_audio:
        kwargs["audio_codec"] = "aac"
    else:
        kwargs["audio"] = False
    clip.write_videofile(output_path, **kwargs)


# =========================
# 素材收集 / 章节
# =========================


def collect_media_files(input_folder: str, recursive: bool = False) -> List[MediaItem]:
    input_root = Path(input_folder)
    files: List[Path] = []

    if recursive:
        for root, dirs, names in os.walk(input_folder):
            dirs[:] = sorted([d for d in dirs if not d.startswith(".") and not d.startswith("__")], key=natural_sort_key)
            for name in sorted(names, key=natural_sort_key):
                if is_ignored_file(name):
                    continue
                if name.lower().endswith(ALL_EXTS):
                    files.append(Path(root) / name)
    else:
        for name in sorted(os.listdir(input_folder), key=natural_sort_key):
            if is_ignored_file(name):
                continue
            p = input_root / name
            if p.is_file() and name.lower().endswith(ALL_EXTS):
                files.append(p)

    items: List[MediaItem] = []
    for p in files:
        rel = str(p.relative_to(input_root)).replace("\\", "/")
        lower = p.name.lower()
        kind = "image" if lower.endswith(IMAGE_EXTS) else "video"
        chapter = None
        parent = p.parent.relative_to(input_root)
        if str(parent) not in (".", ""):
            chapter = str(parent).replace("\\", " / ")
        sig = file_signature(str(p))
        items.append(MediaItem(
            kind=kind,
            path=str(p),
            rel_path=rel,
            display_name=p.name,
            chapter=chapter,
            source_mtime=float(sig["mtime"]),
            source_size=int(sig["size"]),
        ))
    return items


def inject_structure_cards(
    media_items: List[MediaItem],
    title_text: Optional[str],
    end_text: Optional[str],
    chapters_from_dirs: bool,
) -> List[MediaItem]:
    result: List[MediaItem] = []
    if title_text:
        result.append(MediaItem(kind="title", path=None, rel_path="__TITLE__", display_name=title_text))

    last_chapter = None
    chapter_index = 0
    for item in media_items:
        if chapters_from_dirs and item.chapter and item.chapter != last_chapter:
            chapter_index += 1
            result.append(MediaItem(
                kind="chapter",
                path=None,
                rel_path=f"__CHAPTER_{chapter_index}__",
                display_name=item.chapter,
                chapter=item.chapter,
            ))
            last_chapter = item.chapter
        result.append(item)

    if end_text:
        result.append(MediaItem(kind="end", path=None, rel_path="__END__", display_name=end_text))
    return result


# =========================
# 图片 / 背景 / 水印
# =========================


def fix_image_orientation_cached(image_path: str, cache_dir: str) -> str:
    sig = file_signature(image_path)
    h = stable_hash({"type": "fixed_image", **sig})
    out_dir = os.path.join(cache_dir, "fixed_images")
    ensure_dir(out_dir)
    out = os.path.join(out_dir, f"{safe_filename(Path(image_path).stem)}_{h}.jpg")
    if os.path.exists(out):
        return out

    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (0, 0, 0))
        bg.paste(img, mask=img.split()[3])
        img = bg
    img.save(out, quality=95)
    return out


def create_blur_background_cached(image_path: str, resolution: Tuple[int, int], cache_dir: str, blur_radius: int = 32, darken: float = 0.30) -> str:
    sig = file_signature(image_path)
    h = stable_hash({
        "type": "blur_bg",
        "resolution": resolution,
        "blur_radius": blur_radius,
        "darken": darken,
        **sig,
    })
    out_dir = os.path.join(cache_dir, "blur_backgrounds")
    ensure_dir(out_dir)
    out = os.path.join(out_dir, f"{safe_filename(Path(image_path).stem)}_{h}.jpg")
    if os.path.exists(out):
        return out

    target_w, target_h = resolution
    img = Image.open(image_path).convert("RGB")
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    bg_w = max(1, int(src_w * scale))
    bg_h = max(1, int(src_h * scale))
    bg = img.resize((bg_w, bg_h), Image.LANCZOS)
    left = max(0, (bg_w - target_w) // 2)
    top = max(0, (bg_h - target_h) // 2)
    bg = bg.crop((left, top, left + target_w, top + target_h))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    dark = Image.new("RGB", bg.size, (0, 0, 0))
    bg = Image.blend(bg, dark, darken)
    bg.save(out, quality=92)
    return out


def create_watermark_image(text: str, resolution: Tuple[int, int], temp_dir: str) -> Optional[str]:
    if not text:
        return None
    w, h = resolution
    font_path = get_font_path()
    font_size = max(24, int(h * 0.035))
    font = ImageFont.truetype(font_path, font_size) if font_path else ImageFont.load_default()

    dummy = Image.new("RGBA", (10, 10), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dummy)
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    pad_x = int(font_size * 0.7)
    pad_y = int(font_size * 0.45)
    img = Image.new("RGBA", (text_w + pad_x * 2, text_h + pad_y * 2), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, img.width - 1, img.height - 1), radius=int(font_size * 0.5), fill=(0, 0, 0, 105))
    draw.text((pad_x + 2, pad_y + 2), text, font=font, fill=(0, 0, 0, 150))
    draw.text((pad_x, pad_y), text, font=font, fill=(255, 255, 255, 210))
    path = os.path.join(temp_dir, "_watermark.png")
    img.save(path)
    return path


def apply_watermark(clip, watermark_path: Optional[str], resolution: Tuple[int, int]):
    if not watermark_path:
        return clip
    w, h = resolution
    wm = ImageClip(watermark_path).set_duration(clip.duration)
    margin_x = int(w * 0.025)
    margin_y = int(h * 0.035)
    wm = wm.set_position((w - wm.w - margin_x, h - wm.h - margin_y))
    return CompositeVideoClip([clip, wm], size=resolution)


def create_text_card(
    text: str,
    resolution: Tuple[int, int],
    out_path: str,
    subtitle: Optional[str] = None,
    kind: str = "title",
    background_path: Optional[str] = None,
):
    w, h = resolution
    img = Image.new("RGB", (w, h), color=(9, 11, 18))
    draw = ImageDraw.Draw(img)

    # 简单暗色渐变背景
    for y in range(h):
        shade = int(9 + 28 * y / h)
        draw.line((0, y, w, y), fill=(shade, shade + 2, shade + 8))

    font_path = get_font_path()
    title_size = int(h * (0.078 if kind != "chapter" else 0.065))
    sub_size = int(h * 0.035)
    title_font = ImageFont.truetype(font_path, title_size) if font_path else ImageFont.load_default()
    sub_font = ImageFont.truetype(font_path, sub_size) if font_path else ImageFont.load_default()

    def split_lines(s: str, max_chars: int):
        lines, cur = [], ""
        for ch in s:
            cur += ch
            if len(cur) >= max_chars:
                lines.append(cur)
                cur = ""
        if cur:
            lines.append(cur)
        return lines

    max_chars = 24 if w > h else 14
    lines = split_lines(text, max_chars)
    elements = []
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=title_font)
        elements.append((line, title_font, bbox[2] - bbox[0], bbox[3] - bbox[1]))
    if subtitle:
        bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        elements.append((subtitle, sub_font, bbox[2] - bbox[0], bbox[3] - bbox[1]))

    gap = int(h * 0.035)
    total_h = sum(e[3] for e in elements) + gap * max(0, len(elements) - 1)
    y = (h - total_h) // 2
    for line, font, tw, th in elements:
        x = (w - tw) // 2
        draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += th + gap

    img.save(out_path, quality=95)


def split_text_lines(text: str, max_chars: int) -> List[str]:
    lines, cur = [], ""
    for ch in text:
        cur += ch
        if len(cur) >= max_chars:
            lines.append(cur)
            cur = ""
    if cur:
        lines.append(cur)
    return lines


def create_card_background(image_path: str, resolution: Tuple[int, int]) -> Image.Image:
    target_w, target_h = resolution
    img = Image.open(image_path).convert("RGB")
    src_w, src_h = img.size
    scale = max(target_w / src_w, target_h / src_h)
    bg_w = max(1, int(src_w * scale))
    bg_h = max(1, int(src_h * scale))
    bg = img.resize((bg_w, bg_h), Image.LANCZOS)
    left = max(0, (bg_w - target_w) // 2)
    top = max(0, (bg_h - target_h) // 2)
    bg = bg.crop((left, top, left + target_w, top + target_h))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=34))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), 0.48)
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle((0, int(target_h * 0.30), target_w, int(target_h * 0.70)), fill=(0, 0, 0, 78))
    return Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")


def create_structure_text_card(
    text: str,
    resolution: Tuple[int, int],
    out_path: str,
    subtitle: Optional[str] = None,
    kind: str = "title",
    background_path: Optional[str] = None,
):
    if not background_path or not os.path.exists(background_path):
        create_text_card(text, resolution, out_path, subtitle=subtitle, kind=kind)
        return

    w, h = resolution
    img = create_card_background(background_path, resolution)
    draw = ImageDraw.Draw(img)
    font_path = get_font_path()
    title_size = int(h * (0.078 if kind != "chapter" else 0.065))
    sub_size = int(h * 0.035)
    title_font = ImageFont.truetype(font_path, title_size) if font_path else ImageFont.load_default()
    sub_font = ImageFont.truetype(font_path, sub_size) if font_path else ImageFont.load_default()

    elements = []
    for line in split_text_lines(text, 24 if w > h else 14):
        bbox = draw.textbbox((0, 0), line, font=title_font)
        elements.append((line, title_font, bbox[2] - bbox[0], bbox[3] - bbox[1]))
    if subtitle:
        bbox = draw.textbbox((0, 0), subtitle, font=sub_font)
        elements.append((subtitle, sub_font, bbox[2] - bbox[0], bbox[3] - bbox[1]))

    gap = int(h * 0.035)
    total_h = sum(e[3] for e in elements) + gap * max(0, len(elements) - 1)
    y = (h - total_h) // 2
    for line, font, tw, th in elements:
        x = (w - tw) // 2
        draw.text((x + 4, y + 4), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += th + gap

    img.save(out_path, quality=95)


def extract_video_frame_cached(item: MediaItem, position: str, cache_dir: str) -> Optional[str]:
    if not item.path:
        return None

    frame_dir = os.path.join(cache_dir, "card_frames")
    ensure_dir(frame_dir)
    key = stable_hash({"type": "card_frame", "position": position, **file_signature(item.path)})
    out = os.path.join(frame_dir, f"{safe_filename(Path(item.path).stem)}_{position}_{key}.jpg")
    if os.path.exists(out):
        return out

    clip = VideoFileClip(item.path)
    try:
        t = 0 if position == "first" else max(0, float(clip.duration or 0) - 0.08)
        clip.save_frame(out, t=t)
        return out
        emit_event("result", ok=True, output_path=output_file, output_dir=output_dir, percent=100, phase="complete")

        emit_event("result", ok=True, output_path=output_file, output_dir=output_dir, percent=100, phase="complete")

    finally:
        clip.close()


def get_structure_card_background(media_items: List[MediaItem], position: str, cache_dir: str) -> Optional[str]:
    source_items = media_items if position == "first" else list(reversed(media_items))
    for item in source_items:
        if item.kind == "image" and item.path:
            return fix_image_orientation_cached(item.path, cache_dir)
        if item.kind == "video" and item.path:
            try:
                return extract_video_frame_cached(item, position, cache_dir)
            except Exception:
                continue
    return None


# =========================
# 时长估算 / 封面
# =========================


def analyze_image_for_duration(image_path: str, min_d: float, max_d: float) -> Tuple[float, str]:
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img).convert("RGB")
    w, h = img.size
    aspect = w / h

    # 基础时长：横屏风景更久，竖屏人像稍短，全景更久
    if aspect >= 2.0:
        base = 4.4
        reason = "panorama"
    elif aspect >= 1.25:
        base = 3.7
        reason = "landscape"
    elif aspect <= 0.78:
        base = 3.0
        reason = "portrait"
    else:
        base = 3.3
        reason = "square_or_balanced"

    # 亮度/复杂度微调
    small = img.resize((160, max(1, int(160 * h / w))))
    gray = np.asarray(small.convert("L"), dtype=np.float32)
    brightness = float(gray.mean())
    complexity = float(gray.std())
    if brightness < 60:
        base += 0.25
        reason += "+dark"
    if complexity > 58:
        base += 0.25
        reason += "+complex"

    # 微随机，避免机械感
    base += random.uniform(-0.18, 0.22)
    duration = max(min_d, min(max_d, base))
    return duration, reason


def create_cover_image(
    input_folder: str,
    media_items: List[MediaItem],
    resolution: Tuple[int, int],
    output_path: str,
    title: str,
    subtitle: str = "Lumix Travel",
):
    # 选第一张图片；没有图片就取第一个视频首帧
    temp_dir = tempfile.mkdtemp(prefix="cover_")
    try:
        src_img = None
        for item in media_items:
            if item.kind == "image" and item.path:
                src_img = fix_image_orientation_cached(item.path, temp_dir)
                break
        if src_img is None:
            for item in media_items:
                if item.kind == "video" and item.path:
                    clip = VideoFileClip(item.path)
                    frame = os.path.join(temp_dir, "video_cover.jpg")
                    clip.save_frame(frame, t=0)
                    clip.close()
                    src_img = frame
                    break

        if src_img is None:
            create_text_card(title, resolution, output_path, subtitle=subtitle)
            return

        bg_path = create_blur_background_cached(src_img, resolution, temp_dir, blur_radius=24, darken=0.45)
        w, h = resolution
        bg = Image.open(bg_path).convert("RGB")
        draw = ImageDraw.Draw(bg)
        font_path = get_font_path()
        title_font = ImageFont.truetype(font_path, int(h * 0.09)) if font_path else ImageFont.load_default()
        sub_font = ImageFont.truetype(font_path, int(h * 0.04)) if font_path else ImageFont.load_default()

        def center_text(y, text, font):
            bbox = draw.textbbox((0, 0), text, font=font)
            tw = bbox[2] - bbox[0]
            x = (w - tw) // 2
            draw.text((x + 5, y + 5), text, font=font, fill=(0, 0, 0))
            draw.text((x, y), text, font=font, fill=(255, 255, 255))

        center_text(int(h * 0.38), title, title_font)
        center_text(int(h * 0.53), subtitle, sub_font)
        bg.save(output_path, quality=94)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =========================
# 片段生成
# =========================


def make_cache_key(item: MediaItem, options: Dict[str, object]) -> str:
    data: Dict[str, object] = {"item": asdict(item), "options": options}
    if item.path and os.path.exists(item.path):
        data["source"] = file_signature(item.path)
    return stable_hash(data)


def create_photo_segment(item: MediaItem, output_path: str, options: Dict[str, object], temp_dir: str, watermark_path: Optional[str]):
    resolution = tuple(options["resolution"])
    duration = float(item.duration or options["default_image_duration"])
    fixed = fix_image_orientation_cached(item.path, options["cache_dir"])
    bg = create_blur_background_cached(fixed, resolution, options["cache_dir"], blur_radius=options["blur_radius"], darken=options["bg_darken"])

    target_w, target_h = resolution
    bg_clip = ImageClip(bg).set_duration(duration)
    fg_clip = ImageClip(fixed).set_duration(duration)
    scale = min(target_w / fg_clip.w, target_h / fg_clip.h)
    fg_clip = fg_clip.resize((int(fg_clip.w * scale), int(fg_clip.h * scale)))

    if options["ken_burns"]:
        def resize_func(t):
            return 1.0 + options["ken_burns_zoom"] * (t / duration)
        fg_clip = fg_clip.resize(resize_func)

    clip = CompositeVideoClip([bg_clip, fg_clip.set_position("center")], size=resolution)
    clip = apply_watermark(clip, watermark_path, resolution)
    clip = clip.set_audio(make_silent_audio(duration))
    write_clip(clip, output_path, fps=options["fps"], quality=options["quality"], with_audio=True)
    clip.close()


def create_video_segment(item: MediaItem, output_path: str, options: Dict[str, object], temp_dir: str, watermark_path: Optional[str]):
    resolution = tuple(options["resolution"])
    target_w, target_h = resolution
    raw = VideoFileClip(item.path)
    duration = raw.duration

    scale = min(target_w / raw.w, target_h / raw.h)
    resized = raw.resize((int(raw.w * scale), int(raw.h * scale)))

    if options["video_blur_bg"]:
        frame_dir = os.path.join(options["cache_dir"], "video_frames")
        ensure_dir(frame_dir)
        frame_key = make_cache_key(item, {"type": "video_frame", "resolution": resolution})
        frame_path = os.path.join(frame_dir, f"{safe_filename(Path(item.path).stem)}_{frame_key}.jpg")
        if not os.path.exists(frame_path):
            raw.save_frame(frame_path, t=0)
        bg_path = create_blur_background_cached(frame_path, resolution, options["cache_dir"], blur_radius=options["blur_radius"], darken=options["bg_darken"])
        bg = ImageClip(bg_path).set_duration(duration)
    else:
        bg = ColorClip(size=resolution, color=(0, 0, 0), duration=duration)

    clip = CompositeVideoClip([bg, resized.set_position("center")], size=resolution)
    clip = apply_watermark(clip, watermark_path, resolution)

    if options["mute_video_audio"] or raw.audio is None:
        clip = clip.set_audio(make_silent_audio(duration))
    else:
        clip = clip.set_audio(raw.audio)

    write_clip(clip, output_path, fps=options["fps"], quality=options["quality"], with_audio=True)
    raw.close()
    clip.close()


def create_card_segment(item: MediaItem, output_path: str, options: Dict[str, object], temp_dir: str, watermark_path: Optional[str]):
    resolution = tuple(options["resolution"])
    if item.kind == "title":
        duration = options["title_duration"]
        subtitle = options.get("title_subtitle") or "Travel Video"
        kind = "title"
        background_path = options.get("title_card_background")
    elif item.kind == "chapter":
        duration = options["chapter_duration"]
        subtitle = "Chapter"
        kind = "chapter"
        background_path = None
    else:
        duration = options["end_duration"]
        subtitle = None
        kind = "end"
        background_path = options.get("end_card_background")

    img_path = os.path.join(temp_dir, f"_{item.kind}_{make_cache_key(item, options)}.jpg")
    create_structure_text_card(item.display_name, resolution, img_path, subtitle=subtitle, kind=kind, background_path=background_path)
    clip = ImageClip(img_path).set_duration(float(duration))
    clip = apply_watermark(clip, watermark_path, resolution)
    clip = clip.set_audio(make_silent_audio(float(duration)))
    write_clip(clip, output_path, fps=options["fps"], quality=options["quality"], with_audio=True)
    clip.close()


def build_segments(items: List[MediaItem], options: Dict[str, object], temp_dir: str, watermark_path: Optional[str]) -> List[MediaItem]:
    seg_dir = os.path.join(options["cache_dir"], "segments")
    ensure_dir(seg_dir)

    built: List[MediaItem] = []
    for idx, item in enumerate(items, 1):
        # 标准化时长
        if item.kind == "image" and item.path:
            if options["smart_duration"]:
                duration, reason = analyze_image_for_duration(item.path, options["min_image_duration"], options["max_image_duration"])
                item.duration = duration
                item.status = f"duration:{reason}"
            elif options["no_random_duration"]:
                item.duration = options["fixed_image_duration"]
            else:
                item.duration = random.uniform(options["min_image_duration"], options["max_image_duration"])

        key = make_cache_key(item, {
            "ratio": options["ratio"],
            "resolution": options["resolution"],
            "fps": options["fps"],
            "quality": options["quality"],
            "kind": item.kind,
            "duration": item.duration,
            "ken_burns": options["ken_burns"],
            "ken_burns_zoom": options["ken_burns_zoom"],
            "video_blur_bg": options["video_blur_bg"],
            "mute_video_audio": options["mute_video_audio"],
            "watermark": options.get("watermark"),
            "bg_darken": options["bg_darken"],
            "blur_radius": options["blur_radius"],
            "title_card_background": options.get("title_card_background"),
            "end_card_background": options.get("end_card_background"),
        })
        seg_path = os.path.join(seg_dir, f"{idx:05d}_{safe_filename(item.display_name)}_{key}.mp4")
        item.cached_segment = seg_path

        if os.path.exists(seg_path) and not options["rebuild_cache"]:
            item.status = "cache_hit"
            emit_progress(idx, len(items), "segment", f"Cache hit: {item.display_name}", item_kind=item.kind, display_name=item.display_name)
            print(f"[{idx}/{len(items)}] 缓存命中: {item.display_name}")
            built.append(item)
            continue

        print(f"[{idx}/{len(items)}] 生成片段: {item.kind} | {item.display_name}")
        try:
            emit_progress(idx, len(items), "segment", f"Rendering segment: {item.kind} | {item.display_name}", item_kind=item.kind, display_name=item.display_name)
            if item.kind == "image":
                create_photo_segment(item, seg_path, options, temp_dir, watermark_path)
            elif item.kind == "video":
                create_video_segment(item, seg_path, options, temp_dir, watermark_path)
                # 记录真实视频时长
                try:
                    raw = VideoFileClip(item.path)
                    item.duration = raw.duration
                    raw.close()
                except Exception:
                    pass
            else:
                create_card_segment(item, seg_path, options, temp_dir, watermark_path)
                if item.kind == "title":
                    item.duration = options["title_duration"]
                elif item.kind == "chapter":
                    item.duration = options["chapter_duration"]
                else:
                    item.duration = options["end_duration"]

            item.status = "built"
            built.append(item)
        except Exception as exc:
            item.status = "failed"
            item.error = str(exc)
            emit_event("error", message=str(exc), phase="segment", item_kind=item.kind, display_name=item.display_name)
            print(f"[跳过] {item.display_name}，原因: {exc}")
    return built


# =========================
# 最终合成
# =========================


def concat_with_ffmpeg(segments: List[str], output_file: str):
    list_file = os.path.join(tempfile.mkdtemp(prefix="ffmpeg_concat_"), "concat.txt")
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for seg in segments:
                # ffmpeg concat file list prefers forward slashes / escaped single quotes
                safe = os.path.abspath(seg).replace("\\", "/").replace("'", "'\\''")
                f.write(f"file '{safe}'\n")
        cmd = [
            get_ffmpeg_exe(),
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            "-movflags", "+faststart",
            output_file,
        ]
        subprocess.run(cmd, check=True)
    finally:
        shutil.rmtree(os.path.dirname(list_file), ignore_errors=True)


def concat_with_moviepy_crossfade(segments: List[str], output_file: str, transition: float, fps: int, quality: str):
    clips = []
    try:
        for seg in segments:
            clips.append(VideoFileClip(seg))
        if len(clips) == 1:
            final = clips[0]
        else:
            processed = []
            for i, clip in enumerate(clips):
                if i == 0:
                    processed.append(clip)
                else:
                    processed.append(clip.crossfadein(transition))
            final = concatenate_videoclips(processed, method="compose", padding=-transition)
        write_clip(final, output_file, fps=fps, quality=quality, with_audio=True)
        if len(clips) > 1:
            final.close()
    finally:
        for c in clips:
            try:
                c.close()
            except Exception:
                pass


def choose_engine(engine: str, segment_count: int) -> str:
    if engine != "auto":
        return engine
    # 素材多时用 ffmpeg concat，速度优先；素材少时用 moviepy crossfade，效果优先
    return "ffmpeg_concat" if segment_count > 180 else "moviepy_crossfade"


# =========================
# 报告
# =========================


def write_report(report_path: str, options: Dict[str, object], all_items: List[MediaItem], built_items: List[MediaItem], output_file: str, started_at: float):
    elapsed = time.time() - started_at
    total_duration = sum(float(i.duration or 0.0) for i in built_items)
    file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("B站视频生成报告\n")
        f.write("=" * 80 + "\n")
        f.write(f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"输入目录: {options['input_folder']}\n")
        f.write(f"输出文件: {output_file}\n")
        f.write(f"输出比例: {options['ratio']}\n")
        f.write(f"分辨率: {options['resolution'][0]}x{options['resolution'][1]}\n")
        f.write(f"fps: {options['fps']}\n")
        f.write(f"quality: {options['quality']}\n")
        f.write(f"engine: {options['final_engine']}\n")
        f.write(f"素材数量: {len(all_items)}\n")
        f.write(f"成功片段: {len(built_items)}\n")
        f.write(f"预计/实际片段总时长: {total_duration:.2f} 秒 / {total_duration/60:.2f} 分钟\n")
        f.write(f"输出文件大小: {file_size/1024/1024:.2f} MB\n")
        f.write(f"耗时: {elapsed:.1f} 秒\n")
        f.write("\n素材明细:\n")
        for i, item in enumerate(all_items, 1):
            f.write(
                f"{i:04d}. [{item.kind}] {item.rel_path} | "
                f"duration={item.duration} | status={item.status} | error={item.error}\n"
            )


# =========================
# 主流程
# =========================


def run(args):
    started_at = time.time()
    input_folder = args.input_folder.rstrip("\\/")
    output_dir = args.output_dir
    ensure_dir(output_dir)

    resolution = get_resolution(args.ratio)
    cache_dir = args.cache_dir or os.path.join(input_folder, ".cache_bilibili_video")
    ensure_dir(cache_dir)

    raw_media = collect_media_files(input_folder, recursive=args.recursive)
    structured_items = inject_structure_cards(
        raw_media,
        title_text=args.title,
        end_text=args.end,
        chapters_from_dirs=args.chapters_from_dirs,
    )

    image_count = sum(1 for i in raw_media if i.kind == "image")
    video_count = sum(1 for i in raw_media if i.kind == "video")
    emit_phase(
        "scan",
        "Media scan complete",
        percent=5,
        input_folder=input_folder,
        output_dir=output_dir,
        image_count=image_count,
        video_count=video_count,
        item_count=len(structured_items),
    )

    print("=" * 90)
    print("B站横屏视频生成器 V3")
    print("=" * 90)
    print(f"输入目录: {input_folder}")
    print(f"递归读取: {args.recursive}")
    print(f"输出目录: {output_dir}")
    print(f"输出名称: {args.output_name}_{args.ratio.replace(':', 'x')}.mp4")
    print(f"分辨率: {resolution[0]}x{resolution[1]}")
    print(f"图片数量: {image_count}")
    print(f"视频数量: {video_count}")
    print(f"结构片段总数: {len(structured_items)}")
    print(f"缓存目录: {cache_dir}")
    print(f"合成引擎: {args.engine}")
    print("=" * 90)

    print("素材预览:")
    for item in structured_items:
        emit_event("media", item_kind=item.kind, rel_path=item.rel_path, display_name=item.display_name)

    if args.dry_run:
        emit_phase("complete", "素材预检完成", percent=100)
        time.sleep(0.5)  # 确保缓冲区数据被读走
        print("\ndry-run 模式：只预检，不生成视频。")
        return

    options = {
        "input_folder": input_folder,
        "cache_dir": cache_dir,
        "ratio": args.ratio,
        "resolution": resolution,
        "fps": args.fps,
        "quality": args.quality,
        "smart_duration": args.smart_duration,
        "min_image_duration": args.min_image_duration,
        "max_image_duration": args.max_image_duration,
        "fixed_image_duration": args.image_duration,
        "default_image_duration": args.image_duration,
        "no_random_duration": args.no_random_duration,
        "ken_burns": not args.no_ken_burns,
        "ken_burns_zoom": args.ken_burns_zoom,
        "video_blur_bg": not args.no_video_blur_bg,
        "mute_video_audio": args.mute,
        "watermark": args.watermark,
        "title_duration": args.title_duration,
        "chapter_duration": args.chapter_duration,
        "end_duration": args.end_duration,
        "title_subtitle": args.title_subtitle,
        "blur_radius": args.blur_radius,
        "bg_darken": args.bg_darken,
        "rebuild_cache": args.rebuild_cache,
        "final_engine": None,
    }

    options["title_card_background"] = get_structure_card_background(raw_media, "first", cache_dir)
    options["end_card_background"] = get_structure_card_background(raw_media, "last", cache_dir)

    temp_dir = tempfile.mkdtemp(prefix="bilibili_video_v3_")
    try:
        watermark_path = create_watermark_image(args.watermark, resolution, temp_dir) if args.watermark else None

        emit_phase("segment", "Building video segments", percent=10, item_count=len(structured_items))
        built_items = build_segments(structured_items, options, temp_dir, watermark_path)
        if not built_items:
            emit_event("error", message="No video segments were generated", phase="segment")
            print("没有成功生成任何片段，终止。")
            return

        estimated_duration = sum(float(i.duration or 0.0) for i in built_items)
        if args.max_seconds is not None and estimated_duration > args.max_seconds:
            emit_event("error", message=f"Estimated duration {estimated_duration:.1f}s exceeds limit {args.max_seconds:.1f}s", phase="segment")
            print(f"预计片段总时长 {estimated_duration:.1f}s 超过限制 {args.max_seconds:.1f}s，终止。")
            return

        output_file = os.path.join(output_dir, f"{args.output_name}_{args.ratio.replace(':', 'x')}.mp4")
        final_engine = choose_engine(args.engine, len(built_items))
        options["final_engine"] = final_engine

        print("=" * 90)
        print(f"开始最终合成，engine={final_engine}")
        print("=" * 90)
        emit_phase("render", f"Final render started: {final_engine}", percent=92, engine=final_engine)
        segments = [i.cached_segment for i in built_items if i.cached_segment and os.path.exists(i.cached_segment)]
        if final_engine == "ffmpeg_concat":
            concat_with_ffmpeg(segments, output_file)
        elif final_engine == "moviepy_crossfade":
            concat_with_moviepy_crossfade(segments, output_file, args.transition, args.fps, args.quality)
        else:
            raise ValueError(f"未知 engine: {final_engine}")

        if args.cover:
            emit_phase("cover", "Generating cover", percent=95)
            cover_title = args.cover_title or args.title or args.output_name
            cover_path = os.path.join(output_dir, f"cover_{args.output_name}.jpg")
            create_cover_image(input_folder, raw_media, resolution, cover_path, cover_title, subtitle=args.cover_subtitle)
            print(f"封面已生成: {cover_path}")

        if args.report:
            emit_phase("report", "Writing build report", percent=98)
            report_path = os.path.join(output_dir, f"build_report_{args.output_name}.txt")
            write_report(report_path, options, structured_items, built_items, output_file, started_at)
            print(f"报告已生成: {report_path}")

        print("=" * 90)
        print(f"视频生成完成: {output_file}")
        print("=" * 90)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="B站/YouTube 横屏旅行视频生成器 V3")

    parser.add_argument("--input_folder", required=True, help="素材目录")
    parser.add_argument("--output_dir", default=".", help="输出目录，默认当前目录")
    parser.add_argument("--output_name", default="bilibili_travel_video", help="输出文件名前缀")
    parser.add_argument("--cache_dir", default=None, help="缓存目录，默认在素材目录下 .cache_bilibili_video")

    parser.add_argument("--ratio", default="16:9", choices=["16:9", "9:16", "1:1"], help="输出比例，B站建议 16:9")
    parser.add_argument("--fps", type=int, default=30, help="输出帧率，建议 30；运动视频可用 60")
    parser.add_argument("--quality", default="high", choices=["normal", "high", "ultra"], help="画质等级")
    parser.add_argument("--engine", default="auto", choices=["auto", "moviepy_crossfade", "ffmpeg_concat"], help="最终合成引擎")

    parser.add_argument("--recursive", action="store_true", help="递归读取子目录素材")
    parser.add_argument("--chapters_from_dirs", action="store_true", help="递归模式下按子目录生成章节标题卡")

    parser.add_argument("--title", default=None, help="片头文字")
    parser.add_argument("--title_subtitle", default="Travel Video", help="片头副标题")
    parser.add_argument("--end", default=None, help="片尾文字")
    parser.add_argument("--title_duration", type=float, default=2.2, help="片头时长")
    parser.add_argument("--chapter_duration", type=float, default=1.8, help="章节卡时长")
    parser.add_argument("--end_duration", type=float, default=2.2, help="片尾时长")

    parser.add_argument("--smart_duration", action="store_true", default=True, help="启用智能照片时长，默认启用")
    parser.add_argument("--no_smart_duration", dest="smart_duration", action="store_false", help="关闭智能照片时长")
    parser.add_argument("--min_image_duration", type=float, default=2.6, help="照片最短展示时长")
    parser.add_argument("--max_image_duration", type=float, default=4.8, help="照片最长展示时长")
    parser.add_argument("--image_duration", type=float, default=3.2, help="固定照片时长，关闭随机/智能时使用")
    parser.add_argument("--no_random_duration", action="store_true", help="关闭随机时长，使用 --image_duration")

    parser.add_argument("--transition", type=float, default=0.45, help="moviepy_crossfade 引擎下的交叉淡化时长")
    parser.add_argument("--no_ken_burns", action="store_true", help="关闭照片轻微缩放动画")
    parser.add_argument("--ken_burns_zoom", type=float, default=0.012, help="照片轻微缩放强度")
    parser.add_argument("--blur_radius", type=int, default=32, help="模糊背景强度")
    parser.add_argument("--bg_darken", type=float, default=0.30, help="模糊背景变暗比例，0~1")

    parser.add_argument("--watermark", default=None, help="右下角水印文字，例如 PangBo Travel")
    parser.add_argument("--mute", action="store_true", help="静音原视频声音；默认保留原声")
    parser.add_argument("--no_video_blur_bg", action="store_true", help="竖屏视频不使用模糊背景，改用黑底")

    parser.add_argument("--cover", action="store_true", help="生成 B站封面图")
    parser.add_argument("--cover_title", default=None, help="封面标题，不填则用 --title 或 --output_name")
    parser.add_argument("--cover_subtitle", default="Lumix Travel", help="封面副标题")

    parser.add_argument("--report", action="store_true", default=True, help="生成构建报告，默认启用")
    parser.add_argument("--no_report", dest="report", action="store_false", help="关闭构建报告")
    parser.add_argument("--dry_run", action="store_true", help="只预检素材，不生成视频")
    parser.add_argument("--max_seconds", type=float, default=None, help="限制最大时长，超过则停止")
    parser.add_argument("--rebuild_cache", action="store_true", help="强制重建缓存")

    try:
        run(parser.parse_args())
    except Exception as exc:
        emit_event("error", message=str(exc), phase="fatal")
        raise
