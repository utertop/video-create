import type {
  V5Timeline,
  V5TimelineClip,
  V5TimelineContentRef,
  V5TimelinePresentation,
} from "../../lib/engine";
import { resolveRecomputeScope, type TimelineEditOperation } from "./timelineInvalidation";

export function updateClipEnabled(timeline: V5Timeline, clipId: string, enabled: boolean): V5Timeline {
  return applyClipEdit(
    timeline,
    clipId,
    (clip) => ({ ...clip, enabled }),
    ["enabled"],
    { type: "clip_enable_disable", clip_id: clipId },
  );
}

export function updateClipContent(
  timeline: V5Timeline,
  clipId: string,
  patch: Partial<V5TimelineContentRef>,
): V5Timeline {
  const operationType = patch.subtitle_text !== undefined && patch.title_text === undefined
    ? "subtitle_text_change"
    : "title_text_change";
  return applyClipEdit(
    timeline,
    clipId,
    (clip) => ({
      ...clip,
      content_ref: {
        ...(clip.content_ref || {}),
        ...patch,
      },
    }),
    Object.keys(patch).map((key) => `content_ref.${key}`),
    { type: operationType, clip_id: clipId },
  );
}

export function updateClipPresentation(
  timeline: V5Timeline,
  clipId: string,
  patch: Partial<V5TimelinePresentation>,
): V5Timeline {
  return applyClipEdit(
    timeline,
    clipId,
    (clip) => ({
      ...clip,
      presentation: {
        ...(clip.presentation || {}),
        ...patch,
      },
    }),
    Object.keys(patch).map((key) => `presentation.${key}`),
    { type: "title_style_change", clip_id: clipId },
  );
}

export function updateClipDuration(timeline: V5Timeline, clipId: string, duration: number): V5Timeline {
  const location = findClipLocation(timeline, clipId);
  if (!location) return timeline;
  const currentClip = timeline.clip_index[clipId];
  if (!currentClip) return timeline;
  const currentDuration = Number(currentClip.timeline_duration || 0);
  const nextDuration = Number.isFinite(duration) ? Math.max(0.1, roundTime(duration)) : currentDuration;
  if (!Number.isFinite(nextDuration)) return timeline;
  const delta = nextDuration - currentDuration;
  const affectedIds = location.track.clip_ids.slice(location.index);
  const now = new Date().toISOString();
  const clipIndex = { ...timeline.clip_index };

  for (const id of affectedIds) {
    const clip = clipIndex[id];
    if (!clip) continue;
    if (id === clipId) {
      const sourceIn = Number(clip.source_in);
      clipIndex[id] = withEditMetadata(
        {
          ...clip,
          timeline_duration: nextDuration,
          timeline_end: roundTime(clip.timeline_start + nextDuration),
          source_out: Number.isFinite(sourceIn) ? roundTime(sourceIn + nextDuration) : clip.source_out,
        },
        ["timeline_duration", "timeline_end", "source_out"],
        now,
        {
          type: "image_duration_change",
          clip_id: clipId,
          track_id: location.track.track_id,
          affected_clip_ids: affectedIds,
          affected_track_ids: [location.track.track_id],
        },
      );
    } else {
      clipIndex[id] = {
        ...clip,
        timeline_start: roundTime(clip.timeline_start + delta),
        timeline_end: roundTime(clip.timeline_end + delta),
      };
    }
  }

  return markTimelineDirty({ ...timeline, clip_index: clipIndex }, "image_duration_change", now);
}

export function moveClip(timeline: V5Timeline, clipId: string, targetIndex: number): V5Timeline {
  const location = findClipLocation(timeline, clipId);
  if (!location) return timeline;

  const currentIds = [...location.track.clip_ids];
  currentIds.splice(location.index, 1);
  const clampedIndex = Math.max(0, Math.min(targetIndex, currentIds.length));
  currentIds.splice(clampedIndex, 0, clipId);

  const now = new Date().toISOString();
  const tracks = timeline.tracks.map((track) =>
    track.track_id === location.track.track_id ? { ...track, clip_ids: currentIds } : track,
  );
  const clipIndex = relayoutTrackClips(
    { ...timeline.clip_index },
    currentIds,
    location.track.track_id,
    now,
    {
      type: "clip_reorder",
      clip_id: clipId,
      track_id: location.track.track_id,
      affected_clip_ids: currentIds,
      affected_track_ids: [location.track.track_id],
    },
  );

  return markTimelineDirty({ ...timeline, tracks, clip_index: clipIndex }, "clip_reorder", now);
}

export function updateBgmCueVolume(timeline: V5Timeline, clipId: string, volume: number): V5Timeline {
  const safeVolume = Math.max(0, Math.min(1, Number.isFinite(volume) ? volume : 0));
  return applyClipEdit(
    timeline,
    clipId,
    (clip) => ({
      ...clip,
      metadata: {
        ...(clip.metadata || {}),
        bgm_volume: safeVolume,
      },
    }),
    ["metadata.bgm_volume"],
    { type: "bgm_volume_change", clip_id: clipId },
  );
}

function applyClipEdit(
  timeline: V5Timeline,
  clipId: string,
  updater: (clip: V5TimelineClip) => V5TimelineClip,
  overrideFields: string[],
  operation: TimelineEditOperation,
): V5Timeline {
  const clip = timeline.clip_index[clipId];
  if (!clip) return timeline;
  const now = new Date().toISOString();
  const nextClip = withEditMetadata(updater(clip), overrideFields, now, operation);
  return markTimelineDirty(
    {
      ...timeline,
      clip_index: {
        ...timeline.clip_index,
        [clipId]: nextClip,
      },
    },
    operation.type,
    now,
  );
}

function withEditMetadata(
  clip: V5TimelineClip,
  overrideFields: string[],
  now: string,
  operation: TimelineEditOperation,
): V5TimelineClip {
  const previousFields = clip.edit_state?.override_fields || [];
  const mergedFields = Array.from(new Set([...previousFields, ...overrideFields].filter(Boolean)));
  return {
    ...clip,
    edit_state: {
      ...(clip.edit_state || { auto_generated: true }),
      auto_generated: false,
      user_overridden: true,
      override_fields: mergedFields,
      origin: "timeline_edit",
      last_edited_at: now,
    },
    invalidation_hint: resolveRecomputeScope({ operation, clip }),
  };
}

function markTimelineDirty(timeline: V5Timeline, operationType: string, now: string): V5Timeline {
  return {
    ...timeline,
    metadata: {
      ...(timeline.metadata || {}),
      updated_at: now,
      editor_mode: "guided",
      dirty: true,
      dirty_reason: "timeline_edit",
      last_edit_operation: operationType,
    },
  };
}

function relayoutTrackClips(
  clipIndex: Record<string, V5TimelineClip>,
  clipIds: string[],
  trackId: string,
  now: string,
  operation: TimelineEditOperation,
): Record<string, V5TimelineClip> {
  let cursor = 0;
  for (const id of clipIds) {
    const clip = clipIndex[id];
    if (!clip) continue;
    const duration = Math.max(0, Number(clip.timeline_duration || 0));
    const relayout = {
      ...clip,
      timeline_start: roundTime(cursor),
      timeline_end: roundTime(cursor + duration),
    };
    clipIndex[id] = id === operation.clip_id
      ? withEditMetadata(relayout, ["track_order", "timeline_start", "timeline_end"], now, operation)
      : relayout;
    cursor += duration;
  }
  return clipIndex;
}

function findClipLocation(timeline: V5Timeline, clipId: string) {
  for (const track of timeline.tracks) {
    const index = track.clip_ids.indexOf(clipId);
    if (index >= 0) return { track, index };
  }
  return null;
}

function roundTime(value: number): number {
  return Math.round(value * 1000) / 1000;
}
