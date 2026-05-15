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
  PlayCircle,
  Calendar,
  Folder,
  Layers,
  LayoutGrid,
  MapPin,
  Palmtree,
} from "lucide-react";
import { useMemo, useState, useEffect, useRef } from "react";
import { listen } from "@tauri-apps/api/event";
import { convertFileSrc } from "@tauri-apps/api/core";
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
import { StudioState, useStudio } from "./store/studio";
import { BackgroundPickerTarget, VideoEvent } from "./types/studio";
import { applyStructuredEvent, detectPhase, formatProgressLine, parseProgress, parseVideoEvent } from "./lib/progress";
import "./v5-background.css";

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
  const [selectedMaterial, setSelectedMaterial] = useState<VideoEvent | null>(null);
  const [showGalleryOverlay, setShowGalleryOverlay] = useState(false);
  const [galleryView, setGalleryView] = useState<"chapter" | "type" | "time">("chapter");
  const [backgroundPickerTarget, setBackgroundPickerTarget] = useState<BackgroundPickerTarget | null>(null);
  const [isPreparingBackgroundLibrary, setIsPreparingBackgroundLibrary] = useState(false);
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

  useEffect(() => {
    const unlisten = listen<string>("video-progress", (event) => {
      const raw = event.payload;
      const structured = parseVideoEvent(raw);
      if (structured) {
        applyStructuredEvent(structured, setPhase, setProgress, setLogs, setMaterials);
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
    end_background_path: state.endBackgroundPath,
    chapter_background_mode: state.chapterBackgroundMode,
  }), [state.title, state.titleSubtitle, state.watermark, state.aspectRatio, state.quality, state.renderEngine, state.performanceMode, state.editStrategy, state.cover, state.titleBackgroundPath, state.endBackgroundPath, state.chapterBackgroundMode]);

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

  async function onGenerate(dryRun: boolean = false) {
    if (isRendering) {
      await onCancel();
      return;
    }

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

                  {!isRendering && (
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
                       <button className="primary-action pulse-guidance" disabled={!state.outputFolder || isRendering} onClick={() => onGenerate(false)}>
                          <PlayCircle size={24} /> 立即开始最终合成
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

    {selectedMaterial && (
      <PreviewModal material={selectedMaterial} onClose={() => setSelectedMaterial(null)} />
    )}
    </>
  );
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
  if (mode === "quality") return "standard";
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
      summary: "检测到长视频或大量素材，建议启用稳定优先，保留章节动效但降低复杂转场风险。",
      reason: "素材量较大，已建议稳定渲染；章节文字动效会保留，复杂转场和强镜头运动会更克制。",
    };
  }

  if (isMedium) {
    return {
      recommended: "balanced",
      level: "medium",
      estimatedChunkSeconds: 120,
      shouldWarn: false,
      summary: "当前项目适合平衡推荐：保留主要动效，同时用分段策略控制内存。",
      reason: "项目规模中等，平衡推荐能兼顾效果、速度和稳定性。",
    };
  }

  return {
    recommended: "quality",
    level: "low",
    estimatedChunkSeconds: 180,
    shouldWarn: false,
    summary: "当前项目较轻，可以优先保留完整转场、章节动效和高质量输出。",
    reason: "素材规模较小，画质优先风险较低。",
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
