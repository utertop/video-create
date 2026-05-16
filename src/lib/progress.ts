import React from "react";
import { PhotoSegmentCacheStats, ProxyMediaStats, VideoEvent, VideoSegmentCacheStats } from "../types/studio";

export function formatProgressLine(line: string): string | null {
  const trimmed = line.trim();
  if (!trimmed || /^=+$/.test(trimmed)) return null;

  const previewItem = trimmed.match(/^-\s+\[(title|chapter|end|video|image)\]\s+(.+?)\s+\|\s+(.+)$/);
  if (previewItem) {
    const [, kind, relPath, displayName] = previewItem;
    return formatMediaItem(kind, relPath, displayName);
  }

  const segmentItem = trimmed.match(/^\[\d+\/\d+\].*?:\s+(title|chapter|end|video|image)\s+\|\s+(.+)$/);
  if (segmentItem) {
    const [, kind, displayName] = segmentItem;
    return `生成片段：${mediaKindLabel(kind)} - ${displayName}`;
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
  setPhase: React.Dispatch<React.SetStateAction<string>>,
  setProgress: React.Dispatch<React.SetStateAction<number | null>>,
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

  if (event.type === "render_queue" && event.status) {
    if (event.status === "running") setPhase("Rendering");
    if (event.status === "done") setPhase("Render complete");
    if (event.status === "failed") setPhase("Render failed");
    if (event.status === "cancelled") setPhase("Render cancelled");
  }

  if (typeof event.percent === "number") {
    setProgress(Math.max(0, Math.min(100, event.percent)));
  }

  if (event.phase) {
    setPhase(phaseLabel(event.phase));
  }

  const line = formatStructuredEvent(event);
  if (!line) return;

  setLogs((prev) => {
    const next = [...prev, line];
    if (next.length > 100) return next.slice(next.length - 100);
    return next;
  });
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
    return `${event.message || `${event.artifact || "产物"} 已生成`}${event.path ? `: ${event.path}` : ""}`;
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
    return `照片段缓存：复用 ${event.hit || 0}，节省 ${(event.saved_render_seconds || 0)} 秒实时合成，新建 ${event.created || 0}，回退 ${event.fallback || 0}`;
  }
  if (event.type === "video_cache") {
    return `视频段缓存：复用 ${event.hit || 0}，节省 ${(event.saved_render_seconds || 0)} 秒视频适配，新建 ${event.created || 0}，回退 ${event.fallback || 0}`;
  }
  if (event.type === "proxy_cache") {
    return `Proxy media: reused ${event.hit || 0}, created ${event.created || 0}, fallback ${event.fallback || 0}`;
  }
  if (event.type === "render_queue") {
    const status = event.status || "queued";
    const suffix = event.position && event.position > 0 ? ` #${event.position}` : "";
    return `${event.message || "Render queue"} (${status}${suffix})`;
  }
  return event.message || null;
}

export function phaseLabel(phase: string): string {
  return {
    scan: "扫描素材",
    segment: "生成片段",
    render: "合成视频",
    cover: "生成封面",
    report: "生成报告",
    complete: "完成",
    fatal: "失败",
  }[phase] || phase;
}

export function parseProgress(line: string): { current: number; total: number } | null {
  const match = line.match(/\[(\d+)\/(\d+)\]/);
  if (!match) return null;
  return { current: parseInt(match[1], 10), total: parseInt(match[2], 10) };
}

export function detectPhase(line: string): string | null {
  if (line.includes("素材预览")) return "扫描素材";
  if (/\[\d+\/\d+\]\s*(生成片段|缓存命中)/.test(line)) return "生成片段";
  if (line.includes("开始最终合成")) return "合成视频";
  if (line.includes("视频生成完成")) return "完成";
  if (line.includes("封面已生成")) return "生成封面";
  if (line.includes("报告已生成")) return "生成报告";
  return null;
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
