import { invoke } from "@tauri-apps/api/core";

export type AspectRatio = "16:9" | "9:16" | "1:1";
export type Quality = "draft" | "standard" | "high";
export type PythonQuality = "normal" | "high" | "ultra";
export type RenderEngine = "auto" | "ffmpeg_concat" | "moviepy_crossfade";
export type V5DocumentType = "media_library" | "story_blueprint" | "render_plan";
export type V5DirectoryType = "city" | "date" | "scenic_spot" | "chapter" | "unknown";
export type V5AssetType = "image" | "video";
export type V5Orientation = "landscape" | "portrait" | "square" | null;
export type V5SectionType = "title" | "city" | "date" | "scenic_spot" | "chapter" | "end" | string;
export type V5AssetRole = "opening" | "normal" | "highlight";
export type V5DurationPolicy = "auto" | "custom";
export type V5SegmentType = "title" | "chapter" | "video" | "image" | "end";

export const V5_SCHEMA_VERSION = "5.0";

// =========================
// V5 数据结构定义
// =========================

export interface V5MediaLibrary {
  schema_version: string;
  document_type: "media_library";
  project: {
    source_root: string;
    scan_time: string;
    recursive?: boolean;
    strategy?: string;
  };
  directory_nodes: V5DirectoryNode[];
  assets: V5Asset[];
  summary: {
    total_assets: number;
    image_count: number;
    video_count: number;
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
  asset_count: number;
  children: string[];

  /** 自动识别结果是否被用户覆盖。用于 GUI 蓝图审核页。 */
  auto_detected?: boolean;
  user_overridden?: boolean;
}

export interface V5Asset {
  asset_id: string;
  type: V5AssetType;
  relative_path: string;
  absolute_path: string;

  /**
   * V5 扫描阶段生成的缩略图路径。
   * App.tsx 的故事蓝图审核页会优先使用该字段。
   */
  thumbnail_path?: string | null;

  /** 兼容旧事件/旧扫描器可能返回 thumbnail 的情况。 */
  thumbnail?: string | null;

  file: {
    name: string;
    extension: string;
    size_bytes: number;
    modified_time: string;
    hash?: string | null;
  };
  media: {
    width: number | null;
    height: number | null;
    orientation: V5Orientation;
    shooting_date: string | null;
    duration?: number | null;
  };
  classification: {
    directory_node_id: string;
    city: string | null;
    date?: string | null;
    scenic_spot: string | null;
  };
  analysis?: {
    brightness?: number | null;
    complexity?: number | null;
    quality_score?: number | null;
  };
  status?: {
    usable?: boolean;
    error?: string | null;
    ignored?: boolean;
  };
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
    source_library?: string;
    user_overridden?: boolean;
  };
}

export interface V5StorySection {
  section_id: string;
  section_type: V5SectionType;
  title: string;
  subtitle: string | null;
  enabled: boolean;
  source_node_id: string | null;
  asset_refs: V5AssetRef[];
  children: V5StorySection[];

  auto_detected?: boolean;
  user_overridden?: boolean;
  rhythm?: "slow" | "standard" | "fast" | string;
}

export interface V5AssetRef {
  asset_id: string;
  enabled: boolean;
  role: V5AssetRole;
  duration_policy: V5DurationPolicy;
  custom_duration: number | null;
  keep_audio: boolean;
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
}

export interface V5RenderSegment {
  segment_id: string;
  type: V5SegmentType;
  source_path: string | null;
  duration: number;
  text: string | null;
  subtitle: string | null;
  start_time: number;
  end_time: number;
  transition?: "none" | "crossfade" | string;
  background?: "blur" | "black" | "contain" | string;
  keep_audio?: boolean;
  cache_key?: string | null;
}

export interface V5RenderSettings {
  aspect_ratio?: AspectRatio;
  quality?: Quality | PythonQuality;
  watermark?: string;
  fps?: number;
  engine?: RenderEngine;
}

export interface V5CachePolicy {
  enabled: boolean;
  cache_root?: string;
  invalidation?: {
    file_path?: boolean;
    file_size?: boolean;
    modified_time?: boolean;
    render_params?: boolean;
    engine_version?: boolean;
  };
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
  watermark?: string;
  aspect_ratio?: AspectRatio;
  quality?: Quality | PythonQuality;
  fps?: number;
  engine?: RenderEngine;
}

function normalizeErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}

function parseJsonResult<T>(jsonStr: string, context: string): T {
  try {
    return JSON.parse(jsonStr) as T;
  } catch (error) {
    throw new Error(`${context} 返回了无效 JSON：${normalizeErrorMessage(error)}`);
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function assertDocumentType(value: unknown, expected: V5DocumentType, context: string): void {
  if (!isRecord(value) || value.document_type !== expected) {
    throw new Error(`${context} 返回类型异常，期望 document_type=${expected}`);
  }
}

export async function generateVideo(payload: GenerateVideoPayload): Promise<GenerateVideoResult> {
  try {
    return await invoke<GenerateVideoResult>("generate_video", { payload });
  } catch (error) {
    return {
      ok: false,
      message: `生成任务启动失败：${normalizeErrorMessage(error)}`,
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
      message: `无法取消任务：${normalizeErrorMessage(error)}`,
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
// V5 引擎调用函数
// =========================

/** 扫描指定文件夹并返回素材事实库 */
export async function scanV5(inputFolder: string): Promise<V5MediaLibrary> {
  const jsonStr = await invoke<string>("scan_v5", { inputFolder });
  const library = parseJsonResult<V5MediaLibrary>(jsonStr, "scan_v5");
  assertDocumentType(library, "media_library", "scan_v5");
  return library;
}

/** 基于素材库生成故事蓝图 */
export async function planV5(libraryPath: string): Promise<V5StoryBlueprint> {
  const jsonStr = await invoke<string>("plan_v5", { libraryPath });
  const blueprint = parseJsonResult<V5StoryBlueprint>(jsonStr, "plan_v5");
  assertDocumentType(blueprint, "story_blueprint", "plan_v5");
  return blueprint;
}

/** 保存编辑后的蓝图到磁盘 */
export async function saveBlueprintV5(path: string, content: string): Promise<void> {
  await invoke("save_blueprint_v5", { path, content });
}

/** 编译蓝图生成渲染计划 */
export async function compileV5(blueprintPath: string, libraryPath: string): Promise<V5RenderPlan> {
  const jsonStr = await invoke<string>("compile_v5", { blueprintPath, libraryPath });
  const plan = parseJsonResult<V5RenderPlan>(jsonStr, "compile_v5");
  assertDocumentType(plan, "render_plan", "compile_v5");
  return plan;
}

/** 执行最终渲染 */
export async function renderV5(planPath: string, outputPath: string, params: RenderV5Params): Promise<void> {
  await invoke("render_v5", {
    planPath,
    outputPath,
    paramsJson: JSON.stringify(params),
  });
}

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
  ].filter(Boolean);

  return args.join(" ");
}

export function toPythonQuality(quality: Quality): PythonQuality {
  return {
    draft: "normal",
    standard: "high",
    high: "ultra",
  }[quality];
}

function quote(value: string): string {
  return `"${value.split('"').join('\\"')}"`;
}
