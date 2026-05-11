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
  TriangleAlert,
  X,
  Wand2,
} from "lucide-react";
import { useMemo, useState, useEffect, useRef } from "react";
import { create } from "zustand";
import { open } from "@tauri-apps/plugin-dialog";
import { listen } from "@tauri-apps/api/event";
import {
  AspectRatio,
  GenerateVideoPayload,
  GenerateVideoResult,
  Quality,
  RenderEngine,
  buildCommandPreview,
  generateVideo,
  openInExplorer,
} from "./lib/engine";

interface StudioState {
  inputFolder: string | null;
  outputFolder: string | null;
  title: string;
  titleSubtitle: string;
  endText: string;
  outputName: string;
  aspectRatio: AspectRatio;
  quality: Quality;
  watermark: string;
  recursive: boolean;
  chaptersFromDirs: boolean;
  cover: boolean;
  renderEngine: RenderEngine;
  setInputFolder: (folder: string | null) => void;
  setOutputFolder: (folder: string | null) => void;
  patch: (state: Partial<Omit<StudioState, "setInputFolder" | "setOutputFolder" | "patch">>) => void;
}

const useStudio = create<StudioState>((set) => ({
  inputFolder: null,
  outputFolder: null,
  title: "福建旅行混剪",
  titleSubtitle: "Travel Video",
  endText: "To be continued!",
  outputName: "travel_video",
  aspectRatio: "16:9",
  quality: "high",
  watermark: "PangBo Travel",
  recursive: true,
  chaptersFromDirs: true,
  cover: true,
  renderEngine: "auto",
  setInputFolder: (folder) => set({ inputFolder: folder }),
  setOutputFolder: (folder) => set({ outputFolder: folder }),
  patch: (state) => set(state),
}));

export function App() {
  const state = useStudio();
  const [result, setResult] = useState<GenerateVideoResult | null>(null);
  const [isRendering, setIsRendering] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [progress, setProgress] = useState<number | null>(null);
  const [phase, setPhase] = useState("就绪");
  const [toast, setToast] = useState<string | null>(null);
  const [highlightOutput, setHighlightOutput] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  const [activeNav, setActiveNav] = useState("workspace");

  function scrollToSection(id: string) {
    setActiveNav(id);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  useEffect(() => {
    const unlisten = listen<string>("video-progress", (event) => {
      const raw = event.payload;

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

  async function onGenerate() {
    if (!state.inputFolder || !state.outputFolder) {
      const warning = !state.inputFolder ? "请先选择素材目录。" : "请先选择输出目录。";
      setResult({
        ok: false,
        message: warning,
        commandPreview,
      });
      setToast(warning);
      setHighlightOutput(Boolean(state.inputFolder && !state.outputFolder));
      return;
    }

    setIsRendering(true);
    setResult(null);
    setToast(null);
    setHighlightOutput(false);
    setLogs([]);
    setProgress(null);
    setPhase("就绪");
    const response = await generateVideo(payload);
    setResult(response);
    setIsRendering(false);
  }

  return (
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
        {toast && <Toast message={toast} onClose={() => setToast(null)} />}
        <header className="topbar">
          <div>
            <p className="eyebrow">GUI MVP</p>
            <h1>Turn Moments into Motion.</h1>
          </div>
          <button className="primary-action" disabled={isRendering || !state.inputFolder} onClick={onGenerate}>
            {isRendering ? <Wand2 className="spin" size={18} /> : <Play size={18} />}
            {isRendering ? "生成中" : "生成视频"}
          </button>
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
              </label>
              <label>
                片头副标题
                <input value={state.titleSubtitle} onChange={(event) => state.patch({ titleSubtitle: event.target.value })} />
              </label>
              <label>
                片尾文字
                <input value={state.endText} onChange={(event) => state.patch({ endText: event.target.value })} />
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
            <SectionTitle icon={<FileVideo size={18} />} title="任务预览" />
            <div className="command-box">{commandPreview}</div>
            
            {(isRendering || logs.length > 0) && (
              <>
                {progress !== null && <ProgressBar percent={progress} phase={phase} />}
                <div className="log-viewer">
                  {logs.length === 0 ? <div className="log-placeholder">正在启动引擎...</div> : logs.map((log, i) => <div key={i}>{log}</div>)}
                  <div ref={logEndRef} />
                </div>
              </>
            )}

            <div className="status-strip">
              <StatusItem label="输入目录" value={state.inputFolder ? state.inputFolder.split(/[/\\]/).pop() || "已选择" : "未选择"} />
              <StatusItem label="当前画幅" value={state.aspectRatio} />
              <StatusItem label="渲染质量" value={qualityLabel(state.quality)} />
              <StatusItem label="封面" value={state.cover ? "开启" : "关闭"} />
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
        <strong>{result.ok ? "生成完成" : "生成失败"}</strong>
      </div>
      <p className="result-card-message">{result.message}</p>
      {result.ok && result.outputPath && (
        <div className="result-card-actions">
          <button className="result-open-btn" onClick={() => openInExplorer(result.outputPath!)}>
            <ExternalLink size={15} />
            打开输出目录
          </button>
        </div>
      )}
    </div>
  );
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return (
    <div className="toast warning" role="status">
      <div>
        <strong>缺少生成参数</strong>
        <span>{message}</span>
      </div>
      <button aria-label="关闭提示" type="button" onClick={onClose}>
        <X size={16} />
      </button>
    </div>
  );
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

function ProgressBar({ percent, phase }: { percent: number; phase: string }) {
  return (
    <div className="progress-container">
      <div className="progress-header">
        <span className="progress-phase">{phase}</span>
        <span className="progress-percent">{Math.round(percent)}%</span>
      </div>
      <div className="progress-track">
        <div
          className={`progress-fill${percent >= 100 ? " complete" : ""}`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
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

function StatusItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
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
