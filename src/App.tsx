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
  Eye,
  PlayCircle,
  FileWarning,
  Calendar,
  Folder,
  Layers,
  LayoutGrid,
  MapPin,
  Palmtree,
  EyeOff,
  Maximize2,
  Minimize2,
  Pencil
} from "lucide-react";
import { useMemo, useState, useEffect, useRef } from "react";
import { create } from "zustand";
import { open } from "@tauri-apps/plugin-dialog";
import { listen } from "@tauri-apps/api/event";
import { convertFileSrc } from "@tauri-apps/api/core";
import {
  AspectRatio,
  GenerateVideoPayload,
  GenerateVideoResult,
  Quality,
  RenderEngine,
  buildCommandPreview,
  cancelVideo,
  generateVideo,
  openInExplorer,
  scanV5,
  planV5,
  saveBlueprintV5,
  compileV5,
  renderV5,
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
import "./v5-background.css";

interface VideoEvent {
  type?: string;
  message?: string;
  phase?: string;
  percent?: number;
  current?: number;
  total?: number;
  ok?: boolean;
  output_path?: string;
  output_dir?: string;
  artifact?: string;
  path?: string;
  item_kind?: string;
  rel_path?: string;
  display_name?: string;
  width?: number;
  height?: number;
  duration?: number;
  thumbnail?: string;
  error?: string;
  chapter?: string;
  mtime?: number;
}

type BackgroundPickerTarget =
  | { kind: "title" }
  | { kind: "end" }
  | { kind: "section"; sectionId: string; sectionTitle: string };

interface StudioState {
  inputFolder: string | null;
  outputFolder: string | null;
  title: string;
  titleSubtitle: string;
  endText: string;
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
  renderEngine: RenderEngine;
  isDryRun: boolean;
  
  // V5 State
  v5Stage: "INPUT" | "BLUEPRINT" | "RENDER";
  v5Library: any | null;
  v5Blueprint: any | null;
  v5RenderPlan: any | null;

  setInputFolder: (folder: string | null) => void;
  setOutputFolder: (folder: string | null) => void;
  patch: (data: Partial<StudioState>) => void;
}

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

const useStudio = create<StudioState>((set) => ({
  inputFolder: null,
  outputFolder: null,
  title: "福建旅行混剪",
  titleSubtitle: "Travel Video",
  endText: "To be continued!",
  titleBackgroundPath: null,
  endBackgroundPath: null,
  chapterBackgroundMode: "auto_bridge",
  outputName: "travel_video",
  aspectRatio: "16:9",
  quality: "high",
  watermark: "utertop",
  recursive: true,
  chaptersFromDirs: true,
  cover: true,
  renderEngine: "auto",
  isDryRun: false,
  
  v5Stage: "INPUT",
  v5Library: null,
  v5Blueprint: null,
  v5RenderPlan: null,

  setInputFolder: (folder) => set({
    inputFolder: folder,
    v5Stage: "INPUT",
    v5Library: null,
    v5Blueprint: null,
    v5RenderPlan: null,
    titleBackgroundPath: null,
    endBackgroundPath: null,
  }),
  setOutputFolder: (folder) => set({ outputFolder: folder }),
  patch: (state) => set(state),
}));

export function App() {
  const state = useStudio();
  const [result, setResult] = useState<GenerateVideoResult | null>(null);
  const [isRendering, setIsRendering] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);
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
    setHighlightOutput(false);
    setHasPreChecked(false);
    setMaterials([]);
    setSelectedMaterial(null);
    setShowGalleryOverlay(false);
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

  const payload: GenerateVideoPayload = useMemo(
    () => ({
      inputPaths: state.inputFolder ? [state.inputFolder] : [],
      outputDir: state.outputFolder || "",
      title: state.title,
      titleSubtitle: state.titleSubtitle,
      endText: state.endText,
      outputName: state.outputName,
      aspectRatio: state.aspectRatio,
      quality: state.quality,
      watermark: state.watermark,
      recursive: state.recursive,
      chaptersFromDirs: state.chaptersFromDirs,
      cover: state.cover,
      renderEngine: state.renderEngine,
    }),
    [state],
  );

  const commandPreview = useMemo(() => buildCommandPreview(payload), [payload]);

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

  const v5RenderParams: RenderV5Params = useMemo(() => ({
    title: state.title,
    title_subtitle: state.titleSubtitle,
    watermark: state.watermark,
    aspect_ratio: state.aspectRatio,
    quality: state.quality,
    engine: state.renderEngine,
    cover: state.cover,
    fps: 30,
    title_background_path: state.titleBackgroundPath,
    end_background_path: state.endBackgroundPath,
    chapter_background_mode: state.chapterBackgroundMode,
  }), [state.title, state.titleSubtitle, state.watermark, state.aspectRatio, state.quality, state.renderEngine, state.cover, state.titleBackgroundPath, state.endBackgroundPath, state.chapterBackgroundMode]);

  const v5CommandPreview = useMemo(() => buildV5RenderCommandPreview({
    planPath: v5PlanPath || "<render_plan.json>",
    outputPath: v5OutputPath || "<输出视频路径>",
    params: v5RenderParams,
  }), [v5PlanPath, v5OutputPath, v5RenderParams]);

  const activeCommandPreview = state.v5Stage === "RENDER" ? v5CommandPreview : commandPreview;

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
      setToast(`已选择片头背景：${asset.file.name}`);
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
        commandPreview: activeCommandPreview,
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

    const jobId = crypto.randomUUID();
    activeJobRef.current = jobId;
    setIsRendering(true);
    setIsCancelling(false);
    setResult(null);
    setToast(null);
    setHighlightOutput(false);
    setLogs([]);
    setProgress(null);
    setPhase("就绪");
    state.patch({ isDryRun: dryRun });
    const response = await generateVideo({ ...payload, jobId, dryRun });
    if (activeJobRef.current !== jobId) return;
    
    if (response.ok && dryRun) {
      setProgress(100);
      setPhase("预检完成");
      setHasPreChecked(true);
    }
    
    setResult(response);
    setIsRendering(false);
    setIsCancelling(false);
    activeJobRef.current = null;
  }

  async function onStartV5Workflow() {
    if (!state.inputFolder) return;
    if (!state.outputFolder) {
      const warning = "请先选择输出目录。V5.1 会把 media_library / story_blueprint / render_plan 放到输出目录下的 .video_create_project。";
      setToast(warning);
      setHighlightOutput(true);
      return;
    }
    
    setPhase("智能扫描中...");
    setProgress(10);
    try {
      const library = await scanV5(state.inputFolder, v5ProjectDir, state.recursive);
      state.patch({ v5Library: library });
      
      setPhase("规划故事蓝图中...");
      setProgress(40);
      
      const libPath = `${v5ProjectDir}\\media_library.json`;
      const blueprint = await planV5(libPath, `${v5ProjectDir}\\story_blueprint.json`);
      state.patch({ v5Blueprint: blueprint, v5Stage: "BLUEPRINT" });
      
      setPhase("蓝图就绪");
      setProgress(100);
      setToast("故事蓝图已生成，请开始编排您的旅行故事！");
    } catch (error) {
      console.error("V5 Workflow Error:", error);
      setToast(`扫描失败: ${error}`);
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
    setPhase("Stopping");
    setLogs((prev) => [...prev, "Stopping current render job..."]);
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
                片头主标题
                <input value={state.title} onChange={(event) => state.patch({ title: event.target.value })} />
                <div className="background-field-actions">
                  <button type="button" className="background-pick-btn" disabled={!state.inputFolder} onClick={() => ensureBackgroundLibrary({ kind: "title" })}>
                    <ImagePlus size={14} /> 选择片头背景
                  </button>
                  <span className="background-field-hint" title={state.titleBackgroundPath || ""}>
                    {state.titleBackgroundPath ? shortPathName(state.titleBackgroundPath) : "默认：首个素材首帧虚化"}
                  </span>
                </div>
              </label>
              <label>
                片头副标题
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
              <label>
                合成引擎
                <select
                  value={state.renderEngine}
                  onChange={(event) => state.patch({ renderEngine: event.target.value as RenderEngine })}
                >
                  <option value="auto">自动选择</option>
                  <option value="ffmpeg_concat">FFmpeg 快速拼接</option>
                  <option value="moviepy_crossfade">MoviePy 交叉淡化</option>
                </select>
              </label>
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
                    className="primary-action pulse-guidance" 
                    disabled={!state.inputFolder}
                    onClick={onStartV5Workflow}
                  >
                    <Wand2 size={20} /> 开始智能编排
                  </button>
               </div>
            ) : state.v5Stage === "BLUEPRINT" ? (
               <div className="blueprint-editor-container">
                  <SectionTitle icon={<ListChecks size={18} />} title="故事蓝图审核" />
                  <BlueprintEditor 
                    blueprint={state.v5Blueprint} 
                    library={state.v5Library}
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
                       <button className="primary-action pulse-guidance" disabled={!state.outputFolder || isRendering} onClick={() => onGenerate(false)}>
                          <PlayCircle size={24} /> 立即开始最终合成
                       </button>
                       <p className="hint-text">点击上方按钮，启动 V5 渲染引擎合并素材并导出视频。</p>
                    </div>
                  )}

                  {state.v5RenderPlan && (
                    <div className="render-plan-preview">
                       <div className="plan-summary">
                          <span>总时长: {state.v5RenderPlan.total_duration.toFixed(1)}s</span>
                          <span>总片段数: {state.v5RenderPlan.segments.length}</span>
                          {isRendering && progress !== null && <span className="current-progress-text">进度: {progress}%</span>}
                       </div>
                       <div className="segments-timeline">
                          {state.v5RenderPlan.segments.map((seg: V5RenderSegment, idx: number) => {
                            const isCurrent = isRendering && progress !== null && 
                              (progress / 100 * state.v5RenderPlan.total_duration >= seg.start_time) &&
                              (progress / 100 * state.v5RenderPlan.total_duration < seg.end_time);
                            
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

                  <div className="command-box">{activeCommandPreview}</div>
                  
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

function FolderSelector({ inputFolder, setInputFolder }: { inputFolder: string | null; setInputFolder: (folder: string | null) => void }) {
  async function handleSelect() {
    try {
      const selected = await open({
        directory: true,
        multiple: false,
      });
      if (selected && typeof selected === "string") {
        setInputFolder(selected);
      }
    } catch (error) {
      console.error("Failed to select folder:", error);
    }
  }

  return (
    <div className="folder-selector">
      {inputFolder ? (
        <div className="selected-folder">
          <FolderOpen size={24} />
          <div className="folder-info">
            <strong>已选择素材目录</strong>
            <span className="folder-path" title={inputFolder}>{inputFolder}</span>
          </div>
          <button className="folder-change-btn" onClick={handleSelect}>更改目录</button>
        </div>
      ) : (
        <div className="drop-zone" onClick={handleSelect}>
          <ImagePlus size={30} />
          <strong>点击选择照片/视频所在的文件夹</strong>
          <span>脚本将自动扫描该目录下的素材</span>
        </div>
      )}
    </div>
  );
}

function OutputFolderSelector({
  disabled,
  invalid,
  outputFolder,
  setOutputFolder,
}: {
  disabled: boolean;
  invalid: boolean;
  outputFolder: string | null;
  setOutputFolder: (folder: string | null) => void;
}) {
  async function handleSelect() {
    if (disabled) return;

    try {
      const selected = await open({
        directory: true,
        multiple: false,
      });
      if (selected && typeof selected === "string") {
        setOutputFolder(selected);
      }
    } catch (error) {
      console.error("Failed to select output folder:", error);
    }
  }

  return (
    <label className={invalid ? "folder-field invalid" : "folder-field"}>
      输出目录
      <div className="folder-input-row">
        <input
          readOnly
          disabled={disabled}
          title={outputFolder || ""}
          value={outputFolder || (disabled ? "请先选择素材目录" : "请选择输出目录")}
        />
        <button disabled={disabled} type="button" onClick={handleSelect}>
          选择目录
        </button>
      </div>
    </label>
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

function BlueprintEditor({
  blueprint,
  library,
  chapterBackgroundMode,
  onPickSectionBackground,
  onUpdate,
}: {
  blueprint: V5StoryBlueprint;
  library: V5MediaLibrary;
  chapterBackgroundMode: V5ChapterBackgroundMode;
  onPickSectionBackground: (section: V5StorySection) => void;
  onUpdate: (bp: V5StoryBlueprint) => void;
}) {
  if (!blueprint) return null;

  const updateSection = (id: string, updatedSection: V5StorySection) => {
    const newSections = blueprint.sections.map(s => s.section_id === id ? updatedSection : s);
    onUpdate({ ...blueprint, sections: newSections });
  };

  return (
    <div className="blueprint-editor">
      <div className="blueprint-header">
         <input 
           className="blueprint-main-title" 
           value={blueprint.title} 
           onChange={(e) => onUpdate({ ...blueprint, title: e.target.value })} 
         />
      </div>
      <div className="blueprint-sections">
        {blueprint.sections.map((section, idx) => (
          <SectionCard 
            key={section.section_id} 
            section={section} 
            library={library}
            chapterBackgroundMode={chapterBackgroundMode}
            onPickBackground={onPickSectionBackground}
            onUpdate={(upd) => updateSection(section.section_id, upd)}
          />
        ))}
      </div>
    </div>
  );
}

function SectionCard({
  section,
  library,
  chapterBackgroundMode,
  onPickBackground,
  onUpdate,
}: {
  section: V5StorySection;
  library: V5MediaLibrary;
  chapterBackgroundMode: V5ChapterBackgroundMode;
  onPickBackground: (section: V5StorySection) => void;
  onUpdate: (updated: V5StorySection) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const icon = section.section_type === 'city' ? <MapPin size={16} /> : 
               section.section_type === 'date' ? <Calendar size={16} /> : 
               section.section_type === 'scenic_spot' ? <Palmtree size={16} /> : <Layers size={16} />;

  const getAssetById = (id: string) => library?.assets.find(a => a.asset_id === id);
  const bgState = sectionBackgroundLabel(section, chapterBackgroundMode);

  const toggleSection = () => onUpdate({ ...section, enabled: !section.enabled });
  
  const handleTitleChange = (newTitle: string) => onUpdate({ ...section, title: newTitle });

  const updateChild = (childId: string, updatedChild: V5StorySection) => {
    const newChildren = section.children.map(c => c.section_id === childId ? updatedChild : c);
    onUpdate({ ...section, children: newChildren });
  };

  const toggleAsset = (assetId: string) => {
    const newRefs = section.asset_refs.map(ref => 
      ref.asset_id === assetId ? { ...ref, enabled: !ref.enabled } : ref
    );
    onUpdate({ ...section, asset_refs: newRefs });
  };

  return (
    <div className={`section-card ${section.section_type}${!section.enabled ? ' disabled' : ''}`}>
       <div className="section-card-header">
          <div className="section-type-badge">
             {icon}
             <span>{section.section_type.toUpperCase()}</span>
          </div>
          <div className="section-title-wrapper">
            <input 
              className="section-title-input" 
              value={section.title} 
              onChange={(e) => handleTitleChange(e.target.value)}
              placeholder="输入章节标题..."
            />
            <Pencil size={12} className="edit-indicator" />
          </div>
          <div className="section-bg-actions">
             <span className={`section-bg-badge ${bgState.kind}`} title={bgState.description}>背景：{bgState.label}</span>
             <button className="section-bg-btn" type="button" onClick={() => onPickBackground(section)}>选择背景</button>
             {section.background?.user_overridden && (
               <button className="section-bg-btn muted" type="button" onClick={() => onUpdate({ ...section, background: { mode: chapterBackgroundMode, custom_asset_id: null, custom_path: null, user_overridden: false } })}>默认</button>
             )}
          </div>
          <div className="section-actions">
             <button className="icon-btn" onClick={() => setIsExpanded(!isExpanded)} title={isExpanded ? "收起预览" : "放大预览"}>
                {isExpanded ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
             </button>
             <button className="icon-btn" onClick={toggleSection} title={section.enabled ? "禁用此章节" : "启用此章节"}>
                {section.enabled ? <Eye size={16} /> : <EyeOff size={16} />}
             </button>
          </div>
          <div className="section-meta">
             {section.asset_refs.length} 个素材
          </div>
       </div>
       
       {section.enabled && section.children && section.children.length > 0 && (
         <div className="section-children">
            {section.children.map(child => (
              <SectionCard 
                key={child.section_id} 
                section={child} 
                library={library}
                chapterBackgroundMode={chapterBackgroundMode}
                onPickBackground={onPickBackground}
                onUpdate={(upd) => updateChild(child.section_id, upd)}
              />
            ))}
         </div>
       )}

       {section.enabled && section.asset_refs.length > 0 && !section.children.length && (
          <div className={`section-assets-preview${isExpanded ? ' expanded-grid' : ''}`}>
             {section.asset_refs.slice(0, isExpanded ? 50 : 15).map(ref => {
               const asset = getAssetById(ref.asset_id);
               return (
                 <div 
                   key={ref.asset_id} 
                   className={`asset-mini-thumb${!ref.enabled ? ' asset-disabled' : ''}`}
                   title={asset ? `${asset.file.name}\n点击${ref.enabled ? "禁用" : "启用"}` : ""}
                 >
                   <div className="asset-click-area" onClick={() => toggleAsset(ref.asset_id)}>
                     {asset && (getAssetThumbnailPath(asset) || asset.type === 'image') ? (
                       <img src={convertFileSrc(getAssetThumbnailPath(asset) || asset.absolute_path)} alt={asset.file.name} />
                     ) : asset?.type === 'video' ? (
                       <div className="video-placeholder">
                         <PlayCircle size={isExpanded ? 24 : 14} />
                         <span className="video-tag">{asset.file.extension.replace('.', '').toUpperCase()}</span>
                       </div>
                     ) : null}
                   </div>
                   
                   <button 
                     className="asset-toggle-badge" 
                     onClick={(e) => { e.stopPropagation(); toggleAsset(ref.asset_id); }}
                     title={ref.enabled ? "移除素材" : "恢复素材"}
                   >
                     {ref.enabled ? <X size={10} /> : <CheckCircle2 size={10} />}
                   </button>
                 </div>
               );
             })}
             {section.asset_refs.length > (isExpanded ? 50 : 15) && <div className="asset-more">+{section.asset_refs.length - (isExpanded ? 50 : 15)}</div>}
          </div>
       )}
    </div>
  );
}


function updateBlueprintSection(
  blueprint: V5StoryBlueprint,
  sectionId: string,
  updater: (section: V5StorySection) => V5StorySection,
): V5StoryBlueprint {
  return {
    ...blueprint,
    sections: updateSectionList(blueprint.sections || [], sectionId, updater),
    metadata: {
      ...(blueprint.metadata || {}),
      updated_at: new Date().toISOString(),
    },
  };
}

function updateSectionList(
  sections: V5StorySection[],
  sectionId: string,
  updater: (section: V5StorySection) => V5StorySection,
): V5StorySection[] {
  return sections.map((section) => {
    if (section.section_id === sectionId) {
      return updater(section);
    }
    return {
      ...section,
      children: updateSectionList(section.children || [], sectionId, updater),
    };
  });
}

function findSectionById(sections: V5StorySection[] | undefined, sectionId: string): V5StorySection | null {
  for (const section of sections || []) {
    if (section.section_id === sectionId) return section;
    const found = findSectionById(section.children || [], sectionId);
    if (found) return found;
  }
  return null;
}

function withBlueprintMetadata(
  blueprint: V5StoryBlueprint,
  patch: NonNullable<V5StoryBlueprint["metadata"]>,
): V5StoryBlueprint {
  return {
    ...blueprint,
    metadata: {
      ...(blueprint.metadata || {}),
      ...patch,
      updated_at: new Date().toISOString(),
    },
  };
}

function getSelectedBackgroundPath(target: BackgroundPickerTarget, state: StudioState): string | null {
  if (target.kind === "title") return state.titleBackgroundPath;
  if (target.kind === "end") return state.endBackgroundPath;
  const section = findSectionById(state.v5Blueprint?.sections, target.sectionId);
  return section?.background?.custom_path || null;
}

function sectionBackgroundLabel(section: V5StorySection, globalMode: V5ChapterBackgroundMode): { label: string; kind: string; description: string } {
  if (section.background?.user_overridden && section.background.custom_path) {
    return { label: "已自定义", kind: "custom", description: section.background.custom_path };
  }

  if (section.section_type === "scenic_spot") {
    return {
      label: "标题叠加",
      kind: "overlay",
      description: "景点章节默认不插入完整章节卡，而是在首个素材上叠加标题。若手动选择背景，则会升级为完整章节卡。",
    };
  }

  return {
    label: chapterBackgroundModeLabel(globalMode),
    kind: globalMode,
    description: "城市 / 日期 / 普通章节默认使用完整章节卡。",
  };
}

function chapterBackgroundModeLabel(mode: V5ChapterBackgroundMode): string {
  return {
    auto_bridge: "智能过渡",
    auto_first_asset: "章节首图",
    custom_asset: "已自定义",
    plain: "纯色极简",
  }[mode] || mode;
}

function getAssetThumbnailPath(asset: unknown): string | null {
  if (!asset || typeof asset !== "object") return null;
  const maybeAsset = asset as { thumbnail_path?: unknown; thumbnail?: unknown };

  if (typeof maybeAsset.thumbnail_path === "string" && maybeAsset.thumbnail_path.length > 0) {
    return maybeAsset.thumbnail_path;
  }

  if (typeof maybeAsset.thumbnail === "string" && maybeAsset.thumbnail.length > 0) {
    return maybeAsset.thumbnail;
  }

  return null;
}

function formatProgressLine(line: string): string | null {
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

function parseVideoEvent(line: string): VideoEvent | null {
  const trimmed = line.trim();
  if (!trimmed.startsWith("{") || !trimmed.endsWith("}")) return null;
  try {
    const parsed = JSON.parse(trimmed) as VideoEvent;
    return parsed.type ? parsed : null;
  } catch {
    return null;
  }
}

function applyStructuredEvent(
  event: VideoEvent,
  setPhase: React.Dispatch<React.SetStateAction<string>>,
  setProgress: React.Dispatch<React.SetStateAction<number | null>>,
  setLogs: React.Dispatch<React.SetStateAction<string[]>>,
  setMaterials: React.Dispatch<React.SetStateAction<VideoEvent[]>>,
) {
  if (event.type === "media") {
    setMaterials((prev) => [...prev, event]);
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

function formatStructuredEvent(event: VideoEvent): string | null {
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
    return `${event.message || `${event.artifact || "Artifact"} generated`}${event.path ? `: ${event.path}` : ""}`;
  }
  if (event.type === "result") {
    return event.output_path ? `Video generated: ${event.output_path}` : event.message || "Render complete";
  }
  if (event.type === "error") {
    return `Error: ${event.message || "Unknown error"}`;
  }
  if (event.type === "log") {
    return event.message || null;
  }
  return event.message || null;
}

function phaseLabel(phase: string): string {
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

function parseProgress(line: string): { current: number; total: number } | null {
  const match = line.match(/\[(\d+)\/(\d+)\]/);
  if (!match) return null;
  return { current: parseInt(match[1], 10), total: parseInt(match[2], 10) };
}

function detectPhase(line: string): string | null {
  if (line.includes("素材预览")) return "扫描素材";
  if (/\[\d+\/\d+\]\s*(生成片段|缓存命中)/.test(line)) return "生成片段";
  if (line.includes("开始最终合成")) return "合成视频";
  if (line.includes("视频生成完成")) return "完成";
  if (line.includes("封面已生成")) return "生成封面";
  if (line.includes("报告已生成")) return "生成报告";
  return null;
}


function SectionTitle({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="section-title">
      {icon}
      <h2>{title}</h2>
    </div>
  );
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
function BackgroundAssetPicker({
  target,
  library,
  selectedPath,
  loading,
  onSelect,
  onUseDefault,
  onClose,
}: {
  target: BackgroundPickerTarget;
  library: V5MediaLibrary | null;
  selectedPath: string | null;
  loading: boolean;
  onSelect: (asset: V5Asset) => void;
  onUseDefault: () => void;
  onClose: () => void;
}) {
  const visualAssets = useMemo(() => {
    return (library?.assets || [])
      .filter((asset) => (asset.type === "image" || asset.type === "video") && assetStatusState(asset) !== "error")
      .sort((a, b) => a.relative_path.localeCompare(b.relative_path));
  }, [library]);

  const title = target.kind === "title"
    ? "选择片头文案背景"
    : target.kind === "end"
      ? "选择片尾文案背景"
      : `选择章节「${target.sectionTitle}」背景`;

  const defaultHint = target.kind === "title"
    ? "不选择时，默认使用成片第一个素材的首帧/首图作为虚化背景。"
    : target.kind === "end"
      ? "不选择时，默认使用成片最后一个素材的尾帧/末图作为虚化背景。"
      : "不选择时，默认使用章节前后视觉素材生成智能过渡虚化背景；景点章节默认使用首素材标题叠加。";

  const defaultButtonText = target.kind === "section" ? "恢复章节智能背景" : "恢复默认首/尾帧虚化";

  return (
    <div className="background-picker-overlay">
      <div className="background-picker-modal">
        <div className="background-picker-header">
          <div>
            <SectionTitle icon={<ImagePlus size={20} />} title={title} />
            <p>{defaultHint}</p>
          </div>
          <button className="background-picker-close" type="button" onClick={onClose}>
            <X size={18} /> 关闭
          </button>
        </div>

        <div className="background-picker-toolbar">
          <button className="secondary-action" type="button" onClick={onUseDefault}>
            {defaultButtonText}
          </button>
          {selectedPath && (
            <span className="background-picker-selected">当前：{shortPathName(selectedPath)}</span>
          )}
        </div>

        {loading ? (
          <div className="background-picker-empty">正在扫描素材库，请稍候...</div>
        ) : visualAssets.length === 0 ? (
          <div className="background-picker-empty">素材库里还没有可用图片或视频。请先确认素材目录下包含 JPG / PNG / WEBP / MP4 / MOV 等素材。</div>
        ) : (
          <div className="background-picker-grid">
            {visualAssets.map((asset) => {
              const thumb = asset.thumbnail_path || asset.thumbnail || asset.absolute_path;
              const selected = selectedPath === asset.absolute_path;
              return (
                <button
                  type="button"
                  key={asset.asset_id}
                  className={`background-asset-card${selected ? " selected" : ""}`}
                  onClick={() => onSelect(asset)}
                  title={asset.relative_path}
                >
                  <div className="background-asset-thumb">
                    <img src={convertFileSrc(thumb)} alt={asset.file.name} loading="lazy" />
                    {asset.type === "video" && <span className="background-video-badge">VIDEO</span>}
                  </div>
                  <div className="background-asset-info">
                    <strong>{asset.file.name}</strong>
                    <span>{asset.media.width || "?"}x{asset.media.height || "?"}</span>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function shortPathName(path: string | null | undefined): string {
  if (!path) return "";
  return path.split(/[\\/]/).pop() || path;
}

function assetStatusState(asset: V5Asset): string {
  if (!asset.status) return "ready";
  if (typeof asset.status === "string") return asset.status;
  return asset.status.state || "ready";
}

function MaterialGallery({ materials, onSelect, viewMode }: { 
  materials: VideoEvent[]; 
  onSelect: (m: VideoEvent) => void;
  viewMode: "chapter" | "type" | "time";
}) {
  // Group materials based on viewMode
  const groups = useMemo(() => {
    const res: Record<string, VideoEvent[]> = {};
    
    materials.forEach((m) => {
      let key = "其他";
      if (viewMode === "chapter") {
        key = m.chapter || "默认章节";
      } else if (viewMode === "type") {
        key = m.item_kind === "video" ? "视频文件" : m.item_kind === "image" ? "图片素材" : "其他";
      } else if (viewMode === "time") {
        if (m.mtime) {
          const date = new Date(m.mtime * 1000);
          key = `${date.getFullYear()}/${date.getMonth() + 1}/${date.getDate()}`;
        } else {
          key = "未知时间";
        }
      }
      
      if (!res[key]) res[key] = [];
      res[key].push(m);
    });

    // Sort items within groups by filename
    Object.values(res).forEach(list => {
      list.sort((a, b) => (a.display_name || "").localeCompare(b.display_name || ""));
    });

    return res;
  }, [materials, viewMode]);

  return (
    <div className="material-gallery">
      {Object.entries(groups).map(([groupName, items]) => (
        <div className="gallery-section" key={groupName}>
          <div className="gallery-section-header">
            <div className="section-title">
               <span className="dot"></span>
               {groupName}
            </div>
            <span className="count">{items.length} 个项目</span>
          </div>
          <div className="gallery-grid">
            {items.map((item, i) => (
              <div 
                className={`material-card ${item.error ? 'has-error' : ''}`} 
                key={i}
                onClick={() => onSelect(item)}
              >
                <div className="thumbnail-container">
                  {item.thumbnail ? (
                    <img src={convertFileSrc(item.thumbnail)} alt={item.display_name} loading="lazy" />
                  ) : (
                    <div className="thumbnail-placeholder">
                      <FileWarning size={24} />
                    </div>
                  )}
                  {item.item_kind === "video" && (
                    <div className="video-overlay">
                      <div className="play-icon-circle">
                         <PlayCircle size={28} />
                      </div>
                      {item.duration && <span className="duration-tag">{Math.round(item.duration)}s</span>}
                    </div>
                  )}
                  {item.error && (
                    <div className="error-indicator" title={item.error}>
                      <FileWarning size={14} />
                    </div>
                  )}
                </div>
                <div className="material-info">
                  <div className="name-row">
                     <span className="material-name">{item.display_name}</span>
                  </div>
                  <div className="meta-row">
                    {item.width && item.height && (
                      <span className="res-tag">{item.width}x{item.height}</span>
                    )}
                    {item.item_kind === "image" && <span className="type-tag">IMG</span>}
                    {item.item_kind === "video" && <span className="type-tag">MOV</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function PreviewModal({ material, onClose }: { material: VideoEvent; onClose: () => void }) {
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}><X size={24} /></button>
        <div className="preview-container">
          {material.item_kind === "video" ? (
            <video src={convertFileSrc(material.path!)} controls autoPlay />
          ) : (
            <img src={convertFileSrc(material.path!)} alt={material.display_name} />
          )}
        </div>
        <div className="preview-footer">
          <h3>{material.display_name}</h3>
          <p>{material.path}</p>
          <div className="preview-stats">
            {material.width && <span>分辨率: {material.width}x{material.height}</span>}
            {material.duration && <span>时长: {material.duration.toFixed(1)}s</span>}
            {material.error && <span className="error-text">错误: {material.error}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusItem({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className={highlight ? "status-item highlight" : "status-item"}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Feature({ title, text }: { title: string; text: string }) {
  return (
    <article>
      <strong>{title}</strong>
      <p>{text}</p>
    </article>
  );
}



function qualityLabel(quality: Quality): string {
  return {
    draft: "草稿",
    standard: "标准",
    high: "高质量",
  }[quality];
}
