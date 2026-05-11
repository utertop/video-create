import {
  CheckCircle2,
  Clapperboard,
  FileVideo,
  FolderOpen,
  Gauge,
  ImagePlus,
  Play,
  Settings2,
  Sparkles,
  Wand2,
} from "lucide-react";
import { useMemo, useState } from "react";
import { create } from "zustand";
import { open } from "@tauri-apps/plugin-dialog";
import {
  AspectRatio,
  GenerateVideoPayload,
  GenerateVideoResult,
  Quality,
  RenderEngine,
  buildCommandPreview,
  generateVideo,
} from "./lib/engine";

interface StudioState {
  inputFolder: string | null;
  title: string;
  outputName: string;
  aspectRatio: AspectRatio;
  quality: Quality;
  watermark: string;
  recursive: boolean;
  chaptersFromDirs: boolean;
  cover: boolean;
  renderEngine: RenderEngine;
  setInputFolder: (folder: string | null) => void;
  patch: (state: Partial<Omit<StudioState, "setInputFolder" | "patch">>) => void;
}

const useStudio = create<StudioState>((set) => ({
  inputFolder: null,
  title: "福建旅行混剪",
  outputName: "travel_video",
  aspectRatio: "16:9",
  quality: "high",
  watermark: "PangBo Travel",
  recursive: true,
  chaptersFromDirs: true,
  cover: true,
  renderEngine: "auto",
  setInputFolder: (folder) => set({ inputFolder: folder }),
  patch: (state) => set(state),
}));

export function App() {
  const state = useStudio();
  const [result, setResult] = useState<GenerateVideoResult | null>(null);
  const [isRendering, setIsRendering] = useState(false);

  const payload: GenerateVideoPayload = useMemo(
    () => ({
      inputPaths: state.inputFolder ? [state.inputFolder] : [],
      title: state.title,
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
    setIsRendering(true);
    setResult(null);
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
          <a className="nav-item active" href="#workspace">
            <ImagePlus size={18} />
            素材
          </a>
          <a className="nav-item" href="#settings">
            <Settings2 size={18} />
            参数
          </a>
          <a className="nav-item" href="#engine">
            <Gauge size={18} />
            引擎
          </a>
          <a className="nav-item" href="#ai">
            <Sparkles size={18} />
            AI 蓝图
          </a>
        </nav>
      </aside>

      <section className="workspace" id="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">GUI MVP</p>
            <h1>把 V3 脚本装进一个真正好用的桌面工作台</h1>
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
                视频标题
                <input value={state.title} onChange={(event) => state.patch({ title: event.target.value })} />
              </label>
              <label>
                输出文件名
                <input value={state.outputName} onChange={(event) => state.patch({ outputName: event.target.value })} />
              </label>
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
            <div className="status-strip">
              <StatusItem label="输入目录" value={state.inputFolder ? state.inputFolder.split(/[/\\]/).pop() || "已选择" : "未选择"} />
              <StatusItem label="当前画幅" value={state.aspectRatio} />
              <StatusItem label="渲染质量" value={qualityLabel(state.quality)} />
              <StatusItem label="封面" value={state.cover ? "开启" : "关闭"} />
            </div>
            {result && (
              <div className={result.ok ? "result success" : "result warning"}>
                <CheckCircle2 size={18} />
                <span>{result.message}</span>
              </div>
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
        <div className="selected-folder" style={{ display: "flex", alignItems: "center", gap: "1rem", padding: "1rem", background: "var(--bg-muted)", borderRadius: "8px" }}>
          <FolderOpen size={24} />
          <div className="folder-info" style={{ flex: 1, overflow: "hidden" }}>
            <strong style={{ display: "block", marginBottom: "0.25rem" }}>已选择素材目录</strong>
            <span className="folder-path" title={inputFolder} style={{ display: "block", fontSize: "0.875rem", opacity: 0.7, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{inputFolder}</span>
          </div>
          <button style={{ padding: "0.5rem 1rem", cursor: "pointer" }} onClick={handleSelect}>更改目录</button>
        </div>
      ) : (
        <div className="drop-zone" onClick={handleSelect} style={{ cursor: "pointer" }}>
          <ImagePlus size={30} />
          <strong>点击选择照片/视频所在的文件夹</strong>
          <span>脚本将自动扫描该目录下的素材</span>
        </div>
      )}
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

function formatSize(size: number): string {
  if (size < 1024 * 1024) {
    return `${Math.max(1, Math.round(size / 1024))} KB`;
  }

  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function qualityLabel(quality: Quality): string {
  return {
    draft: "草稿",
    standard: "标准",
    high: "高质量",
  }[quality];
}
