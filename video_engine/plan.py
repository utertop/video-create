from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .audio import audio_asset_duration_seconds, auto_music_score, select_auto_music_assets
from .cache import safe_id
from .constants import SCHEMA_VERSION
from .models import AssetRef, StorySection, TitleStyle
from .scan_utils import orientation_from_size, section_to_dict

_emit_event: Callable[..., None] = lambda _event_type, **_payload: None


def set_plan_event_emitter(callback: Callable[..., None]) -> None:
    global _emit_event
    _emit_event = callback


def emit_event(event_type: str, **payload: Any) -> None:
    _emit_event(event_type, **payload)


def _merge_style_dict(base: Optional[Dict[str, Any]], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged: Dict[str, Any] = dict(base or {})
    for key, value in dict(override or {}).items():
        if value is not None:
            merged[key] = value
    return merged


TEMPLATE_MATCHING_PROFILES: List[Dict[str, Any]] = [
    {
        "template_id": "travel_postcard",
        "display_name": "旅行明信片",
        "category": "travel",
        "description": "适合城市、日期、景点层级清晰的旅拍内容，强调章节分段与柔和流动感。",
        "render_defaults": {
            "edit_strategy": "travel_soft",
            "transition_profile": "travel_postcard",
            "rhythm_profile": "travel_story",
            "performance_mode": "balanced",
            "chapter_background_mode": "auto_bridge",
            "scenic_spot_title_mode": "overlay",
            "single_section_chapter_card": "auto",
            "image_motion_profile": "travel_gentle",
            "title_style": {"preset": "travel_postcard", "motion": "postcard_drift", "position": "center"},
            "end_title_style": {"preset": "travel_postcard", "motion": "postcard_drift", "position": "center"},
            "overlay_title_style": {"preset": "travel_postcard", "motion": "postcard_drift", "position": "lower_left"},
            "chapter_title_style_defaults": {"motion": "postcard_drift"},
        },
    },
    {
        "template_id": "food_shop_review",
        "display_name": "探店节奏剪辑",
        "category": "food",
        "description": "适合探店、美食、夜市等高频短段落素材，强调节奏感和重点信息露出。",
        "render_defaults": {
            "edit_strategy": "beat_cut",
            "transition_profile": "food_review",
            "rhythm_profile": "fast_discovery",
            "performance_mode": "balanced",
            "chapter_background_mode": "auto_bridge",
            "scenic_spot_title_mode": "overlay",
            "single_section_chapter_card": "auto",
            "image_motion_profile": "dynamic_punch",
            "title_style": {"preset": "impact_flash", "motion": "impact_slam", "position": "center"},
            "end_title_style": {"preset": "impact_flash", "motion": "impact_slam", "position": "center"},
            "overlay_title_style": {"preset": "minimal_editorial", "motion": "editorial_fade", "position": "lower_left"},
            "chapter_title_style_defaults": {"motion": "impact_slam"},
        },
    },
    {
        "template_id": "daily_vlog",
        "display_name": "日常 Vlog",
        "category": "vlog",
        "description": "适合轻记录、生活碎片、混合图视频材，保持自然流动而不过度造型。",
        "render_defaults": {
            "edit_strategy": "smart_director",
            "transition_profile": "daily_vlog",
            "rhythm_profile": "casual_flow",
            "performance_mode": "balanced",
            "chapter_background_mode": "auto_bridge",
            "scenic_spot_title_mode": "overlay",
            "single_section_chapter_card": "auto",
            "image_motion_profile": "casual_story",
            "title_style": {"preset": "playful_pop", "motion": "playful_bounce", "position": "center"},
            "end_title_style": {"preset": "playful_pop", "motion": "playful_bounce", "position": "center"},
            "overlay_title_style": {"preset": "minimal_editorial", "motion": "editorial_fade", "position": "lower_left"},
            "chapter_title_style_defaults": {"motion": "editorial_fade"},
        },
    },
    {
        "template_id": "product_showcase",
        "display_name": "产品展示",
        "category": "product",
        "description": "适合开箱、测评、教程、功能展示等信息型内容，偏克制与清晰。",
        "render_defaults": {
            "edit_strategy": "documentary",
            "transition_profile": "product_showcase",
            "rhythm_profile": "feature_focus",
            "performance_mode": "quality",
            "chapter_background_mode": "auto_bridge",
            "scenic_spot_title_mode": "full_card",
            "single_section_chapter_card": "auto",
            "image_motion_profile": "product_focus",
            "title_style": {"preset": "documentary_lower_third", "motion": "lower_third_slide", "position": "center"},
            "end_title_style": {"preset": "documentary_lower_third", "motion": "lower_third_slide", "position": "center"},
            "overlay_title_style": {"preset": "documentary_lower_third", "motion": "lower_third_slide", "position": "lower_left"},
            "chapter_title_style_defaults": {"motion": "lower_third_slide"},
        },
    },
    {
        "template_id": "photo_story",
        "display_name": "图文纪实",
        "category": "photo",
        "description": "适合图片为主、叙事感更强的长内容，强调稳定阅读与低干扰过渡。",
        "render_defaults": {
            "edit_strategy": "long_stable",
            "transition_profile": "photo_story",
            "rhythm_profile": "steady_story",
            "performance_mode": "stable",
            "chapter_background_mode": "auto_bridge",
            "scenic_spot_title_mode": "overlay",
            "single_section_chapter_card": "auto",
            "image_motion_profile": "photo_story",
            "title_style": {"preset": "documentary_lower_third", "motion": "static_hold", "position": "center"},
            "end_title_style": {"preset": "documentary_lower_third", "motion": "static_hold", "position": "center"},
            "overlay_title_style": {"preset": "documentary_lower_third", "motion": "static_hold", "position": "lower_left"},
            "chapter_title_style_defaults": {"motion": "static_hold"},
        },
    },
]

TEMPLATE_MATCHING_PROFILE_BY_ID: Dict[str, Dict[str, Any]] = {
    item["template_id"]: item for item in TEMPLATE_MATCHING_PROFILES
}

AUDIO_BLUEPRINT_TEMPLATE_PROFILES: Dict[str, Dict[str, Any]] = {
    "travel_postcard": {
        "music_profile": "travel_light",
        "energy_curve_style": "lifted_journey",
        "music_fit_strategy": "intro_loop_outro",
        "bgm_volume": 0.26,
        "source_audio_volume": 1.0,
        "keep_source_audio": True,
        "auto_ducking": True,
        "duck_bgm_volume": 0.14,
        "fade_in_seconds": 1.6,
        "fade_out_seconds": 3.2,
        "normalize_audio": True,
        "target_lufs": -16.0,
    },
    "food_shop_review": {
        "music_profile": "beat",
        "energy_curve_style": "fast_discovery",
        "music_fit_strategy": "auto",
        "bgm_volume": 0.22,
        "source_audio_volume": 1.0,
        "keep_source_audio": True,
        "auto_ducking": True,
        "duck_bgm_volume": 0.13,
        "fade_in_seconds": 0.8,
        "fade_out_seconds": 1.6,
        "normalize_audio": True,
        "target_lufs": -16.0,
    },
    "daily_vlog": {
        "music_profile": "lifestyle",
        "energy_curve_style": "casual_flow",
        "music_fit_strategy": "auto",
        "bgm_volume": 0.25,
        "source_audio_volume": 1.0,
        "keep_source_audio": True,
        "auto_ducking": True,
        "duck_bgm_volume": 0.15,
        "fade_in_seconds": 1.0,
        "fade_out_seconds": 2.2,
        "normalize_audio": True,
        "target_lufs": -16.0,
    },
    "product_showcase": {
        "music_profile": "calm_documentary",
        "energy_curve_style": "feature_focus",
        "music_fit_strategy": "trim",
        "bgm_volume": 0.2,
        "source_audio_volume": 0.98,
        "keep_source_audio": True,
        "auto_ducking": True,
        "duck_bgm_volume": 0.12,
        "fade_in_seconds": 0.8,
        "fade_out_seconds": 1.8,
        "normalize_audio": True,
        "target_lufs": -15.0,
    },
    "photo_story": {
        "music_profile": "calm_documentary",
        "energy_curve_style": "steady_story",
        "music_fit_strategy": "intro_loop_outro",
        "bgm_volume": 0.23,
        "source_audio_volume": 1.0,
        "keep_source_audio": True,
        "auto_ducking": True,
        "duck_bgm_volume": 0.14,
        "fade_in_seconds": 1.8,
        "fade_out_seconds": 3.6,
        "normalize_audio": True,
        "target_lufs": -16.0,
    },
    "default": {
        "music_profile": "lifestyle",
        "energy_curve_style": "balanced_story",
        "music_fit_strategy": "auto",
        "bgm_volume": 0.24,
        "source_audio_volume": 1.0,
        "keep_source_audio": True,
        "auto_ducking": True,
        "duck_bgm_volume": 0.15,
        "fade_in_seconds": 1.2,
        "fade_out_seconds": 2.4,
        "normalize_audio": True,
        "target_lufs": -16.0,
    },
}

class Planner:
    def __init__(self, library: Dict[str, Any]):
        self.library = library
        self.nodes = {n["node_id"]: n for n in library.get("directory_nodes", [])}
        self.assets = library.get("assets", [])

    def plan(
        self,
        strategy: str = "city_date_spot",
        template_mode: str = "auto",
        top_n_templates: int = 3,
        music_blueprint_mode: str = "recommend",
    ) -> Dict[str, Any]:
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

        template_matching = self._recommend_templates(template_mode=template_mode, top_n=top_n_templates)
        self._apply_template_defaults_to_sections(sections, template_matching.get("applied_render_defaults") or {})
        audio_blueprint = self._build_audio_blueprint(
            sections=sections,
            template_matching=template_matching,
            mode=music_blueprint_mode,
        )
        metadata: Dict[str, Any] = {
            "created_at": datetime.now().isoformat(),
            "template_matching": template_matching,
            "audio_blueprint": audio_blueprint,
        }
        metadata.update(template_matching.get("applied_render_defaults") or {})
        if audio_blueprint.get("mode") == "apply" and not isinstance(metadata.get("audio"), dict):
            metadata["audio"] = dict(audio_blueprint.get("recommended_audio_settings") or {})

        emit_event("phase", phase="plan", message="故事蓝图完成", percent=100)
        return {
            "schema_version": SCHEMA_VERSION,
            "document_type": "story_blueprint",
            "title": self.library.get("project", {}).get("project_title") or "My Travel Vlog",
            "subtitle": "",
            "strategy": strategy,
            "sections": [section_to_dict(s) for s in sections],
            "metadata": metadata,
        }

    def _recommend_templates(self, template_mode: str = "auto", top_n: int = 3) -> Dict[str, Any]:
        mode = str(template_mode or "auto").strip().lower()
        context = self._build_template_matching_context()
        recommendations = [self._score_template(profile, context) for profile in TEMPLATE_MATCHING_PROFILES]
        recommendations.sort(key=lambda item: (-float(item.get("score") or 0.0), str(item.get("template_id") or "")))
        recommendations = recommendations[: max(int(top_n or 3), 1)]

        selected_source = "auto"
        selected_template: Optional[Dict[str, Any]] = recommendations[0] if recommendations else None
        if mode in {"off", "none", "disabled"}:
            selected_source = "disabled"
            selected_template = None
        elif mode not in {"", "auto", "default"}:
            forced = TEMPLATE_MATCHING_PROFILE_BY_ID.get(mode)
            if not forced:
                raise ValueError(f"未知模板 ID: {template_mode}")
            selected_source = "manual"
            selected_template = self._score_template(forced, context)
            if not any(item.get("template_id") == mode for item in recommendations):
                recommendations = [selected_template] + recommendations[: max(len(recommendations) - 1, 0)]

        applied_render_defaults = dict((selected_template or {}).get("render_defaults") or {})
        return {
            "mode": mode or "auto",
            "selected_source": selected_source,
            "selected_template_id": selected_template.get("template_id") if selected_template else None,
            "selected_template": selected_template,
            "recommendations": recommendations,
            "context": context,
            "applied_render_defaults": applied_render_defaults,
        }

    def _apply_template_defaults_to_sections(
        self,
        sections: List[StorySection],
        applied_render_defaults: Dict[str, Any],
    ) -> None:
        chapter_defaults = dict(applied_render_defaults.get("chapter_title_style_defaults") or {})
        overlay_defaults = dict(applied_render_defaults.get("overlay_title_style") or {})
        if not chapter_defaults and not overlay_defaults:
            return

        def visit(section: StorySection) -> None:
            section_style = asdict(section.title_style) if isinstance(section.title_style, TitleStyle) else dict(section.title_style or {})
            merged = section_style
            if section.section_type in {"city", "date", "chapter"} and chapter_defaults:
                merged = _merge_style_dict(chapter_defaults, merged)
            elif section.section_type == "scenic_spot" and overlay_defaults:
                merged = _merge_style_dict(overlay_defaults, merged)
            if merged:
                section.title_style = TitleStyle(**merged)
            for child in section.children:
                visit(child)

        for section in sections:
            visit(section)

    def _build_template_matching_context(self) -> Dict[str, Any]:
        summary = self.library.get("summary") or {}
        profile = dict(summary.get("content_profile") or {})
        visual_assets = [a for a in self.assets if a.get("type") in {"image", "video"}]
        visual_count = int(profile.get("visual_asset_count") or len(visual_assets))
        image_count = int(profile.get("image_count") or sum(1 for a in self.assets if a.get("type") == "image"))
        video_count = int(profile.get("video_count") or sum(1 for a in self.assets if a.get("type") == "video"))
        audio_count = int(profile.get("audio_count") or sum(1 for a in self.assets if a.get("type") == "audio"))

        if "image_ratio" in profile:
            image_ratio = float(profile.get("image_ratio") or 0.0)
        else:
            image_ratio = (image_count / visual_count) if visual_count else 0.0
        if "video_ratio" in profile:
            video_ratio = float(profile.get("video_ratio") or 0.0)
        else:
            video_ratio = (video_count / visual_count) if visual_count else 0.0

        orientation_counts: Counter[str] = Counter()
        for asset in visual_assets:
            media = asset.get("media") or {}
            width = int(media.get("width") or 0)
            height = int(media.get("height") or 0)
            if width > 0 and height > 0:
                orientation_counts[orientation_from_size((width, height))] += 1

        portrait_ratio = float(profile.get("portrait_ratio") or ((orientation_counts.get("portrait", 0) / visual_count) if visual_count else 0.0))
        landscape_ratio = float(profile.get("landscape_ratio") or ((orientation_counts.get("landscape", 0) / visual_count) if visual_count else 0.0))
        square_ratio = float(profile.get("square_ratio") or ((orientation_counts.get("square", 0) / visual_count) if visual_count else 0.0))

        keyword_counts: Counter[str] = Counter()
        for node in self.nodes.values():
            signals = node.get("signals") or {}
            for keyword in signals.get("matched_theme_keywords") or []:
                keyword_counts[str(keyword)] += 2
            for keyword in signals.get("matched_event_keywords") or []:
                keyword_counts[str(keyword)] += 2

        video_durations = [
            float((asset.get("media") or {}).get("duration_seconds") or 0.0)
            for asset in self.assets
            if asset.get("type") == "video" and float((asset.get("media") or {}).get("duration_seconds") or 0.0) > 0.0
        ]
        node_type_counts: Counter[str] = Counter(str(node.get("detected_type") or "unknown") for node in self.nodes.values())

        dominant_media_type = str(profile.get("dominant_media_type") or "")
        if not dominant_media_type:
            dominant_media_type = "mixed"
            if visual_count == 0:
                dominant_media_type = "unknown"
            elif image_ratio >= 0.72:
                dominant_media_type = "image"
            elif video_ratio >= 0.72:
                dominant_media_type = "video"

        estimated_project_duration = self._estimate_project_duration_seconds()

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
            "mixed_media": bool(profile.get("mixed_media")) or (visual_count > 0 and image_count > 0 and video_count > 0),
            "total_video_duration_seconds": round(sum(video_durations), 3),
            "avg_video_duration_seconds": round(sum(video_durations) / len(video_durations), 3) if video_durations else 0.0,
            "top_level_section_count": int(profile.get("top_level_section_count") or sum(1 for node in self.nodes.values() if int(node.get("depth") or 0) == 1)),
            "chapter_node_count": int(profile.get("chapter_node_count") or node_type_counts.get("chapter", 0)),
            "city_node_count": int(profile.get("city_node_count") or node_type_counts.get("city", 0)),
            "date_node_count": int(profile.get("date_node_count") or node_type_counts.get("date", 0)),
            "scenic_spot_node_count": int(profile.get("scenic_spot_node_count") or node_type_counts.get("scenic_spot", 0)),
            "estimated_project_duration_seconds": round(estimated_project_duration, 3),
            "top_keywords": [
                {"keyword": keyword, "count": int(count)}
                for keyword, count in keyword_counts.most_common(6)
            ],
            "keyword_counts": dict(keyword_counts),
        }

    def _estimate_project_duration_seconds(self) -> float:
        total = 0.0
        for asset in self.assets:
            if not isinstance(asset, dict):
                continue
            asset_type = str(asset.get("type") or "")
            if asset_type == "video":
                duration = float((asset.get("media") or {}).get("duration_seconds") or 0.0)
                total += min(max(duration, 0.0), 8.0) if duration > 0 else 4.0
            elif asset_type == "image":
                total += 3.8
        return max(total, 0.0)

    def _score_template(self, profile: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        template_id = str(profile.get("template_id") or "")
        keyword_counts = context.get("keyword_counts") or {}
        score = 5.0
        breakdown: List[Dict[str, Any]] = []

        def add(points: float, reason: str) -> None:
            nonlocal score
            if abs(points) < 0.001:
                return
            score += float(points)
            breakdown.append({"points": round(points, 2), "reason": reason})

        def add_keyword_score(weights: Dict[str, float], label: str) -> None:
            for keyword, weight in weights.items():
                count = int(keyword_counts.get(keyword) or 0)
                if count > 0:
                    add(weight * min(count, 2), f"{label}命中关键词「{keyword}」")

        image_ratio = float(context.get("image_ratio") or 0.0)
        video_ratio = float(context.get("video_ratio") or 0.0)
        portrait_ratio = float(context.get("portrait_ratio") or 0.0)
        square_ratio = float(context.get("square_ratio") or 0.0)
        mixed_media = bool(context.get("mixed_media"))
        top_level_sections = int(context.get("top_level_section_count") or 0)
        city_count = int(context.get("city_node_count") or 0)
        date_count = int(context.get("date_node_count") or 0)
        scenic_count = int(context.get("scenic_spot_node_count") or 0)
        video_count = int(context.get("video_count") or 0)
        avg_video_duration = float(context.get("avg_video_duration_seconds") or 0.0)

        if template_id == "travel_postcard":
            geo_score = min(18.0, city_count * 5.0 + date_count * 4.0 + scenic_count * 4.0)
            add(geo_score, "存在城市/日期/景点层级，适合旅行章节化结构")
            if image_ratio >= 0.55:
                add(6.0, "图片占比较高，适合明信片式旅拍呈现")
            if top_level_sections >= 2:
                add(3.5, "章节数量较完整，适合按旅程分段")
            add_keyword_score(
                {
                    "旅行": 3.0,
                    "旅拍": 3.0,
                    "风景": 2.4,
                    "古镇": 2.4,
                    "露营": 2.2,
                    "大海": 2.2,
                    "湖泊": 2.0,
                    "沙滩": 2.0,
                    "街拍": 1.6,
                    "探店": 1.4,
                    "美食": 1.0,
                },
                "旅行模板",
            )
        elif template_id == "food_shop_review":
            if mixed_media:
                add(4.5, "图视频混合更适合探店式节奏编排")
            if portrait_ratio >= 0.3:
                add(4.0, "竖构图占比较高，适合近景信息型探店内容")
            if top_level_sections <= 4:
                add(2.5, "章节不多，适合紧凑型探店剪辑")
            add_keyword_score(
                {
                    "美食": 3.2,
                    "探店": 3.0,
                    "咖啡": 2.6,
                    "夜市": 2.4,
                    "酒吧": 2.2,
                    "小吃": 2.2,
                    "派对": 1.4,
                },
                "探店模板",
            )
        elif template_id == "daily_vlog":
            if mixed_media:
                add(5.5, "图视频混合素材符合日常 Vlog 的松弛节奏")
            if portrait_ratio >= 0.35:
                add(4.5, "竖构图较多，贴近日常记录内容")
            if top_level_sections <= 4:
                add(3.0, "章节结构较轻，适合日常串联")
            add_keyword_score(
                {
                    "日常": 3.0,
                    "生活": 2.4,
                    "记录": 2.0,
                    "宠物": 1.8,
                    "学习": 1.6,
                    "办公": 1.4,
                },
                "Vlog 模板",
            )
        elif template_id == "product_showcase":
            if video_ratio >= 0.3:
                add(3.5, "视频素材占比不低，适合产品演示")
            if (portrait_ratio + square_ratio) >= 0.45:
                add(2.5, "竖图或方图较多，适合信息展示型版式")
            if top_level_sections <= 2:
                add(2.0, "章节较少，更适合围绕单个主题展开")
            add_keyword_score(
                {
                    "产品": 3.2,
                    "开箱": 3.2,
                    "测评": 3.0,
                    "展示": 2.5,
                    "功能": 2.0,
                    "教程": 1.8,
                    "科技": 2.4,
                    "办公": 1.5,
                    "会议": 1.5,
                },
                "产品模板",
            )
        elif template_id == "photo_story":
            if image_ratio >= 0.78:
                add(12.0, "图片占比很高，适合图文纪实模板")
            if video_count == 0:
                add(4.0, "没有视频素材，图文纪实更稳定")
            elif avg_video_duration <= 4.5:
                add(2.5, "视频较短，更适合作为图文纪实点缀")
            if top_level_sections >= 2:
                add(3.5, "章节较完整，适合按段落缓慢展开")
            add_keyword_score(
                {
                    "风景": 2.4,
                    "自然": 2.2,
                    "雪山": 2.2,
                    "森林": 2.0,
                    "大海": 2.0,
                    "湖泊": 1.8,
                    "沙滩": 1.8,
                    "露营": 1.8,
                },
                "图文纪实模板",
            )

        ordered_reasons = [item["reason"] for item in sorted(breakdown, key=lambda entry: (-float(entry["points"]), entry["reason"]))[:5]]
        return {
            "template_id": template_id,
            "display_name": profile.get("display_name"),
            "category": profile.get("category"),
            "description": profile.get("description"),
            "score": round(score, 2),
            "reasons": ordered_reasons,
            "score_breakdown": breakdown,
            "render_defaults": dict(profile.get("render_defaults") or {}),
        }

    def _flatten_sections(self, sections: List[StorySection]) -> List[StorySection]:
        ordered: List[StorySection] = []

        def visit(section: StorySection) -> None:
            ordered.append(section)
            for child in section.children:
                visit(child)

        for section in sections:
            visit(section)
        return ordered

    def _build_audio_blueprint(
        self,
        sections: List[StorySection],
        template_matching: Dict[str, Any],
        mode: str = "recommend",
    ) -> Dict[str, Any]:
        normalized_mode = str(mode or "recommend").strip().lower()
        if normalized_mode in {"off", "none", "disabled"}:
            normalized_mode = "off"
        elif normalized_mode == "auto":
            normalized_mode = "recommend"
        elif normalized_mode not in {"recommend", "apply"}:
            normalized_mode = "recommend"

        context = template_matching.get("context") or self._build_template_matching_context()
        selected_template_id = str(template_matching.get("selected_template_id") or "daily_vlog")
        profile = dict(
            AUDIO_BLUEPRINT_TEMPLATE_PROFILES.get(selected_template_id)
            or AUDIO_BLUEPRINT_TEMPLATE_PROFILES["default"]
        )

        candidates = select_auto_music_assets(
            self.assets,
            target_duration=float(context.get("total_video_duration_seconds") or 0.0),
        )
        candidate_entries: List[Dict[str, Any]] = []
        for asset in candidates[:3]:
            candidate_entries.append(
                {
                    "asset_id": asset.get("asset_id"),
                    "relative_path": asset.get("relative_path"),
                    "absolute_path": asset.get("absolute_path"),
                    "duration_seconds": round(audio_asset_duration_seconds(asset), 3),
                    "score": round(auto_music_score(asset), 2),
                }
            )

        selected_candidate = candidate_entries[0] if candidate_entries else None
        flattened_sections = self._flatten_sections(sections)
        section_cues: List[Dict[str, Any]] = []
        total_sections = len(flattened_sections)
        energy_curve_style = str(profile.get("energy_curve_style") or "balanced_story")
        estimated_duration = float(context.get("estimated_project_duration_seconds") or 0.0)
        image_ratio = float(context.get("image_ratio") or 0.0)
        video_ratio = float(context.get("video_ratio") or 0.0)
        avg_video_duration = float(context.get("avg_video_duration_seconds") or 0.0)
        longform_project = estimated_duration >= 420.0
        chapter_restart = False

        if longform_project and image_ratio >= 0.7 and total_sections >= 3:
            profile["music_playlist_mode"] = "chapter_restart"
            profile["music_fit_strategy"] = "intro_loop_outro"
            profile["fade_out_seconds"] = max(float(profile.get("fade_out_seconds") or 0.0), 3.2)
            chapter_restart = True
        elif len(candidate_entries) > 1 and estimated_duration >= 240.0:
            profile["music_playlist_mode"] = "auto_playlist"
        else:
            profile["music_playlist_mode"] = profile.get("music_playlist_mode") or ("auto_playlist" if len(candidate_entries) > 1 else "single")

        if image_ratio >= 0.82:
            profile["music_fit_strategy"] = "intro_loop_outro"
            profile["bgm_volume"] = min(0.32, float(profile.get("bgm_volume") or 0.24) + 0.02)
        elif video_ratio >= 0.65 and avg_video_duration >= 7.0:
            profile["music_fit_strategy"] = "trim"
            profile["bgm_volume"] = max(0.16, float(profile.get("bgm_volume") or 0.24) - 0.02)
            profile["duck_bgm_volume"] = max(0.1, min(float(profile.get("duck_bgm_volume") or 0.15), 0.14))

        for index, section in enumerate(flattened_sections):
            phase = "sustain"
            if total_sections <= 1:
                phase = "single_arc"
            elif index == 0:
                phase = "intro"
            elif index == total_sections - 1:
                phase = "outro"
            elif total_sections >= 3 and index == total_sections // 2:
                phase = "peak"

            energy = "medium"
            if energy_curve_style in {"fast_discovery"}:
                energy = {"intro": "medium", "peak": "high", "outro": "medium", "single_arc": "medium_high"}.get(phase, "high")
            elif energy_curve_style in {"steady_story"}:
                energy = {"intro": "low", "peak": "medium", "outro": "low", "single_arc": "low_medium"}.get(phase, "medium")
            elif energy_curve_style in {"lifted_journey"}:
                energy = {"intro": "low_medium", "peak": "medium_high", "outro": "low", "single_arc": "medium"}.get(phase, "medium")
            elif energy_curve_style in {"feature_focus"}:
                energy = {"intro": "low", "peak": "medium", "outro": "low", "single_arc": "medium"}.get(phase, "medium")
            else:
                energy = {"intro": "low_medium", "peak": "medium_high", "outro": "low", "single_arc": "medium"}.get(phase, "medium")

            cue_reason = "保持整体叙事连贯"
            if section.section_type in {"city", "date"}:
                cue_reason = "章节切换适合轻微音乐起伏"
            elif section.section_type == "scenic_spot":
                cue_reason = "景点/主体内容适合承接主旋律"
            if phase == "peak":
                cue_reason = "中段重点内容适合提升能量"
            elif phase == "outro":
                cue_reason = "结尾段建议逐步收束氛围"

            section_cues.append(
                {
                    "section_id": section.section_id,
                    "title": section.title,
                    "section_type": section.section_type,
                    "order": index,
                    "phase": phase,
                    "energy": energy,
                    "asset_count": len(section.asset_refs),
                    "keep_source_audio": bool(profile.get("keep_source_audio", True)),
                    "ducking_hint": "medium" if bool(profile.get("auto_ducking", True)) else "off",
                    "reason": cue_reason,
                }
            )

        top_keywords = [item.get("keyword") for item in (context.get("top_keywords") or []) if item.get("keyword")]
        search_keywords = list(dict.fromkeys([selected_template_id, str(profile.get("music_profile") or "")] + top_keywords))[:8]

        recommended_audio_settings = {
            "music_mode": "auto" if selected_candidate else "off",
            "music_path": selected_candidate.get("absolute_path") if selected_candidate else None,
            "music_source": "library" if selected_candidate else "none",
            "music_profile": str(profile.get("music_profile") or "lifestyle"),
            "music_playlist_mode": str(profile.get("music_playlist_mode") or ("auto_playlist" if len(candidate_entries) > 1 else "single")),
            "music_playlist_paths": [entry["absolute_path"] for entry in candidate_entries if entry.get("absolute_path")],
            "music_fit_strategy": str(profile.get("music_fit_strategy") or "auto"),
            "music_chapter_restart": bool(chapter_restart),
            "bgm_volume": float(profile.get("bgm_volume") or 0.24),
            "source_audio_volume": float(profile.get("source_audio_volume") or 1.0),
            "keep_source_audio": bool(profile.get("keep_source_audio", True)),
            "auto_ducking": bool(profile.get("auto_ducking", True)),
            "duck_bgm_volume": float(profile.get("duck_bgm_volume") or 0.15),
            "fade_in_seconds": float(profile.get("fade_in_seconds") or 1.2),
            "fade_out_seconds": float(profile.get("fade_out_seconds") or 2.4),
            "normalize_audio": bool(profile.get("normalize_audio", True)),
            "target_lufs": float(profile.get("target_lufs") or -16.0),
        }

        return {
            "version": 1,
            "mode": normalized_mode,
            "template_id": selected_template_id,
            "music_profile": recommended_audio_settings["music_profile"],
            "energy_curve_style": energy_curve_style,
            "estimated_project_duration_seconds": round(estimated_duration, 3),
            "longform_project": longform_project,
            "search_keywords": search_keywords,
            "selected_candidate": selected_candidate,
            "candidate_assets": candidate_entries,
            "section_cues": section_cues,
            "recommended_audio_settings": recommended_audio_settings,
            "activation_hint": "set music_blueprint mode to apply or copy recommended_audio_settings into metadata.audio",
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
