"""Title, card, cover, and title-preview render helpers."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple


class TitleStyleRenderer:
    """V5.5 Template-driven Text Animation Engine."""

    def __init__(
        self,
        target_size: Tuple[int, int],
        *,
        image_cls: Any,
        image_draw_mod: Any,
        image_filter_mod: Any,
        color_clip_cls: Any,
        load_font_fn: Callable[[int], Any],
        text_size_fn: Callable[[Any, str, Any], Tuple[int, int]],
        draw_text_with_emoji_fn: Callable[..., None],
    ):
        self.target_size = target_size
        self.image_cls = image_cls
        self.image_draw_mod = image_draw_mod
        self.image_filter_mod = image_filter_mod
        self.color_clip_cls = color_clip_cls
        self.load_font = load_font_fn
        self.text_size = text_size_fn
        self.draw_text_with_emoji = draw_text_with_emoji_fn

    def render_layer(
        self,
        title: str,
        subtitle: Optional[str],
        style: Dict[str, Any],
        is_full_card: bool = True
    ) -> Image.Image:
        w, h = self.target_size
        preset = style.get("preset", "cinematic_bold")
        preset_aliases = {
            "nature_documentary": "documentary_lower_third",
            "romantic_soft": "handwritten_note",
            "tech_future": "neon_night",
        }
        preset = preset_aliases.get(preset, preset)
        
        # Base transparent layer
        img = self.image_cls.new("RGBA", self.target_size, (0, 0, 0, 0))
        draw = self.image_draw_mod.Draw(img)

        # Style definitions
        if preset == "playful_pop":
            # Round box + bright green text
            box_w = min(int(w * 0.5), 800)
            box_h = 160 if subtitle else 100
            bx, by = (w - box_w) // 2, (h - box_h) // 2
            draw.rounded_rectangle((bx, by, bx + box_w, by + box_h), radius=40, fill=(255, 255, 255, 200))
            title_font = self.load_font(64)
            sub_font = self.load_font(32)
            tw, th = self.text_size(draw, title, title_font)
            self.draw_text_with_emoji(draw, ((w - tw) // 2, by + 20), title, font=title_font, fill=(52, 211, 153, 255))
            if subtitle:
                sw, sh = self.text_size(draw, subtitle, sub_font)
                self.draw_text_with_emoji(draw, ((w - sw) // 2, by + 90), subtitle, font=sub_font, fill=(30, 41, 59, 200))

        elif preset == "travel_postcard":
            # Bordered card effect
            if is_full_card:
                draw.rectangle((40, 40, w - 40, h - 40), outline=(255, 255, 255, 180), width=3)
                draw.rectangle((56, 56, w - 56, h - 56), outline=(251, 191, 36, 120), width=2)
            title_font = self.load_font(72)
            sub_font = self.load_font(36)
            tw, th = self.text_size(draw, title, title_font)
            self.draw_text_with_emoji(draw, ((w - tw) // 2 + 3, (h - th) // 2 - 17), title, font=title_font, fill=(35, 24, 18, 190))
            self.draw_text_with_emoji(draw, ((w - tw) // 2, (h - th) // 2 - 20), title, font=title_font, fill=(255, 245, 210, 255))
            if subtitle:
                sw, sh = self.text_size(draw, subtitle, sub_font)
                self.draw_text_with_emoji(draw, ((w - sw) // 2, (h - sh) // 2 + 60), subtitle, font=sub_font, fill=(251, 191, 36, 230))

        elif preset == "impact_flash":
            title_font = self.load_font(92)
            sub_font = self.load_font(38)
            tw, th = self.text_size(draw, title, title_font)
            x, y = (w - tw) // 2, (h - th) // 2 - 26
            for offset in [(6, 6), (-5, 4), (4, -5), (-4, -4)]:
                self.draw_text_with_emoji(draw, (x + offset[0], y + offset[1]), title, font=title_font, fill=(17, 24, 39, 240))
            self.draw_text_with_emoji(draw, (x + 2, y + 2), title, font=title_font, fill=(239, 68, 68, 210))
            self.draw_text_with_emoji(draw, (x, y), title, font=title_font, fill=(255, 255, 255, 255))
            if subtitle:
                sw, sh = self.text_size(draw, subtitle, sub_font)
                draw.rounded_rectangle(((w - sw) // 2 - 18, y + th + 16, (w + sw) // 2 + 18, y + th + 62), radius=8, fill=(15, 23, 42, 210))
                self.draw_text_with_emoji(draw, ((w - sw) // 2, y + th + 22), subtitle, font=sub_font, fill=(255, 255, 255, 235))

        elif preset == "documentary_lower_third":
            band_h = 170 if subtitle else 126
            y0 = h - band_h - int(h * 0.08) if not is_full_card else int(h * 0.62)
            draw.rectangle((0, y0, w, y0 + band_h), fill=(10, 14, 12, 190))
            draw.rectangle((0, y0, 12, y0 + band_h), fill=(214, 182, 107, 255))
            title_font = self.load_font(60)
            sub_font = self.load_font(30)
            self.draw_text_with_emoji(draw, (56, y0 + 28), title, font=title_font, fill=(250, 246, 235, 255))
            if subtitle:
                self.draw_text_with_emoji(draw, (58, y0 + 98), subtitle, font=sub_font, fill=(214, 182, 107, 230))

        elif preset == "minimal_editorial":
            title_font = self.load_font(56)
            sub_font = self.load_font(28)
            tw, th = self.text_size(draw, title, title_font)
            x = int(w * 0.12) if is_full_card else int(w * 0.07)
            y = (h - th) // 2 - 10
            draw.rectangle((x, y - 28, x + 2, y + th + 80), fill=(255, 255, 255, 190))
            self.draw_text_with_emoji(draw, (x + 28, y), title, font=title_font, fill=(255, 255, 255, 235))
            if subtitle:
                self.draw_text_with_emoji(draw, (x + 30, y + th + 24), subtitle, font=sub_font, fill=(255, 255, 255, 170))

        elif preset == "handwritten_note":
            box_w = min(int(w * 0.62), 980)
            box_h = 190 if subtitle else 136
            bx, by = (w - box_w) // 2, (h - box_h) // 2
            draw.rounded_rectangle((bx, by, bx + box_w, by + box_h), radius=34, fill=(255, 251, 235, 225), outline=(255, 255, 255, 240), width=5)
            title_font = self.load_font(66)
            sub_font = self.load_font(32)
            tw, th = self.text_size(draw, title, title_font)
            self.draw_text_with_emoji(draw, ((w - tw) // 2 + 3, by + 28 + 3), title, font=title_font, fill=(14, 165, 233, 110))
            self.draw_text_with_emoji(draw, ((w - tw) // 2, by + 28), title, font=title_font, fill=(31, 41, 55, 255))
            if subtitle:
                sw, sh = self.text_size(draw, subtitle, sub_font)
                self.draw_text_with_emoji(draw, ((w - sw) // 2, by + 106), subtitle, font=sub_font, fill=(234, 88, 12, 220))

        elif preset == "neon_night":
            title_font = self.load_font(74)
            sub_font = self.load_font(32)
            tw, th = self.text_size(draw, title, title_font)
            x, y = (w - tw) // 2, (h - th) // 2 - 22
            for radius, alpha in [(10, 70), (5, 120), (2, 210)]:
                glow = self.image_cls.new("RGBA", self.target_size, (0, 0, 0, 0))
                glow_draw = self.image_draw_mod.Draw(glow)
                self.draw_text_with_emoji(glow_draw, (x, y), title, font=title_font, fill=(244, 114, 182, alpha))
                img.alpha_composite(glow.filter(self.image_filter_mod.GaussianBlur(radius)))
            self.draw_text_with_emoji(draw, (x, y), title, font=title_font, fill=(255, 240, 252, 255))
            if subtitle:
                sw, sh = self.text_size(draw, subtitle, sub_font)
                self.draw_text_with_emoji(draw, ((w - sw) // 2, y + th + 32), subtitle, font=sub_font, fill=(125, 211, 252, 230))

        elif preset == "film_subtitle":
            title_font = self.load_font(56)
            sub_font = self.load_font(28)
            tw, th = self.text_size(draw, title, title_font)
            y = int(h * 0.68) if is_full_card else int(h * 0.72)
            draw.rectangle((0, y - 34, w, y + 116), fill=(0, 0, 0, 115))
            self.draw_text_with_emoji(draw, ((w - tw) // 2, y), title, font=title_font, fill=(248, 240, 220, 245))
            if subtitle:
                sw, sh = self.text_size(draw, subtitle, sub_font)
                self.draw_text_with_emoji(draw, ((w - sw) // 2, y + 62), subtitle, font=sub_font, fill=(248, 240, 220, 190))
            if not is_full_card:
                draw.rectangle((28, 36, 30, h - 36), fill=(248, 240, 220, 42))

        elif preset == "route_marker":
            title_font = self.load_font(64)
            sub_font = self.load_font(30)
            x0, y0 = int(w * 0.22), int(h * 0.58)
            x1, y1 = int(w * 0.72), int(h * 0.38)
            draw.line((x0, y0, int(w * 0.44), y0 - 70, x1, y1), fill=(47, 111, 143, 220), width=5)
            draw.ellipse((x1 - 18, y1 - 18, x1 + 18, y1 + 18), fill=(37, 99, 235, 240))
            draw.ellipse((x1 - 7, y1 - 7, x1 + 7, y1 + 7), fill=(255, 255, 255, 240))
            tw, th = self.text_size(draw, title, title_font)
            draw.rounded_rectangle(((w - tw) // 2 - 32, y0 + 28, (w + tw) // 2 + 32, y0 + 118), radius=18, fill=(255, 251, 235, 220))
            self.draw_text_with_emoji(draw, ((w - tw) // 2, y0 + 42), title, font=title_font, fill=(23, 32, 26, 255))
            if subtitle:
                sw, sh = self.text_size(draw, subtitle, sub_font)
                self.draw_text_with_emoji(draw, ((w - sw) // 2, y0 + 112), subtitle, font=sub_font, fill=(47, 111, 143, 230))

        else: # cinematic_bold (default)
            title_font = self.load_font(78)
            sub_font = self.load_font(34)
            tw, th = self.text_size(draw, title, title_font)
            self.draw_text_with_emoji(draw, ((w - tw) // 2, (h - th) // 2 - 40), title, font=title_font, fill=(255, 255, 255, 255))
            if subtitle:
                sw, sh = self.text_size(draw, subtitle, sub_font)
                self.draw_text_with_emoji(draw, ((w - sw) // 2, (h - sh) // 2 + 55), subtitle, font=sub_font, fill=(52, 211, 153, 255))

        return img

    def _with_dynamic_opacity(self, clip: Any, opacity_fn: Any) -> Any:
        # Apply time-varying opacity using a MoviePy mask.
        # MoviePy 1.0.x set_opacity() only accepts numeric opacity.
        try:
            base_mask = getattr(clip, "mask", None)
            if base_mask is None:
                base_mask = self.color_clip_cls(clip.size, color=1, ismask=True).set_duration(clip.duration)

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
        motion_aliases = {
            "fade_slide_up": "cinematic_reveal",
            "soft_zoom_in": "postcard_drift",
            "pop_bounce": "playful_bounce",
            "quick_zoom_punch": "impact_slam",
            "slow_fade_zoom": "film_burn",
            "fade_only": "editorial_fade",
        }
        motion = motion_aliases.get(motion, motion)
        duration = max(float(duration or 0.1), 0.1)

        animated = clip

        if motion == "static_hold":
            return animated.set_position(("center", "center"))

        if motion in {"soft_zoom_in", "slow_fade_zoom", "cinematic_reveal", "postcard_drift", "film_burn"}:
            animated = self._safe_resize(animated, lambda t: self._soft_zoom_scale(t, duration))
        elif motion in {"pop_bounce", "playful_bounce"}:
            animated = self._safe_resize(animated, lambda t: self._pop_scale(t))
        elif motion in {"quick_zoom_punch", "impact_slam"}:
            animated = self._safe_resize(animated, lambda t: self._punch_scale(t))

        # Dynamic opacity must be mask-based, not set_opacity(lambda...).
        if motion == "neon_flicker":
            animated = self._with_dynamic_opacity(animated, lambda t: self._neon_flicker_curve(t, duration))
        else:
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

    def _neon_flicker_curve(self, t: float, duration: float) -> float:
        if t < 0.08:
            return 0.25
        if t < 0.14:
            return 1.0
        if t < 0.20:
            return 0.48
        if t > duration - 0.35:
            return max(0.0, (duration - t) / 0.35)
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


EmitEvent = Callable[..., None]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def chapter_card(
    renderer: Any,
    seg: Dict[str, Any],
    duration: float,
    *,
    np_module: Any = None,
    image_clip_cls: Any = None,
    composite_video_clip_cls: Any = None,
) -> Any:
    mode = seg.get("background_mode") or "bridge_blur"
    title_style = seg.get("title_style")

    if mode == "plain":
        return text_card(
            renderer,
            seg.get("text") or "",
            seg.get("subtitle"),
            duration,
            main=False,
            background_source=None,
            background_position="first",
            title_style=title_style,
            np_module=np_module,
            image_clip_cls=image_clip_cls,
            composite_video_clip_cls=composite_video_clip_cls,
        )

    if mode == "bridge_blur":
        return text_card(
            renderer,
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
            np_module=np_module,
            image_clip_cls=image_clip_cls,
            composite_video_clip_cls=composite_video_clip_cls,
        )

    return text_card(
        renderer,
        seg.get("text") or "",
        seg.get("subtitle"),
        duration,
        main=False,
        background_source=seg.get("background_source_path"),
        background_position=seg.get("background_source_position") or "first",
        title_style=title_style,
        np_module=np_module,
        image_clip_cls=image_clip_cls,
        composite_video_clip_cls=composite_video_clip_cls,
    )


def text_card(
    renderer: Any,
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
    *,
    np_module: Any = None,
    image_clip_cls: Any = None,
    composite_video_clip_cls: Any = None,
) -> Any:
    bg = build_text_background(
        renderer,
        background_source,
        background_position,
        background_source_2,
        background_position_2,
        blend_sources=blend_sources,
    )
    bg_clip = image_clip_cls(np_module.array(bg)).set_duration(duration)

    style = title_style or {"preset": "cinematic_bold" if main else "cinematic_bold", "motion": "fade_slide_up"}
    text_img = renderer.renderer.render_layer(title, subtitle, style, is_full_card=True)
    text_clip = image_clip_cls(np_module.array(text_img), ismask=False).set_duration(duration)
    text_clip = renderer.renderer.animate(text_clip, style.get("motion", "fade_slide_up"), duration)

    return composite_video_clip_cls([bg_clip, text_clip], size=renderer.target_size)


def text_card_image(
    renderer: Any,
    title: str,
    subtitle: Optional[str],
    main: bool = False,
    background_source: Optional[str] = None,
    background_position: str = "first",
    background_source_2: Optional[str] = None,
    background_position_2: str = "first",
    blend_sources: bool = False,
    title_style: Optional[Dict[str, Any]] = None,
) -> Any:
    img = build_text_background(
        renderer,
        background_source,
        background_position,
        background_source_2,
        background_position_2,
        blend_sources=blend_sources,
    )

    style = title_style or {"preset": "cinematic_bold" if main else "film_subtitle", "motion": "static_hold"}
    text_img = renderer.renderer.render_layer(title, subtitle, style, is_full_card=True)
    composed = img.convert("RGBA")
    composed.alpha_composite(text_img)
    return composed.convert("RGB")


def build_text_background(
    renderer: Any,
    source_1: Optional[str],
    pos_1: str,
    source_2: Optional[str] = None,
    pos_2: str = "first",
    blend_sources: bool = False,
    *,
    image_cls: Any = None,
) -> Any:
    frame_1 = renderer._source_frame_for_background(source_1, pos_1)
    frame_2 = renderer._source_frame_for_background(source_2, pos_2) if source_2 else None
    image_cls = image_cls or renderer.renderer.image_cls

    if frame_1 and frame_1.exists():
        img_1 = image_cls.open(renderer._blur_bg(frame_1)).convert("RGB")
        if blend_sources and frame_2 and frame_2.exists():
            img_2 = image_cls.open(renderer._blur_bg(frame_2)).convert("RGB")
            img = image_cls.blend(img_1, img_2, 0.50)
        else:
            img = img_1
        return image_cls.blend(img, image_cls.new("RGB", renderer.target_size, (0, 0, 0)), 0.20)

    if frame_2 and frame_2.exists():
        img = image_cls.open(renderer._blur_bg(frame_2)).convert("RGB")
        return image_cls.blend(img, image_cls.new("RGB", renderer.target_size, (0, 0, 0)), 0.20)

    return image_cls.new("RGB", renderer.target_size, (17, 31, 25))


def apply_overlay_title(
    renderer: Any,
    clip: Any,
    seg: Dict[str, Any],
    *,
    composite_video_clip_cls: Any = None,
) -> Any:
    text = seg.get("overlay_text")
    if not text:
        return clip
    subtitle = seg.get("overlay_subtitle")
    duration = min(float(seg.get("overlay_duration") or 1.8), float(clip.duration or 1.8))
    style = seg.get("overlay_title_style")
    overlay = overlay_title_clip(renderer, str(text), subtitle, duration, style=style)
    return composite_video_clip_cls([clip, overlay], size=clip.size).set_duration(clip.duration)


def overlay_title_clip(
    renderer: Any,
    title: str,
    subtitle: Optional[str],
    duration: float,
    style: Optional[Dict[str, Any]] = None,
    *,
    np_module: Any = None,
    image_clip_cls: Any = None,
) -> Any:
    if not style:
        style = {"preset": "cinematic_bold", "motion": "fade_slide_up", "position": "lower_left"}

    text_img = renderer.renderer.render_layer(title, subtitle, style, is_full_card=False)
    text_clip = image_clip_cls(np_module.array(text_img), ismask=False).set_duration(duration)
    text_clip = renderer.renderer.animate(text_clip, style.get("motion", "fade_slide_up"), duration)

    pos = style.get("position", "lower_left")
    w, h = renderer.target_size
    if pos == "lower_left":
        text_clip = text_clip.set_position((int(w * 0.05), int(h * 0.70)))
    elif pos == "lower_center":
        text_clip = text_clip.set_position(("center", int(h * 0.75)))
    else:
        text_clip = text_clip.set_position("center")

    return text_clip


def create_cover(renderer: Any, *, emit_event_fn: EmitEvent = _noop_emit_event) -> None:
    cover = renderer.output_path.with_name(f"cover_{renderer.output_path.stem}.jpg")
    title = str(renderer.params.get("title") or "Travel Video")
    subtitle = str(renderer.params.get("title_subtitle") or "Video Create Studio")
    background_source = renderer.params.get("title_background_path") or renderer.first_visual_source

    img = text_card_image(
        renderer,
        title=title,
        subtitle=subtitle,
        main=True,
        background_source=background_source,
        background_position="first",
        title_style=renderer.params.get("title_style") or {"preset": "cinematic_bold", "motion": "static_hold"},
    )

    img.save(cover, quality=92)
    emit_event_fn(
        "artifact",
        artifact="cover",
        path=str(cover),
        message="Cover generated from opening title card background",
    )


def preview_resolution(aspect_ratio: str) -> Tuple[int, int]:
    if aspect_ratio == "9:16":
        return 360, 640
    if aspect_ratio == "1:1":
        return 480, 480
    return 640, 360


def preview_background(size: Tuple[int, int], theme: str, *, image_cls: Any, image_draw_mod: Any, image_filter_mod: Any) -> Any:
    palettes = {
        "nature": ((18, 54, 38), (106, 142, 69), (211, 238, 174)),
        "city": ((7, 12, 28), (43, 63, 88), (47, 157, 210)),
        "clean": ((248, 250, 252), (205, 220, 232), (164, 220, 190)),
        "travel": ((40, 62, 57), (129, 171, 159), (201, 132, 87)),
    }
    c1, c2, c3 = palettes.get(theme, palettes["travel"])
    w, h = size
    img = image_cls.new("RGB", size, c1)
    draw = image_draw_mod.Draw(img)
    for y in range(h):
        ratio = y / max(h - 1, 1)
        if ratio < 0.55:
            local = ratio / 0.55
            color = tuple(int(c1[i] + (c2[i] - c1[i]) * local) for i in range(3))
        else:
            local = (ratio - 0.55) / 0.45
            color = tuple(int(c2[i] + (c3[i] - c2[i]) * local) for i in range(3))
        draw.line([(0, y), (w, y)], fill=color)
    draw.ellipse((int(w * 0.08), int(h * 0.12), int(w * 0.42), int(h * 0.68)), fill=(*c3[:3],))
    overlay = image_cls.new("RGB", size, (8, 18, 14))
    return image_cls.blend(img.filter(image_filter_mod.GaussianBlur(radius=10)), overlay, 0.18)
