# Performance Diagnostics

This project writes render performance diagnostics into the project
`.video_create_project/build_report.json` file after a render attempt.

## Slow Path Report

The main field for long-render diagnosis is:

```text
diagnostics.slow_path_report
```

It is meant to answer: why did this render spend so much time outside the
FFmpeg/chunk fast paths?

Important fields:

- `segments.fast_path_rate`: ratio of segments that reached a segment-level fast path.
- `segments.non_fast_path_count`: number of segments still routed through slower MoviePy-style handling.
- `segments.top_blockers`: most common segment blockers, such as complex transitions, unsupported motion, or text overlays.
- `segments.samples`: representative slow segments with segment id, type, route, motion, transition, and blocker list.
- `chunks.fast_path_rate`: ratio of chunks rendered through FFmpeg chunk routes.
- `chunks.non_fast_path_count`: number of chunks still routed through `moviepy_chunk`.
- `chunks.top_blockers`: most common chunk-level blockers.
- `chunks.samples`: representative slow chunks, sorted by `render_seconds` when available.
- `recommendations`: conservative next actions inferred from the route distribution.

## Related Fields

Useful neighboring fields in the same report:

- `segment_fast_path_rate`
- `chunk_fast_path_rate`
- `slow_segment_count`
- `slow_chunk_count`
- `top_slow_path_blockers`
- `diagnostics.observability.fast_path_coverage`
- `diagnostics.observability.timing_highlights`
- `diagnostics.routing.segment_details`
- `diagnostics.routing.chunk_details`

## How To Use It

For a 10+ minute render that takes hours, inspect these first:

1. If `chunks.fast_path_rate` is low, most time is still going through MoviePy chunk rendering.
2. If `segments.top_blockers` is dominated by `transition:*`, simplify long-video transitions or add an FFmpeg transition route.
3. If `segments.top_blockers` includes `overlay:text`, move more title styles into cacheable card/overlay routes.
4. If `recommendations` includes `enable_hardware_encoder_auto`, final encoding is still CPU-bound.
5. If `timing_highlights.top_steps` points to chunk rendering, improve route coverage before tuning final encoding.

