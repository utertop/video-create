import React from "react";
import { PhotoSegmentCacheStats, ProxyMediaStats, VideoEvent, VideoSegmentCacheStats } from "../types/studio";

const RENDER_PROGRESS_WINDOWS: Record<string, [number, number]> = {
  scan: [0, 20],
  compile: [20, 45],
  render: [45, 92],
  concat: [92, 97],
  cover: [97, 98],
  report: [98, 99],
  complete: [100, 100],
  done: [100, 100],
  fatal: [0, 100],
};

export function formatProgressLine(line: string): string | null {
  const trimmed = line.trim();
  if (!trimmed || /^=+$/.test(trimmed)) return null;

  const previewItem = trimmed.match(/^-\s+\[(title|chapter|end|video|image)\]\s+(.+?)\s+\|\s+(.+)$/);
  if (previewItem) {
    const [, kind, relPath, displayName] = previewItem;
    return formatMediaItem(kind, relPath, displayName);
  }

  const segmentItem = trimmed.match(/^\[(\d+)\/(\d+)\].*?:\s+(title|chapter|end|video|image)\s+\|\s+(.+)$/);
  if (segmentItem) {
    const [, current, total, kind, displayName] = segmentItem;
    return `生成片段 [${current}/${total}]：${mediaKindLabel(kind)} - ${displayName}`;
  }

  return trimmed;
}

export function parseVideoEvent(line: string): VideoEvent | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return null;
  try {
    const parsed = JSON.parse(trimmed) as VideoEvent;
    return parsed.type ? parsed : null;
  } catch {
    return null;
  }
}

export function applyStructuredEvent(
  event: VideoEvent,
  setLogs: React.Dispatch<React.SetStateAction<string[]>>,
  setMaterials: React.Dispatch<React.SetStateAction<VideoEvent[]>>,
  setPhotoSegmentCache: React.Dispatch<React.SetStateAction<PhotoSegmentCacheStats | null>>,
  setVideoSegmentCache: React.Dispatch<React.SetStateAction<VideoSegmentCacheStats | null>>,
  setProxyMedia: React.Dispatch<React.SetStateAction<ProxyMediaStats | null>>,
) {
  if (event.type === "media") {
    setMaterials((prev) => [...prev, event]);
  }

  if (event.type === "photo_cache") {
    setPhotoSegmentCache({
      eligible: Number(event.eligible || 0),
      hit: Number(event.hit || 0),
      created: Number(event.created || 0),
      fallback: Number(event.fallback || 0),
      overlay_eligible: Number(event.overlay_eligible || 0),
      overlay_hit: Number(event.overlay_hit || 0),
      overlay_created: Number(event.overlay_created || 0),
      saved_live_composes: Number(event.saved_live_composes || 0),
      saved_render_seconds: Number(event.saved_render_seconds || 0),
    });
  }

  if (event.type === "video_cache") {
    setVideoSegmentCache({
      eligible: Number(event.eligible || 0),
      hit: Number(event.hit || 0),
      created: Number(event.created || 0),
      fallback: Number(event.fallback || 0),
      saved_live_fits: Number(event.saved_live_fits || 0),
      saved_render_seconds: Number(event.saved_render_seconds || 0),
    });
  }

  if (event.type === "proxy_cache") {
    setProxyMedia({
      eligible: Number(event.eligible || 0),
      hit: Number(event.hit || 0),
      created: Number(event.created || 0),
      fallback: Number(event.fallback || 0),
    });
  }

  const line = formatStructuredEvent(event);
  if (!line) return;

  setLogs((prev) => {
    const next = [...prev, line];
    if (next.length > 100) return next.slice(next.length - 100);
    return next;
  });
}

export function derivePhaseFromStructuredEvent(event: VideoEvent): string | null {
  if (event.phase) return phaseLabel(event.phase);

  if (event.type === "render_queue" && event.status) {
    return {
      queued: "排队中",
      running: "正在渲染",
      done: "渲染完成",
      failed: "渲染失败",
      cancelled: "已取消",
    }[event.status] || null;
  }

  if (event.type === "error") return "渲染失败";
  if (event.type === "result") return "渲染完成";
  return null;
}

export function deriveStructuredProgress(event: VideoEvent, previous: number | null): number | null {
  if (event.type === "render_queue" && event.status) {
    if (event.status === "queued") return previous ?? 0;
    if (event.status === "running") return Math.max(previous ?? 0, 2);
    if (event.status === "done") return 100;
    return previous;
  }

  if (event.type === "result") return 100;
  if (event.type === "error") return previous;

  const phase = event.phase || inferPhaseFromMessage(event.message || "");
  const sourcePercent =
    extractSubProgressPercent(event.message || "") ??
    (typeof event.percent === "number" ? clamp(event.percent, 0, 100) : null);

  if (!phase) {
    if (sourcePercent == null) return previous;
    return monotonicProgress(sourcePercent, previous);
  }

  if (phase === "complete" || phase === "done") return 100;
  if (phase === "fatal") return previous;

  const [start, end] = progressWindowForPhase(phase, event.message || "");
  if (sourcePercent == null) return monotonicProgress(start, previous);
  return monotonicProgress(interpolateProgress(sourcePercent, start, end), previous);
}

export function deriveProgressFromLogLine(line: string, previous: number | null): number | null {
  const phase = detectPhase(line);
  const bracketProgress = parseProgress(line);
  const sourcePercent = bracketProgress
    ? clamp((bracketProgress.current / Math.max(1, bracketProgress.total)) * 100, 0, 100)
    : extractSubProgressPercent(line);

  if (!phase) {
    if (sourcePercent == null) return previous;
    return monotonicProgress(sourcePercent, previous);
  }

  if (phase === "完成") return 100;
  const normalizedPhase = normalizePhaseKey(phase);
  const [start, end] = progressWindowForPhase(normalizedPhase, line);
  if (sourcePercent == null) return monotonicProgress(start, previous);
  return monotonicProgress(interpolateProgress(sourcePercent, start, end), previous);
}

export function extractActiveSegmentIndexFromText(text: string): number | null {
  const processingMatch = text.match(/Processing segment\s+(\d+)\/\d+/i);
  if (processingMatch) return Math.max(0, Number(processingMatch[1]) - 1);

  const renderMatch = text.match(/渲染分段\s+(\d+)\s*[:：]/);
  if (renderMatch) return Math.max(0, Number(renderMatch[1]) - 1);

  const genericMatch = text.match(/\[(\d+)\/\d+\].*(生成片段|渲染分段)/);
  if (genericMatch) return Math.max(0, Number(genericMatch[1]) - 1);

  return null;
}

export function isStructuredFailureEvent(event: VideoEvent): boolean {
  return event.type === "error" || (event.type === "render_queue" && event.status === "failed");
}

export function failureMessageFromStructuredEvent(event: VideoEvent): string | null {
  if (!isStructuredFailureEvent(event)) return null;
  return event.message || "渲染失败，请查看日志。";
}

export function formatStructuredEvent(event: VideoEvent): string | null {
  if (event.type === "media") {
    return formatMediaItem(event.item_kind || "media", event.rel_path || "", event.display_name || "");
  }
  if (event.type === "progress") {
    const prefix = event.current && event.total ? `[${event.current}/${event.total}] ` : "";
    return `${prefix}${event.message || phaseLabel(event.phase || "segment")}`;
  }
  if (event.type === "phase") {
    return event.message || phaseLabel(event.phase || "");
  }
  if (event.type === "artifact") {
    return `${event.message || `${event.artifact || "产物"}已生成`}${event.path ? `：${event.path}` : ""}`;
  }
  if (event.type === "result") {
    return event.output_path ? `视频已生成：${event.output_path}` : event.message || "渲染完成";
  }
  if (event.type === "error") {
    return `错误：${event.message || "未知错误"}`;
  }
  if (event.type === "log") {
    return event.message || null;
  }
  if (event.type === "photo_cache") {
    return `照片段缓存：复用 ${event.hit || 0}，节省 ${(event.saved_render_seconds || 0).toFixed(1)} 秒，新建 ${event.created || 0}，回退 ${event.fallback || 0}`;
  }
  if (event.type === "video_cache") {
    return `视频段缓存：复用 ${event.hit || 0}，节省 ${(event.saved_render_seconds || 0).toFixed(1)} 秒，新建 ${event.created || 0}，回退 ${event.fallback || 0}`;
  }
  if (event.type === "proxy_cache") {
    return `代理素材缓存：复用 ${event.hit || 0}，新建 ${event.created || 0}，回退 ${event.fallback || 0}`;
  }
  if (event.type === "render_queue") {
    const status = event.status || "queued";
    const suffix = event.position && event.position > 0 ? ` #${event.position}` : "";
    return `${event.message || "渲染队列"}（${status}${suffix}）`;
  }
  return event.message || null;
}

export function phaseLabel(phase: string): string {
  return {
    scan: "扫描素材",
    compile: "编译计划",
    segment: "生成片段",
    render: "合成视频",
    concat: "拼接片段",
    cover: "生成封面",
    report: "生成报告",
    complete: "完成",
    done: "完成",
    fatal: "失败",
  }[phase] || phase;
}

export function parseProgress(line: string): { current: number; total: number } | null {
  const match = line.match(/\[(\d+)\/(\d+)\]/);
  if (!match) return null;
  return { current: parseInt(match[1], 10), total: parseInt(match[2], 10) };
}

export function detectPhase(line: string): string | null {
  const normalized = normalizePhaseKey(inferPhaseFromMessage(line));
  return normalized ? phaseLabel(normalized) : null;
}

function inferPhaseFromMessage(message: string): string {
  if (!message) return "";
  if (/scan|扫描|素材扫描/i.test(message)) return "scan";
  if (/compile|编译|render plan/i.test(message)) return "compile";
  if (/concat|拼接/i.test(message)) return "concat";
  if (/cover|封面/i.test(message)) return "cover";
  if (/report|报告/i.test(message)) return "report";
  if (/complete|done|完成/i.test(message)) return "complete";
  if (/fatal|failed|error|失败/i.test(message)) return "fatal";
  if (/render|chunk|Processing segment|渲染分段|导出最终视频/i.test(message)) return "render";
  return "";
}

function progressWindowForPhase(phase: string, message: string): [number, number] {
  if (phase === "render") {
    if (/chunk\s*:\s*-?\d+\/\d+/i.test(message) || /导出最终视频 chunk/i.test(message)) {
      return [45, 82];
    }
    if (/\bt\s*:\s*-?\d+\/\d+/i.test(message) || /导出最终视频 t/i.test(message)) {
      return [82, 96];
    }
  }
  return RENDER_PROGRESS_WINDOWS[phase] || [0, 100];
}

function extractSubProgressPercent(message: string): number | null {
  const matches = [
    message.match(/\bchunk\s*:\s*(-?\d+)\/(\d+)/i),
    message.match(/\bt\s*:\s*(-?\d+)\/(\d+)/i),
    message.match(/Processing segment\s+(\d+)\/(\d+)/i),
    message.match(/渲染分段\s+(\d+)\s*[:：]\s*.*?\/(\d+)/),
  ].filter(Boolean) as RegExpMatchArray[];

  for (const match of matches) {
    const current = Number(match[1]);
    const total = Number(match[2]);
    if (Number.isFinite(current) && Number.isFinite(total) && total > 0) {
      return clamp((Math.max(0, current) / total) * 100, 0, 100);
    }
  }

  return null;
}

function normalizePhaseKey(phase: string | null): string {
  if (!phase) return "";
  return {
    "扫描素材": "scan",
    "编译计划": "compile",
    "生成片段": "segment",
    "合成视频": "render",
    "拼接片段": "concat",
    "生成封面": "cover",
    "生成报告": "report",
    "完成": "complete",
    "失败": "fatal",
  }[phase] || phase;
}

function interpolateProgress(percent: number, start: number, end: number): number {
  if (end <= start) return end;
  return Math.round(start + ((end - start) * clamp(percent, 0, 100)) / 100);
}

function monotonicProgress(next: number, previous: number | null): number {
  const normalized = clamp(next, 0, 100);
  if (previous == null) return normalized;
  return Math.max(previous, normalized);
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatMediaItem(kind: string, relPath: string, displayName: string): string {
  if (kind === "title") return `片头标题卡：${displayName}`;
  if (kind === "chapter") return `章节卡：${displayName}`;
  if (kind === "end") return `片尾卡：${displayName}`;
  return `${mediaKindLabel(kind)}：${displayName || relPath}`;
}

function mediaKindLabel(kind: string): string {
  return {
    image: "图片素材",
    video: "视频素材",
    title: "片头标题卡",
    chapter: "章节卡",
    end: "片尾卡",
  }[kind] || "素材";
}
