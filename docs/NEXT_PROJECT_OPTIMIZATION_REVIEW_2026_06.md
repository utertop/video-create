# Project Optimization Review, 2026-06-16

## Executive Summary

The project is in a strong but heavy phase: the product already has a working Tauri frontend, a modularizing Python render engine, stable render recovery, telemetry/diagnostics, timeline editing, and a broad smoke-test suite. The next high-value work should not be another large feature push. It should reduce the cost of making safe changes.

Recommended next focus:

1. Stabilize and document the validation workflow.
2. Continue shrinking `src/App.tsx` around feature boundaries.
3. Reduce Python render-engine compatibility debt around `video_engine_v5.py`.
4. Refactor large smoke tests into shared helpers.
5. Only then push deeper render performance and backend expansion.

## Review Snapshot

Observed largest frontend files:

- `src/App.tsx`: 4473 lines
- `src/lib/engine.ts`: 701 lines
- `src/lib/v5Types.ts`: 622 lines
- `src/lib/diagnostics.ts`: 551 lines
- `src/components/BlueprintEditor.tsx`: 393 lines
- `src/components/TitleStylePreview.tsx`: 391 lines
- `src/features/timeline/TimelineInspector.tsx`: 355 lines
- `src/features/timeline/TimelineEditor.tsx`: 350 lines

Observed largest Python engine files:

- `video_engine/timeline.py`: 1033 lines
- `video_engine/render_diagnostics.py`: 827 lines
- `video_engine/plan.py`: 800 lines
- `video_engine/scan.py`: 782 lines
- `video_engine/compile.py`: 747 lines
- `video_engine/render_stable.py`: 662 lines
- `video_engine/render_ffmpeg.py`: 631 lines
- `video_engine/render_cards.py`: 564 lines

Validation result:

- `npm.cmd run build:web`: passed.
- `npm.cmd run check`: first run failed at nested Vite build with an emitted absolute `index.html` path error, then a second run passed the full core suite.
- Core suite passed 18 steps, including frontend build, Tauri `cargo check`, Python compile/help checks, and core smoke tests.

The first transient check failure should be tracked as a validation reliability risk, even though the repeat run passed.

## P0: Validation Reliability

### Problem

The project depends on smoke tests and build scripts as the safety net for refactors. A transient failure in `npm.cmd run check` creates uncertainty: developers may not know whether a failure is caused by their code, Vite path casing, environment state, or test artifacts.

### Recommended Work

- Add a short validation guide to `README.md` or `docs/`.
- Record the expected command order:
  - `npm.cmd run build:web`
  - `npm.cmd run check`
  - `npm.cmd run check:full` before release-sized changes
- Investigate the intermittent Vite emitted asset path error if it appears again.
- Consider making `scripts/check.mjs` print cwd, Node version, npm version, and Vite version at startup.
- Consider cleaning or isolating generated `tests/tmp_vcs_*` artifacts before smoke tests that are sensitive to prior runs.

### Acceptance Criteria

- Two consecutive `npm.cmd run check` runs pass on a clean working tree.
- A failed check prints enough environment context to diagnose path/cwd issues.
- Test artifacts remain ignored or cleaned by `npm run clean:test-artifacts`.

## P0: Continue Frontend Boundary Extraction

### Problem

`src/App.tsx` is still the biggest frontend maintenance pressure point. Recent extraction of diagnostics and render result panels helped, but `App.tsx` still mixes:

- render queue orchestration
- project/session recovery
- timeline apply flow
- audio blueprint adoption
- music selection
- cache/proxy status presentation
- large helper functions
- page layout

### Recommended Work

Do this in small, behavior-preserving slices:

1. Extract session/project recovery cards and recovery parsing helpers.
2. Extract audio blueprint and music panels into `src/components` or `src/features/audio`.
3. Extract render queue orchestration helpers into a dedicated hook only after the UI-only pieces are gone.
4. Move cache/proxy status label helpers into a small frontend helper module.

### Guardrails

- Avoid moving stateful render workflow effects until UI and pure helpers are already separated.
- Keep props explicit.
- Do not change Chinese/English display text during extraction.
- Run `npm.cmd run build:web` after each slice.

### Acceptance Criteria

- `src/App.tsx` drops below 3000 lines first, then below 2500 lines.
- Render, preview, queue retry, recovery, telemetry consent, and diagnostics flows behave the same.
- No new global state store fields are introduced just to move code.

## P0: Python Entry Point Compatibility Debt

### Problem

The project has modular files under `video_engine/`, but `video_engine_v5.py` remains a large compatibility entry point. This is useful for public CLI stability, but it can hide duplicated logic and make it unclear which module owns behavior.

### Recommended Work

- Audit `video_engine_v5.py` wrapper methods against `video_engine/*` modules.
- Mark each compatibility function as one of:
  - public CLI boundary
  - thin adapter
  - duplicated implementation to migrate
  - legacy fallback to keep
- Prefer moving implementation into `video_engine/*`, leaving `video_engine_v5.py` as CLI and compatibility glue.

### Acceptance Criteria

- New render logic lands in `video_engine/*`, not directly in `video_engine_v5.py`.
- Compatibility wrappers have clear ownership comments or tests.
- Existing worker protocol and CLI smoke tests continue to pass.

## P1: Smoke Test Maintainability

### Problem

The smoke suite is valuable but several files are large:

- `tests/smoke_v5_ffmpeg_priority.py`: 959 lines
- `tests/smoke_v5_render_scheduler.py`: 924 lines
- `tests/smoke_v5_audio_visual_cache.py`: 736 lines

Large smoke tests are harder to update and often duplicate fixture setup, plan creation, image generation, and assertion utilities.

### Recommended Work

- Create shared helpers under `tests/helpers/` or `tests/_helpers.py`.
- Extract fixture builders for:
  - mock media libraries
  - render plans
  - timeline documents
  - temporary project directories
  - build report assertions
- Keep each smoke test scenario-focused.

### Acceptance Criteria

- The three largest smoke tests each shrink by at least 25 percent.
- Shared helpers do not hide the scenario intent.
- `npm.cmd run check` remains the default confidence command.

## P1: Contract Drift Between Python and TypeScript

### Problem

Types exist in `src/lib/engineContracts.ts`, `src/lib/v5Types.ts`, and Python dictionaries/dataclasses across `video_engine/*`. There is no obvious generated or schema-first contract source. As the render report, recovery summary, telemetry, timeline, and backend structures grow, drift risk increases.

### Recommended Work

- Pick one or two high-value contracts first:
  - `RenderRecoverySummary`
  - `StartupDiagnostics`
  - `V5Timeline`
  - `BuildReportV2`
- Add schema assertions in smoke tests or a lightweight JSON-schema document.
- Keep TS types aligned with smoke-test fixtures.

### Acceptance Criteria

- A changed Python payload shape breaks a focused contract check before it breaks UI behavior.
- Diagnostic bundle and render result UI share the same typed assumptions.

## P1: Render Observability Before More Performance Work

### Problem

Existing docs already point at local invalidation, cache reuse, preview acceleration, and backend fallback. Those are good directions, but the best next performance work should be guided by observability instead of intuition.

### Recommended Work

- Extend Build Report V2 with clearer slow-path reasons where missing.
- Track per-stage timings consistently:
  - scan
  - compile
  - chunk render
  - concat
  - audio mix
  - final validation
- Surface fast-path miss reasons in support diagnostics.
- Add one smoke test that asserts representative slow-path recommendations.

### Acceptance Criteria

- A support bundle can answer why a render was slow without reading raw logs.
- UI can display actual backend, selected backend, fallback used, and cache hit/miss summary.
- Performance work is prioritized by measured slow-path frequency.

## P2: Product UX Polish

### Problem

The application has many capabilities, but the main screen still carries a lot of operational complexity. Mature product feel will come from making state, progress, and recovery easier to understand.

### Recommended Work

- Make progress states more deterministic and less log-dependent.
- Group render controls, queue status, diagnostics, and output actions more clearly.
- Improve large-project material browsing with lazy display or stronger filtering.
- Make preview-vs-final mode visually explicit.

### Acceptance Criteria

- A user can tell whether the app is idle, scanning, compiling, previewing, rendering, cancelling, failed, or recoverable without reading logs.
- Large media libraries remain responsive.
- Preview output and final output are hard to confuse.

## Suggested Next Sprint

The best immediate sprint is not a render-engine feature sprint. It should be a safety-and-maintainability sprint:

1. Add validation reliability notes and investigate any repeated `npm run check` path failure.
2. Extract `SessionRecoveryCard`, `ProjectRecoveryCard`, and recovery helpers from `App.tsx`.
3. Extract `AudioBlueprintPanel` and `MusicAudioPanel` from `App.tsx`.
4. Create shared smoke-test helpers for the render scheduler and FFmpeg priority tests.
5. Run `npm.cmd run check` and record the result in the PR.

This creates a safer base for the next performance sprint.

