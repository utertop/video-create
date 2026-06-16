import type {
  AspectRatio,
  EditStrategy,
  GenerateVideoResult,
  MusicFitStrategy,
  MusicMode,
  MusicPlaylistMode,
  PerformanceMode,
  ProjectStatePayload,
  Quality,
  RenderEngine,
  StartupDiagnostics,
  V5ChapterBackgroundMode,
  V5MediaLibrary,
  V5RenderPlan,
  V5StoryBlueprint,
  V5Timeline,
  V5TitleStyle,
} from "./engine";
import type { ProgressTone } from "../components/ProgressBar";
import type { PhotoSegmentCacheStats, ProxyMediaStats, VideoEvent, VideoSegmentCacheStats } from "../types/studio";

export interface RecentProject {
  id: string;
  inputFolder: string;
  outputFolder: string | null;
  title: string;
  outputName: string;
  updatedAt: number;
}

export interface RecoverableProjectState {
  project: RecentProject;
  snapshot: ProjectStatePayload;
}

export interface StudioDraft {
  inputFolder: string | null;
  outputFolder: string | null;
  title: string;
  titleSubtitle: string;
  endText: string;
  titleStyle: V5TitleStyle;
  endStyle: V5TitleStyle;
  titleBackgroundPath: string | null;
  endBackgroundPath: string | null;
  chapterBackgroundMode: V5ChapterBackgroundMode;
  outputName: string;
  aspectRatio: AspectRatio;
  quality: Quality;
  watermark: string;
  recursive: boolean;
  chaptersFromDirs: boolean;
  cover: boolean;
  editStrategy: EditStrategy;
  performanceMode: PerformanceMode;
  renderEngine: RenderEngine;
  musicMode: MusicMode;
  musicPath: string | null;
  musicPlaylistMode: MusicPlaylistMode;
  musicPlaylistPaths: string[];
  musicFitStrategy: MusicFitStrategy;
  bgmVolume: number;
  sourceAudioVolume: number;
  keepSourceAudio: boolean;
  autoDucking: boolean;
  musicFadeInSeconds: number;
  musicFadeOutSeconds: number;
  isDryRun: boolean;
  telemetryEnabled: boolean;
  v5Stage: "INPUT" | "BLUEPRINT" | "RENDER";
  v5Library: V5MediaLibrary | null;
  v5Blueprint: V5StoryBlueprint | null;
  v5RenderPlan: V5RenderPlan | null;
  v5Timeline: V5Timeline | null;
}

export interface SessionRecoveryData {
  studio: StudioDraft;
  logs: string[];
  phase: string;
  progress: number | null;
  progressTone: ProgressTone;
  progressDetail: string | null;
  result: GenerateVideoResult | null;
  preflightDiagnostics: StartupDiagnostics | null;
  materials: VideoEvent[];
  photoSegmentCache: PhotoSegmentCacheStats | null;
  videoSegmentCache: VideoSegmentCacheStats | null;
  proxyMedia: ProxyMediaStats | null;
  selectedAudioSectionId: string | null;
}

export function parseSessionRecoveryData(value: unknown): SessionRecoveryData | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Partial<SessionRecoveryData>;
  if (!candidate.studio || typeof candidate.studio !== "object") return null;
  return {
    studio: candidate.studio as StudioDraft,
    logs: Array.isArray(candidate.logs) ? candidate.logs.filter((item): item is string => typeof item === "string") : [],
    phase: typeof candidate.phase === "string" ? candidate.phase : "已恢复",
    progress: typeof candidate.progress === "number" ? candidate.progress : null,
    progressTone:
      candidate.progressTone === "running" ||
      candidate.progressTone === "done" ||
      candidate.progressTone === "failed" ||
      candidate.progressTone === "cancelled"
        ? candidate.progressTone
        : "idle",
    progressDetail: typeof candidate.progressDetail === "string" ? candidate.progressDetail : null,
    result: (candidate.result as GenerateVideoResult | null) || null,
    preflightDiagnostics: (candidate.preflightDiagnostics as StartupDiagnostics | null) || null,
    materials: Array.isArray(candidate.materials) ? (candidate.materials as VideoEvent[]) : [],
    photoSegmentCache: (candidate.photoSegmentCache as PhotoSegmentCacheStats | null) || null,
    videoSegmentCache: (candidate.videoSegmentCache as VideoSegmentCacheStats | null) || null,
    proxyMedia: (candidate.proxyMedia as ProxyMediaStats | null) || null,
    selectedAudioSectionId: typeof candidate.selectedAudioSectionId === "string" ? candidate.selectedAudioSectionId : null,
  };
}

export function formatSnapshotSavedAt(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "最近保存";
  return `保存于 ${date.toLocaleString()}`;
}

