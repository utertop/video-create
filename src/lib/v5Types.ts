export type AspectRatio = "16:9" | "9:16";
export type Quality = "draft" | "standard" | "high";
export type PythonQuality = "normal" | "high" | "ultra";
export type RenderEngine = "auto" | "ffmpeg_concat" | "moviepy_crossfade";
// Performance mode may simplify execution paths for stability, but it should
// not silently remove audible BGM, source audio, or overall emotional intent.
export type PerformanceMode = "stable" | "balanced" | "quality";
export type MusicMode = "off" | "auto" | "manual";
export type MusicFitStrategy = "auto" | "loop" | "trim" | "intro_loop_outro" | "once";
export type MusicPlaylistMode = "single" | "auto_playlist" | "manual_playlist" | "chapter_restart";
export type EditStrategy =
  | "smart_director"
  | "fast_assembly"
  | "travel_soft"
  | "beat_cut"
  | "documentary"
  | "long_stable";

// =========================
// V5 common type definitions
// =========================

export type V5DocumentType = "media_library" | "story_blueprint" | "render_plan" | "timeline";
export type V5DirectoryType = "city" | "date" | "scenic_spot" | "chapter" | "unknown";
export type V5AssetType = "image" | "video" | "audio";
export type V5Orientation = "landscape" | "portrait" | "square";
export type V5StorySectionType = "city" | "date" | "scenic_spot" | "chapter" | "opening" | "ending" | string;
export type V5AssetRole = "opening" | "normal" | "highlight";
export type V5DurationPolicy = "auto" | "custom";
export type V5RenderSegmentType = "title" | "chapter" | "video" | "image" | "end";
export type V5ChapterBackgroundMode = "auto_bridge" | "auto_first_asset" | "custom_asset" | "plain";
export type V5SectionTitleMode = "full_card" | "overlay";
export type V5TitlePreset =
  | "cinematic_bold"
  | "travel_postcard"
  | "playful_pop"
  | "impact_flash"
  | "minimal_editorial"
  | "nature_documentary"
  | "romantic_soft"
  | "tech_future"
  | "documentary_lower_third"
  | "handwritten_note"
  | "neon_night"
  | "film_subtitle"
  | "route_marker"
  | string;
export type V5TitleMotion =
  | "fade_only"
  | "fade_slide_up"
  | "soft_zoom_in"
  | "pop_bounce"
  | "quick_zoom_punch"
  | "slow_fade_zoom"
  | "cinematic_reveal"
  | "postcard_drift"
  | "playful_bounce"
  | "impact_slam"
  | "editorial_fade"
  | "lower_third_slide"
  | "handwritten_draw"
  | "neon_flicker"
  | "film_burn"
  | "route_trace"
  | "static_hold"
  | string;

export const V5_SCHEMA_VERSION = "5.5";
export const V5_TIMELINE_VERSION = "v1";

// =========================
// V5 data structure definitions
// =========================

export type V5TimelineVersion = typeof V5_TIMELINE_VERSION | string;
export type V5TimelineTrackKind = "video" | "audio" | "title" | "subtitle" | "overlay";
export type V5TimelineClipKind =
  | "video_asset"
  | "image_asset"
  | "title_card"
  | "chapter_card"
  | "subtitle_overlay"
  | "audio_bgm"
  | "audio_source"
  | "audio_effect";
export type V5TimelineDependencyKind =
  | "derived_from_section"
  | "derived_from_asset"
  | "overlay_of"
  | "audio_sync_to"
  | "paired_with"
  | "generated_from_template";
export type V5TimelineRecomputeScope =
  | "none"
  | "preview_only"
  | "clip_only"
  | "track_only"
  | "timeline_compile"
  | "final_render_only"
  | "full_rebuild";
export type V5TimelinePreviewMode = "proxy" | "low_res" | "original";
export type V5TimelineCacheNamespace = "preview" | "final" | "thumbnail" | "proxy";

export interface V5Timeline {
  schema_version: string;
  document_type: "timeline";
  timeline_version: V5TimelineVersion;
  project_ref: V5TimelineProjectRef;
  source_ref: V5TimelineSourceRef;
  tracks: V5TimelineTrack[];
  clip_index: Record<string, V5TimelineClip>;
  dependency_graph?: V5TimelineDependency[];
  invalidation_rules_version?: string;
  performance_policy?: V5TimelinePerformancePolicy;
  metadata?: V5TimelineMetadata;
}

export interface V5TimelineProjectRef {
  project_id?: string | null;
  project_dir?: string | null;
  title?: string | null;
}

export interface V5TimelineSourceRef {
  media_library_path?: string | null;
  story_blueprint_path?: string | null;
  render_plan_path?: string | null;
  generated_from_blueprint: boolean;
  generated_at?: string | null;
}

export interface V5TimelineTrack {
  track_id: string;
  kind: V5TimelineTrackKind;
  name: string;
  order_index: number;
  enabled: boolean;
  locked?: boolean;
  lane_mode?: "single" | "stacked";
  clip_ids: string[];
  metadata?: Record<string, unknown>;
}

export interface V5TimelineClip {
  clip_id: string;
  kind: V5TimelineClipKind;
  track_id: string;

  /** Position and duration on the editable timeline. */
  timeline_start: number;
  timeline_duration: number;
  timeline_end: number;

  /** Optional in/out range inside the original source media. */
  source_in?: number | null;
  source_out?: number | null;
  playback_rate?: number | null;

  enabled: boolean;
  source_ref?: V5TimelineClipSourceRef | null;
  content_ref?: V5TimelineContentRef | null;
  edit_state?: V5TimelineEditState;
  presentation?: V5TimelinePresentation;
  execution?: V5TimelineExecutionHint;
  invalidation_hint?: V5TimelineInvalidationHint;
  cache_policy?: V5TimelineClipCachePolicy;
  metadata?: Record<string, unknown>;
}

export interface V5TimelineClipSourceRef {
  section_id?: string | null;
  asset_id?: string | null;
  segment_id?: string | null;
  directory_node_id?: string | null;
}

export interface V5TimelineContentRef {
  source_path?: string | null;
  title_text?: string | null;
  subtitle_text?: string | null;
  audio_profile?: string | null;
  template_id?: string | null;
}

export interface V5TimelineEditState {
  auto_generated: boolean;
  user_overridden: boolean;
  override_fields?: string[] | null;
  origin?: "plan" | "timeline_edit" | "migration" | "recovery" | string;
  last_edited_at?: string | null;
}

export interface V5TimelinePresentation {
  title_style?: V5TitleStyle | null;
  transition_type?: string | null;
  transition_duration?: number | null;
  motion_config?: Record<string, unknown> | null;
  background_mode?: string | null;
  background_source_path?: string | null;
}

export interface V5TimelineExecutionHint {
  preferred_route?: string | null;
  route_reason?: string | null;
  cache_key?: string | null;
  preview_supported?: boolean | null;
  final_render_supported?: boolean | null;
}

export interface V5TimelineInvalidationHint {
  primary_scope: V5TimelineRecomputeScope;
  affected_track_ids?: string[] | null;
  affected_clip_ids?: string[] | null;
  cache_reuse_expected?: boolean | null;
  requires_render_plan_recompile?: boolean;
  requires_audio_relayout?: boolean;
  reason?: string | null;
}

export interface V5TimelineClipCachePolicy {
  cache_namespace?: V5TimelineCacheNamespace;
  cache_fingerprint?: string | null;
  cache_reuse_expected?: boolean | null;
}

export interface V5TimelineDependency {
  dependency_id: string;
  from_clip_id: string;
  to_clip_id?: string | null;
  kind: V5TimelineDependencyKind;
  source_section_id?: string | null;
  source_asset_id?: string | null;
  strict: boolean;
  reason?: string | null;
}

export interface V5TimelinePerformancePolicy {
  preview: {
    mode: V5TimelinePreviewMode;
    height?: number;
    fps?: number;
    cache_namespace: "preview";
    preferred_backend?: string | null;
  };
  final: {
    uses_original_source: true;
    allow_proxy: false;
    cache_namespace: "final";
    preferred_backend?: string | null;
  };
  thumbnail?: {
    cache_namespace: "thumbnail";
  };
  proxy?: {
    cache_namespace: "proxy";
  };
  cache_fingerprint_version: string;
}

export interface V5TimelineMetadata {
  created_at?: string | null;
  updated_at?: string | null;
  generated_from?: "blueprint" | "migration" | "recovery" | string;
  editor_mode?: "auto" | "guided" | "manual" | string;
  migration_notes?: string[] | null;
  dirty?: boolean;
  dirty_reason?: string | null;
  last_edit_operation?: string | null;
}

export interface V5MediaLibrary {
  schema_version: string;
  document_type: "media_library";
  project: {
    source_root: string;
    scan_time: string;
    project_title?: string | null;
  };
  directory_nodes: V5DirectoryNode[];
  assets: V5Asset[];
  summary: {
    total_assets: number;
    image_count: number;
    video_count: number;
    audio_count?: number;
    skipped_count?: number;
    error_count?: number;
  };
}

export interface V5DirectoryNode {
  node_id: string;
  name: string;
  relative_path: string;
  depth: number;
  parent_id: string | null;
  detected_type: V5DirectoryType;
  confidence: number;
  reason: string;
  display_title: string;
  raw_detected_type?: string | null;
  signals?: Record<string, unknown>;
  user_override_fields?: string[];
  asset_count: number;
  children: string[];

  /** True when detected by scan/plan automatically. */
  auto_detected?: boolean;
  /** True after the user manually edits the detected type/title/order in GUI. */
  user_overridden?: boolean;
}

export interface V5Asset {
  asset_id: string;
  type: V5AssetType;
  relative_path: string;
  absolute_path: string;

  /** Preferred thumbnail field returned by Python V5 scan. */
  thumbnail_path?: string | null;
  /** Backward-compatible alias for older event/material payloads. */
  thumbnail?: string | null;

  file: {
    name: string;
    extension: string;
    size_bytes: number;
    modified_time: string;
  };
  media: {
    width: number | null;
    height: number | null;
    orientation: V5Orientation | null;
    shooting_date: string | null;
    duration?: number | null;
    duration_seconds?: number | null;
    sample_rate?: number | null;
    channels?: number | null;
    audio_codec?: string | null;
  };
  classification: {
    directory_node_id: string;
    city: string | null;
    scenic_spot: string | null;
    date?: string | null;
  };
  status?: "ready" | "skipped" | "error" | {
    state?: "ready" | "skipped" | "error";
    message?: string | null;
  };
  cache?: V5CacheEntry | null;
}

export interface V5StoryBlueprint {
  schema_version: string;
  document_type: "story_blueprint";
  title: string;
  subtitle: string;
  sections: V5StorySection[];
  strategy: string;
  metadata?: {
    created_at?: string;
    updated_at?: string;
    source_library_path?: string;
    edit_strategy?: EditStrategy;
    transition_profile?: string | null;
    rhythm_profile?: string | null;
    performance_mode?: PerformanceMode | string | null;
    chapter_background_mode?: V5ChapterBackgroundMode;
    /** auto | standard | long_stable. Auto uses V5.6 chunk rendering for long timelines. */
    render_mode?: string | null;
    /** Chunk size in seconds for V5.6 long-video stable renderer. */
    chunk_seconds?: number | null;
    audio?: V5AudioSettings | null;
    audio_blueprint?: V5AudioBlueprint | null;
    scenic_spot_title_mode?: V5SectionTitleMode;
    title_style?: V5TitleStyle | null;
    end_title_style?: V5TitleStyle | null;
    default_title_style?: V5TitleStyle | null;
  };
}

export interface V5StorySection {
  section_id: string;
  section_type: V5StorySectionType;
  title: string;
  subtitle: string | null;
  enabled: boolean;
  source_node_id: string | null;
  asset_refs: V5AssetRef[];
  children: V5StorySection[];

  auto_detected?: boolean;
  user_overridden?: boolean;
  order_index?: number;
  rhythm?: "slow" | "standard" | "fast";
  title_mode?: V5SectionTitleMode;
  title_style?: V5TitleStyle | null;
  background?: V5SectionBackground | null;
}

export interface V5TitleStyle {
  preset?: V5TitlePreset;
  motion?: V5TitleMotion;
  color_theme?: string | null;
  position?: string | null;
}

export interface V5SectionBackground {
  /**
   * auto_bridge: use previous visual frame + current section first frame.
   * auto_first_asset: use the first visual asset in this section.
   * custom_asset: use custom_path/custom_asset_id selected in GUI.
   * plain: use solid brand background.
   */
  mode: V5ChapterBackgroundMode;
  custom_asset_id?: string | null;
  custom_path?: string | null;
  user_overridden?: boolean;
}

export interface V5AssetRef {
  asset_id: string;
  enabled: boolean;
  role: V5AssetRole;
  duration_policy: V5DurationPolicy;
  custom_duration: number | null;
  keep_audio: boolean;
  order_index?: number;
  user_overridden?: boolean;
}

export interface V5RenderPlan {
  schema_version: string;
  document_type: "render_plan";
  output_path: string;
  total_duration: number;
  segments: V5RenderSegment[];
  render_settings?: V5RenderSettings;
  render_scheduler?: V5RenderSchedulerSummary;
  cache_policy?: V5CachePolicy;
  metadata?: {
    generated_at?: string;
    source_blueprint_path?: string;
    source_library_path?: string;
  };
}

export interface V5RenderSegment {
  segment_id: string;
  type: V5RenderSegmentType;
  source_path: string | null;
  duration: number;
  text: string | null;
  subtitle: string | null;
  start_time: number;
  end_time: number;
  section_id?: string | null;
  asset_id?: string | null;
  transition?: string;
  transition_config?: V5TransitionConfig | null;
  motion_config?: V5MotionConfig | null;
  rhythm_config?: V5RhythmConfig | null;
  background?: "blur" | "black" | "solid";
  background_mode?: "plain" | "auto_first_asset" | "bridge_blur" | "custom_blur";
  background_source_path?: string | null;
  background_source_position?: "first" | "last" | "middle" | null;
  background_source_path_2?: string | null;
  background_source_position_2?: "first" | "last" | "middle" | null;
  overlay_text?: string | null;
  overlay_subtitle?: string | null;
  overlay_duration?: number | null;
  keep_audio?: boolean;
  cache_key?: string | null;
  render_route?: string | null;
  render_route_reason?: string | null;
  render_route_tags?: string[] | null;
}

export interface V5RenderSchedulerSummary {
  strategy_version?: string;
  route_counts?: Record<string, number>;
  total_segments?: number;
  total_duration?: number;
}

export interface V5TransitionConfig {
  type: string;
  duration: number;
  profile?: string | null;
  strategy?: EditStrategy | string;
  scope?: "boundary" | "asset" | string;
  reason?: string;
}

export interface V5MotionConfig {
  type: string;
  intensity?: "none" | "low" | "soft" | "medium" | "high" | string;
  strategy?: EditStrategy | string;
  apply_to?: V5RenderSegmentType | string;
  overlay_safe?: boolean;
  reason?: string;
}

export interface V5RhythmConfig {
  role: string;
  pace: string;
  importance?: number;
  profile?: string | null;
  strategy?: EditStrategy | string;
  section_type?: V5StorySectionType | string;
}

export interface V5RenderSettings {
  aspect_ratio: AspectRatio;
  quality: Quality;
  python_quality?: PythonQuality;
  fps?: number;
  preview?: boolean;
  preview_height?: number;
  hardware_encoder?: "off" | "auto" | "nvenc" | "qsv" | "amf" | "videotoolbox" | string;
  watermark?: string;
  engine?: RenderEngine;
  edit_strategy?: EditStrategy;
  transition_profile?: string | null;
  rhythm_profile?: string | null;
  performance_mode?: PerformanceMode | string | null;
  render_mode?: string | null;
  chunk_seconds?: number | null;
  audio?: V5AudioSettings | null;
  audio_blueprint?: V5AudioBlueprint | null;
  cover?: boolean;
}

export interface V5AudioSettings {
  /** Mix strategy can switch execution paths, but should preserve the intended music/original-audio presence. */
  music_mode: MusicMode;
  music_path?: string | null;
  music_source?: "none" | "library" | "manual" | string;
  music_profile?: string | null;
  music_fit_strategy?: MusicFitStrategy | string;
  music_playlist_mode?: MusicPlaylistMode | string;
  music_playlist_paths?: string[] | null;
  music_chapter_restart?: boolean;
  estimated_video_duration?: number | null;
  bgm_volume: number;
  source_audio_volume: number;
  keep_source_audio: boolean;
  auto_ducking: boolean;
  fade_in_seconds: number;
  fade_out_seconds: number;
  normalize_audio?: boolean;
  target_lufs?: number;
}

export interface V5AudioBlueprintCandidateAsset {
  asset_id?: string | null;
  relative_path?: string | null;
  absolute_path?: string | null;
  duration_seconds?: number | null;
  score?: number | null;
}

export interface V5AudioBlueprintCue {
  section_id?: string | null;
  title?: string | null;
  section_type?: string | null;
  order?: number | null;
  phase?: string | null;
  energy?: string | null;
  asset_count?: number | null;
  estimated_duration_seconds?: number | null;
  ducking_hint?: string | null;
  reason?: string | null;
  start_time?: number | null;
  end_time?: number | null;
  duration?: number | null;
}

export interface V5AudioBlueprintAdoptionState {
  source?: boolean;
  mix?: boolean;
  timing?: boolean;
  all?: boolean;
  applied_scopes?: string[] | null;
  updated_at?: string | null;
}

export interface V5AudioBlueprint {
  version?: number;
  mode?: string | null;
  template_id?: string | null;
  music_profile?: string | null;
  energy_curve_style?: string | null;
  estimated_project_duration_seconds?: number | null;
  longform_project?: boolean;
  selected_candidate?: V5AudioBlueprintCandidateAsset | null;
  candidate_assets?: V5AudioBlueprintCandidateAsset[] | null;
  search_keywords?: string[] | null;
  section_cues?: V5AudioBlueprintCue[] | null;
  timeline_cues?: V5AudioBlueprintCue[] | null;
  recommended_audio_settings?: Partial<V5AudioSettings> | null;
  adopted_audio_settings?: Partial<V5AudioSettings> | null;
  ui_adoption_state?: V5AudioBlueprintAdoptionState | null;
  origin_summary?: string | null;
  activation_hint?: string | null;
}

export interface V5CachePolicy {
  enabled: boolean;
  cache_root?: string;
  invalidation_keys: Array<"file_path" | "file_size" | "mtime" | "render_params" | "engine_version" | string>;
}

export interface V5CacheEntry {
  cache_key: string;
  fixed_image_path?: string | null;
  thumbnail_path?: string | null;
  segment_path?: string | null;
  generated_at?: string;
}

