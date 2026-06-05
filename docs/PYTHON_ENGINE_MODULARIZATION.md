# Python Engine Modularization

`video_engine_v5.py` remains the compatibility entrypoint while implementation pieces move into the `video_engine/` package.

## Current Split

- `video_engine/constants.py`
  - engine/schema version
  - media extension sets
  - ignored scan names
  - cache cleanup defaults
- `video_engine/cache.py`
  - stable ID helpers
  - light file hash
  - cache cleanup utilities
- `video_engine/models.py`
  - shared dataclasses for scan, plan, compile, and render
  - `TitleStyle`, `DirectoryNode`, `Asset`, `AssetRef`, `StorySection`, `RenderSegment`
- `video_engine/scan_utils.py`
  - scan-adjacent pure helpers
  - directory recognition constants and `detect_directory_type()`
  - natural sorting, ignored-file checks, orientation labels, section serialization
- `video_engine/scan.py`
  - `Scanner` class for `scan -> media_library.json`
  - scan proxy profile and scan-time EXIF helper
  - scan cache cleanup, metadata cache, thumbnails, and proxy generation
- `video_engine/plan.py`
  - `Planner` class for `plan -> story_blueprint.json`
  - template matching profiles and scoring
  - audio blueprint recommendations
- `video_engine/compile.py`
  - `Compiler` class for `compile -> render_plan.json`
  - render scheduler hints and segment route assignment
  - audio blueprint timeline adoption into render settings
- `video_engine/render_routes.py`
  - pure render route classifiers
  - stable-render auto-selection helpers
  - FFmpeg image/card/video chunk candidate checks
- `video_engine/render_cache.py`
  - stable render cache key builders
  - source fingerprint and chunk grouping helpers
  - atomic replace and build report writing
- `video_engine/render_ffmpeg.py`
  - FFmpeg concat/re-encode helpers
  - stable chunk fast-path writers for direct/video/card/image routes
  - final BGM muxing and silent audio-track muxing helpers
- `video_engine/audio.py`
  - audio probing and normalized-audio cache helpers
  - auto music scoring and playlist selection
  - music bed and chapter-restart bed builders

## Rules

- Keep `video_engine_v5.py` import-compatible for `video_engine_worker.py` and existing tests.
- Move pure helpers first.
- Do not move `Scanner`, `Planner`, or `Renderer` until their dependency surface is smaller.
- After moving a module, update `scripts/package-worker.mjs` tracked inputs so packaged workers rebuild when helper modules change.

## Next Safe Steps

1. Split render diagnostics/report helpers after route/cache/FFmpeg helpers are isolated.
2. Move scan proxy manifest helpers into a small proxy/cache module if render reuse grows.
3. Start shrinking `Renderer` by moving small, hook-light methods before moving the class itself.
