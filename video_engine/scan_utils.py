from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import IGNORED_FILES
from .models import StorySection

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


def natural_sort_key(value: str) -> List[Any]:
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", value)]


def is_ignored_file(path: Path) -> bool:
    lower = path.name.lower()
    if lower in IGNORED_FILES:
        return True
    if lower.endswith("鍓湰.jpg") or lower.endswith("鍓湰.jpeg"):
        return True
    return False


def orientation_from_size(size: Iterable[int]) -> str:
    w, h = list(size)[:2]
    if w > h:
        return "landscape"
    if h > w:
        return "portrait"
    return "square"


def section_to_dict(section: StorySection) -> Dict[str, Any]:
    data = asdict(section)
    data["asset_refs"] = [asdict(ref) for ref in section.asset_refs]
    data["children"] = [section_to_dict(child) for child in section.children]
    return data
