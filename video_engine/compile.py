from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from .audio import select_auto_music_asset
from .cache import safe_id
from .constants import ENGINE_VERSION, SCHEMA_VERSION, STABLE_RENDER_DEFAULTS
from .models import RenderSegment, TitleStyle

_emit_event: Callable[..., None] = lambda _event_type, **_payload: None


def set_compile_event_emitter(callback: Callable[..., None]) -> None:
    global _emit_event
    _emit_event = callback


def emit_event(event_type: str, **payload: Any) -> None:
    _emit_event(event_type, **payload)


class Compiler:
    def __init__(self, blueprint: Dict[str, Any], library: Dict[str, Any]):
        self.blueprint = blueprint
        self.library = library
        self.assets = {a["asset_id"]: a for a in library.get("assets", [])}
        self.blueprint_metadata = blueprint.get("metadata", {}) or {}
        self.audio_blueprint_metadata = self.blueprint_metadata.get("audio_blueprint") or {}
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
            audio_blueprint = self.audio_blueprint_metadata
            if isinstance(audio_blueprint, dict) and str(audio_blueprint.get("mode") or "") == "apply":
                recommended = audio_blueprint.get("recommended_audio_settings")
                if isinstance(recommended, dict):
                    audio = recommended
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

    def _compile_audio_blueprint_timeline(self) -> Dict[str, Any]:
        if not isinstance(self.audio_blueprint_metadata, dict) or not self.audio_blueprint_metadata:
            return {}

        cue_map = {
            str(item.get("section_id")): item
            for item in (self.audio_blueprint_metadata.get("section_cues") or [])
            if isinstance(item, dict) and item.get("section_id")
        }
        section_titles: Dict[str, str] = {}

        def walk_sections(items: List[Dict[str, Any]]) -> None:
            for item in items:
                if not isinstance(item, dict):
                    continue
                section_id = item.get("section_id")
                if section_id:
                    section_titles[str(section_id)] = str(item.get("title") or section_id)
                walk_sections(item.get("children") or [])

        walk_sections(self.blueprint.get("sections") or [])

        section_ranges: Dict[str, Dict[str, Any]] = {}
        for seg in self.segments:
            section_id = str(seg.section_id or "")
            if not section_id:
                continue
            bucket = section_ranges.setdefault(
                section_id,
                {
                    "section_id": section_id,
                    "title": section_titles.get(section_id) or section_id,
                    "start_time": float(seg.start_time),
                    "end_time": float(seg.end_time),
                },
            )
            bucket["start_time"] = min(float(bucket["start_time"]), float(seg.start_time))
            bucket["end_time"] = max(float(bucket["end_time"]), float(seg.end_time))

        timeline_cues: List[Dict[str, Any]] = []
        for section_id, section_range in sorted(section_ranges.items(), key=lambda item: float(item[1]["start_time"])):
            cue = cue_map.get(section_id, {})
            start_time = float(section_range["start_time"])
            end_time = float(section_range["end_time"])
            timeline_cues.append(
                {
                    "section_id": section_id,
                    "title": section_range["title"],
                    "phase": cue.get("phase") or "sustain",
                    "energy": cue.get("energy") or "medium",
                    "reason": cue.get("reason") or "保持段落音乐连续性",
                    "ducking_hint": cue.get("ducking_hint") or "medium",
                    "start_time": round(start_time, 3),
                    "end_time": round(end_time, 3),
                    "duration": round(max(0.0, end_time - start_time), 3),
                }
            )

        recommended = dict(self.audio_blueprint_metadata.get("recommended_audio_settings") or {})
        return {
            "version": int(self.audio_blueprint_metadata.get("version") or 1),
            "mode": self.audio_blueprint_metadata.get("mode") or "recommend",
            "template_id": self.audio_blueprint_metadata.get("template_id"),
            "music_profile": self.audio_blueprint_metadata.get("music_profile"),
            "energy_curve_style": self.audio_blueprint_metadata.get("energy_curve_style"),
            "selected_candidate": self.audio_blueprint_metadata.get("selected_candidate"),
            "candidate_assets": self.audio_blueprint_metadata.get("candidate_assets") or [],
            "search_keywords": self.audio_blueprint_metadata.get("search_keywords") or [],
            "recommended_audio_settings": recommended,
            "adopted_audio_settings": self.audio_blueprint_metadata.get("adopted_audio_settings") or {},
            "ui_adoption_state": self.audio_blueprint_metadata.get("ui_adoption_state") or {},
            "origin_summary": self.audio_blueprint_metadata.get("origin_summary"),
            "timeline_cues": timeline_cues,
            "activation_hint": self.audio_blueprint_metadata.get("activation_hint"),
        }

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
        return motion_type in {"gentle_push", "slow_push", "micro_zoom", "subtle_ken_burns"}

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
        image_heavy = sum(1 for item in self.segments if str(item.type or "") == "image") >= max(12, int(segment_count * STABLE_RENDER_DEFAULTS["image_heavy_ratio"]))
        large_project = (
            performance_mode == "stable"
            or render_mode == "long_stable"
            or total_duration >= float(STABLE_RENDER_DEFAULTS["seconds"])
            or segment_count >= int(STABLE_RENDER_DEFAULTS["segments"])
            or (image_heavy and (total_duration >= float(STABLE_RENDER_DEFAULTS["image_heavy_seconds"]) or segment_count >= int(STABLE_RENDER_DEFAULTS["image_heavy_segments"])))
        )
        medium_project = performance_mode in {"balanced", "quality"} and (
            total_duration >= float(STABLE_RENDER_DEFAULTS["image_heavy_seconds"])
            or segment_count >= int(STABLE_RENDER_DEFAULTS["image_heavy_segments"])
        )
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
        compiled_audio_blueprint = self._compile_audio_blueprint_timeline()

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
                "audio_blueprint": compiled_audio_blueprint,
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
        image_motion_profile = str(self.blueprint_metadata.get("image_motion_profile") or "auto")
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

        def template_motion(kind: str, intensity: str, reason: str) -> Dict[str, Any]:
            if not is_image:
                return motion("none", "none", reason)
            if image_motion_profile == "travel_gentle" and kind in {"ken_burns", "gentle_push", "slow_push"}:
                return motion("gentle_push", "soft", "模板偏好旅拍柔和轻推")
            if image_motion_profile == "dynamic_punch" and kind not in {"none", "still_hold"}:
                return motion("punch_zoom", "high", "模板偏好更有冲击力的图片节奏")
            if image_motion_profile == "casual_story" and kind not in {"none", "still_hold"}:
                return motion("gentle_push", "soft", "模板偏好日常记录型轻推运动")
            if image_motion_profile == "product_focus" and kind not in {"none", "still_hold"}:
                return motion("slow_push", "low", "模板偏好克制稳定的产品展示运动")
            if image_motion_profile == "photo_story" and kind not in {"none", "still_hold"}:
                return motion("subtle_ken_burns", "low", "模板偏好低干扰的图文叙事运动")
            return motion(kind, intensity, reason)

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
                motion("none", "none", "快速成片保持视频原节奏") if is_video else template_motion("still_hold", "none", "快速成片减少逐段运动处理"),
                rhythm("footage" if is_video else "visual", "fast_review", 0.62),
            )
        if strategy == "travel_soft":
            return (
                transition("soft_crossfade", 0.45, "旅拍素材用柔和交叉淡化保持流动感"),
                motion("none", "none", "视频段不额外施加模板图片运动") if is_video else template_motion("gentle_push", "soft", "轻推镜头增加旅行感但不抢主体"),
                rhythm("footage" if is_video else "visual", "medium_soft", 0.72),
            )
        if strategy == "beat_cut":
            return (
                transition("quick_zoom" if is_image else "cut", 0.18, "节奏型剪辑用短促冲击转场"),
                motion("micro_zoom", "high", "增加卡点冲击和画面能量") if is_video else template_motion("punch_zoom", "high", "增加卡点冲击和画面能量"),
                rhythm("beat_asset", "fast_punchy", 0.82),
            )
        if strategy == "documentary":
            return (
                transition("soft_crossfade" if is_image else "cut", 0.28, "纪录叙事保持克制连贯"),
                motion("none", "none", "视频段保持自然纪录感") if is_video else template_motion("slow_push", "low", "慢推帮助观众阅读画面信息"),
                rhythm("story_asset", "steady_story", 0.78),
            )
        if strategy == "long_stable":
            return (
                transition("cut" if is_video else "soft_crossfade", 0.2, "长片降低转场复杂度，保证稳定输出"),
                motion("none", "none", "视频段优先稳定输出") if is_video else template_motion("subtle_ken_burns", "low", "长片保留轻微变化避免疲劳"),
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
            motion("none", "none", "视频段保持素材原节奏") if is_video else template_motion("ken_burns", "medium", "智能导演为静态图补充轻微镜头运动"),
            rhythm("footage" if is_video else "visual", "auto", 0.72),
        )
