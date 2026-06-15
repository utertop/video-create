import type {
  AspectRatio,
  EditStrategy,
  PerformanceMode,
  PythonQuality,
  Quality,
  RenderEngine,
  V5AudioSettings,
  V5ChapterBackgroundMode,
  V5MediaLibrary,
  V5RenderPlan,
  V5StoryBlueprint,
  V5Timeline,
  V5TitleStyle,
} from "./v5Types";

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

