import type {
  V5TimelineClip,
  V5TimelineInvalidationHint,
  V5TimelineRecomputeScope,
} from "../../lib/engine";

export const TIMELINE_INVALIDATION_RULES_VERSION = "timeline_invalidation_v1";

export type TimelineEditOperationType =
  | "title_text_change"
  | "title_style_change"
  | "subtitle_text_change"
  | "clip_enable_disable"
  | "clip_enable_toggle"
  | "clip_reorder"
  | "clip_move"
  | "image_duration_change"
  | "clip_duration_change"
  | "bgm_volume_change"
  | "audio_volume_change"
  | "bgm_cue_range_change"
  | "audio_cue_range_change"
  | "preview_quality_change"
  | "preview_settings_change"
  | "final_quality_change"
  | "final_settings_change"
  | "aspect_ratio_change"
  | string;

export interface TimelineEditOperation {
  type: TimelineEditOperationType;
  clip_id?: string | null;
  track_id?: string | null;
  affected_clip_ids?: string[] | null;
  affected_track_ids?: string[] | null;
}

interface InvalidationInput {
  operation: TimelineEditOperation;
  clip?: V5TimelineClip | null;
}

const OPERATION_ALIASES: Record<string, string> = {
  title_text_change: "title_text_change",
  title_text: "title_text_change",
  title_style_change: "title_style_change",
  title_style: "title_style_change",
  subtitle_text_change: "subtitle_text_change",
  subtitle_text: "subtitle_text_change",
  clip_enable_disable: "clip_enable_disable",
  clip_enable_toggle: "clip_enable_disable",
  clip_enabled_change: "clip_enable_disable",
  clip_reorder: "clip_reorder",
  clip_move: "clip_reorder",
  image_duration_change: "image_duration_change",
  clip_duration_change: "image_duration_change",
  bgm_volume_change: "bgm_volume_change",
  audio_volume_change: "bgm_volume_change",
  bgm_cue_range_change: "bgm_cue_range_change",
  audio_cue_range_change: "bgm_cue_range_change",
  preview_quality_change: "preview_quality_change",
  preview_settings_change: "preview_quality_change",
  final_quality_change: "final_quality_change",
  final_settings_change: "final_quality_change",
  aspect_ratio_change: "aspect_ratio_change",
};

export function resolveRecomputeScope(input: InvalidationInput): V5TimelineInvalidationHint {
  const operation = input.operation || { type: "unknown" };
  const clip = input.clip || null;
  const operationType = normalizeOperation(operation.type);
  const clipIds = uniqueStrings(operation.affected_clip_ids || [operation.clip_id || clip?.clip_id || null]);
  const trackIds = uniqueStrings(operation.affected_track_ids || [operation.track_id || clip?.track_id || null]);

  if (["title_text_change", "title_style_change", "subtitle_text_change"].includes(operationType)) {
    return hint("clip_only", clipIds, trackIds, {
      cacheReuseExpected: false,
      requiresRenderPlanRecompile: true,
      requiresAudioRelayout: false,
      reason: `${operationType} affects only the edited title/subtitle clip`,
    });
  }

  if (["clip_enable_disable", "clip_reorder", "image_duration_change"].includes(operationType)) {
    return hint("timeline_compile", clipIds, trackIds, {
      cacheReuseExpected: false,
      requiresRenderPlanRecompile: true,
      requiresAudioRelayout: false,
      reason: `${operationType} changes visual timeline structure or timing`,
    });
  }

  if (operationType === "bgm_volume_change") {
    return hint("track_only", clipIds, trackIds.length > 0 ? trackIds : ["track_audio_main"], {
      cacheReuseExpected: true,
      requiresRenderPlanRecompile: false,
      requiresAudioRelayout: false,
      reason: "bgm volume change affects audio mix only",
    });
  }

  if (operationType === "bgm_cue_range_change") {
    return hint("track_only", clipIds, trackIds.length > 0 ? trackIds : ["track_audio_main"], {
      cacheReuseExpected: false,
      requiresRenderPlanRecompile: false,
      requiresAudioRelayout: true,
      reason: "bgm cue range change affects audio timeline layout only",
    });
  }

  if (operationType === "preview_quality_change") {
    return hint("preview_only", [], [], {
      cacheReuseExpected: false,
      requiresRenderPlanRecompile: false,
      requiresAudioRelayout: false,
      reason: "preview quality change invalidates preview cache only",
    });
  }

  if (operationType === "final_quality_change") {
    return hint("final_render_only", [], [], {
      cacheReuseExpected: false,
      requiresRenderPlanRecompile: false,
      requiresAudioRelayout: false,
      reason: "final quality change invalidates final render cache only",
    });
  }

  if (operationType === "aspect_ratio_change") {
    return hint("full_rebuild", [], [], {
      cacheReuseExpected: false,
      requiresRenderPlanRecompile: true,
      requiresAudioRelayout: false,
      reason: "aspect ratio change affects project-wide visual geometry",
    });
  }

  return hint("full_rebuild", clipIds, trackIds, {
    cacheReuseExpected: false,
    requiresRenderPlanRecompile: true,
    requiresAudioRelayout: true,
    reason: `unknown timeline edit operation: ${operationType}`,
  });
}

export function withResolvedInvalidationHint(
  clip: V5TimelineClip,
  operation: TimelineEditOperation,
): V5TimelineClip {
  return {
    ...clip,
    invalidation_hint: resolveRecomputeScope({ operation, clip }),
  };
}

function normalizeOperation(type: TimelineEditOperationType): string {
  const key = String(type || "").trim();
  return OPERATION_ALIASES[key] || key || "unknown";
}

function hint(
  primaryScope: V5TimelineRecomputeScope,
  affectedClipIds: string[],
  affectedTrackIds: string[],
  options: {
    cacheReuseExpected: boolean;
    requiresRenderPlanRecompile: boolean;
    requiresAudioRelayout: boolean;
    reason: string;
  },
): V5TimelineInvalidationHint {
  return {
    primary_scope: primaryScope,
    affected_clip_ids: affectedClipIds,
    affected_track_ids: affectedTrackIds,
    cache_reuse_expected: options.cacheReuseExpected,
    requires_render_plan_recompile: options.requiresRenderPlanRecompile,
    requires_audio_relayout: options.requiresAudioRelayout,
    reason: options.reason,
  };
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  for (const value of values) {
    if (!value) continue;
    const text = String(value);
    if (seen.has(text)) continue;
    seen.add(text);
    result.push(text);
  }
  return result;
}
