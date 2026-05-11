import { invoke } from "@tauri-apps/api/core";

export type AspectRatio = "16:9" | "9:16";
export type Quality = "draft" | "standard" | "high";
export type RenderEngine = "auto" | "ffmpeg_concat" | "moviepy_crossfade";

export interface GenerateVideoPayload {
  inputPaths: string[];
  title: string;
  outputName: string;
  aspectRatio: AspectRatio;
  quality: Quality;
  watermark: string;
  recursive: boolean;
  chaptersFromDirs: boolean;
  cover: boolean;
  renderEngine: RenderEngine;
}

export interface GenerateVideoResult {
  ok: boolean;
  message: string;
  commandPreview: string;
  outputPath?: string;
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

export function buildCommandPreview(payload: GenerateVideoPayload): string {
  const input = payload.inputPaths[0] || "<素材文件夹>";
  const args = [
    "python",
    "make_bilibili_video_v3.py",
    "--input_folder",
    quote(input),
    payload.recursive ? "--recursive" : "",
    payload.chaptersFromDirs ? "--chapters_from_dirs" : "",
    "--title",
    quote(payload.title || "未命名旅行视频"),
    "--watermark",
    quote(payload.watermark),
    "--quality",
    toPythonQuality(payload.quality),
    "--engine",
    payload.renderEngine,
    "--ratio",
    payload.aspectRatio,
    payload.cover ? "--cover" : "",
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
