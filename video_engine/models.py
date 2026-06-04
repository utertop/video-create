from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
