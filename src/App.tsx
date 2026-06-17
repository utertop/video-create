import {
  Clapperboard,
  FileVideo,
  FolderOpen,
  Gauge,
  ImagePlus,
  Play,
  Settings2,
  Sparkles,
  Square,
  X,
  Wand2,
  ListChecks,
  Clock,
  Loader2,
  PlayCircle,
  RotateCcw,
  Calendar,
  Folder,
  Layers,
  LayoutGrid,
  MapPin,
  Palmtree,
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
  V5Timeline,
  V5Asset,
  V5TitleStyle,
  V5ChapterBackgroundMode,
  RenderRecoverySummary,
  TelemetrySummary,
  buildV5RenderCommandPreview,
  preflightRenderV5,
  startTelemetrySession,
  startupSelfCheck,
  updateTelemetrySettings,
} from "./lib/engine";
import { getAssetThumbnailPath, updateBlueprintSection, withBlueprintMetadata } from "./lib/blueprint";
import { BackgroundAssetPicker, shortPathName } from "./components/BackgroundAssetPicker";
import { BlueprintEditor } from "./components/BlueprintEditor";
import { Feature, SectionTitle, StatusItem } from "./components/common";
import { EditStrategyPreview } from "./components/EditStrategyPreview";
import { SegmentedControl, Toggle } from "./components/FormControls";
import { FolderSelector, OutputFolderSelector } from "./components/FolderSelector";
import { MaterialGallery, PreviewModal } from "./components/MaterialGallery";
import { PerformanceModeControl, performanceModeLabel } from "./components/PerformanceModeControl";
import { ProgressBar, ProgressTone } from "./components/ProgressBar";
import { DiagnosticsCard, ProjectMigrationCard, StartupHealthCard, TelemetryConsentDialog, TelemetrySummaryCard } from "./components/DiagnosticsPanels";
import { ResultCard } from "./components/RenderResultPanel";
import { ProjectRecoveryCard, RecentProjectsCard, SessionRecoveryCard } from "./components/RecoveryCards";
import { ACTIVE_RENDER_QUEUE_STATUSES, normalizeQueueStatus, RenderQueueItem, RenderQueuePanel, shortJobId } from "./components/RenderQueuePanel";
import { normalizeTitleStyle, titleTemplateLabel, TitleStyleLab } from "./components/TitleStylePreview";
import { Toast } from "./components/Toast";
import { buildAudioSettings, decorateAudioBlueprintForPersist, MusicAudioPanel, RenderAudioTimelineCard, resolveAudioBlueprint } from "./features/audio/AudioPanels";
import { TimelineEditor } from "./features/timeline/TimelineEditor";
import { selectStudioAppState, StudioState, useStudio } from "./store/studio";
import { BackgroundPickerTarget, PhotoSegmentCacheStats, ProxyMediaStats, VideoEvent, VideoSegmentCacheStats } from "./types/studio";
import { buildDiagnosticBundlePayload, buildErrorCodeStats, buildSupportCaseSummary, summarizeErrorCodes } from "./lib/diagnostics";
import { resolveResultError } from "./lib/renderResult";
import { formatSnapshotSavedAt, parseSessionRecoveryData } from "./lib/sessionRecovery";
import type { RecentProject, RecoverableProjectState, SessionRecoveryData } from "./lib/sessionRecovery";
import {
  buildDiagnosticsFileName,
  buildV5FinalOutputName,
  buildV5OutputPath,
  buildV5ProjectDir,
  buildV5RenderParams,
  captureStudioDraft,
  chooseRecoveredTimeline,
  chunkSecondsForPerformance,
  editStrategyHint,
  formatDurationCompact,
  friendlyDiagnosticsMessage,
  friendlyErrorMessage,
  getSelectedBackgroundPath,
  hasMeaningfulStudioDraft,
  latestRecoverableFailedRenderJob,
  loadRecentProjects,
  loadRecoverySummaryForPlan,
  makeTitleLabSection,
  photoSegmentCacheHeadline,
  photoSegmentCacheLabel,
  photoSegmentCacheNote,
  projectDirFromRecentProject,
  proxyMediaLabel,
  qualityLabel,
  recommendPerformanceMode,
  renderModeForPerformance,
  resumeActionSuggestion,
  rhythmProfileForStrategy,
  saveRecentProjects,
  transitionProfileForStrategy,
  videoSegmentCacheHeadline,
  videoSegmentCacheNote,
} from "./lib/studioAppHelpers";
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

const TELEMETRY_PREFERENCE_KEY = "video-create-studio.telemetry-enabled.v1";

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

  const v5ProjectDir = useMemo(() => buildV5ProjectDir(state.outputFolder, state.inputFolder), [state.outputFolder, state.inputFolder]);

  const v5PlanPath = useMemo(() => v5ProjectDir ? `${v5ProjectDir}\\render_plan.json` : "", [v5ProjectDir]);
  const v5TimelinePath = useMemo(() => v5ProjectDir ? `${v5ProjectDir}\\timeline.json` : "", [v5ProjectDir]);

  const v5FinalOutputName = useMemo(() => buildV5FinalOutputName(state.outputName), [state.outputName]);

  const v5OutputPath = useMemo(() => buildV5OutputPath(state.outputFolder, v5FinalOutputName), [state.outputFolder, v5FinalOutputName]);

  const latestRecoverableFailedJob = useMemo(() => latestRecoverableFailedRenderJob(renderQueue), [renderQueue]);

  const performanceRecommendation = useMemo(
    () => recommendPerformanceMode(state.v5RenderPlan, state.v5Library, state.quality, state.editStrategy),
    [state.v5RenderPlan, state.v5Library, state.quality, state.editStrategy],
  );

  const v5RenderParams = useMemo(() => buildV5RenderParams(state), [state]);

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
    const timelineForAutosave = state.v5Timeline;
    const needsTimelineSave = Boolean(timelineForAutosave.metadata?.dirty || timelineForAutosave.metadata?.preview_settings_dirty);
    if (!needsTimelineSave) {
      setTimelineAutosave((current) => (current.status === "idle" ? current : { status: "idle" }));
      return;
    }
    if (isApplyingTimeline) return;

    setTimelineAutosave((current) => (
      current.status === "saving" ? current : { status: "saving", savedAt: current.savedAt || null }
    ));
    const timeoutId = window.setTimeout(() => {
      const shouldClearPreviewSettingsDirty = Boolean(
        timelineForAutosave.metadata?.preview_settings_dirty && !timelineForAutosave.metadata?.dirty,
      );
      const timelineToSave = shouldClearPreviewSettingsDirty
        ? {
            ...timelineForAutosave,
            metadata: {
              ...(timelineForAutosave.metadata || {}),
              preview_settings_dirty: false,
            },
          }
        : timelineForAutosave;
      void saveTimelineV5(v5TimelinePath, JSON.stringify(timelineToSave, null, 2))
        .then(() => {
          if (shouldClearPreviewSettingsDirty) {
            state.patch({ v5Timeline: timelineToSave });
          }
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
