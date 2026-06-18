import type {
  EditStrategy,
  PerformanceMode,
  Quality,
  RenderRecoverySummary,
  RenderV5Params,
  StartupDiagnostics,
  V5MediaLibrary,
  V5RenderPlan,
  V5StorySection,
  V5Timeline,
} from "./engine";
import { loadBuildReportSummary, parseAppError, resolveAppError } from "./engine";
import { findSectionById } from "./blueprint";
import type { PerformanceRecommendation } from "../components/PerformanceModeControl";
import type { RenderQueueItem } from "../components/RenderQueuePanel";
import { normalizeTitleStyle } from "../components/TitleStylePreview";
import { buildAudioSettings } from "../features/audio/AudioPanels";
import type { RecentProject, StudioDraft } from "./sessionRecovery";
import type { StudioState } from "../store/studio";
import type { BackgroundPickerTarget, PhotoSegmentCacheStats, ProxyMediaStats, VideoSegmentCacheStats } from "../types/studio";

const RECENT_PROJECTS_KEY = "video-create-studio.recent-projects.v1";

export function projectDirFromRecentProject(project: RecentProject): string | null {
  const base = project.outputFolder || project.inputFolder;
  return base ? `${base}\\.video_create_project` : null;
}

export function buildV5ProjectDir(outputFolder?: string | null, inputFolder?: string | null): string {
  const base = outputFolder || inputFolder || "";
  return base ? `${base}\\.video_create_project` : "";
}

export function buildV5FinalOutputName(outputName?: string | null): string {
  const name = outputName || "travel_video";
  return name.endsWith(".mp4") ? name : `${name}.mp4`;
}

export function buildV5OutputPath(outputFolder: string | null | undefined, finalOutputName: string): string {
  return outputFolder ? `${outputFolder}\\${finalOutputName}` : "";
}

export function latestRecoverableFailedRenderJob(renderQueue: RenderQueueItem[]): RenderQueueItem | null {
  const failed = renderQueue
    .filter((item) => item.status === "failed" && item.recovery?.resumable && item.recovery.retryable)
    .sort((left, right) => {
      const leftTime = left.finishedAt || left.createdAt;
      const rightTime = right.finishedAt || right.createdAt;
      return rightTime - leftTime;
    });
  return failed[0] || null;
}

export function loadRecentProjects(): RecentProject[] {
  try {
    const raw = window.localStorage.getItem(RECENT_PROJECTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is RecentProject => typeof item?.inputFolder === "string")
      .slice(0, 5);
  } catch {
    return [];
  }
}

export function saveRecentProjects(projects: RecentProject[]) {
  try {
    window.localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(projects.slice(0, 5)));
  } catch {
    // Local storage can be unavailable in browser previews; the desktop app will still work.
  }
}

export function friendlyDiagnosticsMessage(diagnostics: StartupDiagnostics): string {
  const failed = diagnostics.checks.filter((check) => !check.ok);
  if (failed.length === 0) return diagnostics.summary;
  const details = failed
    .map((check) => `${check.label}${check.code ? ` [${check.code}]` : ""}: ${check.message}`)
    .join("\n");
  return `${diagnostics.summary}\n${details}`;
}

export function chooseRecoveredTimeline(
  draftTimeline: V5Timeline | null | undefined,
  diskTimeline: V5Timeline | null | undefined,
): V5Timeline | null {
  if (!draftTimeline) return diskTimeline || null;
  if (!diskTimeline) return draftTimeline;

  const draftUpdatedAt = Date.parse(String(draftTimeline.metadata?.updated_at || ""));
  const diskUpdatedAt = Date.parse(String(diskTimeline.metadata?.updated_at || ""));
  if (Number.isFinite(diskUpdatedAt) && (!Number.isFinite(draftUpdatedAt) || diskUpdatedAt > draftUpdatedAt)) {
    return diskTimeline;
  }
  return draftTimeline;
}

export function friendlyErrorMessage(error: unknown): string {
  const resolved = resolveAppError(error);
  const parts = [resolved.userMessage];
  if (resolved.actionSuggestion) parts.push(`建议操作：${resolved.actionSuggestion}`);
  if (resolved.technicalMessage && resolved.technicalMessage !== resolved.userMessage) {
    parts.push(resolved.technicalMessage);
  }
  return parts.filter(Boolean).join("\n");
}

export function projectDirFromPlanPath(planPath?: string): string | null {
  if (!planPath) return null;
  const normalized = String(planPath).trim();
  if (!normalized) return null;
  const index = Math.max(normalized.lastIndexOf("\\"), normalized.lastIndexOf("/"));
  if (index <= 0) return null;
  return normalized.slice(0, index);
}

export async function loadRecoverySummaryForPlan(planPath?: string): Promise<RenderRecoverySummary | null> {
  const projectDir = projectDirFromPlanPath(planPath);
  if (!projectDir) return null;
  try {
    return await loadBuildReportSummary(projectDir);
  } catch (error) {
    const parsed = parseAppError(error);
    if (parsed.code === "E_BUILD_REPORT_MISSING") return null;
    console.warn("Failed to load build report summary:", error);
    return null;
  }
}

export function resumeActionSuggestion(recovery: RenderRecoverySummary | null): string | null {
  if (!recovery?.resumable || !recovery.retryable) return null;
  const completed = recovery.completedChunkCount;
  if (completed > 0) {
    return `可直接点击“恢复并重试”，系统会复用已完成的 ${completed} 个分段，只重算失败部分。`;
  }
  return "可直接点击“恢复并重试”，系统会接着当前 stable render 进度继续执行。";
}

export function getSelectedBackgroundPath(target: BackgroundPickerTarget, state: StudioState): string | null {
  if (target.kind === "title") return state.titleBackgroundPath;
  if (target.kind === "end") return state.endBackgroundPath;
  const section = findSectionById(state.v5Blueprint?.sections, target.sectionId);
  return section?.background?.custom_path || null;
}

export function makeTitleLabSection(target: "title" | "end", state: StudioState): V5StorySection {
  return {
    section_id: target === "title" ? "opening_title" : "ending_title",
    section_type: target === "title" ? "opening" : "ending",
    title: target === "title" ? state.title : state.endText,
    subtitle: target === "title" ? state.titleSubtitle : null,
    enabled: true,
    source_node_id: null,
    asset_refs: [],
    children: [],
    title_style: target === "title" ? state.titleStyle : state.endStyle,
  };
}

export function captureStudioDraft(state: StudioState): StudioDraft {
  return {
    inputFolder: state.inputFolder,
    outputFolder: state.outputFolder,
    title: state.title,
    titleSubtitle: state.titleSubtitle,
    endText: state.endText,
    titleStyle: state.titleStyle,
    endStyle: state.endStyle,
    titleBackgroundPath: state.titleBackgroundPath,
    endBackgroundPath: state.endBackgroundPath,
    chapterBackgroundMode: state.chapterBackgroundMode,
    outputName: state.outputName,
    aspectRatio: state.aspectRatio,
    quality: state.quality,
    watermark: state.watermark,
    recursive: state.recursive,
    chaptersFromDirs: state.chaptersFromDirs,
    cover: state.cover,
    editStrategy: state.editStrategy,
    performanceMode: state.performanceMode,
    renderEngine: state.renderEngine,
    musicMode: state.musicMode,
    musicPath: state.musicPath,
    musicPlaylistMode: state.musicPlaylistMode,
    musicPlaylistPaths: [...state.musicPlaylistPaths],
    musicFitStrategy: state.musicFitStrategy,
    bgmVolume: state.bgmVolume,
    sourceAudioVolume: state.sourceAudioVolume,
    keepSourceAudio: state.keepSourceAudio,
    autoDucking: state.autoDucking,
    musicFadeInSeconds: state.musicFadeInSeconds,
    musicFadeOutSeconds: state.musicFadeOutSeconds,
    isDryRun: state.isDryRun,
    telemetryEnabled: state.telemetryEnabled,
    v5Stage: state.v5Stage,
    v5Library: state.v5Library,
    v5Blueprint: state.v5Blueprint,
    v5RenderPlan: state.v5RenderPlan,
    v5Timeline: state.v5Timeline,
    v5TimelinePreviewManifest: state.v5TimelinePreviewManifest,
  };
}

export function hasMeaningfulStudioDraft(draft: StudioDraft): boolean {
  return Boolean(
    draft.inputFolder ||
      draft.outputFolder ||
      draft.v5Library ||
      draft.v5Blueprint ||
      draft.v5RenderPlan ||
      draft.v5Timeline ||
      draft.v5TimelinePreviewManifest ||
      draft.titleBackgroundPath ||
      draft.endBackgroundPath ||
      draft.musicPath ||
      draft.musicPlaylistPaths.length > 0,
  );
}

export function buildDiagnosticsFileName(baseName: string): string {
  const safeBase = (baseName || "video-create-studio")
    .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")
    .replace(/\s+/g, "_")
    .slice(0, 48);
  const now = new Date();
  const stamp = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
    "-",
    String(now.getHours()).padStart(2, "0"),
    String(now.getMinutes()).padStart(2, "0"),
    String(now.getSeconds()).padStart(2, "0"),
  ].join("");
  return `${safeBase}_diagnostics_${stamp}.json`;
}

export function editStrategyHint(strategy: EditStrategy): string {
  return {
    smart_director: "根据素材规模自动选择节奏、转场和稳定渲染模式。",
    fast_assembly: "优先速度和稳定，适合快速出样片或大素材库初稿。",
    travel_soft: "柔和旅拍观感，适合风景、美食、生活记录。",
    beat_cut: "快节奏和冲击感，适合短视频、运动和高能素材。",
    documentary: "章节清晰、转场克制，适合中长叙事内容。",
    long_stable: "优先分段缓存和失败恢复，适合长视频和大量素材。",
  }[strategy];
}

export function transitionProfileForStrategy(strategy: EditStrategy): string {
  return {
    smart_director: "auto",
    fast_assembly: "minimal_fast",
    travel_soft: "travel_soft",
    beat_cut: "beat_cut",
    documentary: "documentary",
    long_stable: "stable_light",
  }[strategy];
}

export function rhythmProfileForStrategy(strategy: EditStrategy): string {
  return {
    smart_director: "auto",
    fast_assembly: "fast_review",
    travel_soft: "medium_soft",
    beat_cut: "fast_punchy",
    documentary: "steady_story",
    long_stable: "long_consistent",
  }[strategy];
}

export function renderModeForPerformance(mode: PerformanceMode, strategy: EditStrategy): string {
  if (mode === "stable") return "long_stable";
  // quality should keep visual quality, but must not disable Python's long-project
  // auto stable renderer. Otherwise 80+ image segments can be forced into one
  // monolithic MoviePy timeline and exhaust memory.
  if (mode === "quality") return "auto";
  if (strategy === "long_stable") return "long_stable";
  return "auto";
}

export function chunkSecondsForPerformance(mode: PerformanceMode): number {
  return {
    stable: 60,
    balanced: 120,
    quality: 180,
  }[mode];
}

export function recommendPerformanceMode(
  plan: V5RenderPlan | null,
  library: V5MediaLibrary | null,
  quality: Quality,
  strategy: EditStrategy,
): PerformanceRecommendation {
  const segmentCount = plan?.segments?.length || 0;
  const totalDuration = Number(plan?.total_duration || 0);
  const assetCount = library?.assets?.length || 0;
  const videoCount = library?.assets?.filter((asset) => asset.type === "video").length || 0;

  const isLarge =
    strategy === "long_stable" ||
    totalDuration >= 1800 ||
    segmentCount >= 300 ||
    assetCount >= 1000 ||
    videoCount >= 80;
  const isMedium =
    totalDuration >= 600 ||
    segmentCount >= 80 ||
    assetCount >= 300 ||
    videoCount >= 24 ||
    quality === "high";

  if (isLarge) {
    return {
      recommended: "stable",
      level: "high",
      estimatedChunkSeconds: 60,
      shouldWarn: true,
      summary: "检测到长视频或大批量素材，建议启用稳定优先：保留章节动效、BGM 和原声层次，同时自动简化高风险执行路径。",
      reason: "当前项目规模较大，稳定优先会优先降低复杂转场、重时间线和高风险混音实现，减少内存峰值与最终生成失败风险。",
    };
  }

  if (isMedium) {
    return {
      recommended: "balanced",
      level: "medium",
      estimatedChunkSeconds: 120,
      shouldWarn: false,
      summary: "当前项目适合平衡推荐：保留主要画面与音频表达，同时用分段和缓存策略控制内存与耗时。",
      reason: "当前项目规模中等，平衡推荐能兼顾效果、速度和稳定性，不需要过早牺牲创作表现。",
    };
  }

  return {
    recommended: "quality",
    level: "low",
    estimatedChunkSeconds: 180,
    shouldWarn: false,
    summary: "当前项目规模较小，可以优先保留更完整的画面、动效和混音细节。",
    reason: "素材规模较小，质感优先的性能风险较低。",
  };
}

export function buildV5RenderParams(state: StudioState): RenderV5Params {
  return {
    title: state.title,
    title_subtitle: state.titleSubtitle,
    watermark: state.watermark,
    aspect_ratio: state.aspectRatio,
    quality: state.quality,
    engine: state.renderEngine,
    performance_mode: state.performanceMode,
    render_mode: renderModeForPerformance(state.performanceMode, state.editStrategy),
    chunk_seconds: chunkSecondsForPerformance(state.performanceMode),
    stable_chunk_seconds: chunkSecondsForPerformance(state.performanceMode),
    edit_strategy: state.editStrategy,
    transition_profile: transitionProfileForStrategy(state.editStrategy),
    rhythm_profile: rhythmProfileForStrategy(state.editStrategy),
    cover: state.cover,
    fps: 30,
    title_background_path: state.titleBackgroundPath,
    title_style: normalizeTitleStyle(state.titleStyle),
    end_background_path: state.endBackgroundPath,
    end_title_style: normalizeTitleStyle(state.endStyle),
    chapter_background_mode: state.chapterBackgroundMode,
    audio: buildAudioSettings(state, state.v5Library, state.v5RenderPlan),
  };
}

export function qualityLabel(quality: Quality): string {
  return {
    draft: "草稿",
    standard: "标准",
    high: "高质量",
  }[quality];
}

export function photoSegmentCacheLabel(stats: PhotoSegmentCacheStats): string {
  const parts = [`复用 ${stats.hit}`, `新建 ${stats.created}`];
  if (stats.fallback > 0) {
    parts.push(`回退 ${stats.fallback}`);
  }
  if (stats.saved_render_seconds > 0) {
    parts.push(`节省 ${formatDurationCompact(stats.saved_render_seconds)}`);
  }
  return `${parts.join(" / ")} · 候选 ${stats.eligible}`;
}

export function proxyMediaLabel(stats: ProxyMediaStats): string {
  const parts = [`reuse ${stats.hit}`, `new ${stats.created}`];
  if (stats.fallback > 0) {
    parts.push(`fallback ${stats.fallback}`);
  }
  return `${parts.join(" / ")} of ${stats.eligible}`;
}

export function photoSegmentCacheHeadline(stats: PhotoSegmentCacheStats): string {
  if (stats.hit > 0) {
    return `这次因为照片段缓存，已经省掉 ${stats.saved_live_composes || stats.hit} 段实时拼装`;
  }
  if (stats.created > 0) {
    return `这次已预热 ${stats.created} 段照片缓存，下次会更快`;
  }
  return `这次有 ${stats.eligible} 段照片进入缓存候选`;
}

export function photoSegmentCacheNote(stats: PhotoSegmentCacheStats): string {
  if (stats.fallback > 0) {
    return `有 ${stats.fallback} 段没有走缓存，已自动回退到实时拼装，不会影响最终成片。`;
  }
  if (stats.overlay_hit > 0) {
    return `其中 ${stats.overlay_hit} 段轻量叠字图片也直接复用了缓存，减少了带标题照片段的重复合成。`;
  }
  if (stats.hit > 0 && stats.created > 0) {
    return `已直接复用已有缓存，同时继续把新照片段预烘焙进缓存池，后续同参数再渲染会继续提速。`;
  }
  if (stats.hit > 0) {
    return `这些照片段没有再重复走 ImageClip + 背景模糊 + 运动合成路径，长视频里会更省时。`;
  }
  if (stats.created > 0) {
    return `这次主要在建立照片段缓存，首次收益偏向“为下一次同参数渲染提速”。`;
  }
  return `当前项目照片段不多，或暂时没有命中可安全预烘焙的照片段。`;
}

export function formatDurationCompact(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0s";
  const rounded = Math.round(seconds);
  if (rounded < 60) return `${rounded}s`;
  const minutes = Math.floor(rounded / 60);
  const remain = rounded % 60;
  return remain > 0 ? `${minutes}m ${remain}s` : `${minutes}m`;
}

export function videoSegmentCacheHeadline(stats: VideoSegmentCacheStats): string {
  if (stats.hit > 0) {
    return `这次因为视频段缓存，已经省掉 ${stats.saved_live_fits || stats.hit} 段实时适配`;
  }
  if (stats.created > 0) {
    return `这次已预热 ${stats.created} 段视频缓存，下次会更快`;
  }
  return `这次有 ${stats.eligible} 段视频进入缓存候选`;
}

export function videoSegmentCacheNote(stats: VideoSegmentCacheStats): string {
  if (stats.fallback > 0) {
    return `有 ${stats.fallback} 段没有走 FFmpeg fitted 缓存，已安全回退到 MoviePy/实时适配，不会影响最终导出。`;
  }
  if (stats.hit > 0 && stats.created > 0) {
    return `已直接复用已有视频段缓存，同时继续把新视频段预适配进缓存池，后续相同参数再导出会继续提速。`;
  }
  if (stats.hit > 0) {
    return `这些视频段没有再重复走缩放、补黑边、统一音轨与重编码适配路径，长视频里会更省时。`;
  }
  if (stats.created > 0) {
    return `这次主要在建立视频段缓存，首次收益偏向“为下一次同参数渲染提速”。`;
  }
  return `当前项目视频段不多，或暂时没有命中可安全走 FFmpeg fitted 的视频段。`;
}
