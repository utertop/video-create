import {
  CheckCircle2,
  Clapperboard,
  ExternalLink,
  FileVideo,
  FolderOpen,
  Gauge,
  ImagePlus,
  Play,
  Settings2,
  Sparkles,
  Square,
  TriangleAlert,
  X,
  Wand2,
  ListChecks,
  Clock,
  History,
  Loader2,
  PlayCircle,
  RotateCcw,
  Calendar,
  Folder,
  Layers,
  LayoutGrid,
  MapPin,
  Music,
  Palmtree,
  Volume2,
} from "lucide-react";
import { useMemo, useState, useEffect, useRef } from "react";
import { useShallow } from "zustand/react/shallow";
import { listen } from "@tauri-apps/api/event";
import { convertFileSrc } from "@tauri-apps/api/core";
import { open, save } from "@tauri-apps/plugin-dialog";
import {
  AspectRatio,
  clearTelemetryHistory,
  clearSessionSnapshot,
  EditStrategy,
  exportDiagnosticBundle,
  finishTelemetrySession,
  flushRemoteTelemetryQueue,
  GenerateVideoResult,
  loadBuildReportSummary,
  loadProjectState,
  loadSessionSnapshot,
  loadTelemetrySummary,
  loadProjectDocumentsV5,
  parseAppError,
  ProjectStatePayload,
  recordTelemetryEvent,
  resolveAppError,
  PerformanceMode,
  Quality,
  RenderEngine,
  SessionSnapshotPayload,
  saveProjectState,
  saveSessionSnapshot,
  StartupDiagnostics,
  cancelVideo,
  openInExplorer,
  scanV5,
  planV5,
  saveBlueprintV5,
  compileV5,
  saveTimelineV5,
  timelineCompileV5,
  timelineGenerateV5,
  renderV5,
  previewRenderV5,
  V5StoryBlueprint,
  V5StorySection,
  V5MediaLibrary,
  V5RenderPlan,
  V5Timeline,
  V5Asset,
  V5AudioSettings,
  V5AudioBlueprint,
  V5AudioBlueprintCue,
  V5TitleStyle,
  MusicFitStrategy,
  MusicPlaylistMode,
  V5ChapterBackgroundMode,
  RenderV5Params,
  RenderRecoverySummary,
  TelemetrySummary,
  buildV5RenderCommandPreview,
  preflightRenderV5,
  startTelemetrySession,
  startupSelfCheck,
  updateTelemetrySettings,
} from "./lib/engine";
import { findSectionById, getAssetThumbnailPath, updateBlueprintSection, withBlueprintMetadata } from "./lib/blueprint";
import { BackgroundAssetPicker, shortPathName } from "./components/BackgroundAssetPicker";
import { BlueprintEditor } from "./components/BlueprintEditor";
import { Feature, SectionTitle, StatusItem } from "./components/common";
import { EditStrategyPreview } from "./components/EditStrategyPreview";
import { SegmentedControl, Toggle } from "./components/FormControls";
import { FolderSelector, OutputFolderSelector } from "./components/FolderSelector";
import { MaterialGallery, PreviewModal } from "./components/MaterialGallery";
import { PerformanceModeControl, PerformanceRecommendation, performanceModeLabel } from "./components/PerformanceModeControl";
import { ProgressBar, ProgressTone } from "./components/ProgressBar";
import { ACTIVE_RENDER_QUEUE_STATUSES, normalizeQueueStatus, RenderQueueItem, RenderQueuePanel, shortJobId } from "./components/RenderQueuePanel";
import { normalizeTitleStyle, titleTemplateLabel, TitleStyleLab } from "./components/TitleStylePreview";
import { TimelineEditor } from "./features/timeline/TimelineEditor";
import { selectStudioAppState, StudioState, useStudio } from "./store/studio";
import { BackgroundPickerTarget, PhotoSegmentCacheStats, ProxyMediaStats, VideoEvent, VideoSegmentCacheStats } from "./types/studio";
import { buildDiagnosticBundlePayload, buildErrorCodeStats, buildSupportCaseSummary, summarizeErrorCodes } from "./lib/diagnostics";
import {
  applyStructuredEvent,
  derivePhaseFromStructuredEvent,
  deriveProgressFromLogLine,
  deriveStructuredProgress,
  extractActiveSegmentIndexFromText,
  failureMessageFromStructuredEvent,
  formatProgressLine,
  isStructuredFailureEvent,
  parseVideoEvent,
} from "./lib/progress";
import "./v5-background.css";

const RECENT_PROJECTS_KEY = "video-create-studio.recent-projects.v1";
const TELEMETRY_PREFERENCE_KEY = "video-create-studio.telemetry-enabled.v1";

interface RecentProject {
  id: string;
  inputFolder: string;
  outputFolder: string | null;
  title: string;
  outputName: string;
  updatedAt: number;
}

interface RecoverableProjectState {
  project: RecentProject;
  snapshot: ProjectStatePayload;
}

interface StudioDraft {
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
  musicMode: StudioState["musicMode"];
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
  v5Stage: StudioState["v5Stage"];
  v5Library: V5MediaLibrary | null;
  v5Blueprint: V5StoryBlueprint | null;
  v5RenderPlan: V5RenderPlan | null;
  v5Timeline: V5Timeline | null;
}

interface SessionRecoveryData {
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

export function App() {
  const state = useStudio(useShallow(selectStudioAppState));
  const [result, setResult] = useState<GenerateVideoResult | null>(null);
  const [isRendering, setIsRendering] = useState(false);
  const [isPreviewRendering, setIsPreviewRendering] = useState(false);
  const [isApplyingTimeline, setIsApplyingTimeline] = useState(false);
  const [timelineApplyIntent, setTimelineApplyIntent] = useState<"manual" | "preview" | "final" | null>(null);
  const [timelineAutosave, setTimelineAutosave] = useState<{
    status: "idle" | "saving" | "saved" | "error";
    savedAt?: string | null;
    message?: string | null;
  }>({ status: "idle" });
  const [renderPreviewPath, setRenderPreviewPath] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isPlanningWorkflow, setIsPlanningWorkflow] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [progressTone, setProgressTone] = useState<ProgressTone>("idle");
  const [progressDetail, setProgressDetail] = useState<string | null>(null);
  const [activeSegmentIndex, setActiveSegmentIndex] = useState<number | null>(null);
  const [selectedAudioSectionId, setSelectedAudioSectionId] = useState<string | null>(null);
  const [phase, setPhase] = useState("就绪");
  const [toast, setToast] = useState<string | null>(null);
  const [highlightOutput, setHighlightOutput] = useState(false);
  const [materials, setMaterials] = useState<VideoEvent[]>([]);
  const [photoSegmentCache, setPhotoSegmentCache] = useState<PhotoSegmentCacheStats | null>(null);
  const [videoSegmentCache, setVideoSegmentCache] = useState<VideoSegmentCacheStats | null>(null);
  const [proxyMedia, setProxyMedia] = useState<ProxyMediaStats | null>(null);
  const [renderQueue, setRenderQueue] = useState<RenderQueueItem[]>([]);
  const [selectedMaterial, setSelectedMaterial] = useState<VideoEvent | null>(null);
  const [showGalleryOverlay, setShowGalleryOverlay] = useState(false);
  const [galleryView, setGalleryView] = useState<"chapter" | "type" | "time">("chapter");
  const [backgroundPickerTarget, setBackgroundPickerTarget] = useState<BackgroundPickerTarget | null>(null);
  const [isPreparingBackgroundLibrary, setIsPreparingBackgroundLibrary] = useState(false);
  const [titleLabTarget, setTitleLabTarget] = useState<"title" | "end" | null>(null);
  const [startupDiagnostics, setStartupDiagnostics] = useState<StartupDiagnostics | null>(null);
  const [startupDiagnosticsLoading, setStartupDiagnosticsLoading] = useState(true);
  const [preflightDiagnostics, setPreflightDiagnostics] = useState<StartupDiagnostics | null>(null);
  const [preflightLoading, setPreflightLoading] = useState(false);
  const [recentProjects, setRecentProjects] = useState<RecentProject[]>(() => loadRecentProjects());
  const [recoverableSession, setRecoverableSession] = useState<SessionSnapshotPayload | null>(null);
  const [recoverableProjectState, setRecoverableProjectState] = useState<RecoverableProjectState | null>(null);
  const [sessionSnapshotReady, setSessionSnapshotReady] = useState(false);
  const [isExportingDiagnostics, setIsExportingDiagnostics] = useState(false);
  const [projectMigrationNotes, setProjectMigrationNotes] = useState<string[]>([]);
  const [projectMigrationSource, setProjectMigrationSource] = useState<string | null>(null);
  const [telemetrySummary, setTelemetrySummary] = useState<TelemetrySummary | null>(null);
  const [isClearingTelemetry, setIsClearingTelemetry] = useState(false);
  const [showTelemetryConsentDialog, setShowTelemetryConsentDialog] = useState(false);
  const [pendingTelemetryEnable, setPendingTelemetryEnable] = useState(false);
  const [isSavingTelemetrySettings, setIsSavingTelemetrySettings] = useState(false);
  const [isFlushingRemoteTelemetry, setIsFlushingRemoteTelemetry] = useState(false);
  const [remoteTelemetryEndpoint, setRemoteTelemetryEndpoint] = useState("");
  const [remoteUploadEnabledDraft, setRemoteUploadEnabledDraft] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const segmentsTimelineRef = useRef<HTMLDivElement>(null);
  const activeJobRef = useRef<string | null>(null);
  const telemetrySessionIdRef = useRef<string | null>(null);
  const telemetryInitializedRef = useRef(false);
  const sessionFirstExportRecordedRef = useRef(false);
  const startupTelemetryRecordedRef = useRef(false);
  const skipResetRef = useRef(false);
  const [appView, setAppView] = useState<"studio" | "diagnostics" | "settingsCenter">("studio");
  const [activeNav, setActiveNav] = useState("workspace");

  const [hasPreChecked, setHasPreChecked] = useState(false);

  const resetTask = () => {
    setResult(null);
    setLogs([]);
    setProgress(null);
    setProgressTone("idle");
    setProgressDetail(null);
    setActiveSegmentIndex(null);
    setSelectedAudioSectionId(null);
    setPhase("就绪");
    setIsPlanningWorkflow(false);
    setHighlightOutput(false);
    setHasPreChecked(false);
    setMaterials([]);
    setPhotoSegmentCache(null);
    setVideoSegmentCache(null);
    setProxyMedia(null);
    setRenderQueue([]);
    setSelectedMaterial(null);
    setShowGalleryOverlay(false);
    setRenderPreviewPath(null);
    setBackgroundPickerTarget(null);
    setPreflightDiagnostics(null);
    setProjectMigrationNotes([]);
    setProjectMigrationSource(null);
    state.patch({ isDryRun: false });
  };

  useEffect(() => {
    if (skipResetRef.current) {
      skipResetRef.current = false;
      return;
    }
    resetTask();
  }, [state.inputFolder]);

  useEffect(() => {
    setSelectedAudioSectionId(null);
  }, [state.v5RenderPlan]);

  useEffect(() => {
    if (!selectedAudioSectionId) return;
    const container = segmentsTimelineRef.current;
    if (!container) return;
    const firstMatch = Array.from(container.querySelectorAll<HTMLElement>("[data-section-id]")).find(
      (element) => element.dataset.sectionId === selectedAudioSectionId,
    );
    firstMatch?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, [selectedAudioSectionId, state.v5RenderPlan, state.v5Timeline]);

  useEffect(() => {
    let disposed = false;

    setStartupDiagnosticsLoading(true);
    void startupSelfCheck()
      .then((diagnostics) => {
        if (disposed) return;
        setStartupDiagnostics(diagnostics);
      })
      .catch((error) => {
        if (disposed) return;
        setStartupDiagnostics({
          ok: false,
          summary: `Startup self-check failed: ${String(error)}`,
          checks: [
            {
              id: "startup_self_check",
              label: "Startup self-check",
              ok: false,
              message: String(error),
              detail: null,
            },
          ],
        });
      })
      .finally(() => {
        if (!disposed) setStartupDiagnosticsLoading(false);
      });

    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!startupDiagnostics || startupTelemetryRecordedRef.current) return;
    if (!state.telemetryEnabled || !telemetrySessionIdRef.current) return;
    startupTelemetryRecordedRef.current = true;
    void recordTelemetryEvent({
      sessionId: telemetrySessionIdRef.current,
      eventType: "startup_check",
      timestamp: new Date().toISOString(),
      success: startupDiagnostics.ok,
      errorCode: startupDiagnostics.code || startupDiagnostics.checks.find((item) => !item.ok)?.code || null,
      supportQueue: startupDiagnostics.ok ? "general-triage" : "environment",
      severity: startupDiagnostics.ok ? "info" : "high",
      tags: [
        "startup-check",
        ...(startupDiagnostics.ok ? [] : ["startup-failed"]),
        ...startupDiagnostics.checks.filter((item) => !item.ok).map((item) => item.id),
      ],
    })
      .then((summary) => setTelemetrySummary(summary))
      .catch((error) => {
        console.error("Failed to record startup telemetry:", error);
      });
  }, [startupDiagnostics, state.telemetryEnabled]);

  useEffect(() => {
    let disposed = false;

    void loadSessionSnapshot()
      .then((snapshot) => {
        if (disposed || !snapshot) return;
        const restored = parseSessionRecoveryData(snapshot.data);
        if (!restored || !hasMeaningfulStudioDraft(restored.studio)) return;
        setRecoverableSession(snapshot);
      })
      .catch((error) => {
        console.error("Failed to load session snapshot:", error);
      })
      .finally(() => {
        if (!disposed) setSessionSnapshotReady(true);
      });

    return () => {
      disposed = true;
    };
  }, []);

  useEffect(() => {
    if (!sessionSnapshotReady) return;
    if (recoverableSession) return;
    if (recoverableProjectState) return;
    if (recentProjects.length === 0) return;

    let disposed = false;

    void (async () => {
      for (const project of recentProjects.slice(0, 3)) {
        const projectDir = projectDirFromRecentProject(project);
        if (!projectDir) continue;
        try {
          const snapshot = await loadProjectState(projectDir);
          if (disposed || !snapshot) continue;
          const restored = parseSessionRecoveryData(snapshot.data);
          if (!restored || !hasMeaningfulStudioDraft(restored.studio)) continue;
          setRecoverableProjectState({ project, snapshot });
          return;
        } catch (error) {
          console.warn("Failed to inspect recent project autosave:", error);
        }
      }
    })();

    return () => {
      disposed = true;
    };
  }, [recentProjects, recoverableProjectState, recoverableSession, sessionSnapshotReady]);

  useEffect(() => {
    const stored = window.localStorage.getItem(TELEMETRY_PREFERENCE_KEY);
    void loadTelemetrySummary()
      .then((summary) => {
        setTelemetrySummary(summary);
        if (stored === "false") {
          state.patch({ telemetryEnabled: false });
          return;
        }
        if (stored === "true" && summary.consentAcceptedVersion === summary.currentConsentVersion) {
          state.patch({ telemetryEnabled: true });
          return;
        }
        if (stored === "true") {
          state.patch({ telemetryEnabled: false });
          setPendingTelemetryEnable(true);
          setShowTelemetryConsentDialog(true);
          setToast("Telemetry consent needs to be reviewed again before this version can re-enable anonymous reporting.");
        }
      })
      .catch((error) => {
        console.error("Failed to load telemetry summary:", error);
      });
  }, []);

  useEffect(() => {
    if (!telemetrySummary) return;
    setRemoteUploadEnabledDraft(telemetrySummary.remoteUploadEnabled);
    setRemoteTelemetryEndpoint(telemetrySummary.remoteEndpoint || "");
  }, [telemetrySummary]);

  function scrollToSection(id: string) {
    setAppView("studio");
    setActiveNav(id);
    window.requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function captureTelemetryEventContext(renderResult: GenerateVideoResult, recovery?: RenderRecoverySummary | null) {
    const errorSummary = summarizeErrorCodes({
      startupDiagnostics,
      preflightDiagnostics,
      result: renderResult,
      resultActionSuggestion: renderResult.actionSuggestion || null,
    });
    const errorStats = buildErrorCodeStats(errorSummary);
    return buildSupportCaseSummary({
      summary: errorSummary,
      stats: errorStats,
      result: renderResult,
      recovery: recovery || null,
      startupDiagnostics,
      preflightDiagnostics,
    });
  }

  async function pushTelemetryEvent(
    renderResult: GenerateVideoResult,
    recovery?: RenderRecoverySummary | null,
    extra?: Partial<{
      eventType: string;
      firstExport: boolean;
      tags: string[];
    }>,
  ) {
    if (!state.telemetryEnabled || !telemetrySessionIdRef.current) return;
    const supportCase = captureTelemetryEventContext(renderResult, recovery);
    const mergedTags = [...supportCase.tags, ...(extra?.tags || [])];
    const nextSummary = await recordTelemetryEvent({
      sessionId: telemetrySessionIdRef.current,
      eventType: extra?.eventType || "render_result",
      timestamp: new Date().toISOString(),
      success: renderResult.ok,
      firstExport: extra?.firstExport ?? false,
      errorCode: renderResult.code || null,
      supportQueue: supportCase.queue,
      severity: supportCase.severity,
      tags: Array.from(new Set(mergedTags)),
      recoveryResumable: Boolean(recovery?.resumable),
      recoveryRetryable: Boolean(recovery?.retryable),
      recoveryCompletedChunks: recovery?.completedChunkCount ?? 0,
      recoveryReusedChunks: recovery?.reusedChunkCount ?? 0,
    });
    setTelemetrySummary(nextSummary);
  }

  function rememberCurrentProject() {
    if (!state.inputFolder) return;
    const project: RecentProject = {
      id: state.inputFolder,
      inputFolder: state.inputFolder,
      outputFolder: state.outputFolder,
      title: state.title,
      outputName: state.outputName,
      updatedAt: Date.now(),
    };
    setRecentProjects((current) => {
      const next = [project, ...current.filter((item) => item.id !== project.id)].slice(0, 5);
      saveRecentProjects(next);
      return next;
    });
  }

  useEffect(() => {
    let cancelled = false;
    window.localStorage.setItem(TELEMETRY_PREFERENCE_KEY, String(state.telemetryEnabled));

    const syncTelemetrySession = async () => {
      try {
        if (!telemetryInitializedRef.current) {
          const started = await startTelemetrySession(state.telemetryEnabled);
          if (cancelled) return;
          telemetryInitializedRef.current = true;
          telemetrySessionIdRef.current = started.sessionId || null;
          sessionFirstExportRecordedRef.current = false;
          setTelemetrySummary(started.summary);
          if (started.previousSessionRecoveredAsCrash) {
            setToast("检测到上一次应用会话未正常结束，已记录为匿名 crash 事件。");
          }
          return;
        }

        if (state.telemetryEnabled && !telemetrySessionIdRef.current) {
          const started = await startTelemetrySession(true);
          if (cancelled) return;
          telemetrySessionIdRef.current = started.sessionId || null;
          sessionFirstExportRecordedRef.current = false;
          setTelemetrySummary(started.summary);
          return;
        }

        if (!state.telemetryEnabled && telemetrySessionIdRef.current) {
          const sessionId = telemetrySessionIdRef.current;
          telemetrySessionIdRef.current = null;
          sessionFirstExportRecordedRef.current = false;
          const summary = await finishTelemetrySession(sessionId, true);
          if (!cancelled) setTelemetrySummary(summary);
        }
      } catch (error) {
        console.error("Failed to sync telemetry session:", error);
      }
    };

    void syncTelemetrySession();

    return () => {
      cancelled = true;
    };
  }, [state.telemetryEnabled]);

  useEffect(() => {
    const finishCurrentTelemetrySession = () => {
      const sessionId = telemetrySessionIdRef.current;
      if (!sessionId || !state.telemetryEnabled) return;
      void finishTelemetrySession(sessionId, true).catch((error) => {
        console.error("Failed to finish telemetry session:", error);
      });
      telemetrySessionIdRef.current = null;
    };

    window.addEventListener("beforeunload", finishCurrentTelemetrySession);
    return () => {
      window.removeEventListener("beforeunload", finishCurrentTelemetrySession);
    };
  }, [state.telemetryEnabled]);

  useEffect(() => {
    const handleWindowError = (event: ErrorEvent) => {
      if (!state.telemetryEnabled || !telemetrySessionIdRef.current) return;
      const parsed = parseAppError(event.error ?? event.message);
      void recordTelemetryEvent({
        sessionId: telemetrySessionIdRef.current,
        eventType: "frontend_crash",
        timestamp: new Date().toISOString(),
        success: false,
        errorCode: parsed?.code || null,
        supportQueue: "app-runtime",
        severity: "high",
        tags: ["frontend-runtime", "window-error"],
      })
        .then((summary) => setTelemetrySummary(summary))
        .catch((error) => {
          console.error("Failed to record window error telemetry:", error);
        });
    };

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      if (!state.telemetryEnabled || !telemetrySessionIdRef.current) return;
      const parsed = parseAppError(event.reason);
      void recordTelemetryEvent({
        sessionId: telemetrySessionIdRef.current,
        eventType: "frontend_crash",
        timestamp: new Date().toISOString(),
        success: false,
        errorCode: parsed?.code || null,
        supportQueue: "app-runtime",
        severity: "high",
        tags: ["frontend-runtime", "unhandled-rejection"],
      })
        .then((summary) => setTelemetrySummary(summary))
        .catch((error) => {
          console.error("Failed to record unhandled rejection telemetry:", error);
        });
    };

    window.addEventListener("error", handleWindowError);
    window.addEventListener("unhandledrejection", handleUnhandledRejection);
    return () => {
      window.removeEventListener("error", handleWindowError);
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
    };
  }, [state.telemetryEnabled]);

  function resetRecoveredWorkspaceRuntimeState(nextPhase: string = "已恢复项目") {
    setLogs([]);
    setPhase(nextPhase);
    setProgress(null);
    setProgressTone("idle");
    setProgressDetail(null);
    setResult(null);
    setPreflightDiagnostics(null);
    setMaterials([]);
    setPhotoSegmentCache(null);
    setVideoSegmentCache(null);
    setProxyMedia(null);
    setSelectedAudioSectionId(null);
    setRenderQueue([]);
    setSelectedMaterial(null);
    setShowGalleryOverlay(false);
    setRenderPreviewPath(null);
    setIsPlanningWorkflow(false);
    setIsCancelling(false);
    setHighlightOutput(false);
    setBackgroundPickerTarget(null);
  }

  function applyRecoveredWorkspaceRuntimeState(restored: SessionRecoveryData) {
    setLogs(restored.logs || []);
    setPhase(restored.phase || "已恢复");
    setProgress(restored.progress ?? null);
    setProgressTone(restored.progressTone || "idle");
    setProgressDetail(restored.progressDetail || null);
    setResult(restored.result || null);
    setPreflightDiagnostics(restored.preflightDiagnostics || null);
    setMaterials(restored.materials || []);
    setPhotoSegmentCache(restored.photoSegmentCache || null);
    setVideoSegmentCache(restored.videoSegmentCache || null);
    setProxyMedia(restored.proxyMedia || null);
    setSelectedAudioSectionId(restored.selectedAudioSectionId || null);
    setRenderQueue([]);
    setSelectedMaterial(null);
    setShowGalleryOverlay(false);
    setRenderPreviewPath(null);
    setIsPlanningWorkflow(false);
    setIsCancelling(false);
    setHighlightOutput(false);
    setBackgroundPickerTarget(null);
  }

  async function restoreRecentProject(project: RecentProject) {
    const projectDir = projectDirFromRecentProject(project);
    if (!projectDir) {
      setToast("最近项目缺少可恢复的项目目录。");
      return;
    }
    try {
      const loaded = await loadProjectDocumentsV5(projectDir);
      let restoredProjectState: ProjectStatePayload | null = null;
      try {
        restoredProjectState = await loadProjectState(projectDir);
      } catch (error) {
        console.warn("Project state autosave could not be loaded:", error);
      }
      const recovered = restoredProjectState ? parseSessionRecoveryData(restoredProjectState.data) : null;
      const recoveredStudio = recovered?.studio || null;
      const nextStage: StudioState["v5Stage"] = recoveredStudio?.v5RenderPlan
        ? "RENDER"
        : recoveredStudio?.v5Blueprint
          ? "BLUEPRINT"
          : loaded.renderPlan
            ? "RENDER"
            : loaded.blueprint
              ? "BLUEPRINT"
              : "INPUT";
      skipResetRef.current = true;
      state.patch({
        ...(recoveredStudio || {}),
        inputFolder: recoveredStudio?.inputFolder || project.inputFolder,
        outputFolder: recoveredStudio?.outputFolder || project.outputFolder,
        title: recoveredStudio?.title || loaded.blueprint?.title || project.title,
        titleSubtitle: recoveredStudio?.titleSubtitle || loaded.blueprint?.subtitle || state.titleSubtitle,
        outputName: recoveredStudio?.outputName || project.outputName,
        telemetryEnabled: state.telemetryEnabled,
        v5Stage: nextStage,
        v5Library: recoveredStudio?.v5Library || loaded.library,
        v5Blueprint: recoveredStudio?.v5Blueprint || loaded.blueprint,
        v5RenderPlan: recoveredStudio?.v5RenderPlan || loaded.renderPlan,
        v5Timeline: chooseRecoveredTimeline(recoveredStudio?.v5Timeline, loaded.timeline),
      });
      if (recovered) {
        applyRecoveredWorkspaceRuntimeState(recovered);
      } else {
        resetRecoveredWorkspaceRuntimeState("已恢复最近项目");
      }
      setProjectMigrationNotes(loaded.migrated ? loaded.migrationNotes : []);
      setProjectMigrationSource(project.title || shortPathName(project.inputFolder));
      const migrationSuffix = loaded.migrated ? `，并已自动迁移 ${loaded.migrationNotes.length} 项旧版项目数据` : "";
      const autosaveSuffix = recovered && restoredProjectState
        ? `，并恢复了 ${formatSnapshotSavedAt(restoredProjectState.savedAt)} 的项目草稿`
        : "";
      setRecoverableProjectState(null);
      setToast(`已恢复最近项目：${shortPathName(project.inputFolder)}${migrationSuffix}${autosaveSuffix}`);
    } catch (error) {
      console.error("Restore recent project failed:", error);
      const fallbackMessage = friendlyErrorMessage(error);
      skipResetRef.current = true;
      state.patch({
        inputFolder: project.inputFolder,
        outputFolder: project.outputFolder,
        title: project.title,
        outputName: project.outputName,
        v5Stage: "INPUT",
        v5Library: null,
        v5Blueprint: null,
        v5RenderPlan: null,
        v5Timeline: null,
        titleBackgroundPath: null,
        endBackgroundPath: null,
      });
      resetRecoveredWorkspaceRuntimeState("恢复项目失败");
      setProjectMigrationNotes([]);
      setProjectMigrationSource(null);
      setRecoverableProjectState(null);
      setToast(`已恢复项目路径，但项目文档加载失败：${fallbackMessage}`);
    }
  }

  function restoreSessionDraft(snapshot: SessionSnapshotPayload) {
    const restored = parseSessionRecoveryData(snapshot.data);
    if (!restored) {
      setToast("上次会话草稿无法解析，已跳过恢复。");
      return;
    }

    skipResetRef.current = true;
    state.patch({ ...restored.studio });
    setLogs(restored.logs || []);
    setPhase(restored.phase || "已恢复");
    setProgress(restored.progress ?? null);
    setProgressTone(restored.progressTone || "idle");
    setProgressDetail(restored.progressDetail || null);
    setResult(restored.result || null);
    setPreflightDiagnostics(restored.preflightDiagnostics || null);
    setMaterials(restored.materials || []);
    setPhotoSegmentCache(restored.photoSegmentCache || null);
    setVideoSegmentCache(restored.videoSegmentCache || null);
    setProxyMedia(restored.proxyMedia || null);
    setSelectedAudioSectionId(restored.selectedAudioSectionId || null);
    setRenderQueue([]);
    setRenderPreviewPath(null);
    setIsPlanningWorkflow(false);
    setIsCancelling(false);
    setRecoverableSession(null);
    setToast(`已恢复 ${formatSnapshotSavedAt(snapshot.savedAt)} 保存的会话草稿。`);
  }

  async function dismissSessionDraft() {
    setRecoverableSession(null);
    try {
      await clearSessionSnapshot();
      setToast("已丢弃上次会话草稿。");
    } catch (error) {
      console.error("Failed to clear session snapshot:", error);
      setToast(`丢弃会话草稿失败：${friendlyErrorMessage(error)}`);
    }
  }

  function dismissProjectRecovery() {
    setRecoverableProjectState(null);
    setToast("已忽略最近项目草稿，本次启动不再提醒。");
  }

  async function onExportDiagnostics() {
    const suggestedName = buildDiagnosticsFileName(state.outputName || state.title || "video-create-studio");
    try {
      const target = await save({
        defaultPath: suggestedName,
        filters: [{ name: "JSON", extensions: ["json"] }],
      });
      if (typeof target !== "string" || !target) return;

      setIsExportingDiagnostics(true);
      const resultResolution = result && !result.ok ? resolveResultError(result) : null;
      const exported = await exportDiagnosticBundle(target, buildDiagnosticBundlePayload({
        generatedAt: new Date().toISOString(),
        sections: {
          app: {
            product: "Video Create Studio",
            snapshotSavedAt: recoverableSession?.savedAt || null,
            recentProjectAutosaveSavedAt: recoverableProjectState?.snapshot.savedAt || null,
            exportedAtLocal: new Date().toLocaleString(),
            userAgent: window.navigator.userAgent,
            telemetryEnabled: state.telemetryEnabled,
          },
          project: {
            inputFolder: state.inputFolder,
            outputFolder: state.outputFolder,
            projectDir: v5ProjectDir || null,
            planPath: v5PlanPath || null,
            outputPath: v5OutputPath || null,
            stage: state.v5Stage,
            title: state.title,
            outputName: state.outputName,
            recentProjectAutosaveInputFolder: recoverableProjectState?.project.inputFolder || null,
          },
          upgrade: {
            migrationSource: projectMigrationSource,
            migrationNotes: projectMigrationNotes,
          },
          workflow: {
            phase,
            progress,
            progressTone,
            progressDetail,
            result,
            commandPreview: v5CommandPreview,
          },
          runtime: {
            photoSegmentCache,
            videoSegmentCache,
            proxyMedia,
            renderQueue,
            telemetrySummary: telemetrySummary
              ? {
                  ...telemetrySummary,
                  remoteEndpoint: telemetrySummary.remoteEndpoint ? "[configured]" : null,
                }
              : null,
            materialsSample: materials.slice(0, 120),
            logs: logs.slice(-120),
          },
          sessionDraft: sessionRecoveryData,
        },
        startupDiagnostics,
        preflightDiagnostics,
        result,
        resultActionSuggestion: result?.actionSuggestion || resultResolution?.actionSuggestion || null,
        resultRecovery: result?.recovery || latestRecoverableFailedJob?.recovery || null,
        telemetrySummary: telemetrySummary
          ? {
              ...telemetrySummary,
              remoteEndpoint: telemetrySummary.remoteEndpoint ? "[configured]" : null,
            }
          : null,
      }));
      setToast(`诊断包已导出：${shortPathName(exported)}`);
    } catch (error) {
      console.error("Failed to export diagnostics:", error);
      setToast(`导出诊断包失败：${friendlyErrorMessage(error)}`);
    } finally {
      setIsExportingDiagnostics(false);
    }
  }

  async function onClearTelemetryHistory() {
    setIsClearingTelemetry(true);
    try {
      const summary = await clearTelemetryHistory();
      setTelemetrySummary(summary);
      sessionFirstExportRecordedRef.current = false;
      setToast("已清空本地匿名遥测历史，当前会话将从新的统计基线继续。");
    } catch (error) {
      console.error("Failed to clear telemetry history:", error);
      setToast(`清空匿名遥测历史失败：${friendlyErrorMessage(error)}`);
    } finally {
      setIsClearingTelemetry(false);
    }
  }

  function onToggleTelemetryEnabled(nextValue: boolean) {
    if (!nextValue) {
      state.patch({ telemetryEnabled: false });
      return;
    }
    if (telemetrySummary && telemetrySummary.consentAcceptedVersion === telemetrySummary.currentConsentVersion) {
      state.patch({ telemetryEnabled: true });
      return;
    }
    setPendingTelemetryEnable(true);
    setShowTelemetryConsentDialog(true);
  }

  async function onAcceptTelemetryConsent() {
    if (!telemetrySummary) return;
    setIsSavingTelemetrySettings(true);
    try {
      const summary = await updateTelemetrySettings({
        consentAcceptedVersion: telemetrySummary.currentConsentVersion,
        remoteUploadEnabled: remoteUploadEnabledDraft,
        remoteEndpoint: remoteTelemetryEndpoint || null,
      });
      setTelemetrySummary(summary);
      setShowTelemetryConsentDialog(false);
      if (pendingTelemetryEnable) {
        state.patch({ telemetryEnabled: true });
      }
      setPendingTelemetryEnable(false);
      setToast("Telemetry consent saved. Anonymous local metrics are now available for this version.");
    } catch (error) {
      console.error("Failed to save telemetry consent:", error);
      setToast(`Failed to save telemetry consent: ${friendlyErrorMessage(error)}`);
    } finally {
      setIsSavingTelemetrySettings(false);
    }
  }

  function onDeclineTelemetryConsent() {
    setPendingTelemetryEnable(false);
    setShowTelemetryConsentDialog(false);
    state.patch({ telemetryEnabled: false });
  }

  async function onSaveRemoteTelemetrySettings() {
    setIsSavingTelemetrySettings(true);
    try {
      const summary = await updateTelemetrySettings({
        consentAcceptedVersion:
          telemetrySummary?.consentAcceptedVersion === telemetrySummary?.currentConsentVersion
            ? telemetrySummary?.currentConsentVersion
            : undefined,
        remoteUploadEnabled: remoteUploadEnabledDraft,
        remoteEndpoint: remoteTelemetryEndpoint || null,
      });
      setTelemetrySummary(summary);
      setToast("Remote telemetry settings saved.");
    } catch (error) {
      console.error("Failed to save remote telemetry settings:", error);
      setToast(`Failed to save remote telemetry settings: ${friendlyErrorMessage(error)}`);
    } finally {
      setIsSavingTelemetrySettings(false);
    }
  }

  async function onFlushRemoteTelemetryQueue() {
    setIsFlushingRemoteTelemetry(true);
    try {
      const summary = await flushRemoteTelemetryQueue();
      setTelemetrySummary(summary);
      setToast(summary.lastRemoteUploadError ? "Remote telemetry retry finished with an error." : "Remote telemetry queue flushed.");
    } catch (error) {
      console.error("Failed to flush remote telemetry queue:", error);
      setToast(`Failed to flush remote telemetry queue: ${friendlyErrorMessage(error)}`);
    } finally {
      setIsFlushingRemoteTelemetry(false);
    }
  }

  async function runRenderPreflight(): Promise<boolean> {
    if (!state.inputFolder || !state.outputFolder || !v5PlanPath || !v5OutputPath) {
      const message = "请先选择素材目录、输出目录，并确认故事蓝图生成 render_plan.json。";
      setResult({ ok: false, message, commandPreview: v5CommandPreview });
      setToast(message);
      return false;
    }

    setPreflightLoading(true);
    setPreflightDiagnostics(null);
    setPhase("正在进行渲染前预检...");
    setProgressTone("running");
    setProgressDetail("正在检查素材、输出目录、渲染计划和可写权限。");

    try {
      const diagnostics = await preflightRenderV5({
        inputFolder: state.inputFolder,
        outputDir: state.outputFolder,
        planPath: v5PlanPath,
        outputPath: v5OutputPath,
      });
      setPreflightDiagnostics(diagnostics);
      if (state.telemetryEnabled && telemetrySessionIdRef.current) {
        void recordTelemetryEvent({
          sessionId: telemetrySessionIdRef.current,
          eventType: "preflight_check",
          timestamp: new Date().toISOString(),
          success: diagnostics.ok,
          errorCode: diagnostics.code || diagnostics.checks.find((item) => !item.ok)?.code || null,
          supportQueue: diagnostics.ok ? "general-triage" : "project-validation",
          severity: diagnostics.ok ? "info" : "warning",
          tags: [
            "preflight-check",
            ...(diagnostics.ok ? [] : ["preflight-failed"]),
            ...diagnostics.checks.filter((item) => !item.ok).map((item) => item.id),
          ],
        })
          .then((summary) => setTelemetrySummary(summary))
          .catch((error) => {
            console.error("Failed to record preflight telemetry:", error);
          });
      }

      if (!diagnostics.ok) {
        const message = friendlyDiagnosticsMessage(diagnostics);
        setResult({ ok: false, message, commandPreview: v5CommandPreview });
        setToast(message);
        setProgressTone("failed");
        setProgressDetail(message);
        setPhase("渲染前预检失败");
        return false;
      }

      setLogs((prev) => [...prev, diagnostics.summary].slice(-100));
      setProgressDetail("预检通过，正在加入渲染队列。");
      rememberCurrentProject();
      return true;
    } catch (error) {
      const message = friendlyErrorMessage(error);
      setResult({ ok: false, message, commandPreview: v5CommandPreview });
      setToast(message);
      setProgressTone("failed");
      setProgressDetail(message);
      setPhase("渲染前预检失败");
      return false;
    } finally {
      setPreflightLoading(false);
    }
  }

  function syncRenderQueueEvent(event: VideoEvent) {
    if (event.type === "render_queue" && event.job_id && event.status) {
      const status = normalizeQueueStatus(event.status);
      if (status === "running") {
        activeJobRef.current = event.job_id;
        setIsCancelling(false);
      }
      if (!ACTIVE_RENDER_QUEUE_STATUSES.has(status) && activeJobRef.current === event.job_id) {
        activeJobRef.current = null;
        setIsCancelling(false);
      }

      setRenderQueue((prev) => {
        const now = Date.now();
        const existing = prev.find((item) => item.id === event.job_id);
        const nextItem: RenderQueueItem = {
          ...(existing || {
            id: event.job_id!,
            label: shortJobId(event.job_id!),
            status,
            position: Number(event.position || 0),
            progress: 0,
            createdAt: now,
            retryCount: 0,
          }),
          status,
          position: Number(event.position || 0),
          message: event.message || existing?.message,
          startedAt: status === "running" ? existing?.startedAt || now : existing?.startedAt,
          finishedAt: ACTIVE_RENDER_QUEUE_STATUSES.has(status) ? existing?.finishedAt : existing?.finishedAt || now,
          progress: status === "done" ? 100 : existing?.progress || 0,
        };
        if (existing) return prev.map((item) => (item.id === event.job_id ? nextItem : item));
        return [...prev, nextItem];
      });
      return;
    }

    if (typeof event.percent === "number" || event.message) {
      setRenderQueue((prev) =>
        prev.map((item) => {
          if (item.status !== "running") return item;
          return {
            ...item,
            progress: deriveStructuredProgress(event, item.progress) ?? item.progress,
            message: event.message || item.message,
          };
        }),
      );
    }
  }

  useEffect(() => {
    const unlisten = listen<string>("video-progress", (event) => {
      const raw = event.payload;
      const structured = parseVideoEvent(raw);
      if (structured) {
        syncRenderQueueEvent(structured);
        const nextPhase = derivePhaseFromStructuredEvent(structured);
        if (nextPhase) setPhase(nextPhase);

        const nextSegmentIndex = extractActiveSegmentIndexFromText(structured.message || "");
        if (nextSegmentIndex !== null) {
          setActiveSegmentIndex(nextSegmentIndex);
        } else if (structured.type === "result" || structured.type === "error" || structured.status === "failed" || structured.status === "cancelled") {
          setActiveSegmentIndex(null);
        }

        setProgress((prev) => deriveStructuredProgress(structured, prev));

        if (structured.type === "render_queue" && structured.status) {
          if (structured.status === "queued" || structured.status === "running") {
            setProgressTone("running");
            setProgressDetail(null);
          } else if (structured.status === "done") {
            setProgressTone("done");
            setProgressDetail(null);
          } else if (structured.status === "cancelled") {
            setProgressTone("cancelled");
            setProgressDetail(structured.message || "Render cancelled.");
          } else if (structured.status === "failed") {
            setProgressTone("failed");
            setProgressDetail(structured.message || "Render failed. Check logs for details.");
          }
        } else if (structured.type === "result") {
          setProgressTone("done");
          setProgressDetail(null);
        } else if (isStructuredFailureEvent(structured)) {
          setProgressTone("failed");
          setProgressDetail(failureMessageFromStructuredEvent(structured));
        }

        applyStructuredEvent(structured, setLogs, setMaterials, setPhotoSegmentCache, setVideoSegmentCache, setProxyMedia);
        return;
      }

      const nextSegmentIndex = extractActiveSegmentIndexFromText(raw);
      if (nextSegmentIndex !== null) setActiveSegmentIndex(nextSegmentIndex);

      setProgress((prev) => deriveProgressFromLogLine(raw, prev));
      const formattedLine = formatProgressLine(raw);
      if (!formattedLine) return;

      setLogs((prev) => {
        const next = [...prev, formattedLine];
        if (next.length > 100) return next.slice(next.length - 100);
        return next;
      });
    });

    return () => {
      unlisten.then((f) => f());
    };
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => {
    const hasLiveJobs = renderQueue.some((item) => ACTIVE_RENDER_QUEUE_STATUSES.has(item.status));
    setIsRendering(hasLiveJobs);
    if (!hasLiveJobs) {
      activeJobRef.current = null;
      setIsCancelling(false);
    }
  }, [renderQueue]);

  const v5ProjectDir = useMemo(() => {
    const base = state.outputFolder || state.inputFolder || "";
    return base ? `${base}\\.video_create_project` : "";
  }, [state.outputFolder, state.inputFolder]);

  const v5PlanPath = useMemo(() => v5ProjectDir ? `${v5ProjectDir}\\render_plan.json` : "", [v5ProjectDir]);
  const v5TimelinePath = useMemo(() => v5ProjectDir ? `${v5ProjectDir}\\timeline.json` : "", [v5ProjectDir]);

  const v5FinalOutputName = useMemo(() => {
    const outputName = state.outputName || "travel_video";
    return outputName.endsWith(".mp4") ? outputName : `${outputName}.mp4`;
  }, [state.outputName]);

  const v5OutputPath = useMemo(() => {
    return state.outputFolder ? `${state.outputFolder}\\${v5FinalOutputName}` : "";
  }, [state.outputFolder, v5FinalOutputName]);

  const latestRecoverableFailedJob = useMemo(() => {
    const failed = renderQueue
      .filter((item) => item.status === "failed" && item.recovery?.resumable && item.recovery.retryable)
      .sort((left, right) => {
        const leftTime = left.finishedAt || left.createdAt;
        const rightTime = right.finishedAt || right.createdAt;
        return rightTime - leftTime;
      });
    return failed[0] || null;
  }, [renderQueue]);

  const performanceRecommendation = useMemo(
    () => recommendPerformanceMode(state.v5RenderPlan, state.v5Library, state.quality, state.editStrategy),
    [state.v5RenderPlan, state.v5Library, state.quality, state.editStrategy],
  );

  const v5RenderParams: RenderV5Params = useMemo(() => ({
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
  }), [
    state.title,
    state.titleSubtitle,
    state.watermark,
    state.aspectRatio,
    state.quality,
    state.renderEngine,
    state.performanceMode,
    state.editStrategy,
    state.cover,
    state.titleStyle,
    state.endStyle,
    state.titleBackgroundPath,
    state.endBackgroundPath,
    state.chapterBackgroundMode,
    state.v5Library,
    state.musicMode,
    state.musicPath,
    state.musicPlaylistMode,
    state.musicPlaylistPaths,
    state.musicFitStrategy,
    state.bgmVolume,
    state.sourceAudioVolume,
    state.keepSourceAudio,
    state.autoDucking,
    state.musicFadeInSeconds,
    state.musicFadeOutSeconds,
  ]);

  const v5CommandPreview = useMemo(() => buildV5RenderCommandPreview({
    planPath: v5PlanPath || "<render_plan.json>",
    outputPath: v5OutputPath || "<输出视频路径>",
    params: v5RenderParams,
  }), [v5PlanPath, v5OutputPath, v5RenderParams]);

  const sessionRecoveryData = useMemo<SessionRecoveryData>(() => ({
    studio: captureStudioDraft(state),
    logs: logs.slice(-60),
    phase,
    progress,
    progressTone,
    progressDetail,
    result,
    preflightDiagnostics,
    materials: materials.slice(-120),
    photoSegmentCache,
    videoSegmentCache,
    proxyMedia,
    selectedAudioSectionId,
  }), [
    state,
    logs,
    phase,
    progress,
    progressTone,
    progressDetail,
    result,
    preflightDiagnostics,
    materials,
    photoSegmentCache,
    videoSegmentCache,
    proxyMedia,
    selectedAudioSectionId,
  ]);

  useEffect(() => {
    if (!sessionSnapshotReady) return;
    if (!hasMeaningfulStudioDraft(sessionRecoveryData.studio)) return;

    const timeoutId = window.setTimeout(() => {
      void saveSessionSnapshot({
        savedAt: new Date().toISOString(),
        data: sessionRecoveryData as unknown as Record<string, unknown>,
      }).catch((error) => {
        console.error("Failed to save session snapshot:", error);
      });
    }, 900);

    return () => window.clearTimeout(timeoutId);
  }, [sessionRecoveryData, sessionSnapshotReady]);

  useEffect(() => {
    if (!state.outputFolder || !v5ProjectDir) return;
    if (!hasMeaningfulStudioDraft(sessionRecoveryData.studio)) return;

    const timeoutId = window.setTimeout(() => {
      const payload: ProjectStatePayload = {
        savedAt: new Date().toISOString(),
        data: sessionRecoveryData as unknown as Record<string, unknown>,
      };
      void saveProjectState(v5ProjectDir, payload).catch((error) => {
        console.error("Failed to save project state autosave:", error);
      });
    }, 1200);

    return () => window.clearTimeout(timeoutId);
  }, [sessionRecoveryData, state.outputFolder, v5ProjectDir]);

  useEffect(() => {
    if (!state.v5Timeline || !v5TimelinePath) {
      setTimelineAutosave({ status: "idle" });
      return;
    }
    if (!state.v5Timeline.metadata?.dirty) {
      setTimelineAutosave((current) => (current.status === "idle" ? current : { status: "idle" }));
      return;
    }
    if (isApplyingTimeline) return;

    setTimelineAutosave((current) => (
      current.status === "saving" ? current : { status: "saving", savedAt: current.savedAt || null }
    ));
    const timeoutId = window.setTimeout(() => {
      const timelineToSave = state.v5Timeline;
      void saveTimelineV5(v5TimelinePath, JSON.stringify(timelineToSave, null, 2))
        .then(() => {
          setTimelineAutosave({
            status: "saved",
            savedAt: new Date().toISOString(),
            message: "Timeline draft autosaved",
          });
        })
        .catch((error) => {
          console.error("Failed to autosave dirty timeline:", error);
          setTimelineAutosave({
            status: "error",
            message: friendlyErrorMessage(error),
          });
        });
    }, 800);

    return () => window.clearTimeout(timeoutId);
  }, [state.v5Timeline, v5TimelinePath, isApplyingTimeline]);

  async function ensureBackgroundLibrary(target: BackgroundPickerTarget) {
    if (!state.inputFolder) {
      setToast("请先选择素材目录，然后再选择片头/片尾背景图。");
      return;
    }

    setBackgroundPickerTarget(target);

    if (state.v5Library) {
      return;
    }

    if (!state.outputFolder) {
      setToast("请先选择输出目录。素材库 JSON 将写入输出目录下的 .video_create_project，避免污染原始素材目录。");
      setHighlightOutput(true);
      setBackgroundPickerTarget(null);
      return;
    }

    setIsPreparingBackgroundLibrary(true);
    setPhase("正在准备素材库...");
    setProgress(10);
    setProgressTone("running");
    setProgressDetail(null);
    try {
      const library = await scanV5(state.inputFolder, v5ProjectDir, state.recursive);
      state.patch({ v5Library: library, v5Blueprint: null, v5RenderPlan: null, v5Timeline: null });
      setToast(target.kind === "title" ? "请选择片头文案背景图片。" : target.kind === "end" ? "请选择片尾文案背景图片。" : `请选择章节「${target.sectionTitle}」背景图片或视频帧。`);
    } catch (error) {
      console.error("Prepare background library failed:", error);
      setToast(`素材库准备失败: ${error}`);
      setBackgroundPickerTarget(null);
    } finally {
      setIsPreparingBackgroundLibrary(false);
    }
  }

  function onSelectBackgroundAsset(target: BackgroundPickerTarget, asset: V5Asset) {
    if (target.kind === "title") {
      state.patch({ titleBackgroundPath: asset.absolute_path, v5Timeline: null });
      setToast(`已选择片头卡背景：${asset.file.name}`);
    } else if (target.kind === "end") {
      state.patch({ endBackgroundPath: asset.absolute_path, v5Timeline: null });
      setToast(`已选择片尾背景：${asset.file.name}`);
    } else if (state.v5Blueprint) {
      const updated = updateBlueprintSection(state.v5Blueprint, target.sectionId, (section) => ({
        ...section,
        background: {
          mode: "custom_asset",
          custom_asset_id: asset.asset_id,
          custom_path: asset.absolute_path,
          user_overridden: true,
        },
        user_overridden: true,
      }));
      state.patch({ v5Blueprint: updated, v5Timeline: null });
      setToast(`已为章节「${target.sectionTitle}」选择背景：${asset.file.name}`);
    }
    setBackgroundPickerTarget(null);
  }

  function onClearBackgroundAsset(target: BackgroundPickerTarget) {
    if (target.kind === "title") {
      state.patch({ titleBackgroundPath: null, v5Timeline: null });
      setToast("片头背景已恢复默认：使用成片第一个画面首帧虚化。");
    } else if (target.kind === "end") {
      state.patch({ endBackgroundPath: null, v5Timeline: null });
      setToast("片尾背景已恢复默认：使用成片最后一个画面尾帧虚化。");
    } else if (state.v5Blueprint) {
      const updated = updateBlueprintSection(state.v5Blueprint, target.sectionId, (section) => ({
        ...section,
        background: {
          mode: state.chapterBackgroundMode,
          custom_asset_id: null,
          custom_path: null,
          user_overridden: false,
        },
      }));
      state.patch({ v5Blueprint: updated, v5Timeline: null });
      setToast(`章节「${target.sectionTitle}」背景已恢复默认。`);
    }
    setBackgroundPickerTarget(null);
  }

  async function onPickMusicFile() {
    try {
      const selected = await open({
        multiple: false,
        directory: false,
        filters: [
          { name: "Audio", extensions: ["mp3", "wav", "m4a", "aac", "flac", "ogg"] },
        ],
      });
      const path = Array.isArray(selected) ? selected[0] : selected;
      if (typeof path === "string" && path) {
        state.patch({
          musicMode: "manual",
          musicPath: path,
          musicPlaylistMode: "single",
          musicPlaylistPaths: [],
        });
        setToast(`已选择背景音乐：${shortPathName(path)}`);
      }
    } catch (error) {
      setToast(`选择音乐失败：${error}`);
    }
  }

  async function onPickMusicFiles() {
    try {
      const selected = await open({
        multiple: true,
        directory: false,
        filters: [
          { name: "Audio", extensions: ["mp3", "wav", "m4a", "aac", "flac", "ogg"] },
        ],
      });
      const paths = Array.isArray(selected)
        ? selected.filter((item): item is string => typeof item === "string" && item.length > 0)
        : [];
      if (paths.length > 0) {
        state.patch({
          musicMode: "manual",
          musicPath: paths[0],
          musicPlaylistMode: "manual_playlist",
          musicPlaylistPaths: paths,
        });
        setToast(`已添加 ${paths.length} 首背景音乐，将按顺序接力使用。`);
      }
    } catch (error) {
      setToast(`选择多首音乐失败：${error}`);
    }
  }

  function projectDirFromPlanPath(planPath?: string): string | null {
    if (!planPath) return null;
    const normalized = String(planPath).trim();
    if (!normalized) return null;
    const index = Math.max(normalized.lastIndexOf("\\"), normalized.lastIndexOf("/"));
    if (index <= 0) return null;
    return normalized.slice(0, index);
  }

  async function loadRecoverySummaryForPlan(planPath?: string): Promise<RenderRecoverySummary | null> {
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

  function resumeActionSuggestion(recovery: RenderRecoverySummary | null): string | null {
    if (!recovery?.resumable || !recovery.retryable) return null;
    const completed = recovery.completedChunkCount;
    if (completed > 0) {
      return `可直接点击“恢复并重试”，系统会复用已完成的 ${completed} 个分段，只重算失败部分。`;
    }
    return "可直接点击“恢复并重试”，系统会接着当前 stable render 进度继续执行。";
  }

  async function enqueueV5RenderJob() {
    if (!v5PlanPath || !v5OutputPath) {
      const message = "V5 渲染计划或输出路径缺失。请先确认故事蓝图并生成 render_plan.json。";
      setResult({ ok: false, message, commandPreview: v5CommandPreview });
      setToast(message);
      return;
    }

    const timelineApplied = await ensureTimelineAppliedBeforeRender("final");
    if (!timelineApplied) return;

    const preflightOk = await runRenderPreflight();
    if (!preflightOk) return;

    const hasLiveJobs = renderQueue.some((item) => ACTIVE_RENDER_QUEUE_STATUSES.has(item.status));
    if (!hasLiveJobs) {
      setToast(null);
      setResult(null);
      setLogs([]);
      setProgress(0);
      setPhase("V5 渲染已排队");
      setProgressTone("running");
      setProgressDetail(null);
      setActiveSegmentIndex(null);
      setIsCancelling(false);
    }

    const jobId = crypto.randomUUID();
    const job: RenderQueueItem = {
      id: jobId,
      label: v5FinalOutputName,
      status: "queued",
      position: 0,
      progress: 0,
      message: hasLiveJobs ? "Waiting for current render" : "Ready to start",
      planPath: v5PlanPath,
      outputPath: v5OutputPath,
      outputDir: state.outputFolder || undefined,
      commandPreview: v5CommandPreview,
      params: v5RenderParams,
      createdAt: Date.now(),
      retryCount: 0,
    };

    setRenderQueue((prev) => [...prev, job]);
    setLogs((prev) => [...prev, `渲染任务已排队: ${job.label} (${shortJobId(job.id)})`].slice(-100));
    void runRenderQueueJob(job);
  }

  async function runRenderQueueJob(job: RenderQueueItem) {
    if (!job.planPath || !job.outputPath || !job.params) return;
    try {
      await renderV5(job.planPath, job.outputPath, job.params, job.id);
      const recovery = await loadRecoverySummaryForPlan(job.planPath);
      setRenderQueue((prev) =>
        prev.map((item) =>
          item.id === job.id
            ? {
                ...item,
                status: "done",
                progress: 100,
                message: recovery?.reusedChunkCount
                  ? `Render completed with ${recovery.reusedChunkCount} reused chunks`
                  : "Render completed",
                finishedAt: item.finishedAt || Date.now(),
                recovery,
              }
            : item,
        ),
      );
      setResult({
        ok: true,
        message: `V5 视频渲染完成：${job.outputPath}`,
        commandPreview: job.commandPreview || v5CommandPreview,
        outputPath: job.outputPath,
        outputDir: job.outputDir,
        recovery,
      });
      if (recovery?.resumedFromManifest || recovery?.reusedChunkCount) {
        setLogs((prev) =>
          [
            ...prev,
            `Stable render resumed: reused ${recovery.reusedChunkCount} completed chunks for ${job.label}.`,
          ].slice(-100),
        );
      }
      const successResult: GenerateVideoResult = {
        ok: true,
        message: `V5 render completed: ${job.outputPath}`,
        commandPreview: job.commandPreview || v5CommandPreview,
        outputPath: job.outputPath,
        outputDir: job.outputDir,
        recovery,
      };
      const isFirstExport = !sessionFirstExportRecordedRef.current;
      sessionFirstExportRecordedRef.current = true;
      void pushTelemetryEvent(successResult, recovery, {
        firstExport: isFirstExport,
        tags: ["render-success"],
      }).catch((error) => {
        console.error("Failed to record render success telemetry:", error);
      });
      rememberCurrentProject();
      setProgress(100);
      setProgressTone("done");
      setPhase("渲染完成");
      setProgressTone("done");
      setProgressDetail(null);
      setActiveSegmentIndex(null);
    } catch (err: any) {
      const resolution = resolveAppError(err);
      const message = friendlyErrorMessage(err);
      const recovery = await loadRecoverySummaryForPlan(job.planPath);
      const actionSuggestion = resumeActionSuggestion(recovery) || resolution.actionSuggestion || null;
      let shouldShowFailure = true;
      let cancelled = false;
      setRenderQueue((prev) =>
        prev.map((item) => {
          if (item.id !== job.id) return item;
          const wasCancelled = item.status === "cancelled" || message.toLowerCase().includes("cancel");
          cancelled = wasCancelled;
          shouldShowFailure = !wasCancelled;
          return {
            ...item,
            status: wasCancelled ? "cancelled" : "failed",
            message: wasCancelled ? "渲染已取消" : message,
            finishedAt: item.finishedAt || Date.now(),
            recovery: wasCancelled ? null : recovery,
          };
        }),
      );
      if (shouldShowFailure) {
        setResult({
          ok: false,
          code: resolution.code || null,
          message,
          commandPreview: job.commandPreview || v5CommandPreview,
          outputPath: job.outputPath,
          outputDir: job.outputDir,
          actionSuggestion,
          recovery,
        });
        const failedResult: GenerateVideoResult = {
          ok: false,
          code: resolution.code || null,
          message,
          commandPreview: job.commandPreview || v5CommandPreview,
          outputPath: job.outputPath,
          outputDir: job.outputDir,
          actionSuggestion,
          recovery,
        };
        const isFirstExport = !sessionFirstExportRecordedRef.current;
        sessionFirstExportRecordedRef.current = true;
        void pushTelemetryEvent(failedResult, recovery, {
          firstExport: isFirstExport,
          tags: ["render-failure"],
        }).catch((error) => {
          console.error("Failed to record render failure telemetry:", error);
        });
      }
      if (!cancelled && recovery?.resumable && recovery.retryable) {
        setLogs((prev) =>
          [
            ...prev,
            `Stable render failure can resume: ${recovery.completedChunkCount} completed chunks saved for ${job.label}.`,
          ].slice(-100),
        );
      }
      setProgressTone(cancelled ? "cancelled" : "failed");
      setProgressDetail(cancelled ? "渲染已取消。" : message);
      setPhase(cancelled ? "已取消" : "渲染失败");
      setActiveSegmentIndex(null);
    }
  }

  async function onGenerate(dryRun: boolean = false) {
    if (!state.inputFolder || (!dryRun && !state.outputFolder)) {
      const warning = !state.inputFolder ? "请先选择素材目录。" : "请先选择输出目录。";
      setResult({
        ok: false,
        message: warning,
        commandPreview: v5CommandPreview,
      });
      setToast(warning);
      setHighlightOutput(Boolean(state.inputFolder && !state.outputFolder && !dryRun));
      return;
    }

    // V5 渲染路径
    if (state.v5Stage === "RENDER" && !dryRun) {
      await enqueueV5RenderJob();
      return;
      setToast(null);
      setIsRendering(true);
      setIsCancelling(false);
      setResult(null);
      setLogs([]);
      setProgress(0);
      setPhase("V5 引擎初始化...");

      try {
        if (!v5PlanPath || !v5OutputPath) {
          throw new Error("V5 渲染需要输出目录与 render_plan.json。请先选择输出目录并确认故事蓝图。")
        }

        const jobId = crypto.randomUUID();
        activeJobRef.current = jobId;
        await renderV5(v5PlanPath, v5OutputPath, v5RenderParams, jobId);
        
        setResult({ 
          ok: true, 
          message: `V5 视频渲染成功！\n保存至: ${v5OutputPath}`, 
          commandPreview: v5CommandPreview,
          outputPath: v5OutputPath,
          outputDir: state.outputFolder || undefined,
        });
        setProgress(100);
        setPhase("渲染完成");
      } catch (err: any) {
        console.error("V5 Render Error:", err);
        setResult({ 
          ok: false, 
          message: `V5 渲染失败: ${err}`, 
          commandPreview: v5CommandPreview 
        });
      } finally {
        setIsRendering(false);
        activeJobRef.current = null;
        setIsCancelling(false);
      }
      return;
    }

    const message = "请先完成 V5 扫描、故事蓝图审核和渲染计划编译，再开始最终合成。";
    setToast(message);
    setResult({
      ok: false,
      message,
      commandPreview: v5CommandPreview,
      isDryRun: dryRun,
    });
  }

  async function onPreviewRenderSample() {
    if (!v5PlanPath || !state.v5RenderPlan) {
      setToast("请先完成智能编排并生成 render_plan.json。");
      return;
    }
    const timelineApplied = await ensureTimelineAppliedBeforeRender("preview");
    if (!timelineApplied) return;
    setIsPreviewRendering(true);
    setToast(null);
    try {
      const previewPath = await previewRenderV5({
        planPath: v5PlanPath,
        params: v5RenderParams,
        maxDuration: 20,
        maxSegments: 8,
        height: 540,
        fps: 15,
      });
      setRenderPreviewPath(previewPath);
      setResult({
        ok: true,
        message: `低清预览已生成：${previewPath}`,
        commandPreview: buildV5RenderCommandPreview({
          planPath: v5PlanPath,
          outputPath: previewPath,
          params: { ...v5RenderParams, preview: true },
        }),
        outputPath: previewPath,
      });
    } catch (err: any) {
      const message = friendlyErrorMessage(err);
      setResult({
        ok: false,
        message: `低清预览生成失败：${message}`,
        commandPreview: v5CommandPreview,
      });
    } finally {
      setIsPreviewRendering(false);
    }
  }

  async function onStartV5Workflow() {
    if (isPlanningWorkflow) return;
    if (!state.inputFolder) return;
    if (!state.outputFolder) {
      const warning = "请先选择输出目录。V5.1 会把 media_library / story_blueprint / render_plan 放到输出目录下的 .video_create_project。";
      setToast(warning);
      setHighlightOutput(true);
      return;
    }
    
    setPhase("智能扫描中...");
    setProgress(10);
    setIsPlanningWorkflow(true);
    setToast(null);
    try {
      const library = await scanV5(state.inputFolder, v5ProjectDir, state.recursive);
      state.patch({ v5Library: library, v5Blueprint: null, v5RenderPlan: null, v5Timeline: null });
      
      setPhase("规划故事蓝图中...");
      setProgress(40);
      
      const libPath = `${v5ProjectDir}\\media_library.json`;
      const blueprint = await planV5(libPath, `${v5ProjectDir}\\story_blueprint.json`);
      const blueprintWithGuiText = {
        ...blueprint,
        title: state.title,
        subtitle: state.titleSubtitle,
        end_text: state.endText,
        metadata: {
          ...(blueprint.metadata || {}),
          end_text: state.endText,
          gui_title_applied: true,
        },
      };
      state.patch({ v5Blueprint: blueprintWithGuiText, v5RenderPlan: null, v5Timeline: null, v5Stage: "BLUEPRINT" });
      rememberCurrentProject();
      
      setPhase("蓝图就绪");
      setProgress(100);
      setToast("故事蓝图已生成，请开始编排您的旅行故事！");
    } catch (error) {
      console.error("V5 Workflow Error:", error);
      const message = friendlyErrorMessage(error);
      setProgressTone("failed");
      setProgressDetail(message);
      setPhase("智能编排失败");
      setToast(`智能编排失败：${message}`);
    } finally {
      setIsPlanningWorkflow(false);
    }
  }

  async function onConfirmBlueprint() {
    if (!state.inputFolder || !state.v5Blueprint) return;
    setToast(null);
    
    setPhase("正在保存蓝图...");
    setProgress(20);
    try {
      const bpPath = `${v5ProjectDir}\\story_blueprint.json`;
      const libPath = `${v5ProjectDir}\\media_library.json`;
      
      // 1. 保存：把全局章节背景模式写入故事蓝图，供 compile 阶段生成 Render Plan。
      const blueprintForCompile = withBlueprintMetadata(state.v5Blueprint, {
        edit_strategy: state.editStrategy,
        transition_profile: transitionProfileForStrategy(state.editStrategy),
        rhythm_profile: rhythmProfileForStrategy(state.editStrategy),
        performance_mode: state.performanceMode,
        render_mode: renderModeForPerformance(state.performanceMode, state.editStrategy),
        chunk_seconds: chunkSecondsForPerformance(state.performanceMode),
        chapter_background_mode: state.chapterBackgroundMode,
        title_style: normalizeTitleStyle(state.titleStyle),
        end_title_style: normalizeTitleStyle(state.endStyle),
        audio: buildAudioSettings(state, state.v5Library, state.v5RenderPlan),
        audio_blueprint: decorateAudioBlueprintForPersist(state, resolveAudioBlueprint(state), state.v5RenderPlan),
        scenic_spot_title_mode: "overlay",
      });
      await saveBlueprintV5(bpPath, JSON.stringify(blueprintForCompile, null, 2));
      
      // 2. 编译
      setPhase("正在编译渲染计划...");
      setProgress(60);
      const plan = await compileV5(bpPath, libPath, `${v5ProjectDir}\\render_plan.json`);
      setPhase("正在生成可编辑 Timeline...");
      setProgress(82);
      let timeline: V5Timeline | null = null;
      try {
        timeline = await timelineGenerateV5({
          renderPlanPath: v5PlanPath || `${v5ProjectDir}\\render_plan.json`,
          outputPath: v5TimelinePath || `${v5ProjectDir}\\timeline.json`,
          blueprintPath: bpPath,
          libraryPath: libPath,
          existingTimelinePath: v5TimelinePath || null,
          projectDir: v5ProjectDir || null,
        });
      } catch (error) {
        console.warn("Timeline generation failed; render plan fallback remains available:", error);
        setToast(`渲染计划已生成，但 Timeline 自动生成失败，将先使用 fallback 展示：${friendlyErrorMessage(error)}`);
      }
      
      // 3. 进入渲染阶段
      state.patch({ v5Blueprint: blueprintForCompile, v5RenderPlan: plan, v5Timeline: timeline, v5Stage: "RENDER" });
      rememberCurrentProject();
      setPhase("渲染计划就绪");
      setProgress(100);
    } catch (error) {
      console.error("Confirm Blueprint Error:", error);
      setToast(`确认失败：${friendlyErrorMessage(error)}`);
    }
  }

  function timelineApplyCopy(intent: "manual" | "preview" | "final") {
    if (intent === "preview") {
      return {
        phase: "正在应用 Timeline 编辑，用于生成预览...",
      };
    }
    if (intent === "final") {
      return {
        phase: "正在应用 Timeline 编辑，用于最终导出...",
      };
    }
    return {
      phase: "正在应用 Timeline 编辑...",
    };
  }

  async function onApplyTimelineToRenderPlan(intent: "manual" | "preview" | "final" = "manual"): Promise<boolean> {
    if (!state.v5Timeline || !state.v5RenderPlan || !v5TimelinePath || !v5PlanPath) {
      setToast("当前没有可应用的 Timeline。请先生成可编辑 Timeline。");
      return false;
    }
    if (isApplyingTimeline) {
      setToast("Timeline 正在应用中，请等待当前编译完成。");
      return false;
    }
    const copy = timelineApplyCopy(intent);
    setIsApplyingTimeline(true);
    setTimelineApplyIntent(intent);
    setToast(null);
    setPhase(copy.phase);
    setProgress(70);
    try {
      await saveTimelineV5(v5TimelinePath, JSON.stringify(state.v5Timeline, null, 2));
      const nextPlan = await timelineCompileV5(v5TimelinePath, v5PlanPath, v5PlanPath);
      const nextTimeline: V5Timeline = {
        ...state.v5Timeline,
        metadata: {
          ...(state.v5Timeline.metadata || {}),
          dirty: false,
          dirty_reason: null,
          last_edit_operation: "timeline_compile",
        },
      };
      await saveTimelineV5(v5TimelinePath, JSON.stringify(nextTimeline, null, 2));
      state.patch({ v5Timeline: nextTimeline, v5RenderPlan: nextPlan, v5Stage: "RENDER" });
      rememberCurrentProject();
      setPhase("Timeline 已应用到渲染计划");
      setProgress(100);
      setToast("Timeline 编辑已应用，预览和导出会使用新的 render_plan.json。");
      return true;
    } catch (error) {
      console.error("Apply Timeline Error:", error);
      setToast(`Timeline 应用失败：${friendlyErrorMessage(error)}`);
      return false;
    } finally {
      setIsApplyingTimeline(false);
      setTimelineApplyIntent(null);
    }
  }

  async function ensureTimelineAppliedBeforeRender(intent: "preview" | "final"): Promise<boolean> {
    if (!state.v5Timeline?.metadata?.dirty) return true;
    if (isApplyingTimeline) {
      setToast("Timeline 正在应用中，请稍后再开始预览或导出。");
      return false;
    }
    return await onApplyTimelineToRenderPlan(intent);
  }

  async function onCancel() {
    const jobId = activeJobRef.current;
    if (!jobId || isCancelling) return;

    setIsCancelling(true);
    setPhase("正在停止");
    setLogs((prev) => [...prev, "正在停止当前渲染任务..."]);
    const response = await cancelVideo(jobId);
    if (!response.ok) {
      setToast(response.message);
      setIsCancelling(false);
    }
  }

  async function onCancelQueueJob(jobId: string) {
    const isCurrent = activeJobRef.current === jobId;
    if (isCurrent) setIsCancelling(true);
    setRenderQueue((prev) =>
      prev.map((item) =>
        item.id === jobId && ACTIVE_RENDER_QUEUE_STATUSES.has(item.status)
          ? { ...item, message: "Cancelling..." }
          : item,
      ),
    );
    const response = await cancelVideo(jobId);
    if (!response.ok) {
      setToast(response.message);
      if (isCurrent) setIsCancelling(false);
      return;
    }
    setRenderQueue((prev) =>
      prev.map((item) =>
        item.id === jobId
          ? {
              ...item,
              status: "cancelled",
              message: response.message || "Render cancelled",
              finishedAt: item.finishedAt || Date.now(),
            }
          : item,
      ),
    );
  }

  function onRetryQueueJob(item: RenderQueueItem) {
    if (!item.planPath || !item.outputPath || !item.params) {
      setToast("This render job cannot be retried because its render parameters are missing.");
      return;
    }
    const hasLiveJobs = renderQueue.some((queueItem) => ACTIVE_RENDER_QUEUE_STATUSES.has(queueItem.status));
    if (!hasLiveJobs) {
      setResult(null);
      setProgress(0);
      setPhase("V5 render queued");
      setIsCancelling(false);
    }
    const retryJob: RenderQueueItem = {
      ...item,
      id: crypto.randomUUID(),
      status: "queued",
      position: 0,
      progress: 0,
      message: item.recovery?.resumable ? "Resume retry queued" : "Retry queued",
      createdAt: Date.now(),
      startedAt: undefined,
      finishedAt: undefined,
      retryCount: item.retryCount + 1,
      recovery: null,
    };
    setRenderQueue((prev) => [...prev, retryJob]);
    setLogs((prev) =>
      [
        ...prev,
        item.recovery?.resumable
          ? `Resume retry queued: ${retryJob.label} (${shortJobId(retryJob.id)}) will reuse completed stable chunks.`
          : `Retry queued: ${retryJob.label} (${shortJobId(retryJob.id)})`,
      ].slice(-100),
    );
    void runRenderQueueJob(retryJob);
  }

  return (
    <>
      <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <Clapperboard size={22} />
          </div>
          <div>
            <strong>Video Create Studio</strong>
            <span>智能旅行视频生成器</span>
          </div>
        </div>

        <nav className="nav-list" aria-label="主工作台流程">
          <button className={`nav-item${activeNav === "workspace" ? " active" : ""}`} onClick={() => scrollToSection("workspace")}>
            <ImagePlus size={18} />
            素材
          </button>
          <button className={`nav-item${activeNav === "settings" ? " active" : ""}`} onClick={() => scrollToSection("settings")}>
            <Settings2 size={18} />
            参数
          </button>
          <button className={`nav-item${activeNav === "engine" ? " active" : ""}`} onClick={() => scrollToSection("engine")}>
            <Gauge size={18} />
            引擎
          </button>
          <button className={`nav-item${activeNav === "ai" ? " active" : ""}`} onClick={() => scrollToSection("ai")}>
            <Sparkles size={18} />
            AI 蓝图
          </button>
        </nav>
        <div className="sidebar-secondary-nav" aria-label="辅助页面">
          <button className={`nav-item${appView === "studio" ? " active" : ""}`} onClick={() => setAppView("studio")}>
            <LayoutGrid size={18} />
            主工作台
          </button>
          <button className={`nav-item${appView === "diagnostics" ? " active" : ""}`} onClick={() => setAppView("diagnostics")}>
            <ListChecks size={18} />
            诊断中心
          </button>
          <button className={`nav-item${appView === "settingsCenter" ? " active" : ""}`} onClick={() => setAppView("settingsCenter")}>
            <Settings2 size={18} />
            设置中心
          </button>
        </div>
      </aside>

      <section className="workspace" id="workspace">
        {toast && <Toast title={state.v5Stage === "BLUEPRINT" ? "蓝图生成成功" : "提示"} message={toast} onClose={() => setToast(null)} />}
        <div className="workspace-inner">
        {appView === "diagnostics" ? (
          <>
            <header className="topbar support-page-header">
              <div>
                <p className="eyebrow">SUPPORT & DIAGNOSTICS</p>
                <h1>诊断中心</h1>
                <p className="page-subtitle">排障、支持和研发验证集中在这里，不进入用户制作视频的主流程。</p>
              </div>
              <div className="topbar-actions">
                <button className="secondary-action" disabled={isExportingDiagnostics} onClick={onExportDiagnostics}>
                  {isExportingDiagnostics ? <Loader2 className="spin" size={18} /> : <ListChecks size={18} />}
                  {isExportingDiagnostics ? "正在导出诊断包" : "导出诊断包"}
                </button>
              </div>
            </header>
            <StartupHealthCard diagnostics={startupDiagnostics} loading={startupDiagnosticsLoading} />
            {(preflightLoading || preflightDiagnostics) && (
              <DiagnosticsCard
                title="渲染前预检"
                kicker="RENDER PREFLIGHT"
                diagnostics={preflightDiagnostics}
                loading={preflightLoading}
                loadingText="正在检查素材、输出目录和渲染计划..."
              />
            )}
            {projectMigrationNotes.length > 0 && projectMigrationSource && (
              <ProjectMigrationCard notes={projectMigrationNotes} source={projectMigrationSource} />
            )}
          </>
        ) : appView === "settingsCenter" ? (
          <>
            <header className="topbar support-page-header">
              <div>
                <p className="eyebrow">PREFERENCES & ACCOUNT</p>
                <h1>设置中心</h1>
                <p className="page-subtitle">偏好、授权、远程上报和后续账号能力集中在这里。</p>
              </div>
            </header>
            <TelemetrySummaryCard
              enabled={state.telemetryEnabled}
              summary={telemetrySummary}
              isClearing={isClearingTelemetry}
              onClear={onClearTelemetryHistory}
              remoteEndpoint={remoteTelemetryEndpoint}
              remoteUploadEnabled={remoteUploadEnabledDraft}
              isSavingSettings={isSavingTelemetrySettings}
              isFlushingRemote={isFlushingRemoteTelemetry}
              onRemoteEndpointChange={setRemoteTelemetryEndpoint}
              onRemoteUploadEnabledChange={setRemoteUploadEnabledDraft}
              onSaveRemoteSettings={onSaveRemoteTelemetrySettings}
              onFlushRemoteQueue={onFlushRemoteTelemetryQueue}
            />
            <section className="startup-health-card">
              <div className="startup-health-head">
                <div>
                  <span className="startup-health-kicker">ACCOUNT</span>
                  <strong>邮箱授权登录</strong>
                </div>
                <span className="startup-health-badge pending">Planned</span>
              </div>
              <p className="telemetry-summary-note">
                后续可用于绑定授权、同步诊断包和支持工单；当前版本先保留本地设置与手动诊断包导出。
              </p>
            </section>
          </>
        ) : (
          <>
        {projectMigrationNotes.length > 0 && projectMigrationSource && (
          <ProjectMigrationCard notes={projectMigrationNotes} source={projectMigrationSource} />
        )}
        {recoverableSession && (
          <SessionRecoveryCard
            snapshot={recoverableSession}
            onDismiss={dismissSessionDraft}
            onRestore={restoreSessionDraft}
          />
        )}
        {!recoverableSession && recoverableProjectState && (
          <ProjectRecoveryCard
            project={recoverableProjectState.project}
            snapshot={recoverableProjectState.snapshot}
            onDismiss={dismissProjectRecovery}
            onRestore={() => void restoreRecentProject(recoverableProjectState.project)}
          />
        )}
        <RecentProjectsCard projects={recentProjects} onRestore={restoreRecentProject} />
        {(preflightLoading || preflightDiagnostics) && (
          <DiagnosticsCard
            title="渲染前预检"
            kicker="RENDER PREFLIGHT"
            diagnostics={preflightDiagnostics}
            loading={preflightLoading}
            loadingText="正在检查素材、输出目录和渲染计划..."
          />
        )}
        <header className="topbar">
          <div>
            <p className="eyebrow">GUI MVP</p>
            <h1>Turn Moments into Motion.</h1>
          </div>
          <div className="topbar-actions">
            <button className="secondary-action" disabled={isExportingDiagnostics} onClick={onExportDiagnostics}>
              {isExportingDiagnostics ? <Loader2 className="spin" size={18} /> : <ListChecks size={18} />}
              {isExportingDiagnostics ? "正在导出诊断包" : "导出诊断包"}
            </button>
            {state.v5Stage === "BLUEPRINT" && (
               <button className="secondary-action" onClick={() => state.patch({ v5Stage: "INPUT" })}>
                 <FolderOpen size={18} /> 重新选择
               </button>
            )}
            {state.v5Stage === "RENDER" && (
              <button
                className={`primary-action${isRendering ? " danger" : ""}`}
                onClick={isRendering ? onCancel : () => onGenerate(false)}
              >
                {isRendering ? (isCancelling ? <Wand2 className="spin" size={18} /> : <Square size={16} />) : <Play size={18} />}
                {isRendering ? (isCancelling ? "正在停止" : "停止生成") : "开始渲染"}
              </button>
            )}
          </div>
        </header>

        <div className="content-grid">
          <section className="panel import-panel">
            <SectionTitle icon={<FolderOpen size={18} />} title="素材导入" />
            <FolderSelector inputFolder={state.inputFolder} setInputFolder={state.setInputFolder} />
          </section>

          <section className="panel" id="settings">
            <SectionTitle icon={<Settings2 size={18} />} title="生成参数" />
            <div className="form-grid">
              <label>
                视频片头标题（非封面）
                <input value={state.title} onChange={(event) => state.patch({ title: event.target.value })} />
                <div className="background-field-actions">
                  <button type="button" className="background-pick-btn title-template" onClick={() => setTitleLabTarget("title")}>
                    <Sparkles size={14} /> {titleTemplateLabel(state.titleStyle)}
                  </button>
                  <button type="button" className="background-pick-btn" disabled={!state.inputFolder} onClick={() => ensureBackgroundLibrary({ kind: "title" })}>
                    <ImagePlus size={14} /> 选择片头背景
                  </button>
                  <span className="background-field-hint" title={state.titleBackgroundPath || ""}>
                    {state.titleBackgroundPath ? shortPathName(state.titleBackgroundPath) : "默认：首个素材首帧虚化；封面默认复用片头卡"}
                  </span>
                </div>
              </label>
              <label>
                视频片头副标题（可选，不填则不显示）
                <input value={state.titleSubtitle} onChange={(event) => state.patch({ titleSubtitle: event.target.value })} />
              </label>
              <label>
                片尾文字
                <input value={state.endText} onChange={(event) => state.patch({ endText: event.target.value })} />
                <div className="background-field-actions">
                  <button type="button" className="background-pick-btn title-template" onClick={() => setTitleLabTarget("end")}>
                    <Sparkles size={14} /> {titleTemplateLabel(state.endStyle)}
                  </button>
                  <button type="button" className="background-pick-btn" disabled={!state.inputFolder} onClick={() => ensureBackgroundLibrary({ kind: "end" })}>
                    <ImagePlus size={14} /> 选择片尾背景
                  </button>
                  <span className="background-field-hint" title={state.endBackgroundPath || ""}>
                    {state.endBackgroundPath ? shortPathName(state.endBackgroundPath) : "默认：最后素材尾帧虚化"}
                  </span>
                </div>
              </label>
              <label>
                输出文件名
                <input value={state.outputName} onChange={(event) => state.patch({ outputName: event.target.value })} />
              </label>
              <OutputFolderSelector
                disabled={!state.inputFolder}
                invalid={highlightOutput && !state.outputFolder}
                outputFolder={state.outputFolder}
                setOutputFolder={(folder) => {
                  state.setOutputFolder(folder);
                  setHighlightOutput(false);
                  setToast(null);
                }}
              />
              <label>
                水印
                <input value={state.watermark} onChange={(event) => state.patch({ watermark: event.target.value })} />
              </label>
              <EditStrategyPreview
                value={state.editStrategy}
                onChange={(editStrategy) => state.patch({ editStrategy })}
              />
              <label>
                底层渲染方式
                <select
                  value={state.renderEngine}
                  onChange={(event) => state.patch({ renderEngine: event.target.value as RenderEngine })}
                >
                  <option value="auto">自动选择</option>
                  <option value="ffmpeg_concat">FFmpeg 快速拼接</option>
                  <option value="moviepy_crossfade">MoviePy 交叉淡化</option>
                </select>
              </label>
              <PerformanceModeControl
                value={state.performanceMode}
                recommendation={performanceRecommendation}
                onChange={(performanceMode) => state.patch({ performanceMode })}
              />
              {photoSegmentCache && photoSegmentCache.eligible > 0 ? (
                <div className="photo-cache-insight-card">
                  <div className="photo-cache-insight-head">
                    <div>
                      <span className="photo-cache-kicker">照片段缓存反馈</span>
                      <strong>{photoSegmentCacheHeadline(photoSegmentCache)}</strong>
                    </div>
                    <span className="photo-cache-badge">候选 {photoSegmentCache.eligible}</span>
                  </div>
                  <div className="photo-cache-insight-grid">
                    <div>
                      <span>复用缓存</span>
                      <strong>{photoSegmentCache.hit} 段</strong>
                    </div>
                    <div>
                      <span>省掉实时拼装</span>
                      <strong>{photoSegmentCache.saved_live_composes || photoSegmentCache.hit} 次</strong>
                    </div>
                    <div>
                      <span>节省实时合成</span>
                      <strong>{formatDurationCompact(photoSegmentCache.saved_render_seconds)}</strong>
                    </div>
                    <div>
                      <span>本次新建</span>
                      <strong>{photoSegmentCache.created} 段</strong>
                    </div>
                    <div>
                      <span>叠字命中</span>
                      <strong>{photoSegmentCache.overlay_hit} 段</strong>
                    </div>
                    <div>
                      <span>安全回退</span>
                      <strong>{photoSegmentCache.fallback} 段</strong>
                    </div>
                  </div>
                  <p className="photo-cache-insight-note">
                    {photoSegmentCacheNote(photoSegmentCache)}
                  </p>
                </div>
              ) : null}
              {videoSegmentCache && videoSegmentCache.eligible > 0 ? (
                <div className="video-cache-insight-card">
                  <div className="video-cache-insight-head">
                    <div>
                      <span className="video-cache-kicker">视频段缓存反馈</span>
                      <strong>{videoSegmentCacheHeadline(videoSegmentCache)}</strong>
                    </div>
                    <span className="video-cache-badge">候选 {videoSegmentCache.eligible}</span>
                  </div>
                  <div className="video-cache-insight-grid">
                    <div>
                      <span>复用缓存</span>
                      <strong>{videoSegmentCache.hit} 段</strong>
                    </div>
                    <div>
                      <span>省掉实时适配</span>
                      <strong>{videoSegmentCache.saved_live_fits || videoSegmentCache.hit} 次</strong>
                    </div>
                    <div>
                      <span>节省视频适配</span>
                      <strong>{formatDurationCompact(videoSegmentCache.saved_render_seconds)}</strong>
                    </div>
                    <div>
                      <span>本次新建</span>
                      <strong>{videoSegmentCache.created} 段</strong>
                    </div>
                    <div>
                      <span>安全回退</span>
                      <strong>{videoSegmentCache.fallback} 段</strong>
                    </div>
                  </div>
                  <p className="video-cache-insight-note">
                    {videoSegmentCacheNote(videoSegmentCache)}
                  </p>
                </div>
              ) : null}
              <MusicAudioPanel state={state} onPickMusicFile={onPickMusicFile} onPickMusicFiles={onPickMusicFiles} />
              {proxyMedia && proxyMedia.eligible > 0 ? (
                <StatusItem
                  label="Proxy media"
                  value={proxyMediaLabel(proxyMedia)}
                  highlight={proxyMedia.hit > 0}
                />
              ) : null}
            </div>

            <div className="option-row">
              <SegmentedControl
                label="画幅"
                value={state.aspectRatio}
                options={[
                  ["16:9", "横屏"],
                  ["9:16", "竖屏"],
                ]}
                onChange={(value) => state.patch({ aspectRatio: value as AspectRatio })}
              />
              <SegmentedControl
                label="质量"
                value={state.quality}
                options={[
                  ["draft", "草稿"],
                  ["standard", "标准"],
                  ["high", "高质量"],
                ]}
                onChange={(value) => state.patch({ quality: value as Quality })}
              />
            </div>

            <div className="option-row chapter-bg-option-row">
              <SegmentedControl
                label="章节卡背景"
                value={state.chapterBackgroundMode}
                options={[
                  ["auto_bridge", "智能过渡"],
                  ["auto_first_asset", "章节首图"],
                  ["plain", "纯色极简"],
                ]}
                onChange={(value) => state.patch({ chapterBackgroundMode: value as V5ChapterBackgroundMode })}
              />
              <div className="chapter-bg-help">
                城市 / 日期默认插入完整章节卡；景点默认使用首素材标题叠加，减少视频割裂。
              </div>
            </div>

            <div className="toggles">
              <Toggle checked={state.recursive} label="递归读取子目录" onChange={(recursive) => state.patch({ recursive })} />
              <Toggle
                checked={state.chaptersFromDirs}
                label="按子目录生成章节卡"
                onChange={(chaptersFromDirs) => state.patch({ chaptersFromDirs })}
              />
              <Toggle checked={state.cover} label="生成 B 站封面" onChange={(cover) => state.patch({ cover })} />
              <Toggle checked={state.telemetryEnabled} label="匿名遥测（可选）" onChange={onToggleTelemetryEnabled} />
            </div>
          </section>

          <section className="panel wide-panel" id="engine">
            {state.v5Stage === "INPUT" ? (
               <div className="v5-welcome-hero">
                  <div className="hero-icon"><Sparkles size={48} /></div>
                  <h2>欢迎使用 Video Create Studio V5</h2>
                  <p>选择素材文件夹后，我们将为您自动识别城市、日期与景点。</p>
                  <button
                    className={`primary-action pulse-guidance${isPlanningWorkflow ? " busy" : ""}`}
                    disabled={!state.inputFolder || isPlanningWorkflow}
                    onClick={onStartV5Workflow}
                  >
                    <Wand2 size={20} className={isPlanningWorkflow ? "spin" : undefined} />
                    {isPlanningWorkflow ? "正在智能编排" : "开始智能编排"}
                  </button>
                  {isPlanningWorkflow && (
                    <div className="hero-planning-progress" role="status" aria-live="polite">
                      <ProgressBar
                        isDryRun={false}
                        percent={progress || 0}
                        phase={phase}
                        status="running"
                        detail={progressDetail}
                      />
                      <p className="hero-progress-hint">
                        素材较多时可能需要几十秒到几分钟，正在扫描素材并生成故事蓝图。
                      </p>
                    </div>
                  )}
               </div>
            ) : state.v5Stage === "BLUEPRINT" ? (
               <div className="blueprint-editor-container">
                  <SectionTitle icon={<ListChecks size={18} />} title="故事蓝图审核" />
                  <BlueprintEditor 
                    blueprint={state.v5Blueprint!} 
                    library={state.v5Library!}
                    chapterBackgroundMode={state.chapterBackgroundMode}
                    onPickSectionBackground={(section) =>
                      ensureBackgroundLibrary({
                        kind: "section",
                        sectionId: section.section_id,
                        sectionTitle: section.title,
                        assetIds: (section.asset_refs || [])
                          .filter((ref) => ref.enabled !== false)
                          .map((ref) => ref.asset_id),
                      })
                    }
                    onUpdate={(bp) => state.patch({ v5Blueprint: bp, v5Timeline: null })}
                  />
                  <div className="blueprint-actions">
                     <button className="secondary-action" onClick={() => state.patch({ v5Stage: "INPUT" })}>重新扫描</button>
                     <button className="primary-action" onClick={onConfirmBlueprint}>确认并进入渲染</button>
                  </div>
               </div>
            ) : (
               <div className="render-stage-container">
                  <SectionTitle icon={<FileVideo size={18} />} title="渲染执行" />
                  
                  {(isRendering || logs.length > 0 || progress !== null || Boolean(progressDetail)) && (
                    <div className="render-progress-area">
                      <ProgressBar
                        isDryRun={state.isDryRun}
                        percent={progress || 0}
                        phase={phase}
                        status={progressTone}
                        detail={progressDetail}
                      />
                    </div>
                  )}

                  {renderQueue.length > 0 && (
                    <RenderQueuePanel
                      queue={renderQueue}
                      onCancel={onCancelQueueJob}
                      onRetry={onRetryQueueJob}
                    />
                  )}

                  {(
                    <div className="v5-render-trigger">
                       <button className="secondary-action" disabled={!state.v5RenderPlan || isPreviewRendering || isApplyingTimeline} onClick={onPreviewRenderSample}>
                          <Play size={18} /> {isPreviewRendering ? "正在生成低清预览..." : "生成低清小样"}
                       </button>
                       {renderPreviewPath && (
                         <div className="render-real-preview">
                           <div className="render-real-preview-header">
                             <strong>真实低清预览</strong>
                             <span>同一份 render plan，低分辨率快速审核</span>
                           </div>
                           <video src={convertFileSrc(renderPreviewPath)} controls />
                         </div>
                       )}
                       <button className="primary-action pulse-guidance" disabled={!state.outputFolder || !state.v5RenderPlan || isApplyingTimeline} onClick={() => onGenerate(false)}>
                          {isRendering ? <Clock size={24} /> : <PlayCircle size={24} />} {isRendering ? "Add to render queue" : "Start final render"}
                       </button>
                       <p className="hint-text">点击上方按钮，启动 V5 渲染引擎合并素材并导出视频。</p>
                    </div>
                  )}

                  {state.v5RenderPlan && (
                    <div className="render-plan-preview">
                       <div className="plan-summary">
                          <span>总时长: {state.v5RenderPlan!.total_duration.toFixed(1)}s</span>
                          <span>总片段数: {state.v5RenderPlan!.segments.length}</span>
                          {selectedAudioSectionId ? <span>章节聚焦: {selectedAudioSectionId}</span> : null}
                          {isRendering && progress !== null && <span className="current-progress-text">进度: {progress}%</span>}
                       </div>
                       {state.v5Timeline ? (
                         <div className="timeline-action-bar">
                           <span>{state.v5Timeline.metadata?.dirty ? "Timeline 有未应用编辑" : "Timeline 已同步到当前渲染计划"}</span>
                           <span className={`timeline-apply-status${isApplyingTimeline ? " applying" : state.v5Timeline.metadata?.dirty ? " dirty" : ""}`}>
                             {isApplyingTimeline
                               ? timelineApplyIntent === "preview"
                                 ? "正在为预览应用编辑"
                                 : timelineApplyIntent === "final"
                                   ? "正在为最终导出应用编辑"
                                   : "正在应用编辑"
                               : state.v5Timeline.metadata?.dirty
                                 ? "预览/导出前会自动应用"
                                 : "预览和导出已使用最新方案"}
                           </span>
                           {timelineAutosave.status !== "idle" ? (
                             <span className={`timeline-autosave-status ${timelineAutosave.status}`}>
                               {timelineAutosave.status === "saving"
                                 ? "草稿保存中"
                                 : timelineAutosave.status === "saved"
                                   ? `草稿已保存${timelineAutosave.savedAt ? ` ${new Date(timelineAutosave.savedAt).toLocaleTimeString()}` : ""}`
                                   : `草稿保存失败${timelineAutosave.message ? `：${timelineAutosave.message}` : ""}`}
                             </span>
                           ) : null}
                           <button
                             className={`timeline-apply-btn${state.v5Timeline.metadata?.dirty ? " dirty" : ""}`}
                             type="button"
                             disabled={isApplyingTimeline || isRendering}
                             onClick={() => onApplyTimelineToRenderPlan("manual")}
                           >
                             {isApplyingTimeline ? <Loader2 className="spin" size={14} /> : <ListChecks size={14} />}
                             {state.v5Timeline.metadata?.dirty ? "应用 Timeline 编辑" : "同步 Timeline"}
                           </button>
                         </div>
                       ) : null}
                       <div ref={segmentsTimelineRef}>
                         <TimelineEditor
                           timeline={state.v5Timeline}
                           renderPlan={state.v5RenderPlan}
                           activeSegmentIndex={activeSegmentIndex}
                           isRendering={isRendering}
                           isApplyingTimeline={isApplyingTimeline}
                           selectedSectionId={selectedAudioSectionId}
                           onSelectSection={(sectionId) => {
                             setSelectedAudioSectionId((current) => (current === sectionId ? null : sectionId));
                           }}
                           onTimelineChange={(timeline) => state.patch({ v5Timeline: timeline })}
                         />
                       </div>
                    </div>
                  )}

                  {state.v5RenderPlan ? (
                    <RenderAudioTimelineCard
                      plan={state.v5RenderPlan}
                      activeSegmentIndex={activeSegmentIndex}
                      isRendering={isRendering}
                      selectedSectionId={selectedAudioSectionId}
                      onSelectSection={setSelectedAudioSectionId}
                    />
                  ) : null}

                  <div className="command-box">{v5CommandPreview}</div>
                  
                  {(isRendering || logs.length > 0) && (
                    <div className="log-viewer">
                      {logs.length === 0 ? <div className="log-placeholder">正在启动引擎...</div> : logs.map((log, i) => <div key={i}>{log}</div>)}
                      <div ref={logEndRef} />
                    </div>
                  )}
               </div>
            )}
            
            <div className="status-strip">
               <StatusItem label="输入目录" value={state.inputFolder ? state.inputFolder.split(/[/\\]/).pop() || "已选择" : "未选择"} />
               <StatusItem 
                 label="叙事阶段" 
                 value={isRendering ? "正在渲染" : (state.v5Stage === "BLUEPRINT" ? "故事编排" : "就绪执行")} 
                 highlight={isRendering}
               />
               <StatusItem label="当前画幅" value={state.aspectRatio} />
              <StatusItem label="渲染质量" value={qualityLabel(state.quality)} />
              <StatusItem label="性能档位" value={performanceModeLabel(state.performanceMode)} />
              {photoSegmentCache && photoSegmentCache.eligible > 0 ? (
                <StatusItem
                  label="照片缓存"
                  value={photoSegmentCacheLabel(photoSegmentCache)}
                  highlight={photoSegmentCache.hit > 0}
                />
              ) : null}
            </div>
            {result && (
              <ResultCard
                result={result}
                onResumeRetry={
                  !result.ok && result.recovery?.resumable && result.recovery.retryable && latestRecoverableFailedJob
                    ? () => onRetryQueueJob(latestRecoverableFailedJob)
                    : undefined
                }
              />
            )}
          </section>

          <section className="panel wide-panel ai-panel" id="ai">
            <SectionTitle icon={<Sparkles size={18} />} title="下一阶段能力" />
            <div className="feature-list">
              <Feature title="AI 配乐蓝图" text="根据画面节奏生成 BGM 风格与时间段建议。" />
              <Feature title="模板匹配" text="按旅行、探店、日常 Vlog 等素材特征选择剪辑方案。" />
              <Feature title="时间线微调" text="引入轨道视图，后续只同步状态，不在前端重渲染视频。" />
            </div>
          </section>
        </div>
          </>
        )}
        </div>
      </section>
    </main>
    {showGalleryOverlay && (
      <div className="gallery-overlay">
        <div className="gallery-overlay-header">
          <div className="gallery-title-area">
             <SectionTitle icon={<LayoutGrid size={22} />} title="素材资产库" />
             <p className="gallery-subtitle">共有 {materials.length} 个扫描到的媒体文件</p>
          </div>
          
          <div className="gallery-nav-pills">
             <button 
               className={galleryView === 'chapter' ? 'active' : ''} 
               onClick={() => setGalleryView('chapter')}
             >
               {(() => {
                 const chapters = Array.from(new Set(materials.map(m => m.chapter).filter(Boolean))) as string[];
                 const isDate = chapters.some(c => /day|天|日|\d{4}|\d{1,2}[-.]\d{1,2}/i.test(c));
                 if (isDate) return <><Calendar size={14} /> 按日期</>;
                 const isCity = chapters.some(c => /市|镇|区|州|岛/i.test(c));
                 if (isCity) return <><MapPin size={14} /> 按城市</>;
                 const isSpot = chapters.some(c => /寺|校|山|园|桥|塔|宫|馆/i.test(c));
                 if (isSpot) return <><Palmtree size={14} /> 按景点</>;
                 return <><Folder size={14} /> 按目录</>;
               })()}
             </button>
             <button 
               className={galleryView === 'type' ? 'active' : ''} 
               onClick={() => setGalleryView('type')}
             >
               <Layers size={14} /> 按类型
             </button>
             <button 
               className={galleryView === 'time' ? 'active' : ''} 
               onClick={() => setGalleryView('time')}
             >
               <Calendar size={14} /> 按拍摄时间
             </button>
          </div>


          <button className="close-overlay-btn" onClick={() => setShowGalleryOverlay(false)}>
            <X size={20} /> 退出管理
          </button>
        </div>
        <div className="gallery-overlay-content">
          <MaterialGallery materials={materials} onSelect={setSelectedMaterial} viewMode={galleryView} />
        </div>
      </div>
    )}

    {showTelemetryConsentDialog && telemetrySummary && (
      <TelemetryConsentDialog
        consentVersion={telemetrySummary.currentConsentVersion}
        isSaving={isSavingTelemetrySettings}
        onAccept={onAcceptTelemetryConsent}
        onDecline={onDeclineTelemetryConsent}
      />
    )}

    {backgroundPickerTarget && (
      <BackgroundAssetPicker
        target={backgroundPickerTarget}
        library={state.v5Library}
        selectedPath={getSelectedBackgroundPath(backgroundPickerTarget, state)}
        loading={isPreparingBackgroundLibrary}
        onSelect={(asset) => onSelectBackgroundAsset(backgroundPickerTarget, asset)}
        onUseDefault={() => onClearBackgroundAsset(backgroundPickerTarget)}
        onClose={() => setBackgroundPickerTarget(null)}
      />
    )}

    {titleLabTarget && (
      <TitleStyleLab
        currentSection={makeTitleLabSection(titleLabTarget, state)}
        initialStyle={normalizeTitleStyle(titleLabTarget === "title" ? state.titleStyle : state.endStyle)}
        onApplyCurrent={(style) => state.patch(titleLabTarget === "title" ? { titleStyle: normalizeTitleStyle(style) } : { endStyle: normalizeTitleStyle(style) })}
        onApplySameType={(style) => state.patch(titleLabTarget === "title" ? { titleStyle: normalizeTitleStyle(style) } : { endStyle: normalizeTitleStyle(style) })}
        onApplyAll={(style) => state.patch({ titleStyle: normalizeTitleStyle(style), endStyle: normalizeTitleStyle(style) })}
        onSaveDefault={(style) => state.patch(titleLabTarget === "title" ? { titleStyle: normalizeTitleStyle(style) } : { endStyle: normalizeTitleStyle(style) })}
        onClose={() => setTitleLabTarget(null)}
      />
    )}

    {selectedMaterial && (
      <PreviewModal material={selectedMaterial} onClose={() => setSelectedMaterial(null)} />
    )}
    </>
  );
}

function formatRecentProjectTime(timestamp: number): string {
  const date = new Date(timestamp);
  const now = Date.now();
  if (now - timestamp < 24 * 60 * 60 * 1000) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString();
}

function projectDirFromRecentProject(project: RecentProject): string | null {
  const base = project.outputFolder || project.inputFolder;
  return base ? `${base}\\.video_create_project` : null;
}

function loadRecentProjects(): RecentProject[] {
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

function saveRecentProjects(projects: RecentProject[]) {
  try {
    window.localStorage.setItem(RECENT_PROJECTS_KEY, JSON.stringify(projects.slice(0, 5)));
  } catch {
    // Local storage can be unavailable in browser previews; the desktop app will still work.
  }
}

function friendlyDiagnosticsMessage(diagnostics: StartupDiagnostics): string {
  const failed = diagnostics.checks.filter((check) => !check.ok);
  if (failed.length === 0) return diagnostics.summary;
  const details = failed
    .map((check) => `${check.label}${check.code ? ` [${check.code}]` : ""}: ${check.message}`)
    .join("\n");
  return `${diagnostics.summary}\n${details}`;
}

function chooseRecoveredTimeline(
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

function friendlyErrorMessage(error: unknown): string {
  const resolved = resolveAppError(error);
  const parts = [resolved.userMessage];
  if (resolved.actionSuggestion) parts.push(`建议操作：${resolved.actionSuggestion}`);
  if (resolved.technicalMessage && resolved.technicalMessage !== resolved.userMessage) {
    parts.push(resolved.technicalMessage);
  }
  return parts.filter(Boolean).join("\n");
}

function formatTelemetryRate(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function describeTopTelemetryEntry(entries: TelemetrySummary["topErrorCodes"]): string {
  const top = entries[0];
  if (!top) return "No events yet";
  return `${top.key} (${top.count})`;
}

function TelemetrySummaryCard({
  enabled,
  summary,
  isClearing,
  onClear,
  remoteEndpoint,
  remoteUploadEnabled,
  isSavingSettings,
  isFlushingRemote,
  onRemoteEndpointChange,
  onRemoteUploadEnabledChange,
  onSaveRemoteSettings,
  onFlushRemoteQueue,
}: {
  enabled: boolean;
  summary: TelemetrySummary | null;
  isClearing: boolean;
  onClear: () => void;
  remoteEndpoint: string;
  remoteUploadEnabled: boolean;
  isSavingSettings: boolean;
  isFlushingRemote: boolean;
  onRemoteEndpointChange: (value: string) => void;
  onRemoteUploadEnabledChange: (value: boolean) => void;
  onSaveRemoteSettings: () => void;
  onFlushRemoteQueue: () => void;
}) {
  const recentEvents = summary?.recentEvents || [];
  const recentEvent = recentEvents.length > 0 ? recentEvents[recentEvents.length - 1] : null;

  return (
    <section className="startup-health-card">
      <div className="startup-health-head">
        <div>
          <span className="startup-health-kicker">OPTIONAL TELEMETRY</span>
          <strong>{enabled ? "匿名稳定性指标已启用" : "匿名稳定性指标未启用"}</strong>
        </div>
        <div className="startup-health-badge-group">
          <span className={`startup-health-badge ${enabled ? "ok" : "pending"}`}>
            {enabled ? (
              <>
                <CheckCircle2 size={14} /> Enabled
              </>
            ) : (
              <>
                <Clock size={14} /> Opt-in
              </>
            )}
          </span>
          <button className="secondary-action telemetry-reset-btn" disabled={isClearing} type="button" onClick={onClear}>
            {isClearing ? <Loader2 className="spin" size={16} /> : <RotateCcw size={16} />}
            {isClearing ? "清空中" : "清空本地历史"}
          </button>
        </div>
      </div>

      <div className="startup-health-grid">
        <div className="startup-health-item">
          <div className="startup-health-item-head">
            <Gauge size={16} />
            <strong>Crash-free sessions</strong>
          </div>
          <span>{summary ? formatTelemetryRate(summary.crashFreeSessionRate) : "Waiting for local metrics"}</span>
          <small>
            {summary
              ? `${summary.sessionsCompletedCleanly}/${summary.sessionsStarted} sessions closed cleanly`
              : "Enable telemetry to start measuring app stability."}
          </small>
        </div>

        <div className="startup-health-item">
          <div className="startup-health-item-head">
            <PlayCircle size={16} />
            <strong>First export success</strong>
          </div>
          <span>{summary ? formatTelemetryRate(summary.firstExportSuccessRate) : "Waiting for export attempts"}</span>
          <small>
            {summary
              ? `${summary.firstExportSuccesses}/${summary.firstExportSessions} first exports succeeded`
              : "Tracked once per session after the first render result."}
          </small>
        </div>

        <div className="startup-health-item">
          <div className="startup-health-item-head">
            <TriangleAlert size={16} />
            <strong>Common error code</strong>
          </div>
          <span>{summary ? describeTopTelemetryEntry(summary.topErrorCodes) : "No failures recorded yet"}</span>
          <small>{summary ? `${summary.renderFailures} render failures recorded locally` : "Recent failures will surface here."}</small>
        </div>

        <div className="startup-health-item">
          <div className="startup-health-item-head">
            <History size={16} />
            <strong>Support routing</strong>
          </div>
          <span>{summary ? describeTopTelemetryEntry(summary.topSupportQueues) : "No support events yet"}</span>
          <small>
            {summary
              ? `Recovery resumable: ${summary.recoveryResumableEvents}, retryable: ${summary.recoveryRetryableEvents}`
              : "Queue, severity, tag, and recovery labels stay anonymous."}
          </small>
        </div>
      </div>

      {summary ? (
        <div className="telemetry-summary-footer">
          <span>Render attempts: {summary.renderAttempts}</span>
          <span>Last event: {recentEvent ? `${recentEvent.eventType}${recentEvent.errorCode ? ` [${recentEvent.errorCode}]` : ""}` : "none"}</span>
          <span>Last updated: {summary.lastUpdatedAt ? new Date(summary.lastUpdatedAt).toLocaleString() : "not yet"}</span>
        </div>
      ) : null}

      <div className="telemetry-remote-panel">
        <div className="telemetry-remote-head">
          <strong>Remote Crash Reporting</strong>
          <span>Consent: {summary?.consentAcceptedVersion === summary?.currentConsentVersion ? summary?.currentConsentVersion : "not accepted"}</span>
        </div>
        <label className="telemetry-remote-field">
          <span>Remote endpoint</span>
          <input
            placeholder="https://telemetry.example.com/collect"
            type="url"
            value={remoteEndpoint}
            onChange={(event) => onRemoteEndpointChange(event.target.value)}
          />
        </label>
        <div className="telemetry-remote-actions">
          <Toggle checked={remoteUploadEnabled} label="允许远程匿名上报" onChange={onRemoteUploadEnabledChange} />
          <button className="secondary-action telemetry-remote-btn" disabled={isSavingSettings} type="button" onClick={onSaveRemoteSettings}>
            {isSavingSettings ? <Loader2 className="spin" size={16} /> : <Settings2 size={16} />}
            {isSavingSettings ? "Saving" : "Save remote settings"}
          </button>
          <button className="secondary-action telemetry-remote-btn" disabled={isFlushingRemote || !summary?.pendingRemoteEvents} type="button" onClick={onFlushRemoteQueue}>
            {isFlushingRemote ? <Loader2 className="spin" size={16} /> : <RotateCcw size={16} />}
            {isFlushingRemote ? "Retrying" : `Retry queued uploads${summary?.pendingRemoteEvents ? ` (${summary.pendingRemoteEvents})` : ""}`}
          </button>
        </div>
        <div className="telemetry-summary-footer">
          <span>Endpoint: {summary?.remoteEndpointHost || "not configured"}</span>
          <span>Pending uploads: {summary?.pendingRemoteEvents || 0}</span>
          <span>Last remote upload: {summary?.lastRemoteUploadAt ? new Date(summary.lastRemoteUploadAt).toLocaleString() : "never"}</span>
          <span>Last remote status: {summary?.lastRemoteUploadError || "ok"}</span>
        </div>
      </div>

      <p className="telemetry-summary-note">
        仅记录匿名稳定性标签与聚合计数，不包含素材路径、标题文本或媒体内容；可以随时关闭或清空本地历史。
      </p>
    </section>
  );
}

function TelemetryConsentDialog({
  consentVersion,
  isSaving,
  onAccept,
  onDecline,
}: {
  consentVersion: string;
  isSaving: boolean;
  onAccept: () => void;
  onDecline: () => void;
}) {
  return (
    <div className="gallery-overlay">
      <div className="telemetry-consent-modal">
        <div className="telemetry-consent-head">
          <strong>Telemetry Consent</strong>
          <span>{consentVersion}</span>
        </div>
        <p>
          Anonymous telemetry helps track crash-free sessions, first export success, common failure codes, and render recovery outcomes.
        </p>
        <p>
          It does not include media content, titles, or raw project text. Remote upload is optional and can stay disabled even after consent.
        </p>
        <p>
          Privacy notice: <code>docs/TELEMETRY_PRIVACY_NOTICE_V2026_05.md</code>
        </p>
        <div className="telemetry-consent-actions">
          <button className="secondary-action" type="button" onClick={onDecline}>
            Not now
          </button>
          <button className="primary-action" disabled={isSaving} type="button" onClick={onAccept}>
            {isSaving ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
            {isSaving ? "Saving consent" : "Accept privacy notice"}
          </button>
        </div>
      </div>
    </div>
  );
}

function StartupHealthCard({
  diagnostics,
  loading,
}: {
  diagnostics: StartupDiagnostics | null;
  loading: boolean;
}) {
  return (
    <DiagnosticsCard
      title="桌面运行环境"
      kicker="STARTUP SELF-CHECK"
      diagnostics={diagnostics}
      loading={loading}
      loadingText="正在检查 worker、资源文件和可写目录..."
    />
  );
}

function DiagnosticsCard({
  title,
  kicker,
  diagnostics,
  loading,
  loadingText,
}: {
  title: string;
  kicker: string;
  diagnostics: StartupDiagnostics | null;
  loading: boolean;
  loadingText: string;
}) {
  if (!loading && !diagnostics) return null;

  return (
    <section className={`startup-health-card${diagnostics && !diagnostics.ok ? " failed" : ""}`}>
      <div className="startup-health-head">
        <div>
          <span className="startup-health-kicker">{kicker}</span>
          <strong>{loading ? title : diagnostics?.summary || `${title}不可用。`}</strong>
        </div>
        <div className="startup-health-badge-group">
          {diagnostics?.code ? <span className="error-code-badge">{diagnostics.code}</span> : null}
          <span className={`startup-health-badge ${loading ? "pending" : diagnostics?.ok ? "ok" : "failed"}`}>
            {loading ? (
              <>
                <Loader2 className="spin" size={14} /> 检查中
              </>
            ) : diagnostics?.ok ? (
              <>
                <CheckCircle2 size={14} /> 通过
              </>
            ) : (
              <>
                <TriangleAlert size={14} /> 需处理
              </>
            )}
          </span>
        </div>
      </div>

      <div className="startup-health-grid">
        {loading ? (
          <div className="startup-health-item pending">
            <strong>{title}</strong>
            <span>{loadingText}</span>
          </div>
        ) : (
          diagnostics?.checks.map((check) => (
            <div className={`startup-health-item ${check.ok ? "ok" : "failed"}`} key={check.id}>
              <div className="startup-health-item-head">
                {check.ok ? <CheckCircle2 size={16} /> : <TriangleAlert size={16} />}
                <strong>{check.label}</strong>
              </div>
              {check.code ? <span className="error-code-inline">{check.code}</span> : null}
              <span>{check.message}</span>
              {check.detail ? <small>{check.detail}</small> : null}
            </div>
          ))
        )}
      </div>
    </section>
  );
}

function SessionRecoveryCard({
  snapshot,
  onRestore,
  onDismiss,
}: {
  snapshot: SessionSnapshotPayload;
  onRestore: (snapshot: SessionSnapshotPayload) => void;
  onDismiss: () => void;
}) {
  const restored = parseSessionRecoveryData(snapshot.data);
  if (!restored) return null;

  const draft = restored.studio;
  const summary = draft.title || (draft.inputFolder ? shortPathName(draft.inputFolder) : "未命名项目");

  return (
    <section className="session-recovery-card">
      <div className="session-recovery-head">
        <div>
          <span className="startup-health-kicker">SESSION RECOVERY</span>
          <strong>检测到上次未完成会话</strong>
        </div>
        <span className="session-recovery-badge">{formatSnapshotSavedAt(snapshot.savedAt)}</span>
      </div>
      <div className="session-recovery-body">
        <div className="session-recovery-summary">
          <strong>{summary}</strong>
          <span>{draft.inputFolder ? shortPathName(draft.inputFolder) : "未选择素材目录"} → {draft.outputFolder ? shortPathName(draft.outputFolder) : "未选择输出目录"}</span>
          <small>恢复后会带回当前阶段、渲染计划、最近日志和预检上下文，但不会自动继续中断中的渲染任务。</small>
        </div>
        <div className="session-recovery-actions">
          <button className="primary-action" type="button" onClick={() => onRestore(snapshot)}>
            <RotateCcw size={16} /> 恢复草稿
          </button>
          <button className="secondary-action" type="button" onClick={onDismiss}>
            <X size={16} /> 丢弃草稿
          </button>
        </div>
      </div>
    </section>
  );
}

function ProjectRecoveryCard({
  project,
  snapshot,
  onRestore,
  onDismiss,
}: {
  project: RecentProject;
  snapshot: ProjectStatePayload;
  onRestore: () => void;
  onDismiss: () => void;
}) {
  const restored = parseSessionRecoveryData(snapshot.data);
  if (!restored) return null;

  const draft = restored.studio;
  const summary = draft.title || project.title || shortPathName(project.inputFolder);

  return (
    <section className="session-recovery-card">
      <div className="session-recovery-head">
        <div>
          <span className="startup-health-kicker">PROJECT AUTOSAVE</span>
          <strong>检测到上次未完成项目</strong>
        </div>
        <span className="session-recovery-badge">{formatSnapshotSavedAt(snapshot.savedAt)}</span>
      </div>
      <div className="session-recovery-body">
        <div className="session-recovery-summary">
          <strong>{summary}</strong>
          <span>{shortPathName(project.inputFolder)}{" -> "}{project.outputFolder ? shortPathName(project.outputFolder) : "未选择输出目录"}</span>
          <small>恢复后会先重新加载项目文档，再尽量带回自动保存的阶段、日志、预检和最近渲染上下文。</small>
        </div>
        <div className="session-recovery-actions">
          <button className="primary-action" type="button" onClick={onRestore}>
            <RotateCcw size={16} /> 恢复最近项目
          </button>
          <button className="secondary-action" type="button" onClick={onDismiss}>
            <X size={16} /> 稍后再说
          </button>
        </div>
      </div>
    </section>
  );
}

function ProjectMigrationCard({
  source,
  notes,
}: {
  source: string;
  notes: string[];
}) {
  return (
    <section className="project-migration-card">
      <div className="project-migration-head">
        <div>
          <span className="startup-health-kicker">PROJECT MIGRATION</span>
          <strong>已自动迁移旧版项目文档</strong>
        </div>
        <span className="project-migration-badge">{source}</span>
      </div>
      <div className="project-migration-body">
        <p>当前项目在恢复时检测到旧版 schema，系统已自动升级到当前版本。以下是本次迁移内容：</p>
        <ul>
          {notes.map((note, index) => (
            <li key={`${note}-${index}`}>{note}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function RecentProjectsCard({
  projects,
  onRestore,
}: {
  projects: RecentProject[];
  onRestore: (project: RecentProject) => void;
}) {
  if (projects.length === 0) return null;

  return (
    <section className="recent-projects-card">
      <div className="recent-projects-head">
        <div>
          <span className="startup-health-kicker">RECENT PROJECTS</span>
          <strong>最近项目</strong>
        </div>
        <History size={18} />
      </div>
      <div className="recent-projects-list">
        {projects.map((project) => (
          <button key={project.id} type="button" onClick={() => onRestore(project)}>
            <span>
              <strong>{project.title || shortPathName(project.inputFolder)}</strong>
              <small>{shortPathName(project.inputFolder)} → {project.outputFolder ? shortPathName(project.outputFolder) : "未选择输出目录"}</small>
            </span>
            <em>{formatRecentProjectTime(project.updatedAt)}</em>
          </button>
        ))}
      </div>
    </section>
  );
}

function ResultCard({
  result,
  onResumeRetry,
}: {
  result: GenerateVideoResult;
  onResumeRetry?: () => void;
}) {
  const resolution = resolveResultError(result);
  const recovery = result.recovery || null;
  const actionSuggestion = result.actionSuggestion || resolution.actionSuggestion || null;
  const showRecovery =
    Boolean(recovery) &&
    (
      recovery!.resumable ||
      recovery!.resumedFromManifest ||
      recovery!.reusedChunkCount > 0 ||
      recovery!.completedChunkCount > 0 ||
      recovery!.failedChunkCount > 0
    );
  return (
    <div className={`result-card ${result.ok ? "success" : "warning"}`}>
      <div className="result-card-header">
        {result.ok ? <CheckCircle2 size={20} /> : <TriangleAlert size={20} />}
        <strong>{result.isDryRun ? (result.ok ? "预检完成" : "预检失败") : (result.ok ? "生成完成" : "生成失败")}</strong>
      </div>
      {result.code ? <div className="result-code-row"><span className="error-code-badge">{result.code}</span></div> : null}
      <p className="result-card-message">
        {result.message}
        {result.isDryRun && result.ok && (
          <span style={{ display: 'block', marginTop: '4px', opacity: 0.8, fontSize: '0.9em' }}>
            提示：素材状态良好，您可以点击右上角的“生成视频”开始正式合成。
          </span>
        )}
      </p>
      {false && !result.ok && actionSuggestion ? (
        <div className="result-action-note">建议操作：{resolution.actionSuggestion}</div>
      ) : null}
      {!result.ok && actionSuggestion ? (
        <div className="result-action-note">建议操作：{actionSuggestion}</div>
      ) : null}
      {showRecovery && recovery ? (
        <div className="result-recovery-card">
          <div className="result-recovery-header">
            <RotateCcw size={16} />
            <strong>{result.ok ? "Stable Render 复用摘要" : "Stable Render 恢复点"}</strong>
          </div>
          <p className="result-recovery-message">
            {result.ok
              ? recovery.reusedChunkCount > 0
                ? `本次渲染复用了 ${recovery.reusedChunkCount} 个已完成分段，不需要从头开始。`
                : recovery.resumedFromManifest
                  ? "本次渲染接续了上一次 stable render 的进度。"
                  : "本次渲染已记录 stable render 恢复信息。"
              : recovery.resumable && recovery.retryable
                ? "当前失败可直接恢复重试，系统会尽量复用已经完成的 stable chunks。"
                : "当前失败已生成 stable render 恢复摘要，便于定位失败段和支持排障。"}
          </p>
          <div className="result-recovery-metrics">
            <span>已完成 {recovery.completedChunkCount}</span>
            <span>已复用 {recovery.reusedChunkCount}</span>
            <span>失败 {recovery.failedChunkCount}</span>
            {recovery.chunkCount ? <span>总分段 {recovery.chunkCount}</span> : null}
            {typeof recovery.segmentFastPathRate === "number" ? <span>段快路径 {Math.round(recovery.segmentFastPathRate * 100)}%</span> : null}
            {typeof recovery.chunkFastPathRate === "number" ? <span>块快路径 {Math.round(recovery.chunkFastPathRate * 100)}%</span> : null}
          </div>
          {(recovery.selectedBackend || recovery.actualBackend || recovery.fallbackUsed || recovery.segmentRouteDifferenceCount || recovery.failedStage || recovery.failedChunk || recovery.failureCode) ? (
            <div className="result-recovery-meta">
              {recovery.selectedBackend ? (
                <span>
                  后端：{recovery.actualBackend && recovery.actualBackend !== recovery.selectedBackend
                    ? `${recovery.selectedBackend} -> ${recovery.actualBackend}`
                    : recovery.selectedBackend}
                </span>
              ) : null}
              {recovery.fallbackUsed ? <span>回退：{recovery.fallbackUsed}</span> : null}
              {recovery.fallbackReason ? <span>回退原因：{recovery.fallbackReason}</span> : null}
              {recovery.segmentRouteDifferenceCount ? <span>运行期路由变化：{recovery.segmentRouteDifferenceCount}</span> : null}
              {recovery.failedStage ? <span>失败阶段：{recovery.failedStage}</span> : null}
              {recovery.failedChunk ? <span>失败分段：{recovery.failedChunk}</span> : null}
              {recovery.failureCode ? <span>失败标识：{recovery.failureCode}</span> : null}
            </div>
          ) : null}
          {!result.ok && onResumeRetry && recovery.resumable && recovery.retryable ? (
            <div className="result-card-actions">
              <button className="result-open-btn result-resume-btn" onClick={onResumeRetry}>
                <RotateCcw size={15} />
                恢复并重试
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      <BuildReportV2Panel recovery={recovery} />
      {result.ok && result.outputPath && (
        <div className="result-card-actions">
          <button className="result-open-btn" onClick={() => openInExplorer(result.outputDir || result.outputPath!)}>
            <ExternalLink size={15} />
            打开输出目录
          </button>
        </div>
      )}
    </div>
  );
}

function asReportObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function reportString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function reportNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function reportBool(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function reportPercent(value: unknown): string | null {
  const number = reportNumber(value);
  return number === null ? null : `${Math.round(number * 100)}%`;
}

function buildReportSuggestions(value: unknown): Array<{ id?: string; priority?: string; message: string }> {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asReportObject(item))
    .map((item) => ({
      id: reportString(item.id) || undefined,
      priority: reportString(item.priority) || undefined,
      message: reportString(item.message) || "",
    }))
    .filter((item) => item.message)
    .slice(0, 4);
}

function BuildReportV2Panel({ recovery }: { recovery: RenderRecoverySummary | null }) {
  if (!recovery) return null;
  const timeline = asReportObject(recovery.timelineSummary);
  const route = asReportObject(recovery.routeSummary);
  const fallback = asReportObject(recovery.fallbackSummary);
  const cache = asReportObject(recovery.cacheSummary);
  const recompute = asReportObject(recovery.recomputeSummary);
  const quality = asReportObject(recovery.qualitySummary);
  const performance = asReportObject(recovery.performanceSummary);
  const recoveryV2 = asReportObject(recovery.recoverySummary);
  const cachePolicy = asReportObject(cache.policy);
  const suggestions = buildReportSuggestions(recovery.reportSuggestions);
  const hasV2 =
    recovery.buildReportVersion === "v2" ||
    Object.keys(timeline).length > 0 ||
    Object.keys(route).length > 0 ||
    Object.keys(cache).length > 0 ||
    Object.keys(quality).length > 0;
  if (!hasV2) return null;

  const source = reportString(timeline.source) || "render_plan";
  const renderIntent = reportString(quality.render_intent) || reportString(cachePolicy.render_intent) || recovery.renderIntent || "final";
  const actualBackend = reportString(route.actual_backend) || recovery.actualBackend || recovery.selectedBackend || "auto";
  const fallbackApplied = reportBool(fallback.applied) ?? Boolean(recovery.fallbackApplied);
  const usesOriginalSource = reportBool(quality.uses_original_source);
  const allowProxy = reportBool(quality.allow_proxy);
  const elapsedSeconds = reportNumber(performance.elapsed_seconds);
  const outputSize = reportNumber(performance.output_size_bytes);

  const facts = [
    ["Timeline", source === "timeline" ? "compiled" : source],
    ["Intent", renderIntent],
    ["Backend", actualBackend],
    ["Fallback", fallbackApplied ? (reportString(fallback.used) || recovery.fallbackUsed || "applied") : "none"],
    ["Cache", reportString(cachePolicy.cache_namespace) || "default"],
    ["Recompute", reportBool(recompute.timeline_dirty) ? "dirty" : "clean"],
    ["Source", usesOriginalSource === null ? "unknown" : usesOriginalSource ? "original" : "proxy/derived"],
    ["Proxy", allowProxy === null ? "unknown" : allowProxy ? "allowed" : "blocked"],
  ];

  return (
    <div className="build-report-v2-panel">
      <div className="build-report-v2-header">
        <ListChecks size={16} />
        <strong>Build Report V2</strong>
        <span>{recovery.buildReportVersion || "compatible"}</span>
      </div>
      <div className="build-report-v2-grid">
        {facts.map(([label, value]) => (
          <div className="build-report-v2-item" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="build-report-v2-meta">
        {reportPercent(route.segment_fast_path_rate) ? <span>Segment fast path {reportPercent(route.segment_fast_path_rate)}</span> : null}
        {reportPercent(route.chunk_fast_path_rate) ? <span>Chunk fast path {reportPercent(route.chunk_fast_path_rate)}</span> : null}
        {elapsedSeconds !== null ? <span>Elapsed {elapsedSeconds.toFixed(2)}s</span> : null}
        {outputSize !== null ? <span>Output {(outputSize / 1024 / 1024).toFixed(1)} MB</span> : null}
        {reportString(recoveryV2.failure_code) ? <span>Failure {reportString(recoveryV2.failure_code)}</span> : null}
      </div>
      {suggestions.length > 0 ? (
        <div className="build-report-v2-suggestions">
          {suggestions.map((item) => (
            <span key={item.id || item.message}>
              {item.priority ? `${item.priority}: ` : ""}
              {item.message}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function RenderAudioTimelineCard({
  plan,
  activeSegmentIndex,
  isRendering,
  selectedSectionId,
  onSelectSection,
}: {
  plan: V5RenderPlan;
  activeSegmentIndex: number | null;
  isRendering: boolean;
  selectedSectionId: string | null;
  onSelectSection: (sectionId: string | null) => void;
}) {
  const blueprint = plan.render_settings?.audio_blueprint || null;
  const cues = blueprintCueList(blueprint);
  if (!blueprint || cues.length === 0) return null;

  const activeSectionId =
    activeSegmentIndex !== null && activeSegmentIndex >= 0 ? plan.segments[activeSegmentIndex]?.section_id || null : null;
  const adopted = blueprint.adopted_audio_settings || plan.render_settings?.audio || {};
  const playlistMode = normalizeBlueprintPlaylistMode(
    typeof adopted.music_playlist_mode === "string" ? adopted.music_playlist_mode : null,
    Boolean(adopted.music_chapter_restart),
  );
  const totalDuration = Math.max(0.1, Number(plan.total_duration || 0));
  const originSummary = blueprint.origin_summary || "本次编译后的章节配乐执行结果。";

  return (
    <section className="render-audio-timeline-card">
      <div className="render-audio-timeline-head">
        <div>
          <strong>本次实际采用的章节配乐时间线</strong>
          <span>{originSummary}</span>
        </div>
        <span className="render-audio-timeline-badge">{musicPlaylistModeLabel(playlistMode)}</span>
      </div>

      <div className="render-audio-timeline-summary">
        {blueprint.music_profile ? <span>{blueprint.music_profile}</span> : null}
        {adopted.music_fit_strategy ? <span>{adopted.music_fit_strategy}</span> : null}
        {typeof adopted.bgm_volume === "number" ? <span>BGM {Math.round(adopted.bgm_volume * 100)}%</span> : null}
        {typeof adopted.source_audio_volume === "number" ? <span>原声 {Math.round(adopted.source_audio_volume * 100)}%</span> : null}
        {adopted.auto_ducking ? <span>自动 Ducking</span> : null}
        {adopted.music_chapter_restart ? <span>章节切点重启</span> : null}
      </div>

      <div className="render-audio-timeline-list">
        {cues.map((cue, index) => {
          const startTime = Math.max(0, Number(cue.start_time || 0));
          const duration = Math.max(0, Number(cue.duration || 0));
          const widthPercent = Math.max(3, Math.min(100, (duration / totalDuration) * 100));
          const offsetPercent = Math.max(0, Math.min(100, (startTime / totalDuration) * 100));
          const isActive = Boolean(activeSectionId) && activeSectionId === cue.section_id;
          const isSelected = Boolean(selectedSectionId) && selectedSectionId === cue.section_id;

          return (
            <div
              className={`render-audio-cue${isActive ? " active" : ""}${isSelected ? " selected" : ""}`}
              key={`${cue.section_id || cue.title || index}-${index}`}
              role={cue.section_id ? "button" : undefined}
              tabIndex={cue.section_id ? 0 : undefined}
              onClick={() => {
                if (!cue.section_id) return;
                onSelectSection(selectedSectionId === cue.section_id ? null : cue.section_id);
              }}
              onKeyDown={(event) => {
                if (!cue.section_id) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectSection(selectedSectionId === cue.section_id ? null : cue.section_id);
                }
              }}
            >
              <div className="render-audio-cue-main">
                <div className="render-audio-cue-title-row">
                  <strong>{cue.title || cue.section_id || `章节 ${index + 1}`}</strong>
                  <span>
                    {formatDurationLabel(startTime)} - {formatDurationLabel(Number(cue.end_time || startTime))}
                  </span>
                </div>
                <div className="render-audio-cue-rail">
                  <span
                    className="render-audio-cue-bar"
                    style={{ left: `${offsetPercent}%`, width: `${Math.max(widthPercent, 4)}%` }}
                  />
                </div>
              </div>
              <div className="render-audio-cue-meta">
                <span>{cue.phase || "sustain"}</span>
                <span>{cue.energy || "medium"}</span>
                <span>{cue.ducking_hint || "medium ducking"}</span>
                {isSelected ? <span>已联动片段</span> : null}
              </div>
              <p>{cue.reason || "保持音乐连续性并跟随章节节奏变化。"}</p>
              {isRendering && isActive ? <div className="render-audio-cue-live">当前渲染中</div> : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Toast({ title = "缺少生成参数", message, onClose }: { title?: string; message: string; onClose: () => void }) {
  return (
    <div className="toast warning" role="status">
      <div>
        <strong>{title}</strong>
        <span>{message}</span>
      </div>
      <button aria-label="关闭提示" type="button" onClick={onClose}>
        <X size={16} />
      </button>
    </div>
  );
}

function getSelectedBackgroundPath(target: BackgroundPickerTarget, state: StudioState): string | null {
  if (target.kind === "title") return state.titleBackgroundPath;
  if (target.kind === "end") return state.endBackgroundPath;
  const section = findSectionById(state.v5Blueprint?.sections, target.sectionId);
  return section?.background?.custom_path || null;
}

function makeTitleLabSection(target: "title" | "end", state: StudioState): V5StorySection {
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

function buildAudioSettings(state: StudioState, library: V5MediaLibrary | null, plan: V5RenderPlan | null): V5AudioSettings {
  const resolved = resolveMusicSelection(state, library, plan);
  return {
    music_mode: state.musicMode,
    music_path: resolved.primaryPath,
    music_playlist_mode: state.musicPlaylistMode,
    music_playlist_paths: resolved.paths,
    music_chapter_restart: state.musicPlaylistMode === "chapter_restart",
    music_fit_strategy: state.musicFitStrategy,
    estimated_video_duration: Number(plan?.total_duration || 0),
    music_source:
      state.musicMode === "manual" && resolved.paths.length > 0
        ? "manual"
        : state.musicMode === "auto" && resolved.paths.length > 0
          ? "library"
          : "none",
    bgm_volume: clampNumber(state.bgmVolume, 0, 1, 0.28),
    source_audio_volume: clampNumber(state.sourceAudioVolume, 0, 1, 1),
    keep_source_audio: Boolean(state.keepSourceAudio),
    auto_ducking: Boolean(state.autoDucking),
    fade_in_seconds: clampNumber(state.musicFadeInSeconds, 0, 10, 1.5),
    fade_out_seconds: clampNumber(state.musicFadeOutSeconds, 0, 20, 3),
    normalize_audio: false,
  };
}

type AudioBlueprintApplyScope = "source" | "mix" | "timing" | "all";

function resolveAudioBlueprint(state: StudioState): V5AudioBlueprint | null {
  return state.v5RenderPlan?.render_settings?.audio_blueprint || state.v5Blueprint?.metadata?.audio_blueprint || null;
}

function resolveEditableAudioBlueprint(state: StudioState): V5AudioBlueprint | null {
  return state.v5Blueprint?.metadata?.audio_blueprint || resolveAudioBlueprint(state);
}

function normalizeStringList(values: string[] | null | undefined): string[] {
  return Array.isArray(values) ? values.map((item) => String(item || "").trim()).filter(Boolean) : [];
}

function normalizeBlueprintPlaylistMode(mode: string | null | undefined, chapterRestart?: boolean | null): MusicPlaylistMode {
  if (chapterRestart || mode === "chapter_restart") return "chapter_restart";
  if (mode === "auto_playlist" || mode === "manual_playlist" || mode === "single") return mode;
  return "single";
}

function musicPlaylistModeLabel(mode: MusicPlaylistMode): string {
  return {
    single: "单曲",
    auto_playlist: "自动多曲",
    manual_playlist: "手动歌单",
    chapter_restart: "章节重启",
  }[mode];
}

function blueprintCueList(blueprint: V5AudioBlueprint | null) {
  const raw = blueprint?.timeline_cues?.length ? blueprint.timeline_cues : blueprint?.section_cues;
  return Array.isArray(raw) ? raw.filter((item) => item && (item.section_id || item.title)) : [];
}

function normalizeEditableCueList(blueprint: V5AudioBlueprint | null): V5AudioBlueprintCue[] {
  const raw = blueprint?.section_cues?.length ? blueprint.section_cues : blueprintCueList(blueprint);
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item) => item && item.section_id)
    .map((item, index) => ({
      ...item,
      order: typeof item.order === "number" ? item.order : index,
      phase: item.phase || "sustain",
      energy: item.energy || "medium",
      ducking_hint: item.ducking_hint || "medium",
      reason: item.reason || "",
      title: item.title || item.section_id || `section_${index + 1}`,
    }))
    .sort((a, b) => {
      const orderA = typeof a.order === "number" ? a.order : Number.MAX_SAFE_INTEGER;
      const orderB = typeof b.order === "number" ? b.order : Number.MAX_SAFE_INTEGER;
      if (orderA !== orderB) return orderA - orderB;
      return String(a.section_id || "").localeCompare(String(b.section_id || ""));
    });
}

function syncTimelineCuesWithSectionEdits(
  timelineCues: V5AudioBlueprintCue[] | null | undefined,
  sectionCues: V5AudioBlueprintCue[],
): V5AudioBlueprintCue[] | null | undefined {
  if (!Array.isArray(timelineCues)) return timelineCues;
  const overrideMap = new Map(sectionCues.map((item) => [String(item.section_id || ""), item]));
  return timelineCues.map((item) => {
    const override = overrideMap.get(String(item.section_id || ""));
    if (!override) return item;
    return {
      ...item,
      title: override.title || item.title,
      phase: override.phase || item.phase,
      energy: override.energy || item.energy,
      ducking_hint: override.ducking_hint || item.ducking_hint,
      reason: override.reason || item.reason,
    };
  });
}

function patchAudioBlueprintCue(
  state: StudioState,
  sectionId: string,
  patch: Partial<Pick<V5AudioBlueprintCue, "phase" | "energy" | "ducking_hint" | "reason">>,
): void {
  if (!state.v5Blueprint) return;
  const editableBlueprint = resolveEditableAudioBlueprint(state);
  if (!editableBlueprint) return;

  const nextSectionCues = normalizeEditableCueList(editableBlueprint).map((item) =>
    item.section_id === sectionId
      ? {
          ...item,
          ...patch,
        }
      : item,
  );

  const nextAudioBlueprint: V5AudioBlueprint = {
    ...editableBlueprint,
    section_cues: nextSectionCues,
    timeline_cues: syncTimelineCuesWithSectionEdits(editableBlueprint.timeline_cues, nextSectionCues),
  };

  const nextBlueprint = withBlueprintMetadata(state.v5Blueprint, {
    audio_blueprint: nextAudioBlueprint,
  });

  const nextPatch: Partial<StudioState> = {
    v5Blueprint: nextBlueprint,
    v5Timeline: null,
  };

  if (state.v5RenderPlan?.render_settings?.audio_blueprint) {
    nextPatch.v5RenderPlan = {
      ...state.v5RenderPlan,
      render_settings: {
        ...(state.v5RenderPlan.render_settings || {}),
        audio_blueprint: {
          ...state.v5RenderPlan.render_settings.audio_blueprint,
          section_cues: nextSectionCues,
          timeline_cues: syncTimelineCuesWithSectionEdits(
            state.v5RenderPlan.render_settings.audio_blueprint.timeline_cues,
            nextSectionCues,
          ),
        },
      },
    };
  }

  state.patch(nextPatch);
}

function restoreCompiledAudioBlueprintCues(state: StudioState): void {
  if (!state.v5Blueprint || !state.v5RenderPlan?.render_settings?.audio_blueprint) return;
  const compiledBlueprint = state.v5RenderPlan.render_settings.audio_blueprint;
  const nextAudioBlueprint: V5AudioBlueprint = {
    ...(resolveEditableAudioBlueprint(state) || compiledBlueprint),
    section_cues: normalizeEditableCueList(compiledBlueprint),
    timeline_cues: compiledBlueprint.timeline_cues || null,
  };
  state.patch({
    v5Blueprint: withBlueprintMetadata(state.v5Blueprint, {
      audio_blueprint: nextAudioBlueprint,
    }),
    v5Timeline: null,
  });
}

function audioBlueprintCueEditsPending(state: StudioState): boolean {
  const editable = normalizeEditableCueList(resolveEditableAudioBlueprint(state));
  const compiled = normalizeEditableCueList(state.v5RenderPlan?.render_settings?.audio_blueprint || null);
  if (compiled.length === 0 || editable.length !== compiled.length) return false;
  return editable.some((item, index) => {
    const baseline = compiled[index];
    return (
      item.phase !== baseline.phase ||
      item.energy !== baseline.energy ||
      item.ducking_hint !== baseline.ducking_hint ||
      String(item.reason || "") !== String(baseline.reason || "")
    );
  });
}

function blueprintCandidatePaths(blueprint: V5AudioBlueprint | null): string[] {
  return normalizeStringList(
    (blueprint?.candidate_assets || []).map((item) => item?.absolute_path || ""),
  );
}

function buildAudioBlueprintPatch(blueprint: V5AudioBlueprint | null, scope: AudioBlueprintApplyScope): Partial<StudioState> {
  const recommended = blueprint?.recommended_audio_settings;
  if (!recommended) return {};

  const patch: Partial<StudioState> = {};
  if (scope === "source" || scope === "all") {
    const recommendedMode = recommended.music_mode === "off" ? "off" : "auto";
    const recommendedPlaylistMode = normalizeBlueprintPlaylistMode(
      recommended.music_playlist_mode,
      recommended.music_chapter_restart,
    );
    const recommendedPaths = normalizeStringList(recommended.music_playlist_paths);
    const playlistPaths = recommendedPaths.length > 0 ? recommendedPaths : blueprintCandidatePaths(blueprint);
    const primaryPath = String(recommended.music_path || "").trim() || playlistPaths[0] || null;
    const explicitPaths = playlistPaths.length > 0 ? playlistPaths : primaryPath ? [primaryPath] : [];

    patch.musicMode = recommendedMode;
    patch.musicPlaylistMode = recommendedMode === "off" ? "single" : recommendedPlaylistMode;
    patch.musicPath = recommendedMode === "off" ? null : primaryPath;
    patch.musicPlaylistPaths = recommendedMode === "off" ? [] : explicitPaths;
  }

  if (scope === "mix" || scope === "all") {
    if (typeof recommended.bgm_volume === "number") patch.bgmVolume = clampNumber(recommended.bgm_volume, 0, 1, 0.28);
    if (typeof recommended.source_audio_volume === "number") {
      patch.sourceAudioVolume = clampNumber(recommended.source_audio_volume, 0, 1, 1);
    }
    if (typeof recommended.keep_source_audio === "boolean") patch.keepSourceAudio = recommended.keep_source_audio;
    if (typeof recommended.auto_ducking === "boolean") patch.autoDucking = recommended.auto_ducking;
  }

  if (scope === "timing" || scope === "all") {
    if (
      recommended.music_fit_strategy === "auto" ||
      recommended.music_fit_strategy === "loop" ||
      recommended.music_fit_strategy === "trim" ||
      recommended.music_fit_strategy === "intro_loop_outro" ||
      recommended.music_fit_strategy === "once"
    ) {
      patch.musicFitStrategy = recommended.music_fit_strategy;
    }
    if (typeof recommended.fade_in_seconds === "number") {
      patch.musicFadeInSeconds = clampNumber(recommended.fade_in_seconds, 0, 10, 1.5);
    }
    if (typeof recommended.fade_out_seconds === "number") {
      patch.musicFadeOutSeconds = clampNumber(recommended.fade_out_seconds, 0, 20, 3);
    }
  }

  return patch;
}

function audioBlueprintScopeApplied(
  state: StudioState,
  blueprint: V5AudioBlueprint | null,
  scope: AudioBlueprintApplyScope,
): boolean {
  const recommended = blueprint?.recommended_audio_settings;
  if (!recommended) return false;

  const sourcePatch = buildAudioBlueprintPatch(blueprint, "source");
  const mixPatch = buildAudioBlueprintPatch(blueprint, "mix");
  const timingPatch = buildAudioBlueprintPatch(blueprint, "timing");

  if (scope === "source" || scope === "all") {
    const sameSource =
      state.musicMode === sourcePatch.musicMode &&
      state.musicPlaylistMode === sourcePatch.musicPlaylistMode &&
      state.musicPath === sourcePatch.musicPath &&
      sameStringArray(state.musicPlaylistPaths, sourcePatch.musicPlaylistPaths || []);
    if (scope === "source" && !sameSource) return false;
    if (scope === "all" && !sameSource) return false;
  }

  if (scope === "mix" || scope === "all") {
    const sameMix =
      numbersClose(state.bgmVolume, mixPatch.bgmVolume) &&
      numbersClose(state.sourceAudioVolume, mixPatch.sourceAudioVolume) &&
      state.keepSourceAudio === mixPatch.keepSourceAudio &&
      state.autoDucking === mixPatch.autoDucking;
    if (scope === "mix" && !sameMix) return false;
    if (scope === "all" && !sameMix) return false;
  }

  if (scope === "timing" || scope === "all") {
    const sameTiming =
      state.musicFitStrategy === timingPatch.musicFitStrategy &&
      numbersClose(state.musicFadeInSeconds, timingPatch.musicFadeInSeconds) &&
      numbersClose(state.musicFadeOutSeconds, timingPatch.musicFadeOutSeconds);
    if (scope === "timing" && !sameTiming) return false;
    if (scope === "all" && !sameTiming) return false;
  }

  return true;
}

function numbersClose(current: number | undefined, next: number | undefined): boolean {
  if (current === undefined || next === undefined) return false;
  return Math.abs(current - next) < 0.001;
}

function sameStringArray(current: string[] | undefined, next: string[] | undefined): boolean {
  const a = normalizeStringList(current || []);
  const b = normalizeStringList(next || []);
  if (a.length !== b.length) return false;
  return a.every((item, index) => item === b[index]);
}

function buildAudioBlueprintAdoptionState(state: StudioState, blueprint: V5AudioBlueprint | null) {
  const source = audioBlueprintScopeApplied(state, blueprint, "source");
  const mix = audioBlueprintScopeApplied(state, blueprint, "mix");
  const timing = audioBlueprintScopeApplied(state, blueprint, "timing");
  const appliedScopes = [
    source ? "source" : null,
    mix ? "mix" : null,
    timing ? "timing" : null,
  ].filter(Boolean) as string[];

  return {
    source,
    mix,
    timing,
    all: source && mix && timing,
    applied_scopes: appliedScopes,
    updated_at: new Date().toISOString(),
  };
}

function buildAudioBlueprintOriginSummary(state: StudioState, blueprint: V5AudioBlueprint | null): string | null {
  if (!blueprint?.recommended_audio_settings) return null;
  const adoption = buildAudioBlueprintAdoptionState(state, blueprint);
  const labels = [
    adoption.source ? "曲目" : null,
    adoption.mix ? "混音" : null,
    adoption.timing ? "节奏" : null,
  ].filter(Boolean);
  const appliedText = labels.length > 0 ? labels.join(" / ") : "尚未采纳";
  const source = blueprint.template_id || blueprint.music_profile || "audio_blueprint";
  return `来自 ${source} 的 AI 配乐建议，当前已采纳：${appliedText}`;
}

function decorateAudioBlueprintForPersist(
  state: StudioState,
  blueprint: V5AudioBlueprint | null,
  plan: V5RenderPlan | null,
): V5AudioBlueprint | null {
  if (!blueprint) return null;
  return {
    ...blueprint,
    ui_adoption_state: buildAudioBlueprintAdoptionState(state, blueprint),
    adopted_audio_settings: buildAudioSettings(state, state.v5Library, plan),
    origin_summary: buildAudioBlueprintOriginSummary(state, blueprint),
  };
}

function AudioBlueprintPanel({ state }: { state: StudioState }) {
  const blueprint = resolveEditableAudioBlueprint(state) || resolveAudioBlueprint(state);
  const recommended = blueprint?.recommended_audio_settings;
  const cues = blueprintCueList(blueprint);
  const editableCues = normalizeEditableCueList(blueprint);
  const candidateAssets = (blueprint?.candidate_assets || []).filter((item) => item?.absolute_path || item?.relative_path);
  if (!blueprint || !recommended) return null;

  const sourceApplied = audioBlueprintScopeApplied(state, blueprint, "source");
  const mixApplied = audioBlueprintScopeApplied(state, blueprint, "mix");
  const timingApplied = audioBlueprintScopeApplied(state, blueprint, "timing");
  const allApplied = sourceApplied && mixApplied && timingApplied;
  const cueEditsPending = state.v5Stage === "RENDER" && audioBlueprintCueEditsPending(state);
  const playlistMode = normalizeBlueprintPlaylistMode(recommended.music_playlist_mode, recommended.music_chapter_restart);
  const primaryLabel = shortPathName(
    String(recommended.music_path || blueprint.selected_candidate?.absolute_path || blueprint.selected_candidate?.relative_path || ""),
  );
  const keywords = normalizeStringList(blueprint.search_keywords).slice(0, 5);
  const phaseSummary = cues.slice(0, 4).map((item) => item.phase || item.title || "section").join(" / ");
  const originSummary = buildAudioBlueprintOriginSummary(state, blueprint) || blueprint.origin_summary;
  const applyScope = (scope: AudioBlueprintApplyScope) => {
    const patch = buildAudioBlueprintPatch(blueprint, scope);
    if (Object.keys(patch).length > 0) state.patch(patch);
  };

  return (
    <section className="audio-blueprint-panel">
      <div className="audio-blueprint-head">
        <div className="audio-blueprint-title">
          <Sparkles size={16} />
          <div>
            <strong>AI 配乐蓝图</strong>
            <span>
              {blueprint.timeline_cues?.length
                ? "已进入渲染计划，可看到章节时间线建议。"
                : "已根据模板和素材节奏生成配乐建议。"}
            </span>
          </div>
        </div>
        <div className="audio-blueprint-head-actions">
          <span className={`audio-blueprint-badge${allApplied ? " active" : ""}`}>
            {allApplied ? "已全部采纳" : blueprint.timeline_cues?.length ? "编译后建议" : "蓝图建议"}
          </span>
          <button
            className={`audio-blueprint-apply-btn${allApplied ? " active" : ""}`}
            disabled={allApplied}
            type="button"
            onClick={() => applyScope("all")}
          >
            {allApplied ? "当前已同步" : "一键采纳"}
          </button>
        </div>
      </div>

      <div className="audio-blueprint-chip-row">
        {blueprint.template_id ? <span>{blueprint.template_id}</span> : null}
        {blueprint.music_profile ? <span>{blueprint.music_profile}</span> : null}
        {playlistMode ? <span>{musicPlaylistModeLabel(playlistMode)}</span> : null}
        {blueprint.longform_project ? <span>长视频策略</span> : null}
        {allApplied ? <span>当前参数已与 AI 对齐</span> : null}
        {keywords.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>

      {originSummary ? <p className="audio-blueprint-origin">{originSummary}</p> : null}

      {state.v5Stage === "RENDER" ? (
        <p className={`audio-blueprint-origin${cueEditsPending ? " pending" : ""}`}>
          {cueEditsPending
            ? "章节微调已写入蓝图预览，重新点击“确认并进入渲染”后正式应用到新的 render plan。"
            : "可以先微调章节配乐，再重新编译 render plan 查看正式结果。"}
        </p>
      ) : null}

      <div className="audio-blueprint-grid">
        <div className="audio-blueprint-card">
          <div className="audio-blueprint-card-head">
            <strong>曲目与播放方式</strong>
            <span className={sourceApplied ? "applied" : ""}>{sourceApplied ? "已采纳" : "建议可采纳"}</span>
          </div>
          <p>
            {recommended.music_mode === "off"
              ? "当前建议关闭 BGM，保留原声表达。"
              : `${musicPlaylistModeLabel(playlistMode)} · ${primaryLabel || "未命名曲目"}`}
          </p>
          <div className="audio-blueprint-stats">
            <span>候选 {candidateAssets.length || normalizeStringList(recommended.music_playlist_paths).length || 1} 首</span>
            <span>{cues.length > 0 ? `${cues.length} 个章节提示` : "以素材匹配结果为主"}</span>
          </div>
          <button disabled={sourceApplied} type="button" onClick={() => applyScope("source")}>
            {sourceApplied ? "已采用曲目建议" : "采纳曲目建议"}
          </button>
        </div>

        <div className="audio-blueprint-card">
          <div className="audio-blueprint-card-head">
            <strong>混音层级</strong>
            <span className={mixApplied ? "applied" : ""}>{mixApplied ? "已采纳" : "建议可采纳"}</span>
          </div>
          <p>
            BGM {Math.round(Number(recommended.bgm_volume || 0) * 100)}% · 原声{" "}
            {Math.round(Number(recommended.source_audio_volume || 0) * 100)}%
          </p>
          <div className="audio-blueprint-stats">
            <span>{recommended.keep_source_audio ? "保留原声" : "弱化原声"}</span>
            <span>{recommended.auto_ducking ? "启用自动压低 BGM" : "关闭自动压低"}</span>
          </div>
          <button disabled={mixApplied} type="button" onClick={() => applyScope("mix")}>
            {mixApplied ? "已采用混音建议" : "采纳混音建议"}
          </button>
        </div>

        <div className="audio-blueprint-card">
          <div className="audio-blueprint-card-head">
            <strong>节奏与时长</strong>
            <span className={timingApplied ? "applied" : ""}>{timingApplied ? "已采纳" : "建议可采纳"}</span>
          </div>
          <p>
            {recommended.music_fit_strategy || "auto"} · 淡入 {Number(recommended.fade_in_seconds || 0).toFixed(1)}s · 淡出{" "}
            {Number(recommended.fade_out_seconds || 0).toFixed(1)}s
          </p>
          <div className="audio-blueprint-stats">
            <span>{blueprint.energy_curve_style || "balanced_story"}</span>
            <span>{phaseSummary || "保持段落起伏与收束感"}</span>
          </div>
          <button disabled={timingApplied} type="button" onClick={() => applyScope("timing")}>
            {timingApplied ? "已采用节奏建议" : "采纳节奏建议"}
          </button>
        </div>
      </div>

      {candidateAssets.length > 0 && (
        <div className="audio-blueprint-shelf">
          <strong>候选曲目</strong>
          <div className="audio-blueprint-candidate-list">
            {candidateAssets.slice(0, 4).map((item, index) => {
              const isSelected =
                item.absolute_path &&
                item.absolute_path === (blueprint.selected_candidate?.absolute_path || recommended.music_path || null);
              return (
                <div className={`audio-blueprint-candidate${isSelected ? " selected" : ""}`} key={`${item.absolute_path || item.relative_path || index}`}>
                  <div>
                    <strong>{shortPathName(item.relative_path || item.absolute_path || `候选曲目 ${index + 1}`)}</strong>
                    <span>
                      {typeof item.duration_seconds === "number" && item.duration_seconds > 0
                        ? formatDurationLabel(item.duration_seconds)
                        : "时长待检测"}
                    </span>
                  </div>
                  <span>{typeof item.score === "number" ? `score ${Math.round(item.score)}` : isSelected ? "主推荐" : "候选"}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {cues.length > 0 && (
        <div className="audio-blueprint-timeline">
          <strong>章节节奏提示</strong>
          <div className="audio-blueprint-cue-list">
            {cues.slice(0, 6).map((item, index) => (
              <div className="audio-blueprint-cue" key={`${item.section_id || item.title || index}-${index}`}>
                <div className="audio-blueprint-cue-main">
                  <span className="audio-blueprint-cue-title">{item.title || item.section_id || `章节 ${index + 1}`}</span>
                  <span className="audio-blueprint-cue-meta">
                    {[item.phase, item.energy, typeof item.duration === "number" ? formatDurationLabel(item.duration) : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </div>
                <p>{item.reason || "保持音乐连续性并跟随章节节奏变化。"}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {editableCues.length > 0 ? (
        <div className="audio-blueprint-editor">
          <div className="audio-blueprint-editor-head">
            <div>
              <strong>章节级配乐微调</strong>
              <span>按章节调整节奏、能量与 ducking，修改会写回蓝图元数据。</span>
            </div>
            {state.v5RenderPlan?.render_settings?.audio_blueprint ? (
              <button type="button" onClick={() => restoreCompiledAudioBlueprintCues(state)}>
                恢复上次编译结果
              </button>
            ) : null}
          </div>

          <div className="audio-blueprint-editor-list">
            {editableCues.map((cue, index) => (
              <div className="audio-blueprint-editor-card" key={`${cue.section_id || index}-${index}`}>
                <div className="audio-blueprint-editor-card-head">
                  <strong>{cue.title || cue.section_id || `章节 ${index + 1}`}</strong>
                  <span>{cue.section_type || "section"}</span>
                </div>

                <div className="audio-blueprint-editor-grid">
                  <label>
                    <span>阶段</span>
                    <select
                      value={cue.phase || "sustain"}
                      onChange={(event) => patchAudioBlueprintCue(state, String(cue.section_id), { phase: event.target.value })}
                    >
                      <option value="intro">开场</option>
                      <option value="sustain">承接</option>
                      <option value="peak">高潮</option>
                      <option value="outro">收束</option>
                    </select>
                  </label>
                  <label>
                    <span>能量</span>
                    <select
                      value={cue.energy || "medium"}
                      onChange={(event) => patchAudioBlueprintCue(state, String(cue.section_id), { energy: event.target.value })}
                    >
                      <option value="low">低</option>
                      <option value="medium">中</option>
                      <option value="high">高</option>
                    </select>
                  </label>
                  <label>
                    <span>Ducking</span>
                    <select
                      value={cue.ducking_hint || "medium"}
                      onChange={(event) => patchAudioBlueprintCue(state, String(cue.section_id), { ducking_hint: event.target.value })}
                    >
                      <option value="off">关闭</option>
                      <option value="light">轻</option>
                      <option value="medium">中</option>
                      <option value="high">强</option>
                    </select>
                  </label>
                </div>

                <label className="audio-blueprint-editor-reason">
                  <span>说明</span>
                  <textarea
                    rows={2}
                    value={cue.reason || ""}
                    onChange={(event) => patchAudioBlueprintCue(state, String(cue.section_id), { reason: event.target.value })}
                  />
                </label>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

function MusicAudioPanel({
  state,
  onPickMusicFile,
  onPickMusicFiles,
}: {
  state: StudioState;
  onPickMusicFile: () => void;
  onPickMusicFiles: () => void;
}) {
  const audioBlueprint = resolveAudioBlueprint(state);
  const sourceAligned = audioBlueprintScopeApplied(state, audioBlueprint, "source");
  const mixAligned = audioBlueprintScopeApplied(state, audioBlueprint, "mix");
  const timingAligned = audioBlueprintScopeApplied(state, audioBlueprint, "timing");
  const resolved = resolveMusicSelection(state, state.v5Library, state.v5RenderPlan);
  const resolvedMusicPath = resolved.primaryPath;
  const musicEnabled = state.musicMode !== "off" && resolved.paths.length > 0;
  const bgmPercent = Math.round(clampNumber(state.bgmVolume, 0, 1, 0.28) * 100);
  const sourcePercent = Math.round(clampNumber(state.sourceAudioVolume, 0, 1, 1) * 100);
  const summary = buildMusicPlanSummarySafe(state, resolved, state.v5RenderPlan);
  const statusText =
    state.musicMode === "auto"
      ? resolved.paths.length > 0
        ? state.musicPlaylistMode === "chapter_restart"
          ? `章节重启 ${resolved.paths.length} 首`
          : state.musicPlaylistMode === "auto_playlist"
            ? `自动多曲 ${resolved.paths.length} 首`
            : "自动匹配 BGM"
        : "未找到可用音频"
      : musicEnabled
        ? state.musicPlaylistMode === "manual_playlist"
          ? `歌单 ${resolved.paths.length} 首`
          : "已启用 BGM"
        : "未添加 BGM";
  const musicHint =
    state.musicMode === "auto"
      ? resolved.paths.length > 0
        ? state.musicPlaylistMode === "chapter_restart"
          ? `章节重启会按章节切点重新进入推荐曲目：${resolved.labels.slice(0, 3).join(" / ")}${resolved.labels.length > 3 ? " ..." : ""}`
          : state.musicPlaylistMode === "auto_playlist"
            ? `自动模式将按顺序使用 ${resolved.paths.length} 首候选：${resolved.labels.slice(0, 3).join(" / ")}${resolved.labels.length > 3 ? " ..." : ""}`
            : `自动模式将使用：${shortPathName(resolvedMusicPath || "")}`
        : "当前素材目录里还没有可用的 BGM 候选，至少需要一首 15 秒以上的音频文件。"
      : resolved.paths.length > 0
        ? state.musicPlaylistMode === "manual_playlist"
          ? `当前歌单：${resolved.labels.slice(0, 3).join(" / ")}${resolved.labels.length > 3 ? ` 等 ${resolved.labels.length} 首` : ""}`
          : shortPathName(resolvedMusicPath || "")
        : "选择本地音乐后，低清小样和最终视频会听到同一套混音与时长适配策略。";

  return (
    <div className={`music-audio-card${musicEnabled ? " has-music" : ""}`}>
      <div className="music-audio-head">
        <div className="music-audio-title">
          <Music size={18} />
          <div>
            <strong>音乐与原声</strong>
            <span>BGM、视频原声、淡入淡出与长视频适配都在这里统一控制。</span>
          </div>
        </div>
        <span className="music-status-badge">{statusText}</span>
      </div>

      {audioBlueprint ? (
        <div className="music-ai-status-row">
          <span className={sourceAligned ? "active" : ""}>曲目建议 {sourceAligned ? "已生效" : "未完全采纳"}</span>
          <span className={mixAligned ? "active" : ""}>混音建议 {mixAligned ? "已生效" : "未完全采纳"}</span>
          <span className={timingAligned ? "active" : ""}>节奏建议 {timingAligned ? "已生效" : "未完全采纳"}</span>
        </div>
      ) : null}

      <div className="music-mode-buttons">
        <button
          className={state.musicMode === "off" ? "active" : ""}
          type="button"
          onClick={() => state.patch({ musicMode: "off", musicPath: null, musicPlaylistPaths: [], musicPlaylistMode: "single" })}
        >
          无音乐
        </button>
        <button
          className={state.musicMode === "manual" ? "active" : ""}
          type="button"
          onClick={onPickMusicFile}
        >
          手动选择
        </button>
        <button
          className={state.musicMode === "auto" ? "active" : ""}
          type="button"
          onClick={() => state.patch({ musicMode: "auto", musicPath: null, musicPlaylistPaths: [] })}
        >
          自动选择
        </button>
      </div>

      {state.musicMode !== "off" && (
        <div className="music-submode-row">
          <div className={`music-submode-group${sourceAligned ? " ai-aligned" : ""}`}>
            <span>配乐方式</span>
            <div className="music-submode-buttons">
              <button
                className={state.musicPlaylistMode === "single" ? "active" : ""}
                type="button"
                onClick={() => state.patch({ musicPlaylistMode: "single", musicPlaylistPaths: state.musicPlaylistPaths })}
              >
                单曲
              </button>
              <button
                className={state.musicPlaylistMode === "auto_playlist" ? "active" : ""}
                disabled={state.musicMode !== "auto"}
                type="button"
                onClick={() => state.patch({ musicMode: "auto", musicPlaylistMode: "auto_playlist", musicPath: null, musicPlaylistPaths: [] })}
              >
                自动多曲
              </button>
              <button
                className={state.musicPlaylistMode === "chapter_restart" ? "active" : ""}
                disabled={state.musicMode !== "auto"}
                type="button"
                onClick={() => state.patch({ musicMode: "auto", musicPlaylistMode: "chapter_restart", musicPath: null, musicPlaylistPaths: [] })}
              >
                章节重启
              </button>
              <button
                className={state.musicPlaylistMode === "manual_playlist" ? "active" : ""}
                type="button"
                onClick={onPickMusicFiles}
              >
                手动歌单
              </button>
            </div>
          </div>
          <div className={`music-submode-group${timingAligned ? " ai-aligned" : ""}`}>
            <span>时长适配</span>
            <div className="music-fit-select-wrap">
              <select
                disabled={!musicEnabled}
                value={state.musicFitStrategy}
                onChange={(event) => state.patch({ musicFitStrategy: event.target.value as MusicFitStrategy })}
              >
                <option value="auto">自动适配</option>
                <option value="intro_loop_outro">首尾保留，中间循环</option>
                <option value="loop">循环铺满</option>
                <option value="trim">智能裁切</option>
                <option value="once">仅播放一次</option>
              </select>
            </div>
          </div>
        </div>
      )}

      <div className={`music-file-row${sourceAligned ? " ai-aligned" : ""}`}>
        <Volume2 size={16} />
        <span title={resolvedMusicPath || ""}>{musicHint}</span>
        {state.musicPlaylistMode === "manual_playlist" && state.musicMode !== "off" ? (
          <button type="button" onClick={onPickMusicFiles}>管理歌单</button>
        ) : state.musicMode === "manual" ? (
          <button type="button" onClick={onPickMusicFile}>更换</button>
        ) : null}
        {resolved.paths.length > 0 && (
          <button
            type="button"
            onClick={() => state.patch({ musicMode: "off", musicPath: null, musicPlaylistPaths: [], musicPlaylistMode: "single" })}
          >
            移除
          </button>
        )}
      </div>

      {audioBlueprint ? <AudioBlueprintPanel state={state} /> : null}

      {state.musicMode !== "off" && (
        <div className="music-plan-grid">
          <div>
            <strong>预计视频</strong>
            <span>{summary.videoDurationLabel}</span>
          </div>
          <div>
            <strong>音乐总长</strong>
            <span>{summary.musicDurationLabel}</span>
          </div>
          <div>
            <strong>当前策略</strong>
            <span>{summary.strategyLabel}</span>
          </div>
          <div>
            <strong>预计执行</strong>
            <span>{summary.executionLabel}</span>
          </div>
        </div>
      )}

      <div className={`music-slider-grid${mixAligned ? " ai-aligned" : ""}`}>
        <label>
          <span>BGM 音量 <strong>{bgmPercent}%</strong></span>
          <input
            disabled={!musicEnabled}
            max={100}
            min={0}
            type="range"
            value={bgmPercent}
            onChange={(event) => state.patch({ bgmVolume: Number(event.target.value) / 100 })}
          />
        </label>
        <label>
          <span>视频原声 <strong>{sourcePercent}%</strong></span>
          <input
            max={100}
            min={0}
            type="range"
            value={sourcePercent}
            onChange={(event) => state.patch({ sourceAudioVolume: Number(event.target.value) / 100 })}
          />
        </label>
      </div>

      <div className={`music-mix-options${mixAligned ? " ai-aligned" : ""}`}>
        <Toggle
          checked={state.keepSourceAudio}
          label="保留视频原声"
          onChange={(keepSourceAudio) => state.patch({ keepSourceAudio })}
        />
        <Toggle
          checked={state.autoDucking}
          label="有原声时自动压低 BGM"
          onChange={(autoDucking) => state.patch({ autoDucking })}
        />
      </div>

      <div className={`music-fade-grid${timingAligned ? " ai-aligned" : ""}`}>
        <label>
          淡入秒数
          <input
            disabled={!musicEnabled}
            max={10}
            min={0}
            step={0.5}
            type="number"
            value={state.musicFadeInSeconds}
            onChange={(event) => state.patch({ musicFadeInSeconds: Number(event.target.value) })}
          />
        </label>
        <label>
          淡出秒数
          <input
            disabled={!musicEnabled}
            max={20}
            min={0}
            step={0.5}
            type="number"
            value={state.musicFadeOutSeconds}
            onChange={(event) => state.patch({ musicFadeOutSeconds: Number(event.target.value) })}
          />
        </label>
      </div>

      <p className="music-audio-note">
        性能档位只会影响混音执行路径，不会默认牺牲 BGM 存在感、视频原声保留和整体情绪表达；长视频场景下会优先用更稳的 FFmpeg 与缓存路径完成混音。
      </p>
    </div>
  );
}

function resolveMusicSelection(state: StudioState, library: V5MediaLibrary | null, plan: V5RenderPlan | null) {
  const videoDuration = Number(plan?.total_duration || 0);
  const autoMusicAssets = selectAutoMusicAssets(library, videoDuration);
  const autoMusicAsset = autoMusicAssets[0] || null;

  if (state.musicMode === "manual") {
    if (state.musicPlaylistMode === "manual_playlist") {
      const paths = state.musicPlaylistPaths.filter(Boolean);
      return {
        primaryPath: paths[0] || state.musicPath || null,
        paths,
        labels: paths.map((item) => shortPathName(item)),
      };
    }
    const path = state.musicPath || null;
    return {
      primaryPath: path,
      paths: path ? [path] : [],
      labels: path ? [shortPathName(path)] : [],
    };
  }

  if (state.musicMode === "auto") {
    const explicitPaths = state.musicPlaylistPaths.filter(Boolean);
    const explicitPrimary = explicitPaths[0] || null;
    if (state.musicPlaylistMode === "auto_playlist" || state.musicPlaylistMode === "chapter_restart") {
      const paths = explicitPaths.length > 0 ? explicitPaths : autoMusicAssets.map((asset) => asset.absolute_path);
      return {
        primaryPath: explicitPrimary || paths[0] || null,
        paths,
        labels: paths.map((item) => shortPathName(item)),
      };
    }
    if (explicitPrimary) {
      return {
        primaryPath: explicitPrimary,
        paths: [explicitPrimary],
        labels: [shortPathName(explicitPrimary)],
      };
    }
    const assets = autoMusicAsset ? [autoMusicAsset] : [];
    return {
      primaryPath: assets[0]?.absolute_path || null,
      paths: assets.map((asset) => asset.absolute_path),
      labels: assets.map((asset) => asset.file.name || shortPathName(asset.absolute_path)),
    };
  }

  return { primaryPath: null, paths: [], labels: [] };
}

function selectAutoMusicAsset(library: V5MediaLibrary | null): V5Asset | null {
  return selectAutoMusicAssets(library, 0)[0] || null;
}

function selectAutoMusicAssets(library: V5MediaLibrary | null, targetDuration: number): V5Asset[] {
  const audioAssets = (library?.assets || []).filter((asset) => asset.type === "audio" && assetStatusState(asset) !== "error");
  if (audioAssets.length === 0) return [];

  const ranked = audioAssets
    .map((asset) => ({ asset, score: autoMusicScore(asset) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      const durationA = Number(a.asset.media.duration_seconds || 0);
      const durationB = Number(b.asset.media.duration_seconds || 0);
      if (durationB !== durationA) return durationB - durationA;
      return a.asset.relative_path.localeCompare(b.asset.relative_path);
    })
    .map((entry) => entry.asset);

  if (targetDuration <= 0) return ranked.slice(0, 1);
  if (targetDuration < 600) return ranked.slice(0, 1);

  const selected: V5Asset[] = [];
  let totalDuration = 0;
  for (const asset of ranked) {
    selected.push(asset);
    totalDuration += Number(asset.media.duration_seconds || asset.media.duration || 0);
    if (selected.length >= 4 || totalDuration >= targetDuration * 0.72) break;
  }
  return selected.length > 0 ? selected : ranked.slice(0, 1);
}

function autoMusicScore(asset: V5Asset): number {
  const duration = Number(asset.media.duration_seconds || asset.media.duration || 0);
  if (duration < 15) return 0;

  const rawHaystack = `${asset.file.name} ${asset.relative_path}`;
  const haystack = rawHaystack.toLowerCase();
  const ext = asset.file.extension.toLowerCase();
  let score = duration >= 45 ? 12 : 6;

  if (/(^|[^a-z])(bgm|music|soundtrack|instrumental|score|theme|ambient|travel)([^a-z]|$)/.test(haystack)) score += 40;
  if (/配乐|音乐|伴奏|纯音乐|背景音乐|旅拍|轻音乐/.test(rawHaystack)) score += 40;
  if (/effect|sfx|hit|whoosh|click|音效|提示音|转场音/.test(rawHaystack)) score -= 25;
  if (duration >= 90) score += 18;
  else if (duration >= 45) score += 10;
  else if (duration >= 25) score += 4;

  score += {
    ".wav": 6,
    ".m4a": 5,
    ".mp3": 4,
    ".flac": 4,
    ".aac": 3,
    ".ogg": 2,
  }[ext] || 0;

  return score;
}

function buildMusicPlanSummary(state: StudioState, resolved: { paths: string[] }, plan: V5RenderPlan | null) {
  const videoDuration = Number(plan?.total_duration || 0);
  const assetMap = new Map((state.v5Library?.assets || []).map((asset) => [asset.absolute_path, asset]));
  const musicDuration = resolved.paths.reduce((sum, item) => {
    const asset = assetMap.get(item);
    return sum + Number(asset?.media.duration_seconds || asset?.media.duration || 0);
  }, 0);
  const loops = musicDuration > 0 && videoDuration > musicDuration ? Math.ceil(videoDuration / musicDuration) : 1;

  const fitLabel: Record<MusicFitStrategy, string> = {
    auto: "自动适配",
    loop: "循环铺满",
    trim: "智能裁切",
    intro_loop_outro: "首尾保留，中间循环",
    once: "仅播放一次",
  };
  const playlistLabel: Record<string, string> = {
    single: "单曲",
    auto_playlist: "自动多曲",
    manual_playlist: "手动歌单",
  };

  let executionLabel = playlistLabel[state.musicPlaylistMode];
  if (state.musicPlaylistMode === "single") {
    executionLabel = loops > 1 ? `预计循环 ${loops} 次` : "单曲完整使用";
  } else if (resolved.paths.length > 0) {
    executionLabel = `${playlistLabel[state.musicPlaylistMode]} ${resolved.paths.length} 首接力`;
  }

  return {
    videoDurationLabel: formatDurationLabel(videoDuration),
    musicDurationLabel: musicDuration > 0 ? formatDurationLabel(musicDuration) : "待选择",
    strategyLabel: fitLabel[state.musicFitStrategy],
    executionLabel,
  };
}

function buildMusicPlanSummarySafe(state: StudioState, resolved: { paths: string[] }, plan: V5RenderPlan | null) {
  const videoDuration = Number(plan?.total_duration || 0);
  const assetMap = new Map((state.v5Library?.assets || []).map((asset) => [asset.absolute_path, asset]));
  const musicDuration = resolved.paths.reduce((sum, item) => {
    const asset = assetMap.get(item);
    return sum + Number(asset?.media.duration_seconds || asset?.media.duration || 0);
  }, 0);
  const loops = musicDuration > 0 && videoDuration > musicDuration ? Math.ceil(videoDuration / musicDuration) : 1;

  const fitLabel: Record<MusicFitStrategy, string> = {
    auto: "自动适配",
    loop: "循环铺满",
    trim: "智能裁切",
    intro_loop_outro: "首尾保留，中间循环",
    once: "仅播放一次",
  };
  const playlistLabel: Record<MusicPlaylistMode, string> = {
    single: "单曲",
    auto_playlist: "自动多曲",
    manual_playlist: "手动歌单",
    chapter_restart: "章节重启",
  };

  let executionLabel = playlistLabel[state.musicPlaylistMode];
  if (state.musicPlaylistMode === "single") {
    executionLabel = loops > 1 ? `音乐循环 ${loops} 次` : "单曲完整使用";
  } else if (state.musicPlaylistMode === "chapter_restart") {
    executionLabel = resolved.paths.length > 0 ? `章节重启 ${resolved.paths.length} 首轮换` : "按章节切点重新进入";
  } else if (resolved.paths.length > 0) {
    executionLabel = `${playlistLabel[state.musicPlaylistMode]} ${resolved.paths.length} 首接力`;
  }

  return {
    videoDurationLabel: formatDurationLabel(videoDuration),
    musicDurationLabel: musicDuration > 0 ? formatDurationLabel(musicDuration) : "待选择",
    strategyLabel: fitLabel[state.musicFitStrategy],
    executionLabel,
  };
}

function formatDurationLabel(duration: number): string {
  if (!Number.isFinite(duration) || duration <= 0) return "待生成";
  const totalSeconds = Math.max(0, Math.round(duration));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function assetStatusState(asset: V5Asset): string {
  if (!asset.status) return "ready";
  if (typeof asset.status === "string") return asset.status;
  return asset.status.state || "ready";
}

function clampNumber(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}

function captureStudioDraft(state: StudioState): StudioDraft {
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
  };
}

function hasMeaningfulStudioDraft(draft: StudioDraft): boolean {
  return Boolean(
    draft.inputFolder ||
      draft.outputFolder ||
      draft.v5Library ||
      draft.v5Blueprint ||
      draft.v5RenderPlan ||
      draft.v5Timeline ||
      draft.titleBackgroundPath ||
      draft.endBackgroundPath ||
      draft.musicPath ||
      draft.musicPlaylistPaths.length > 0,
  );
}

function parseSessionRecoveryData(value: unknown): SessionRecoveryData | null {
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

function formatSnapshotSavedAt(timestamp: string): string {
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "最近保存";
  return `保存于 ${date.toLocaleString()}`;
}

function buildDiagnosticsFileName(baseName: string): string {
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

function resolveResultError(result: GenerateVideoResult) {
  if (result.code) {
    return resolveAppError(`[${result.code}] ${result.message}`);
  }
  return resolveAppError(result.message);
}

function editStrategyHint(strategy: EditStrategy): string {
  return {
    smart_director: "根据素材规模自动选择节奏、转场和稳定渲染模式。",
    fast_assembly: "优先速度和稳定，适合快速出样片或大素材库初稿。",
    travel_soft: "柔和旅拍观感，适合风景、美食、生活记录。",
    beat_cut: "快节奏和冲击感，适合短视频、运动和高能素材。",
    documentary: "章节清晰、转场克制，适合中长叙事内容。",
    long_stable: "优先分段缓存和失败恢复，适合长视频和大量素材。",
  }[strategy];
}

function transitionProfileForStrategy(strategy: EditStrategy): string {
  return {
    smart_director: "auto",
    fast_assembly: "minimal_fast",
    travel_soft: "travel_soft",
    beat_cut: "beat_cut",
    documentary: "documentary",
    long_stable: "stable_light",
  }[strategy];
}

function rhythmProfileForStrategy(strategy: EditStrategy): string {
  return {
    smart_director: "auto",
    fast_assembly: "fast_review",
    travel_soft: "medium_soft",
    beat_cut: "fast_punchy",
    documentary: "steady_story",
    long_stable: "long_consistent",
  }[strategy];
}

function renderModeForPerformance(mode: PerformanceMode, strategy: EditStrategy): string {
  if (mode === "stable") return "long_stable";
  // quality should keep visual quality, but must not disable Python's long-project
  // auto stable renderer. Otherwise 80+ image segments can be forced into one
  // monolithic MoviePy timeline and exhaust memory.
  if (mode === "quality") return "auto";
  if (strategy === "long_stable") return "long_stable";
  return "auto";
}

function chunkSecondsForPerformance(mode: PerformanceMode): number {
  return {
    stable: 60,
    balanced: 120,
    quality: 180,
  }[mode];
}

function recommendPerformanceMode(
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
function qualityLabel(quality: Quality): string {
  return {
    draft: "草稿",
    standard: "标准",
    high: "高质量",
  }[quality];
}

function photoSegmentCacheLabel(stats: PhotoSegmentCacheStats): string {
  const parts = [`复用 ${stats.hit}`, `新建 ${stats.created}`];
  if (stats.fallback > 0) {
    parts.push(`回退 ${stats.fallback}`);
  }
  if (stats.saved_render_seconds > 0) {
    parts.push(`节省 ${formatDurationCompact(stats.saved_render_seconds)}`);
  }
  return `${parts.join(" / ")} · 候选 ${stats.eligible}`;
}

function proxyMediaLabel(stats: ProxyMediaStats): string {
  const parts = [`reuse ${stats.hit}`, `new ${stats.created}`];
  if (stats.fallback > 0) {
    parts.push(`fallback ${stats.fallback}`);
  }
  return `${parts.join(" / ")} of ${stats.eligible}`;
}

function photoSegmentCacheHeadline(stats: PhotoSegmentCacheStats): string {
  if (stats.hit > 0) {
    return `这次因为照片段缓存，已经省掉 ${stats.saved_live_composes || stats.hit} 段实时拼装`;
  }
  if (stats.created > 0) {
    return `这次已预热 ${stats.created} 段照片缓存，下次会更快`;
  }
  return `这次有 ${stats.eligible} 段照片进入缓存候选`;
}

function photoSegmentCacheNote(stats: PhotoSegmentCacheStats): string {
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

function formatDurationCompact(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return "0s";
  const rounded = Math.round(seconds);
  if (rounded < 60) return `${rounded}s`;
  const minutes = Math.floor(rounded / 60);
  const remain = rounded % 60;
  return remain > 0 ? `${minutes}m ${remain}s` : `${minutes}m`;
}

function videoSegmentCacheHeadline(stats: VideoSegmentCacheStats): string {
  if (stats.hit > 0) {
    return `这次因为视频段缓存，已经省掉 ${stats.saved_live_fits || stats.hit} 段实时适配`;
  }
  if (stats.created > 0) {
    return `这次已预热 ${stats.created} 段视频缓存，下次会更快`;
  }
  return `这次有 ${stats.eligible} 段视频进入缓存候选`;
}

function videoSegmentCacheNote(stats: VideoSegmentCacheStats): string {
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
