import { invoke } from "@tauri-apps/api/core";

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

export interface GenerateVideoPayload {
  jobId?: string;
  inputPaths: string[];
  outputDir: string;
  title: string;
  titleSubtitle: string;
  endText: string;
  outputName: string;
  aspectRatio: AspectRatio;
  quality: Quality;
  watermark: string;
  recursive: boolean;
  chaptersFromDirs: boolean;
  cover: boolean;
  editStrategy?: EditStrategy;
  renderEngine: RenderEngine;
  dryRun?: boolean;
}

export interface GenerateVideoResult {
  ok: boolean;
  code?: string | null;
  message: string;
  commandPreview: string;
  outputPath?: string;
  outputDir?: string;
  cancelled?: boolean;
  isDryRun?: boolean;
  actionSuggestion?: string | null;
  recovery?: RenderRecoverySummary | null;
}

export interface StartupCheckItem {
  id: string;
  label: string;
  ok: boolean;
  code?: string | null;
  message: string;
  detail?: string | null;
}

export interface StartupDiagnostics {
  ok: boolean;
  code?: string | null;
  summary: string;
  checks: StartupCheckItem[];
}

export interface AppErrorInfo {
  code?: string | null;
  message: string;
  userMessage?: string | null;
  actionSuggestion?: string | null;
  detail?: string | null;
  raw?: string;
}

export interface AppErrorResolution {
  code?: string | null;
  technicalMessage: string;
  userMessage: string;
  actionSuggestion?: string | null;
}

export interface SessionSnapshotPayload {
  savedAt: string;
  data: Record<string, unknown>;
}

export interface ProjectStatePayload {
  savedAt: string;
  data: Record<string, unknown>;
}

export interface DiagnosticBundlePayload {
  generatedAt: string;
  data: Record<string, unknown>;
}

export interface ProjectDocumentsLoadResult {
  projectDir: string;
  migrated: boolean;
  migrationNotes: string[];
  library: V5MediaLibrary | null;
  blueprint: V5StoryBlueprint | null;
  renderPlan: V5RenderPlan | null;
  timeline: V5Timeline | null;
}

export type BuildReportJsonObject = Record<string, unknown>;

export interface BuildReportSuggestion extends BuildReportJsonObject {
  id?: string;
  priority?: string;
  message?: string;
}

export interface RenderRecoverySummary {
  reportPath: string;
  manifestPath?: string | null;
  buildReportVersion?: string | null;
  timelineSummary?: BuildReportJsonObject | null;
  routeSummary?: BuildReportJsonObject | null;
  fallbackSummary?: BuildReportJsonObject | null;
  cacheSummary?: BuildReportJsonObject | null;
  recomputeSummary?: BuildReportJsonObject | null;
  performanceSummary?: BuildReportJsonObject | null;
  qualitySummary?: BuildReportJsonObject | null;
  recoverySummary?: BuildReportJsonObject | null;
  migrationNotes?: string[] | null;
  reportSuggestions?: BuildReportSuggestion[] | null;
  status?: string | null;
  renderIntent?: string | null;
  renderMode?: string | null;
  failedStage?: string | null;
  outputPath?: string | null;
  selectedBackend?: string | null;
  actualBackend?: string | null;
  backendReason?: string | null;
  fallbackChain?: string[] | null;
  fallbackUsed?: string | null;
  fallbackReason?: string | null;
  fallbackApplied?: boolean;
  chunkCount?: number | null;
  segmentFastPathRate?: number | null;
  chunkFastPathRate?: number | null;
  segmentRouteDifferenceCount?: number | null;
  segmentRouteDifferenceRate?: number | null;
  createdAt?: string | null;
  resumable: boolean;
  resumedFromManifest: boolean;
  reusedChunkCount: number;
  completedChunkCount: number;
  failedChunkCount: number;
  reportedChunkCount: number;
  failedChunk?: string | null;
  failureCode?: string | null;
  failureMessage?: string | null;
  retryable: boolean;
}

export interface TelemetryCountEntry {
  key: string;
  count: number;
}

export interface TelemetryEventPayload {
  sessionId?: string | null;
  eventType: string;
  timestamp?: string | null;
  success?: boolean | null;
  firstExport?: boolean | null;
  errorCode?: string | null;
  supportQueue?: string | null;
  severity?: string | null;
  tags?: string[] | null;
  recoveryResumable?: boolean | null;
  recoveryRetryable?: boolean | null;
  recoveryCompletedChunks?: number | null;
  recoveryReusedChunks?: number | null;
}

export interface TelemetrySummary {
  telemetryEnabled: boolean;
  currentConsentVersion: string;
  consentAcceptedVersion?: string | null;
  remoteUploadEnabled: boolean;
  remoteEndpointConfigured: boolean;
  remoteEndpoint?: string | null;
  remoteEndpointHost?: string | null;
  pendingRemoteEvents: number;
  lastRemoteUploadAt?: string | null;
  lastRemoteUploadError?: string | null;
  sessionsStarted: number;
  sessionsCompletedCleanly: number;
  sessionsCrashed: number;
  crashFreeSessionRate: number;
  firstExportSessions: number;
  firstExportSuccesses: number;
  firstExportSuccessRate: number;
  renderAttempts: number;
  renderSuccesses: number;
  renderFailures: number;
  recoveryResumableEvents: number;
  recoveryRetryableEvents: number;
  topErrorCodes: TelemetryCountEntry[];
  topSupportQueues: TelemetryCountEntry[];
  topTags: TelemetryCountEntry[];
  topSeverities: TelemetryCountEntry[];
  recentEvents: Array<{
    sessionId?: string | null;
    eventType: string;
    timestamp: string;
    success?: boolean | null;
    errorCode?: string | null;
    supportQueue?: string | null;
    severity?: string | null;
    tags: string[];
    recoveryResumable: boolean;
    recoveryRetryable: boolean;
    recoveryCompletedChunks: number;
    recoveryReusedChunks: number;
  }>;
  lastUpdatedAt?: string | null;
}

export interface TelemetrySessionStartResponse {
  sessionId?: string | null;
  telemetryEnabled: boolean;
  previousSessionRecoveredAsCrash: boolean;
  summary: TelemetrySummary;
}

export interface TelemetrySettingsPayload {
  consentAcceptedVersion?: string | null;
  remoteUploadEnabled?: boolean | null;
  remoteEndpoint?: string | null;
}

export interface RenderV5Params {
  title?: string;
  title_subtitle?: string;
  /** Optional ending text. Real render text is compiled from story_blueprint before render. */
  end_text?: string | null;
  watermark?: string;
  aspect_ratio?: AspectRatio;
  quality?: Quality;
  python_quality?: PythonQuality;
  engine?: RenderEngine;
  performance_mode?: PerformanceMode;
  render_mode?: string | null;
  chunk_seconds?: number | null;
  stable_chunk_seconds?: number | null;
  edit_strategy?: EditStrategy;
  transition_profile?: string | null;
  rhythm_profile?: string | null;
  cover?: boolean;
  fps?: number;
  preview?: boolean;
  preview_height?: number;
  hardware_encoder?: "off" | "auto" | "nvenc" | "qsv" | "amf" | "videotoolbox" | string;

  /** Optional custom background image for the opening title card.
   * If omitted, the renderer uses the first visual frame in render_plan. */
  title_background_path?: string | null;
  title_style?: V5TitleStyle | null;

  /** Optional custom background image for the ending card.
   * If omitted, the renderer uses the last visual frame in render_plan. */
  end_background_path?: string | null;
  end_title_style?: V5TitleStyle | null;
  chapter_background_mode?: V5ChapterBackgroundMode;
  audio?: V5AudioSettings | null;
}

// =========================
// Legacy V3 engine calls
// =========================

export async function generateVideo(payload: GenerateVideoPayload): Promise<GenerateVideoResult> {
  try {
    return await invoke<GenerateVideoResult>("generate_video", { payload });
  } catch (error) {
    return {
      ok: false,
      message: formatInvokeError(error, "当前运行在浏览器预览模式，或 Tauri 后端尚未启动。"),
      commandPreview: buildCommandPreview(payload),
    };
  }
}

export async function cancelVideo(jobId: string): Promise<GenerateVideoResult> {
  try {
    return await invoke<GenerateVideoResult>("cancel_video", { jobId });
  } catch (error) {
    return {
      ok: false,
      message: formatInvokeError(error, "无法取消任务：Tauri 后端尚未响应。"),
      commandPreview: "",
    };
  }
}

export async function openInExplorer(path: string): Promise<void> {
  try {
    await invoke("open_in_explorer", { path });
  } catch (error) {
    console.error("Failed to open in explorer:", error);
  }
}

export async function startupSelfCheck(): Promise<StartupDiagnostics> {
  try {
    return await invoke<StartupDiagnostics>("startup_self_check");
  } catch (error) {
    return {
      ok: false,
      summary: formatInvokeError(error, "Startup self-check is unavailable."),
      checks: [
        {
          id: "startup_self_check",
          label: "Startup self-check",
          ok: false,
          message: formatInvokeError(error, "Tauri backend did not respond."),
          detail: null,
        },
      ],
    };
  }
}

export async function preflightRenderV5({
  inputFolder,
  outputDir,
  planPath,
  outputPath,
}: {
  inputFolder: string;
  outputDir: string;
  planPath: string;
  outputPath: string;
}): Promise<StartupDiagnostics> {
  try {
    return await invoke<StartupDiagnostics>("preflight_render_v5", {
      inputFolder,
      outputDir,
      planPath,
      outputPath,
    });
  } catch (error) {
    return {
      ok: false,
      summary: formatInvokeError(error, "渲染前预检不可用。"),
      checks: [
        {
          id: "preflight_render_v5",
          label: "渲染前预检",
          ok: false,
          message: formatInvokeError(error, "Tauri 后端未响应。"),
          detail: null,
        },
      ],
    };
  }
}

export async function saveSessionSnapshot(snapshot: SessionSnapshotPayload): Promise<void> {
  await invoke("save_session_snapshot", { snapshotJson: JSON.stringify(snapshot) });
}

export async function loadSessionSnapshot(): Promise<SessionSnapshotPayload | null> {
  const raw = await invoke<string | null>("load_session_snapshot");
  if (!raw) return null;
  const parsed = JSON.parse(raw) as SessionSnapshotPayload;
  if (!parsed || typeof parsed !== "object" || typeof parsed.savedAt !== "string" || !parsed.data || typeof parsed.data !== "object") {
    throw new Error("会话快照格式无效。");
  }
  return parsed;
}

export async function clearSessionSnapshot(): Promise<void> {
  await invoke("clear_session_snapshot");
}

export async function saveProjectState(projectDir: string, payload: ProjectStatePayload): Promise<void> {
  await invoke("save_project_state", {
    projectDir,
    payloadJson: JSON.stringify(payload),
  });
}

export async function loadProjectState(projectDir: string): Promise<ProjectStatePayload | null> {
  const raw = await invoke<string | null>("load_project_state", { projectDir });
  if (!raw) return null;
  return parseSnapshotPayload<ProjectStatePayload>(raw, "project state");
}

export async function exportDiagnosticBundle(outputPath: string, payload: DiagnosticBundlePayload): Promise<string> {
  return await invoke<string>("export_diagnostic_bundle", {
    outputPath,
    payloadJson: JSON.stringify(payload, null, 2),
  });
}

export async function loadProjectDocumentsV5(projectDir: string): Promise<ProjectDocumentsLoadResult> {
  const payload = await invoke<{
    projectDir: string;
    migrated: boolean;
    migrationNotes?: string[] | null;
    library?: unknown;
    blueprint?: unknown;
    renderPlan?: unknown;
    render_plan?: unknown;
    timeline?: unknown;
  }>("load_project_documents_v5", { projectDir });

  return {
    projectDir: payload.projectDir,
    migrated: Boolean(payload.migrated),
    migrationNotes: Array.isArray(payload.migrationNotes) ? payload.migrationNotes.filter((item): item is string => typeof item === "string") : [],
    library: payload.library ? parseV5Value<V5MediaLibrary>(payload.library, "media_library") : null,
    blueprint: payload.blueprint ? parseV5Value<V5StoryBlueprint>(payload.blueprint, "story_blueprint") : null,
    renderPlan: (payload.renderPlan || payload.render_plan) ? parseV5Value<V5RenderPlan>(payload.renderPlan || payload.render_plan, "render_plan") : null,
    timeline: payload.timeline ? parseV5Value<V5Timeline>(payload.timeline, "timeline") : null,
  };
}

export async function loadBuildReportSummary(projectDir: string): Promise<RenderRecoverySummary> {
  return await invoke<RenderRecoverySummary>("load_build_report_summary", { projectDir });
}

export async function startTelemetrySession(telemetryEnabled: boolean): Promise<TelemetrySessionStartResponse> {
  return await invoke<TelemetrySessionStartResponse>("start_telemetry_session", { telemetryEnabled });
}

export async function finishTelemetrySession(sessionId: string, cleanExit: boolean): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("finish_telemetry_session", { sessionId, cleanExit });
}

export async function recordTelemetryEvent(payload: TelemetryEventPayload): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("record_telemetry_event", {
    payloadJson: JSON.stringify(payload),
  });
}

export async function loadTelemetrySummary(): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("load_telemetry_summary");
}

export async function clearTelemetryHistory(): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("clear_telemetry_history");
}

export async function updateTelemetrySettings(payload: TelemetrySettingsPayload): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("update_telemetry_settings", {
    payloadJson: JSON.stringify(payload),
  });
}

export async function flushRemoteTelemetryQueue(): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("flush_remote_telemetry_queue");
}

// =========================
// V5 engine calls
// =========================

/** Scan a folder and return Media Library JSON. V5.1 writes project JSON into projectDir. */
export async function scanV5(inputFolder: string, projectDir?: string, recursive: boolean = true): Promise<V5MediaLibrary> {
  const jsonStr = await invoke<string>("scan_v5", { inputFolder, projectDir: projectDir || null, recursive });
  return parseV5Json<V5MediaLibrary>(jsonStr, "media_library");
}

/** Generate a Story Blueprint from a Media Library JSON file. */
export async function planV5(libraryPath: string, outputPath?: string): Promise<V5StoryBlueprint> {
  const jsonStr = await invoke<string>("plan_v5", { libraryPath, outputPath: outputPath || null });
  return parseV5Json<V5StoryBlueprint>(jsonStr, "story_blueprint");
}

/** Save edited Story Blueprint JSON to disk. */
export async function saveBlueprintV5(path: string, content: string): Promise<void> {
  await invoke("save_blueprint_v5", { path, content });
}

/** Compile Story Blueprint + Media Library into Render Plan. */
export async function compileV5(blueprintPath: string, libraryPath: string, outputPath?: string): Promise<V5RenderPlan> {
  const jsonStr = await invoke<string>("compile_v5", { blueprintPath, libraryPath, outputPath: outputPath || null });
  return parseV5Json<V5RenderPlan>(jsonStr, "render_plan");
}

export async function saveTimelineV5(path: string, content: string): Promise<void> {
  await invoke("save_timeline_v5", { path, content });
}

export async function timelineGenerateV5({
  renderPlanPath,
  outputPath,
  blueprintPath,
  libraryPath,
  existingTimelinePath,
  projectDir,
}: {
  renderPlanPath: string;
  outputPath: string;
  blueprintPath?: string | null;
  libraryPath?: string | null;
  existingTimelinePath?: string | null;
  projectDir?: string | null;
}): Promise<V5Timeline> {
  const jsonStr = await invoke<string>("timeline_generate_v5", {
    renderPlanPath,
    outputPath,
    blueprintPath: blueprintPath || null,
    libraryPath: libraryPath || null,
    existingTimelinePath: existingTimelinePath || null,
    projectDir: projectDir || null,
  });
  return parseV5Json<V5Timeline>(jsonStr, "timeline");
}

export async function timelineCompileV5(timelinePath: string, baseRenderPlanPath: string, outputPath: string): Promise<V5RenderPlan> {
  const jsonStr = await invoke<string>("timeline_compile_v5", { timelinePath, baseRenderPlanPath, outputPath });
  return parseV5Json<V5RenderPlan>(jsonStr, "render_plan");
}

/** Execute final V5 render. */
export async function renderV5(planPath: string, outputPath: string, params: RenderV5Params, jobId?: string): Promise<void> {
  await invoke("render_v5", {
    planPath,
    outputPath,
    paramsJson: JSON.stringify(params),
    jobId: jobId || null,
  });
}

/** Render a short, real low-resolution preview from the same V5 render plan. */
export async function previewRenderV5({
  planPath,
  params,
  maxDuration = 20,
  maxSegments = 8,
  height = 540,
  fps = 15,
}: {
  planPath: string;
  params: RenderV5Params;
  maxDuration?: number;
  maxSegments?: number;
  height?: number;
  fps?: number;
}): Promise<string> {
  return await invoke<string>("preview_render_v5", {
    planPath,
    paramsJson: JSON.stringify(params),
    maxDuration,
    maxSegments,
    height,
    fps,
  });
}

/** Render a short low-resolution MP4 using the real Python/MoviePy title renderer. */
export async function previewTitleV5({
  title,
  subtitle,
  style,
  aspectRatio = "16:9",
  background = "travel",
}: {
  title: string;
  subtitle?: string | null;
  style: V5TitleStyle;
  aspectRatio?: AspectRatio | "1:1";
  background?: string;
}): Promise<string> {
  return await invoke<string>("preview_title_v5", {
    title,
    subtitle: subtitle || null,
    styleJson: JSON.stringify(style),
    aspectRatio,
    background,
  });
}

// =========================
// Command preview helpers
// =========================

export function buildCommandPreview(payload: GenerateVideoPayload): string {
  const input = payload.inputPaths[0] || "<素材文件夹>";
  const outputDir = payload.outputDir || "<输出目录>";
  const args = [
    "python",
    "make_bilibili_video_v3.py",
    "--input_folder",
    quote(input),
    payload.outputDir ? "--output_dir" : "",
    payload.outputDir ? quote(outputDir) : "",
    payload.recursive ? "--recursive" : "",
    payload.chaptersFromDirs ? "--chapters_from_dirs" : "",
    "--title",
    quote(payload.title || "未命名旅行视频"),
    "--title_subtitle",
    quote(payload.titleSubtitle || "Travel Video"),
    payload.endText ? "--end" : "",
    payload.endText ? quote(payload.endText) : "",
    payload.watermark ? "--watermark" : "",
    payload.watermark ? quote(payload.watermark) : "",
    "--quality",
    toPythonQuality(payload.quality),
    "--engine",
    payload.renderEngine,
    "--ratio",
    payload.aspectRatio,
    payload.cover ? "--cover" : "",
    payload.dryRun ? "--dry_run" : "",
    "--output_name",
    quote(payload.outputName || "travel_video"),
  ].filter((arg): arg is string => Boolean(arg));

  return args.join(" ");
}


export function buildV5RenderCommandPreview({
  planPath,
  outputPath,
  params,
}: {
  planPath: string;
  outputPath: string;
  params?: RenderV5Params;
}): string {
  const args = [
    "python",
    "video_engine_v5.py",
    "render",
    "--plan",
    quote(planPath),
    "--output",
    quote(outputPath),
  ];

  if (params && Object.keys(params).length > 0) {
    args.push("--params", quote(JSON.stringify(params)));
  }

  return args.join(" ");
}

export function toPythonQuality(quality: Quality): PythonQuality {
  const mapping: Record<Quality, PythonQuality> = {
    draft: "normal",
    standard: "high",
    high: "ultra",
  };
  return mapping[quality];
}

export function toPythonQualityLabel(quality: Quality): string {
  return toPythonQuality(quality);
}

function quote(value: string): string {
  return `"${value.split('"').join('\\"')}"`;
}

function parseSnapshotPayload<T extends { savedAt?: string; data?: Record<string, unknown> }>(
  raw: string,
  label: string,
): T {
  const parsed = JSON.parse(raw) as T;
  if (!parsed || typeof parsed !== "object" || typeof parsed.savedAt !== "string" || !parsed.data || typeof parsed.data !== "object") {
    throw new Error(`${label} payload is invalid.`);
  }
  return parsed;
}

function parseV5Json<T extends { document_type?: V5DocumentType; schema_version?: string }>(
  jsonStr: string,
  expectedType: V5DocumentType,
): T {
  let parsed: unknown;

  try {
    parsed = JSON.parse(jsonStr);
  } catch (error) {
    throw new Error(`V5 JSON 解析失败：${formatUnknownError(error)}`);
  }

  return parseV5Value<T>(parsed, expectedType);
}

function parseV5Value<T extends { document_type?: V5DocumentType; schema_version?: string }>(
  parsed: unknown,
  expectedType: V5DocumentType,
): T {
  const migrated = migrateV5Document(parsed, expectedType);

  if (!migrated || typeof migrated !== "object") {
    throw new Error(`V5 返回结果不是有效对象，期望 document_type=${expectedType}`);
  }

  const doc = migrated as { document_type?: unknown; schema_version?: unknown };
  if (doc.document_type !== expectedType) {
    throw new Error(`V5 返回 document_type 不匹配：期望 ${expectedType}，实际 ${String(doc.document_type)}`);
  }

  if (typeof doc.schema_version !== "string" || doc.schema_version.length === 0) {
    throw new Error(`V5 返回结果缺少 schema_version，document_type=${expectedType}`);
  }

  return migrated as T;
}

function migrateV5Document(parsed: unknown, expectedType: V5DocumentType): unknown {
  if (!parsed || typeof parsed !== "object") return parsed;
  const doc = structuredClone(parsed) as Record<string, unknown>;
  if (doc.document_type !== expectedType) return parsed;

  if (expectedType === "media_library") {
    if (!doc.project || typeof doc.project !== "object") doc.project = {};
    const project = doc.project as Record<string, unknown>;
    if (!("project_title" in project)) project.project_title = null;
    if (!Array.isArray(doc.directory_nodes)) doc.directory_nodes = [];
    if (!Array.isArray(doc.assets)) doc.assets = [];
    if (!doc.summary || typeof doc.summary !== "object") doc.summary = {};
    for (const asset of doc.assets as Record<string, unknown>[]) {
      if (!asset || typeof asset !== "object") continue;
      if (asset.thumbnail_path == null && asset.thumbnail != null) asset.thumbnail_path = asset.thumbnail;
      if (asset.thumbnail == null && asset.thumbnail_path != null) asset.thumbnail = asset.thumbnail_path;
      if (asset.status == null) asset.status = "ready";
    }
  } else if (expectedType === "story_blueprint") {
    if (typeof doc.subtitle !== "string") doc.subtitle = String(doc.subtitle || "");
    if (!Array.isArray(doc.sections)) doc.sections = [];
    if (!doc.metadata || typeof doc.metadata !== "object") doc.metadata = {};
    const metadata = doc.metadata as Record<string, unknown>;
    if (metadata.chapter_background_mode == null) metadata.chapter_background_mode = "auto_bridge";
    migrateStorySections(doc.sections as Record<string, unknown>[]);
  } else if (expectedType === "render_plan") {
    if (!Array.isArray(doc.segments)) doc.segments = [];
    if (typeof doc.output_path !== "string") doc.output_path = "";
    for (const segment of doc.segments as Record<string, unknown>[]) {
      if (!segment || typeof segment !== "object") continue;
      if (!Array.isArray(segment.render_route_tags)) segment.render_route_tags = [];
    }
  }

  doc.schema_version = V5_SCHEMA_VERSION;
  return doc;
}

function migrateStorySections(sections: Record<string, unknown>[]) {
  for (const section of sections) {
    if (!section || typeof section !== "object") continue;
    if (!Array.isArray(section.asset_refs)) section.asset_refs = [];
    if (!Array.isArray(section.children)) section.children = [];
    migrateStorySections(section.children as Record<string, unknown>[]);
  }
}

export function parseAppError(error: unknown): AppErrorInfo {
  const raw = formatUnknownError(error);
  const match = raw.match(/^\[([A-Z0-9_]+)\]\s*(.*)$/s);
  if (match) {
    const guidance = errorGuidanceForCode(match[1]);
    return {
      code: match[1],
      message: match[2] || match[1],
      userMessage: guidance?.userMessage || null,
      actionSuggestion: guidance?.actionSuggestion || null,
      raw,
    };
  }
  return {
    code: null,
    message: raw || "未知错误",
    userMessage: null,
    actionSuggestion: null,
    raw,
  };
}

export function resolveAppError(error: unknown): AppErrorResolution {
  const parsed = parseAppError(error);
  const guidance = parsed.code ? errorGuidanceForCode(parsed.code) : null;
  const fallback = fallbackErrorResolution(parsed.message);
  return {
    code: parsed.code || null,
    technicalMessage: parsed.message,
    userMessage: guidance?.userMessage || fallback.userMessage,
    actionSuggestion: guidance?.actionSuggestion || fallback.actionSuggestion || null,
  };
}

function errorGuidanceForCode(code: string): { userMessage: string; actionSuggestion?: string } | null {
  const map: Record<string, { userMessage: string; actionSuggestion?: string }> = {
    E_OUTPUT_DIR_REQUIRED: {
      userMessage: "缺少输出目录：请先选择输出目录后再继续。",
      actionSuggestion: "在“生成参数”区域选择一个明确可写的输出目录。",
    },
    E_OUTPUT_NOT_WRITABLE: {
      userMessage: "输出目录不可写：请换到桌面、文档或其他可写目录后重试。",
      actionSuggestion: "避免写入系统目录、只读目录或云盘受限目录。",
    },
    E_MEDIA_SOURCE_MISSING: {
      userMessage: "素材缺失：请确认素材没有被移动或删除，然后重新扫描并编译。",
      actionSuggestion: "恢复原素材路径，或重新扫描素材并重新生成 render_plan.json。",
    },
    E_RENDER_PLAN_INVALID_JSON: {
      userMessage: "渲染计划损坏：请重新确认蓝图并生成新的 render_plan.json。",
      actionSuggestion: "不要手工修改 render_plan.json；若已修改，请重新编译。",
    },
    E_PROJECT_DIR_MISSING: {
      userMessage: "项目目录不存在：最近项目对应的 .video_create_project 已丢失或不可访问。",
      actionSuggestion: "确认输出目录仍在原位置；若已丢失，请重新扫描素材创建新项目。",
    },
    E_PROJECT_DOC_INVALID_JSON: {
      userMessage: "项目文档损坏：项目 JSON 无法解析，建议重新扫描和编译。",
      actionSuggestion: "优先保留仍可读取的 JSON，损坏文件建议重新生成。",
    },
    E_PROJECT_DOC_TYPE_MISMATCH: {
      userMessage: "项目文档类型异常：项目目录中的 JSON 与当前步骤不匹配。",
      actionSuggestion: "检查 media_library.json、story_blueprint.json、render_plan.json 是否被错误覆盖。",
    },
    E_PROJECT_DOC_REWRITE_FAILED: {
      userMessage: "项目迁移失败：旧项目已识别，但无法写回迁移结果。",
      actionSuggestion: "确认 .video_create_project 可写后，再重新恢复最近项目。",
    },
    E_WORKER_ENTRYPOINT_MISSING: {
      userMessage: "Worker 不可用：请先运行 npm run check，确认桌面 worker 已正确打包。",
      actionSuggestion: "重点检查打包资源、src-tauri/bin 和安装目录完整性。",
    },
    E_WORKER_HEALTH_FAILED: {
      userMessage: "Worker 健康检查失败：请先运行 npm run check，确认渲染依赖正常。",
      actionSuggestion: "重点查看 FFmpeg、Python worker、编码器检测和环境权限。",
    },
    E_TASK_ALREADY_RUNNING: {
      userMessage: "已有渲染任务正在运行，请等待完成或先取消当前任务。",
      actionSuggestion: "查看渲染队列，避免重复点击“开始渲染”。",
    },
    E_TASK_CANCELLED: {
      userMessage: "渲染已取消。",
      actionSuggestion: "如果不是主动取消，请导出诊断包并检查最近日志。",
    },
    E_STARTUP_CHECK_FAILED: {
      userMessage: "启动自检未通过：请先修复自检卡中的失败项。",
      actionSuggestion: "优先处理 worker、资源文件和可写目录相关问题。",
    },
    E_PREFLIGHT_CHECK_FAILED: {
      userMessage: "渲染前预检未通过：请先修复预检卡中的失败项。",
      actionSuggestion: "优先处理输出目录、render_plan.json 和素材缺失问题。",
    },
  };
  return map[code] || null;
}

function fallbackErrorResolution(message: string): { userMessage: string; actionSuggestion?: string } {
  const lower = message.toLowerCase();
  if (lower.includes("permission") || message.includes("拒绝访问") || message.includes("access is denied")) {
    return {
      userMessage: "权限不足：请确认素材目录和输出目录可读写。",
      actionSuggestion: "必要时换到桌面或文档目录后重试。",
    };
  }
  if (lower.includes("no such file") || message.includes("系统找不到") || message.includes("找不到")) {
    return {
      userMessage: "文件缺失：请确认素材没有被移动或删除。",
      actionSuggestion: "重新扫描素材并生成新的渲染计划。",
    };
  }
  if (lower.includes("moviepy") || lower.includes("ffmpeg") || lower.includes("pyinstaller")) {
    return {
      userMessage: "渲染依赖异常：请先运行 npm run check。",
      actionSuggestion: "确认 Python worker、MoviePy 和 FFmpeg 都可用。",
    };
  }
  if (lower.includes("json") || lower.includes("render_plan")) {
    return {
      userMessage: "渲染计划异常：请重新确认故事蓝图。",
      actionSuggestion: "重新生成 render_plan.json 后再试。",
    };
  }
  if (lower.includes("cancel")) {
    return {
      userMessage: "渲染已取消。",
      actionSuggestion: "如非主动取消，请导出诊断包继续排查。",
    };
  }
  return {
    userMessage: message || "发生未知错误，请查看日志。",
    actionSuggestion: "如问题可复现，请导出诊断包并附带错误截图。",
  };
}

function formatInvokeError(error: unknown, fallback: string): string {
  const parsed = parseAppError(error);
  const detail = parsed.message;
  return detail ? `${fallback} ${detail}` : fallback;
}

function formatUnknownError(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (error == null) return "";
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}
