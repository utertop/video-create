import { invoke } from "@tauri-apps/api/core";

export type AspectRatio = "16:9" | "9:16";
export type Quality = "draft" | "standard" | "high";
export type RenderEngine = "auto" | "ffmpeg_concat" | "moviepy_crossfade";

// =========================
// V5 数据结构定义
// =========================

export interface V5MediaLibrary {
  schema_version: string;
  document_type: "media_library";
  project: {
    source_root: string;
    scan_time: string;
  };
  directory_nodes: V5DirectoryNode[];
  assets: V5Asset[];
  summary: {
    total_assets: number;
    image_count: number;
    video_count: number;
  };
}

export interface V5DirectoryNode {
  node_id: string;
  name: string;
  relative_path: string;
  depth: number;
  parent_id: string | null;
  detected_type: "city" | "date" | "scenic_spot" | "chapter" | "unknown";
  confidence: number;
  reason: string;
  display_title: string;
  asset_count: number;
  children: string[];
}

export interface V5Asset {
  asset_id: string;
  type: "image" | "video";
  relative_path: string;
  absolute_path: string;
  file: {
    name: string;
    extension: string;
    size_bytes: number;
    modified_time: string;
  };
  media: {
    width: number | null;
    height: number | null;
    orientation: "landscape" | "portrait" | "square" | null;
    shooting_date: string | null;
  };
  classification: {
    directory_node_id: string;
    city: string | null;
    scenic_spot: string | null;
  };
}

export interface V5StoryBlueprint {
  schema_version: string;
  document_type: "story_blueprint";
  title: string;
  subtitle: string;
  sections: V5StorySection[];
  strategy: string;
}

export interface V5StorySection {
  section_id: string;
  section_type: string;
  title: string;
  subtitle: string | null;
  enabled: boolean;
  source_node_id: string | null;
  asset_refs: V5AssetRef[];
  children: V5StorySection[];
}

export interface V5AssetRef {
  asset_id: string;
  enabled: boolean;
  role: "opening" | "normal" | "highlight";
  duration_policy: "auto" | "custom";
  custom_duration: number | null;
  keep_audio: boolean;
}

export interface V5RenderPlan {
  schema_version: string;
  document_type: "render_plan";
  output_path: string;
  total_duration: number;
  segments: V5RenderSegment[];
}

export interface V5RenderSegment {
  segment_id: string;
  type: "title" | "chapter" | "video" | "image" | "end";
  source_path: string | null;
  duration: number;
  text: string | null;
  subtitle: string | null;
  start_time: number;
  end_time: number;
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
      message: "当前运行在浏览器预览模式，或 Tauri 后端尚未启动。",
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
      message: "无法取消任务：Tauri 后端尚未响应。",
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

/**
 * 扫描指定文件夹并返回素材事实库
 */
export async function scanV5(inputFolder: string): Promise<V5MediaLibrary> {
  const jsonStr = await invoke<string>("scan_v5", { inputFolder });
  return JSON.parse(jsonStr);
}

/**
 * 基于素材库生成故事蓝图
 */
export async function planV5(libraryPath: string): Promise<V5StoryBlueprint> {
  const jsonStr = await invoke<string>("plan_v5", { libraryPath });
  return JSON.parse(jsonStr);
}

/**
 * 保存编辑后的蓝图到磁盘
 */
export async function saveBlueprintV5(path: string, content: string): Promise<void> {
  await invoke("save_blueprint_v5", { path, content });
}

/**
 * 编译蓝图生成渲染计划
 */
export async function compileV5(blueprintPath: string, libraryPath: string): Promise<V5RenderPlan> {
  const jsonStr = await invoke<string>("compile_v5", { blueprintPath, libraryPath });
  return JSON.parse(jsonStr);
}

/**
 * 执行最终渲染
 */
export async function renderV5(planPath: string, outputPath: string, params: any): Promise<void> {
  await invoke("render_v5", { 
    planPath, 
    outputPath, 
    paramsJson: JSON.stringify(params) 
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
    "--watermark",
    quote(payload.watermark),
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

function toPythonQuality(quality: Quality): string {
  return {
    draft: "normal",
    standard: "high",
    high: "ultra",
  }[quality];
}

function quote(value: string): string {
  return `"${value.split('"').join('\\"')}"`;
}
