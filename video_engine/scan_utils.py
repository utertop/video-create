from __future__ import annotations

import re
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .constants import IGNORED_FILES
from .models import StorySection


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
