# Implementation Plan: Video Create Studio V5.5 Text Animation System

This plan outlines the steps to upgrade the text rendering system from static images to animated, template-driven title cards and overlays.

## 1. Data Model Updates

### 1.1 StorySection Update
Add `title_style` field to `StorySection` in `video_engine_v5.py`.
```python
@dataclass
class TitleStyle:
    preset: str = "cinematic_bold"
    motion: str = "fade_slide_up"
    color_theme: str = "auto"
    position: str = "center"
    user_overridden: bool = False

@dataclass
class StorySection:
    ...
    title_style: Optional[TitleStyle] = None
```

### 1.2 RenderSegment Update
Add `title_style` to `RenderSegment`.

## 2. Engine Logic: TitleStyleRenderer

Implement a new helper class `TitleStyleRenderer` in `video_engine_v5.py` to handle the visual templates.

### 2.1 Presets Implementation (PIL based)
- **cinematic_bold**: White bold font, 20% black overlay.
- **travel_postcard**: Cream background, border effect, handwriting-style font (if available).
- **playful_pop**: Bright colors, rounded rectangle background.
- **impact_flash**: High contrast, bold fonts.
- **minimal_editorial**: Elegant thin fonts, centered.
- **nature_documentary**: Subtle green/earth tones.

### 2.2 Animation Implementation (MoviePy based)
Use lambda functions to animate properties over time.
- **fade_only**: `set_opacity(lambda t: fade_in_out(t))`
- **fade_slide_up**: `set_position(lambda t: ("center", y0 - velocity*t))`
- **soft_zoom_in**: `resize(lambda t: 0.96 + 0.04 * (t/duration))`
- **pop_bounce**: Multi-stage scale animation.

## 3. Automatic Recommendation (Scanner)

Update `Scanner` to analyze directory keywords and suggest a style:
- `PETS`, `CATS` -> `playful_pop`
- `MOUNTAIN`, `SNOW`, `FOREST` -> `nature_documentary`
- `SKI`, `ACTION` -> `impact_flash`
- `FOOD`, `TOWN` -> `travel_postcard`
- Default -> `cinematic_bold`

## 4. Execution Steps

1.  **Phase 1: Foundation**
    - Modify `video_engine_v5.py` to add `TitleStyle` and update `StorySection`/`RenderSegment`.
    - Implement `TitleStyleRenderer.render_text_layer` to generate transparent PNGs.
2.  **Phase 2: Animation Engine**
    - Implement `TitleStyleRenderer.animate_clip` to apply MoviePy effects.
    - Update `_chapter_card` and `_apply_overlay_title` in the engine.
3.  **Phase 3: Intelligence**
    - Update `Scanner` for auto-recommendation.
    - Update `Planner` and `Compiler` to propagate styles.
4.  **Phase 4: Validation**
    - Create `tests/smoke_v5_5_title_style.py`.
    - Verify with different aspect ratios (9:16, 16:9).

## 5. File Changes
- `video_engine_v5.py`: Main logic update.
- `docs/V5_5_CHAPTER_TITLE_STYLE_AND_MOTION.md`: New documentation.
- `tests/smoke_v5_5_title_style.py`: New test script.
