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
  - natural sorting, ignored-file checks, orientation labels, section serialization

## Rules

- Keep `video_engine_v5.py` import-compatible for `video_engine_worker.py` and existing tests.
- Move pure helpers first.
- Do not move `Scanner`, `Planner`, or `Renderer` until their dependency surface is smaller.
- After moving a module, update `scripts/package-worker.mjs` tracked inputs so packaged workers rebuild when helper modules change.

## Next Safe Steps

1. Move directory recognition constants and `detect_directory_type()` into `video_engine/scan_utils.py`.
2. Move audio-only helpers into `video_engine/audio.py`.
3. Move `Scanner` into `video_engine/scan.py` after scan helpers are isolated.
4. Move `Planner` and compile helpers after shared models/constants are stable.
5. Move render cache key builders and FFmpeg command builders before moving the `Renderer` class.
