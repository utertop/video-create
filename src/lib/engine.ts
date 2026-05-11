import { invoke } from "@tauri-apps/api/core";

export type AspectRatio = "16:9" | "9:16";
export type Quality = "draft" | "standard" | "high";
export type PythonQuality = "normal" | "high" | "ultra";
export type RenderEngine = "auto" | "ffmpeg_concat" | "moviepy_crossfade";

export type V5DocumentType = "media_library" | "story_blueprint" | "render_plan";
export type V5DirectoryType = "city" | "date" | "scenic_spot" | "chapter" | "unknown";
export type V5AssetType = "image" | "video";
export type V5Orientation = "landscape" | "portrait" | "square";
export type V5StorySectionType = "city" | "date" | "scenic_spot" | "chapter" | "opening" | "ending" | string;
export type V5AssetRole = "opening" | "normal" | "highlight";
export type V5DurationPolicy = "auto" | "custom";
export type V5RenderSegmentType = "title" | "chapter" | "video" | "image" | "end";

export const V5_SCHEMA_VERSION = "5.0";

export interface V5MediaLibrary {
  schema_version: string;
  document_type: "media_library";
  engine_version?: string;
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
  auto_detected?: boolean;
  user_overridden?: boolean;
}

export interface V5Asset {
  asset_id: string;
  type: V5AssetType;
  relative_path: string;
  absolute_path: string;
  thumbnail_path?: string | null;
  thumbnail?: string | null;
  file: {
    name: string;
    extension: string;
    size_bytes: number;
    modified_time: string;
    content_hash?: string | null;
  };
  media: {
    width: number | null;
    height: number | null;
    orientation: V5Orientation | null;
    shooting_date: string | null;
    duration_seconds?: number | null;
    duration?: number | null;
  };
  classification: {
    directory_node_id: string;
    city: string | null;
    scenic_spot: string | null;
    date?: string | null;
    detected_role?: string;
    confidence?: number;
  };
  status?: string | { state?: "ready" | "supported" | "skipped" | "error"; message?: string | null };
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
  transition?: "none" | "crossfade";
  background?: "blur" | "black" | "solid";
  keep_audio?: boolean;
  cache_key?: string | null;
}

export interface V5RenderSettings {
  aspect_ratio: AspectRatio;
  quality: Quality;
  python_quality?: PythonQuality;
  fps?: number;
  watermark?: string;
  engine?: RenderEngine;
  cover?: boolean;
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

export interface V5RenderParams {
  title: string;
  title_subtitle: string;
  watermark: string;
  aspect_ratio: AspectRatio;
  quality: Quality;
  engine?: RenderEngine;
  cover?: boolean;
  fps?: number;
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

export async function scanV5(inputFolder: string): Promise<V5MediaLibrary> {
  const jsonStr = await invoke<string>("scan_v5", { inputFolder });
  return parseV5Json<V5MediaLibrary>(jsonStr, "media_library");
}

export async function planV5(libraryPath: string): Promise<V5StoryBlueprint> {
  const jsonStr = await invoke<string>("plan_v5", { libraryPath });
  return parseV5Json<V5StoryBlueprint>(jsonStr, "story_blueprint");
}

export async function saveBlueprintV5(path: string, content: string): Promise<void> {
  await invoke("save_blueprint_v5", { path, content });
}

export async function compileV5(blueprintPath: string, libraryPath: string): Promise<V5RenderPlan> {
  const jsonStr = await invoke<string>("compile_v5", { blueprintPath, libraryPath });
  return parseV5Json<V5RenderPlan>(jsonStr, "render_plan");
}

export async function renderV5(planPath: string, outputPath: string, params: V5RenderParams): Promise<void> {
  await invoke("render_v5", {
    planPath,
    outputPath,
    paramsJson: JSON.stringify({
      ...params,
      python_quality: toPythonQuality(params.quality),
    }),
  });
}

/** Legacy V3 command preview. Used only when running the old generate_video path. */
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

export function buildV5RenderCommandPreview(args: {
  inputFolder: string;
  outputFolder: string;
  outputFileName: string;
  params: V5RenderParams;
}): string {
  const planPath = joinPath(args.inputFolder, "render_plan.json");
  const outputPath = joinPath(args.outputFolder, args.outputFileName);
  return [
    "python",
    "video_engine_v5.py",
    "render",
    "--plan",
    quote(planPath),
    "--output",
    quote(outputPath),
    "--params",
    quote(JSON.stringify({ ...args.params, python_quality: toPythonQuality(args.params.quality) })),
  ].join(" ");
}

export function toPythonQuality(quality: Quality): PythonQuality {
  const mapping: Record<Quality, PythonQuality> = {
    draft: "normal",
    standard: "high",
    high: "ultra",
  };
  return mapping[quality];
}

function joinPath(base: string, name: string): string {
  const separator = base.includes("\\") ? "\\" : "/";
  return `${base.replace(/[\\/]+$/, "")}${separator}${name}`;
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
