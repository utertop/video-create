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
export type MusicPlaylistMode = "single" | "auto_playlist" | "manual_playlist";
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

export type V5DocumentType = "media_library" | "story_blueprint" | "render_plan";
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
  | string;
export type V5TitleMotion =
  | "fade_only"
  | "fade_slide_up"
  | "soft_zoom_in"
  | "pop_bounce"
  | "quick_zoom_punch"
  | "slow_fade_zoom"
  | string;

export const V5_SCHEMA_VERSION = "5.5";

// =========================
// V5 data structure definitions
// =========================

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
    scenic_spot_title_mode?: V5SectionTitleMode;
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
  cover?: boolean;
}

export interface V5AudioSettings {
  /** Mix strategy can switch execution paths, but should preserve the intended music/original-audio presence. */
  music_mode: MusicMode;
  music_path?: string | null;
  music_source?: "none" | "library" | "manual" | string;
  music_fit_strategy?: MusicFitStrategy | string;
  music_playlist_mode?: MusicPlaylistMode | string;
  music_playlist_paths?: string[] | null;
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
  message: string;
  commandPreview: string;
  outputPath?: string;
  outputDir?: string;
  cancelled?: boolean;
  isDryRun?: boolean;
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

  /** Optional custom background image for the ending card.
   * If omitted, the renderer uses the last visual frame in render_plan. */
  end_background_path?: string | null;
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

  if (!parsed || typeof parsed !== "object") {
    throw new Error(`V5 返回结果不是有效对象，期望 document_type=${expectedType}`);
  }

  const doc = parsed as { document_type?: unknown; schema_version?: unknown };
  if (doc.document_type !== expectedType) {
    throw new Error(`V5 返回 document_type 不匹配：期望 ${expectedType}，实际 ${String(doc.document_type)}`);
  }

  if (typeof doc.schema_version !== "string" || doc.schema_version.length === 0) {
    throw new Error(`V5 返回结果缺少 schema_version，document_type=${expectedType}`);
  }

  return parsed as T;
}

function formatInvokeError(error: unknown, fallback: string): string {
  const detail = formatUnknownError(error);
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
