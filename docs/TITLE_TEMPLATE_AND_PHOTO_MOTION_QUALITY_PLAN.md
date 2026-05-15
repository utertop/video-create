# Title Template and Photo Motion Quality Plan

## Goals

This upgrade addresses two viewer-facing quality problems:

- Chapter/title text currently feels too simple because "style + motion" is exposed as two small engineering controls instead of a designed title package.
- Photo segments can feel shaky or dizzy because still-image motion is too noticeable for long viewing.

The product goal is to make generated videos feel packaged, intentional, and comfortable to watch.

## Problem 1: Title Text Quality

### Current State

- The blueprint editor exposes separate controls for text preset and motion.
- Existing presets are visually useful, but too few and too plain for modern travel/vlog packaging.
- Preview and the text motion lab are valuable and should remain.
- Opening title, chapter cards, overlays, ending cards, and cover generation should share the same title-template language.

### New Model

Replace the row-level "style + motion" control with one title-template button. A template is a designed package:

- typography direction
- layout
- texture/decorative treatment
- best matching motion
- static-compatible mode for covers and still title cards

The lab keeps more control: users can choose a template package, override motion, preview instantly, render a real low-resolution preview, apply to current/same-type/all chapters, and save as default.

### Template Set

| Preset ID | Label | Matching Motion ID | Use |
| --- | --- | --- | --- |
| `cinematic_bold` | Cinematic Bold / 电影感 | `cinematic_reveal` | mountains, city scale, dramatic chapter breaks |
| `travel_postcard` | Travel Postcard / 旅游明信片 | `postcard_drift` | travel, food, old streets, warm vlogs |
| `playful_pop` | Playful Pop / 活泼弹跳 | `playful_bounce` | pets, daily life, light clips |
| `impact_flash` | Impact Flash / 冲击标题 | `impact_slam` | sports, snow, high-energy scenes |
| `minimal_editorial` | Minimal Editorial / 极简高级 | `editorial_fade` | architecture, photography, city mood |
| `documentary_lower_third` | Documentary Lower-third / 记录片字幕条 | `lower_third_slide` | location, people, time notes |
| `handwritten_note` | Handwritten Note / 手写贴纸 | `handwritten_draw` | vlog notes, seaside, casual travel |
| `neon_night` | Neon Night / 霓虹夜景 | `neon_flicker` | night city, cyber, nightlife |
| `film_subtitle` | Film Subtitle / 胶片字幕 | `film_burn` | warm memory, golden hour, cinematic subtitles |
| `route_marker` | Route Marker / 地图路线标记 | `route_trace` | route, itinerary, day markers |

Motion also includes `static_hold` for cover/end-card/still-image export.

### Implementation Rules

- Keep JSON fields as `title_style.preset` and `title_style.motion` for compatibility.
- Template buttons set both preset and matching motion.
- Motion override remains available in the lab, including `static_hold`.
- If an old preset or old motion appears, normalize it to the closest new template/motion.
- Cover/title/end rendering uses the same renderer, with `static_hold` disabling animation.

## Problem 2: Photo Motion Comfort

### Current State

- Static images receive motion like Ken Burns, push, or punch zoom.
- This avoids dead stills, but can create visible shake or viewer dizziness.
- The issue is most visible in travel projects with many photos.

### New Motion Policy

Default photo motion should be "steady premium":

- No visible shake.
- No elastic bounce on ordinary photo segments.
- Use very slow, very small scale drift.
- Keep the image center stable.
- Stronger motion belongs mostly to title text, not every photo.

### Motion Mapping

| Motion Type | Old Feeling | New Behavior |
| --- | --- | --- |
| `ken_burns` | noticeable movement | very slow 2.2% zoom |
| `gentle_push` | moving push | 1.8% slow push |
| `slow_push` | moving push | 1.5% slow push |
| `subtle_ken_burns` | subtle but visible | 1.2% breathe |
| `punch_zoom` | punchy photo hit | reduced to 3.5%, short ease only |
| `micro_zoom` | small hit | reduced to 2.5%, short ease only |
| `none` / `still_hold` | stable | unchanged |

### Verification

After title-renderer or photo-motion changes:

- `npm.cmd run build`
- `python tests\smoke_v5_edit_strategy_compile.py`
- `python tests\smoke_v5_low_res_preview.py`
- `python tests\smoke_v5_video_geometry.py`

For audio or long-video side effects:

- `python tests\smoke_v5_bgm_mix.py`
- `python tests\smoke_v5_6_long_video_stability.py`
