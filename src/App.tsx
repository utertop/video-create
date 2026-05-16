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
import { listen } from "@tauri-apps/api/event";
import { convertFileSrc } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";
import {
  AspectRatio,
  EditStrategy,
  GenerateVideoResult,
  PerformanceMode,
  Quality,
  RenderEngine,
  cancelVideo,
  openInExplorer,
  scanV5,
  planV5,
  saveBlueprintV5,
  compileV5,
  renderV5,
  previewRenderV5,
  V5StoryBlueprint,
  V5StorySection,
  V5MediaLibrary,
  V5RenderPlan,
  V5RenderSegment,
  V5Asset,
  V5AudioSettings,
  V5TitleStyle,
  MusicFitStrategy,
  MusicPlaylistMode,
  V5ChapterBackgroundMode,
  RenderV5Params,
  buildV5RenderCommandPreview
} from "./lib/engine";
import { findSectionById, getAssetThumbnailPath, updateBlueprintSection, withBlueprintMetadata } from "./lib/blueprint";
import { BackgroundAssetPicker, shortPathName } from "./components/BackgroundAssetPicker";
import { BlueprintEditor } from "./components/BlueprintEditor";
import { Feature, SectionTitle, StatusItem } from "./components/common";
import { EditStrategyPreview } from "./components/EditStrategyPreview";
import { FolderSelector, OutputFolderSelector } from "./components/FolderSelector";
import { MaterialGallery, PreviewModal } from "./components/MaterialGallery";
import { PerformanceModeControl, PerformanceRecommendation, performanceModeLabel } from "./components/PerformanceModeControl";
import { normalizeTitleStyle, titleTemplateLabel, TitleStyleLab } from "./components/TitleStylePreview";
import { StudioState, useStudio } from "./store/studio";
import { BackgroundPickerTarget, PhotoSegmentCacheStats, ProxyMediaStats, VideoEvent, VideoSegmentCacheStats } from "./types/studio";
import { applyStructuredEvent, detectPhase, formatProgressLine, parseProgress, parseVideoEvent } from "./lib/progress";
import "./v5-background.css";

type RenderQueueStatus = "queued" | "running" | "done" | "failed" | "cancelled";

interface RenderQueueItem {
  id: string;
  label: string;
  status: RenderQueueStatus;
  position: number;
  progress: number;
  message?: string;
  planPath?: string;
  outputPath?: string;
  outputDir?: string;
  commandPreview?: string;
  params?: RenderV5Params;
  createdAt: number;
  startedAt?: number;
  finishedAt?: number;
  retryCount: number;
}

const ACTIVE_RENDER_QUEUE_STATUSES = new Set<RenderQueueStatus>(["queued", "running"]);

function ProgressBar({ percent, phase, isDryRun }: { percent: number; phase: string; isDryRun: boolean }) {
  return (
    <div className="progress-container">
      <div className="progress-header">
        <div className="phase-info">
          <div className={`phase-dot ${isDryRun ? 'dry-run' : 'rendering'}`} />
          <span>{phase}</span>
        </div>
        <span className="percent-number">{percent}%</span>
      </div>
      <div className="progress-track">
        <div 
          className="progress-fill" 
          style={{ width: `${percent}%` }}
        >
          <div className="progress-glow" />
        </div>
      </div>
    </div>
  );
}

export function App() {
  const state = useStudio();
  const [result, setResult] = useState<GenerateVideoResult | null>(null);
  const [isRendering, setIsRendering] = useState(false);
  const [isPreviewRendering, setIsPreviewRendering] = useState(false);
  const [renderPreviewPath, setRenderPreviewPath] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);
  const [isPlanningWorkflow, setIsPlanningWorkflow] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
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
  const logEndRef = useRef<HTMLDivElement>(null);
  const activeJobRef = useRef<string | null>(null);
  const [activeNav, setActiveNav] = useState("workspace");

  const [hasPreChecked, setHasPreChecked] = useState(false);

  const resetTask = () => {
    setResult(null);
    setLogs([]);
    setProgress(null);
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
    state.patch({ isDryRun: false });
  };

  useEffect(() => {
    resetTask();
  }, [state.inputFolder]);

  function scrollToSection(id: string) {
    setActiveNav(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
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
            progress: typeof event.percent === "number" ? Math.max(0, Math.min(100, event.percent)) : item.progress,
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
        applyStructuredEvent(structured, setPhase, setProgress, setLogs, setMaterials, setPhotoSegmentCache, setVideoSegmentCache, setProxyMedia);
        return;
      }

      const prog = parseProgress(raw);
      if (prog) setProgress(Math.round((prog.current / prog.total) * 90));

      const newPhase = detectPhase(raw);
      if (newPhase) {
        setPhase(newPhase);
        if (newPhase === "合成视频") setProgress(92);
        if (newPhase === "生成封面") setProgress(95);
        if (newPhase === "生成报告") setProgress(98);
        if (newPhase === "完成") setProgress(100);
      }

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

  const v5FinalOutputName = useMemo(() => {
    const outputName = state.outputName || "travel_video";
    return outputName.endsWith(".mp4") ? outputName : `${outputName}.mp4`;
  }, [state.outputName]);

  const v5OutputPath = useMemo(() => {
    return state.outputFolder ? `${state.outputFolder}\\${v5FinalOutputName}` : "";
  }, [state.outputFolder, v5FinalOutputName]);

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
    try {
      const library = await scanV5(state.inputFolder, v5ProjectDir, state.recursive);
      state.patch({ v5Library: library });
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
      state.patch({ titleBackgroundPath: asset.absolute_path });
      setToast(`已选择片头卡背景：${asset.file.name}`);
    } else if (target.kind === "end") {
      state.patch({ endBackgroundPath: asset.absolute_path });
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
      state.patch({ v5Blueprint: updated });
      setToast(`已为章节「${target.sectionTitle}」选择背景：${asset.file.name}`);
    }
    setBackgroundPickerTarget(null);
  }

  function onClearBackgroundAsset(target: BackgroundPickerTarget) {
    if (target.kind === "title") {
      state.patch({ titleBackgroundPath: null });
      setToast("片头背景已恢复默认：使用成片第一个画面首帧虚化。");
    } else if (target.kind === "end") {
      state.patch({ endBackgroundPath: null });
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
      state.patch({ v5Blueprint: updated });
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

  function enqueueV5RenderJob() {
    if (!v5PlanPath || !v5OutputPath) {
      const message = "V5 render plan or output path is missing. Please compile the V5 plan first.";
      setResult({ ok: false, message, commandPreview: v5CommandPreview });
      setToast(message);
      return;
    }

    const hasLiveJobs = renderQueue.some((item) => ACTIVE_RENDER_QUEUE_STATUSES.has(item.status));
    if (!hasLiveJobs) {
      setToast(null);
      setResult(null);
      setLogs([]);
      setProgress(0);
      setPhase("V5 render queued");
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
    setLogs((prev) => [...prev, `Render queued: ${job.label} (${shortJobId(job.id)})`].slice(-100));
    void runRenderQueueJob(job);
  }

  async function runRenderQueueJob(job: RenderQueueItem) {
    if (!job.planPath || !job.outputPath || !job.params) return;
    try {
      await renderV5(job.planPath, job.outputPath, job.params, job.id);
      setRenderQueue((prev) =>
        prev.map((item) =>
          item.id === job.id
            ? {
                ...item,
                status: "done",
                progress: 100,
                message: "Render completed",
                finishedAt: item.finishedAt || Date.now(),
              }
            : item,
        ),
      );
      setResult({
        ok: true,
        message: `V5 render completed: ${job.outputPath}`,
        commandPreview: job.commandPreview || v5CommandPreview,
        outputPath: job.outputPath,
        outputDir: job.outputDir,
      });
      setProgress(100);
      setPhase("Render complete");
    } catch (err: any) {
      const message = String(err);
      let shouldShowFailure = true;
      setRenderQueue((prev) =>
        prev.map((item) => {
          if (item.id !== job.id) return item;
          const wasCancelled = item.status === "cancelled" || message.toLowerCase().includes("cancel");
          shouldShowFailure = !wasCancelled;
          return {
            ...item,
            status: wasCancelled ? "cancelled" : "failed",
            message: wasCancelled ? "Render cancelled" : message,
            finishedAt: item.finishedAt || Date.now(),
          };
        }),
      );
      if (shouldShowFailure) {
        setResult({
          ok: false,
          message: `V5 render failed: ${message}`,
          commandPreview: job.commandPreview || v5CommandPreview,
        });
      }
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
      enqueueV5RenderJob();
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
      setResult({
        ok: false,
        message: `低清预览生成失败: ${err}`,
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
      state.patch({ v5Library: library });
      
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
      state.patch({ v5Blueprint: blueprintWithGuiText, v5Stage: "BLUEPRINT" });
      
      setPhase("蓝图就绪");
      setProgress(100);
      setToast("故事蓝图已生成，请开始编排您的旅行故事！");
    } catch (error) {
      console.error("V5 Workflow Error:", error);
      setPhase("智能编排失败");
      setToast(`扫描失败: ${error}`);
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
        scenic_spot_title_mode: "overlay",
      });
      await saveBlueprintV5(bpPath, JSON.stringify(blueprintForCompile, null, 2));
      
      // 2. 编译
      setPhase("正在编译渲染计划...");
      setProgress(60);
      const plan = await compileV5(bpPath, libPath, `${v5ProjectDir}\\render_plan.json`);
      
      // 3. 进入渲染阶段
      state.patch({ v5Blueprint: blueprintForCompile, v5RenderPlan: plan, v5Stage: "RENDER" });
      setPhase("渲染计划就绪");
      setProgress(100);
    } catch (error) {
      console.error("Confirm Blueprint Error:", error);
      setToast(`确认失败: ${error}`);
    }
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
      message: "Retry queued",
      createdAt: Date.now(),
      startedAt: undefined,
      finishedAt: undefined,
      retryCount: item.retryCount + 1,
    };
    setRenderQueue((prev) => [...prev, retryJob]);
    setLogs((prev) => [...prev, `Retry queued: ${retryJob.label} (${shortJobId(retryJob.id)})`].slice(-100));
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

        <nav className="nav-list" aria-label="主导航">
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
      </aside>

      <section className="workspace" id="workspace">
        {toast && <Toast title={state.v5Stage === "BLUEPRINT" ? "蓝图生成成功" : "提示"} message={toast} onClose={() => setToast(null)} />}
        <div className="workspace-inner">
        <header className="topbar">
          <div>
            <p className="eyebrow">GUI MVP</p>
            <h1>Turn Moments into Motion.</h1>
          </div>
          <div className="topbar-actions">
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
                      <ProgressBar isDryRun={false} percent={progress || 0} phase={phase} />
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
                    onPickSectionBackground={(section) => ensureBackgroundLibrary({ kind: "section", sectionId: section.section_id, sectionTitle: section.title })}
                    onUpdate={(bp) => state.patch({ v5Blueprint: bp })}
                  />
                  <div className="blueprint-actions">
                     <button className="secondary-action" onClick={() => state.patch({ v5Stage: "INPUT" })}>重新扫描</button>
                     <button className="primary-action" onClick={onConfirmBlueprint}>确认并进入渲染</button>
                  </div>
               </div>
            ) : (
               <div className="render-stage-container">
                  <SectionTitle icon={<FileVideo size={18} />} title="渲染执行" />
                  
                  {(isRendering || logs.length > 0) && (
                    <div className="render-progress-area">
                      <ProgressBar isDryRun={state.isDryRun} percent={progress || 0} phase={phase} />
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
                       <button className="secondary-action" disabled={!state.v5RenderPlan || isPreviewRendering} onClick={onPreviewRenderSample}>
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
                       <button className="primary-action pulse-guidance" disabled={!state.outputFolder} onClick={() => onGenerate(false)}>
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
                          {isRendering && progress !== null && <span className="current-progress-text">进度: {progress}%</span>}
                       </div>
                       <div className="segments-timeline">
                          {state.v5RenderPlan!.segments.map((seg: V5RenderSegment, idx: number) => {
                            const isCurrent = isRendering && progress !== null && 
                              (progress / 100 * state.v5RenderPlan!.total_duration >= seg.start_time) &&
                              (progress / 100 * state.v5RenderPlan!.total_duration < seg.end_time);
                            
                            return (
                              <div key={seg.segment_id} className={`segment-strip ${seg.type}${isCurrent ? ' active-rendering' : ''}`}>
                                 <div className="seg-label">
                                   {isCurrent ? <Wand2 size={10} className="spin" /> : seg.type.toUpperCase()}
                                 </div>
                                 <div className="seg-info">
                                    {seg.text || seg.source_path?.split(/[/\\]/).pop()}
                                 </div>
                                 <div className="seg-time">{seg.duration.toFixed(1)}s</div>
                              </div>
                            );
                          })}
                       </div>
                    </div>
                  )}

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
            {result && <ResultCard result={result} />}
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

function RenderQueuePanel({
  queue,
  onCancel,
  onRetry,
}: {
  queue: RenderQueueItem[];
  onCancel: (jobId: string) => void;
  onRetry: (item: RenderQueueItem) => void;
}) {
  const current = queue.find((item) => item.status === "running") || null;
  const waiting = queue.filter((item) => item.status === "queued");
  const history = queue
    .filter((item) => !ACTIVE_RENDER_QUEUE_STATUSES.has(item.status))
    .slice()
    .reverse();

  return (
    <div className="render-queue-panel">
      <div className="render-queue-header">
        <div>
          <strong>Render queue</strong>
          <span>{waiting.length} waiting, {history.length} finished</span>
        </div>
      </div>

      <div className="render-queue-grid">
        <div className="render-queue-section current">
          <div className="render-queue-section-title">
            <Loader2 size={16} className={current ? "spin" : undefined} />
            Current
          </div>
          {current ? (
            <RenderQueueRow item={current} onCancel={onCancel} onRetry={onRetry} />
          ) : (
            <div className="render-queue-empty">No active render</div>
          )}
        </div>

        <div className="render-queue-section">
          <div className="render-queue-section-title">
            <Clock size={16} />
            Waiting
          </div>
          {waiting.length > 0 ? (
            waiting.map((item) => <RenderQueueRow key={item.id} item={item} onCancel={onCancel} onRetry={onRetry} />)
          ) : (
            <div className="render-queue-empty">Queue is empty</div>
          )}
        </div>

        <div className="render-queue-section history">
          <div className="render-queue-section-title">
            <History size={16} />
            History
          </div>
          {history.length > 0 ? (
            history.map((item) => <RenderQueueRow key={item.id} item={item} onCancel={onCancel} onRetry={onRetry} />)
          ) : (
            <div className="render-queue-empty">No completed jobs yet</div>
          )}
        </div>
      </div>
    </div>
  );
}

function RenderQueueRow({
  item,
  onCancel,
  onRetry,
}: {
  item: RenderQueueItem;
  onCancel: (jobId: string) => void;
  onRetry: (item: RenderQueueItem) => void;
}) {
  const canCancel = ACTIVE_RENDER_QUEUE_STATUSES.has(item.status);
  const canRetry = item.status === "failed";
  return (
    <div className={`render-queue-row ${item.status}`}>
      <div className="render-queue-main">
        <div className="render-queue-name">
          <span className={`render-queue-status-dot ${item.status}`} />
          <strong>{item.label}</strong>
          {item.retryCount > 0 && <span className="render-queue-retry-badge">retry {item.retryCount}</span>}
        </div>
        <div className="render-queue-meta">
          <span>{queueStatusLabel(item.status)}</span>
          <span>{shortJobId(item.id)}</span>
          {item.position > 0 && <span>#{item.position}</span>}
          <span>{formatQueueTime(item.finishedAt || item.startedAt || item.createdAt)}</span>
        </div>
        {item.message && <div className="render-queue-message">{item.message}</div>}
        {item.status === "running" && (
          <div className="render-queue-progress">
            <div style={{ width: `${Math.max(2, item.progress)}%` }} />
          </div>
        )}
      </div>
      <div className="render-queue-actions">
        {canCancel && (
          <button className="render-queue-icon-btn danger" type="button" onClick={() => onCancel(item.id)} title="Cancel render">
            <Square size={14} />
          </button>
        )}
        {canRetry && (
          <button className="render-queue-icon-btn" type="button" onClick={() => onRetry(item)} title="Retry failed render">
            <RotateCcw size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

function normalizeQueueStatus(status: string): RenderQueueStatus {
  if (status === "running" || status === "done" || status === "failed" || status === "cancelled") return status;
  return "queued";
}

function queueStatusLabel(status: RenderQueueStatus): string {
  return {
    queued: "Waiting",
    running: "Rendering",
    done: "Done",
    failed: "Failed",
    cancelled: "Cancelled",
  }[status];
}

function shortJobId(jobId: string): string {
  return jobId.length > 8 ? jobId.slice(0, 8) : jobId;
}

function formatQueueTime(timestamp?: number): string {
  if (!timestamp) return "";
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function ResultCard({ result }: { result: GenerateVideoResult }) {
  return (
    <div className={`result-card ${result.ok ? "success" : "warning"}`}>
      <div className="result-card-header">
        {result.ok ? <CheckCircle2 size={20} /> : <TriangleAlert size={20} />}
        <strong>{result.isDryRun ? (result.ok ? "预检完成" : "预检失败") : (result.ok ? "生成完成" : "生成失败")}</strong>
      </div>
      <p className="result-card-message">
        {result.message}
        {result.isDryRun && result.ok && (
          <span style={{ display: 'block', marginTop: '4px', opacity: 0.8, fontSize: '0.9em' }}>
            提示：素材状态良好，您可以点击右上角的“生成视频”开始正式合成。
          </span>
        )}
      </p>
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

function MusicAudioPanel({
  state,
  onPickMusicFile,
  onPickMusicFiles,
}: {
  state: StudioState;
  onPickMusicFile: () => void;
  onPickMusicFiles: () => void;
}) {
  const resolved = resolveMusicSelection(state, state.v5Library, state.v5RenderPlan);
  const resolvedMusicPath = resolved.primaryPath;
  const musicEnabled = state.musicMode !== "off" && resolved.paths.length > 0;
  const bgmPercent = Math.round(clampNumber(state.bgmVolume, 0, 1, 0.28) * 100);
  const sourcePercent = Math.round(clampNumber(state.sourceAudioVolume, 0, 1, 1) * 100);
  const summary = buildMusicPlanSummary(state, resolved, state.v5RenderPlan);
  const statusText =
    state.musicMode === "auto"
      ? resolved.paths.length > 0
        ? state.musicPlaylistMode === "auto_playlist"
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
        ? state.musicPlaylistMode === "auto_playlist"
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

      <div className="music-mode-buttons">
        <button
          className={state.musicMode === "off" ? "active" : ""}
          type="button"
          onClick={() => state.patch({ musicMode: "off" })}
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
          onClick={() => state.patch({ musicMode: "auto" })}
        >
          自动选择
        </button>
      </div>

      {state.musicMode !== "off" && (
        <div className="music-submode-row">
          <div className="music-submode-group">
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
                onClick={() => state.patch({ musicMode: "auto", musicPlaylistMode: "auto_playlist" })}
              >
                自动多曲
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
          <div className="music-submode-group">
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

      <div className="music-file-row">
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
            onClick={() => state.patch({ musicMode: "off", musicPlaylistPaths: [], musicPlaylistMode: "single" })}
          >
            移除
          </button>
        )}
      </div>

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

      <div className="music-slider-grid">
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

      <div className="music-mix-options">
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

      <div className="music-fade-grid">
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
    const assets = state.musicPlaylistMode === "auto_playlist" ? autoMusicAssets : autoMusicAsset ? [autoMusicAsset] : [];
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
  const playlistLabel: Record<MusicPlaylistMode, string> = {
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
function SegmentedControl({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  onChange: (value: string) => void;
}) {
  return (
    <div className="segmented-group">
      <span>{label}</span>
      <div className="segmented-control">
        {options.map(([optionValue, optionLabel]) => (
          <button
            className={value === optionValue ? "selected" : ""}
            key={optionValue}
            onClick={() => onChange(optionValue)}
            type="button"
          >
            {optionLabel}
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({ checked, label, onChange }: { checked: boolean; label: string; onChange: (value: boolean) => void }) {
  return (
    <label className="toggle">
      <input checked={checked} type="checkbox" onChange={(event) => onChange(event.target.checked)} />
      <span />
      {label}
    </label>
  );
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
