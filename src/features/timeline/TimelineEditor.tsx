import { useMemo, useState } from "react";
import type { V5RenderPlan, V5RenderSegment, V5Timeline, V5TimelineClip, V5TimelineTrack } from "../../lib/engine";
import { TimelineInspector } from "./TimelineInspector";
import {
  moveClip,
  updateBgmCueVolume,
  updateClipContent,
  updateClipDuration,
  updateClipEnabled,
  updateClipPresentation,
} from "./timelineOps";
import { TimelineRuler } from "./TimelineRuler";
import { TimelineTrack } from "./TimelineTrack";

interface TimelineEditorProps {
  timeline: V5Timeline | null;
  renderPlan: V5RenderPlan | null;
  activeSegmentIndex: number | null;
  isRendering: boolean;
  selectedSectionId: string | null;
  onSelectSection: (sectionId: string | null) => void;
  onTimelineChange?: (timeline: V5Timeline) => void;
}

interface TimelineViewModel {
  source: "timeline" | "render_plan";
  tracks: V5TimelineTrack[];
  clipIndex: Record<string, V5TimelineClip>;
  duration: number;
  clipCount: number;
}

export function TimelineEditor({
  timeline,
  renderPlan,
  activeSegmentIndex,
  isRendering,
  selectedSectionId,
  onSelectSection,
  onTimelineChange,
}: TimelineEditorProps) {
  const viewModel = useMemo(() => buildTimelineViewModel(timeline, renderPlan), [timeline, renderPlan]);
  const [selectedClipId, setSelectedClipId] = useState<string | null>(null);
  const [draggingClipId, setDraggingClipId] = useState<string | null>(null);
  const [dragOverClipId, setDragOverClipId] = useState<string | null>(null);
  const selectedClip = selectedClipId ? viewModel.clipIndex[selectedClipId] || null : null;
  const selectedTrack = selectedClip ? viewModel.tracks.find((track) => track.track_id === selectedClip.track_id) || null : null;
  const editable = Boolean(timeline && onTimelineChange && viewModel.source === "timeline");
  const activeSegmentId =
    isRendering && activeSegmentIndex !== null && renderPlan?.segments?.[activeSegmentIndex]
      ? renderPlan.segments[activeSegmentIndex].segment_id
      : null;
  const pixelsPerSecond = resolvePixelsPerSecond(viewModel.duration);

  if (!renderPlan && !timeline) return null;

  const commitTimeline = (nextTimeline: V5Timeline) => {
    onTimelineChange?.(nextTimeline);
  };

  const handleMoveClip = (clipId: string, targetIndex: number) => {
    if (!timeline || !editable) return;
    commitTimeline(moveClip(timeline, clipId, targetIndex));
  };

  const handleDrop = (targetClipId: string) => {
    if (!timeline || !editable || !draggingClipId || draggingClipId === targetClipId) {
      setDraggingClipId(null);
      setDragOverClipId(null);
      return;
    }
    const targetTrack = viewModel.tracks.find((track) => track.clip_ids.includes(targetClipId));
    if (!targetTrack || !targetTrack.clip_ids.includes(draggingClipId)) {
      setDraggingClipId(null);
      setDragOverClipId(null);
      return;
    }
    const targetIndex = targetTrack.clip_ids.indexOf(targetClipId);
    commitTimeline(moveClip(timeline, draggingClipId, targetIndex));
    setSelectedClipId(draggingClipId);
    setDraggingClipId(null);
    setDragOverClipId(null);
  };

  return (
    <div className="timeline-editor-shell">
      <div className="timeline-editor-head">
        <div>
          <strong>{viewModel.source === "timeline" ? "Timeline" : "Render Plan Fallback"}</strong>
          <span>
            {viewModel.tracks.length} tracks · {viewModel.clipCount} clips · {viewModel.duration.toFixed(1)}s
          </span>
        </div>
        <span className={`timeline-source-badge ${viewModel.source}`}>
          {viewModel.source === "timeline" ? "v5Timeline" : "segments fallback"}
        </span>
      </div>

      <div className="timeline-editor-grid">
        <div className="timeline-scroll-surface">
          <TimelineRuler duration={viewModel.duration} pixelsPerSecond={pixelsPerSecond} />
          <div className="timeline-track-list">
            {viewModel.tracks.map((track) => {
              const clips = track.clip_ids
                .map((clipId) => viewModel.clipIndex[clipId])
                .filter((clip): clip is V5TimelineClip => Boolean(clip));
              return (
                <TimelineTrack
                  key={track.track_id}
                  track={track}
                  clips={clips}
                  duration={viewModel.duration}
                  pixelsPerSecond={pixelsPerSecond}
                  selectedClipId={selectedClipId}
                  activeSegmentId={activeSegmentId}
                  selectedSectionId={selectedSectionId}
                  editable={editable}
                  draggingClipId={draggingClipId}
                  dragOverClipId={dragOverClipId}
                  onSelectClip={(clip) => setSelectedClipId(clip.clip_id)}
                  onSelectSection={onSelectSection}
                  onDragStart={(clipId) => setDraggingClipId(clipId)}
                  onDragOver={(clipId) => setDragOverClipId(clipId)}
                  onDrop={handleDrop}
                  onDragEnd={() => {
                    setDraggingClipId(null);
                    setDragOverClipId(null);
                  }}
                />
              );
            })}
          </div>
        </div>
        <TimelineInspector
          clip={selectedClip}
          editable={editable}
          trackClipIds={selectedTrack?.clip_ids || []}
          onUpdateEnabled={(clipId, enabled) => {
            if (timeline) commitTimeline(updateClipEnabled(timeline, clipId, enabled));
          }}
          onUpdateContent={(clipId, patch) => {
            if (timeline) commitTimeline(updateClipContent(timeline, clipId, patch));
          }}
          onUpdatePresentation={(clipId, patch) => {
            if (timeline) commitTimeline(updateClipPresentation(timeline, clipId, patch));
          }}
          onUpdateDuration={(clipId, duration) => {
            if (timeline) commitTimeline(updateClipDuration(timeline, clipId, duration));
          }}
          onUpdateBgmVolume={(clipId, volume) => {
            if (timeline) commitTimeline(updateBgmCueVolume(timeline, clipId, volume));
          }}
          onMoveClip={handleMoveClip}
        />
      </div>
    </div>
  );
}

function buildTimelineViewModel(timeline: V5Timeline | null, renderPlan: V5RenderPlan | null): TimelineViewModel {
  if (timeline && Array.isArray(timeline.tracks) && timeline.tracks.length > 0) {
    const clips = Object.values(timeline.clip_index || {});
    return {
      source: "timeline",
      tracks: [...timeline.tracks].sort((a, b) => a.order_index - b.order_index),
      clipIndex: timeline.clip_index || {},
      duration: Math.max(renderPlan?.total_duration || 0, ...clips.map((clip) => Number(clip.timeline_end || 0)), 1),
      clipCount: clips.length,
    };
  }

  return buildFallbackTimelineViewModel(renderPlan);
}

function buildFallbackTimelineViewModel(renderPlan: V5RenderPlan | null): TimelineViewModel {
  const segments = renderPlan?.segments || [];
  const tracks: V5TimelineTrack[] = [
    { track_id: "fallback_video_main", kind: "video", name: "Render Segments", order_index: 0, enabled: segments.length > 0, clip_ids: [] },
  ];
  const clipIndex: Record<string, V5TimelineClip> = {};

  segments.forEach((segment, index) => {
    const clip = fallbackClipFromSegment(segment, index);
    clipIndex[clip.clip_id] = clip;
    tracks[0].clip_ids.push(clip.clip_id);
  });

  return {
    source: "render_plan",
    tracks,
    clipIndex,
    duration: Math.max(renderPlan?.total_duration || 0, ...segments.map((segment) => Number(segment.end_time || 0)), 1),
    clipCount: segments.length,
  };
}

function fallbackClipFromSegment(segment: V5RenderSegment, index: number): V5TimelineClip {
  const start = Number(segment.start_time || 0);
  const duration = Number(segment.duration || Math.max(0, Number(segment.end_time || 0) - start));
  const end = Number(segment.end_time || start + duration);
  const kind = segment.type === "video"
    ? "video_asset"
    : segment.type === "image"
      ? "image_asset"
      : segment.type === "chapter"
        ? "chapter_card"
        : "title_card";

  return {
    clip_id: `fallback_${segment.segment_id || index}`,
    kind,
    track_id: "fallback_video_main",
    timeline_start: start,
    timeline_duration: duration,
    timeline_end: end,
    source_in: segment.type === "video" || segment.type === "image" ? 0 : null,
    source_out: segment.type === "video" || segment.type === "image" ? duration : null,
    playback_rate: 1,
    enabled: true,
    source_ref: {
      section_id: segment.section_id || null,
      asset_id: segment.asset_id || null,
      segment_id: segment.segment_id,
      directory_node_id: null,
    },
    content_ref: {
      source_path: segment.source_path || null,
      title_text: segment.text || segment.overlay_text || null,
      subtitle_text: segment.subtitle || segment.overlay_subtitle || null,
      audio_profile: null,
      template_id: null,
    },
    execution: {
      preferred_route: segment.render_route || null,
      route_reason: segment.render_route_reason || null,
      cache_key: segment.cache_key || null,
      preview_supported: true,
      final_render_supported: true,
    },
    invalidation_hint: {
      primary_scope: kind === "title_card" || kind === "chapter_card" ? "clip_only" : "timeline_compile",
      affected_clip_ids: [`fallback_${segment.segment_id || index}`],
      affected_track_ids: ["fallback_video_main"],
      cache_reuse_expected: true,
      requires_render_plan_recompile: kind !== "title_card" && kind !== "chapter_card",
      requires_audio_relayout: false,
      reason: "readonly render_plan fallback clip",
    },
    cache_policy: {
      cache_namespace: "final",
      cache_fingerprint: segment.cache_key || null,
      cache_reuse_expected: true,
    },
  };
}

function resolvePixelsPerSecond(duration: number): number {
  if (duration >= 1800) return 1.2;
  if (duration >= 900) return 1.8;
  if (duration >= 360) return 3;
  if (duration >= 120) return 5;
  return 8;
}
