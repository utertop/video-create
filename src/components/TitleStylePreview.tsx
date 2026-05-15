import { useEffect, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { Check, FlaskConical, Play, RotateCcw, Save, Sparkles, X } from "lucide-react";
import { previewTitleV5, V5StorySection, V5TitleStyle } from "../lib/engine";

export const TITLE_PRESETS = [
  { value: "cinematic_bold", label: "电影感", motion: "cinematic_reveal", hint: "厚重白字、暗场遮罩和电影级入场，适合山川、城市、大场面。" },
  { value: "travel_postcard", label: "旅游明信片", motion: "postcard_drift", hint: "手写感、纸张边框和温暖漂移，适合旅行、美食、古镇。" },
  { value: "playful_pop", label: "活泼弹跳", motion: "playful_bounce", hint: "贴纸、粗描边和轻快弹出，适合宠物、日常、轻松内容。" },
  { value: "impact_flash", label: "冲击标题", motion: "impact_slam", hint: "速度线、厚描边和冲击入场，适合运动、雪崩、高能片段。" },
  { value: "minimal_editorial", label: "极简高级", motion: "editorial_fade", hint: "留白、细字重和杂志排版，适合建筑、摄影、城市夜色。" },
  { value: "documentary_lower_third", label: "记录片字幕条", motion: "lower_third_slide", hint: "地点/时间字幕条，信息清晰，适合纪实、人物、地点说明。" },
  { value: "handwritten_note", label: "手写贴纸", motion: "handwritten_draw", hint: "手写线条、涂鸦和贴纸感，适合 Vlog、海边、生活记录。" },
  { value: "neon_night", label: "霓虹夜景", motion: "neon_flicker", hint: "霓虹发光和夜景氛围，适合城市夜景、潮流、科技感。" },
  { value: "film_subtitle", label: "胶片字幕", motion: "film_burn", hint: "胶片边码、颗粒和温柔字幕，适合回忆、日落、文艺片段。" },
  { value: "route_marker", label: "地图路线标记", motion: "route_trace", hint: "路线箭头和定位标记，适合行程、路线、Day 标题。" },
] as const;

export const TITLE_MOTIONS = [
  { value: "cinematic_reveal", label: "电影揭幕", hint: "暗场浮现、轻微推近，适配电影感。" },
  { value: "postcard_drift", label: "明信片漂移", hint: "纸张轻落和温柔漂移，适配旅游明信片。" },
  { value: "playful_bounce", label: "贴纸弹跳", hint: "轻快弹入，适配活泼弹跳。" },
  { value: "impact_slam", label: "冲击砸入", hint: "快速压入和短促闪白，适配冲击标题。" },
  { value: "editorial_fade", label: "杂志淡入", hint: "克制淡入和轻微排版滑动，适配极简高级。" },
  { value: "lower_third_slide", label: "字幕条滑入", hint: "下三分之一信息条滑入，适配记录片字幕条。" },
  { value: "handwritten_draw", label: "手写描绘", hint: "像手写线条被画出来，适配手写贴纸。" },
  { value: "neon_flicker", label: "霓虹闪烁", hint: "轻微霓虹点亮，适配夜景标题。" },
  { value: "film_burn", label: "胶片显影", hint: "颗粒、显影和温柔淡出，适配胶片字幕。" },
  { value: "route_trace", label: "路线绘制", hint: "路线被画出后标题出现，适配地图路线标记。" },
  { value: "static_hold", label: "静态定帧", hint: "无入场动画，适配封面、封尾和静态导出。" },
] as const;

const RECOMMENDED_COMBOS = [
  { name: "旅行记录", preset: "travel_postcard", motion: "postcard_drift" },
  { name: "电影开场", preset: "cinematic_bold", motion: "cinematic_reveal" },
  { name: "高能运动", preset: "impact_flash", motion: "impact_slam" },
  { name: "安静纪实", preset: "documentary_lower_third", motion: "lower_third_slide" },
  { name: "夜景潮流", preset: "neon_night", motion: "neon_flicker" },
  { name: "行程路线", preset: "route_marker", motion: "route_trace" },
] as const;

const PREVIEW_BACKGROUNDS = [
  { value: "travel", label: "旅行" },
  { value: "nature", label: "自然" },
  { value: "city", label: "城市" },
  { value: "clean", label: "浅色" },
] as const;

export const DEFAULT_TITLE_STYLE: Required<Pick<V5TitleStyle, "preset" | "motion">> = {
  preset: "cinematic_bold",
  motion: "cinematic_reveal",
};

export function normalizeTitleStyle(style: V5TitleStyle | null | undefined): Required<Pick<V5TitleStyle, "preset" | "motion">> {
  const preset = normalizePreset(style?.preset);
  return {
    preset,
    motion: normalizeMotion(style?.motion, preset),
  };
}

export function titlePresetLabel(value: string | undefined): string {
  return titleTemplateForPreset(value).label;
}

export function titleMotionLabel(value: string | undefined): string {
  return TITLE_MOTIONS.find((option) => option.value === value)?.label || value || TITLE_MOTIONS[0].label;
}

export function titleTemplateForPreset(value: string | undefined) {
  return TITLE_PRESETS.find((option) => option.value === normalizePreset(value)) || TITLE_PRESETS[0];
}

export function titleTemplateLabel(style: V5TitleStyle | null | undefined): string {
  const normalized = normalizeTitleStyle(style);
  const template = titleTemplateForPreset(normalized.preset);
  if (normalized.motion === template.motion) return template.label;
  return `${template.label} / ${titleMotionLabel(normalized.motion)}`;
}

function normalizePreset(value: string | undefined): string {
  const aliases: Record<string, string> = {
    nature_documentary: "documentary_lower_third",
    romantic_soft: "handwritten_note",
    tech_future: "neon_night",
  };
  const raw = aliases[value || ""] || value || DEFAULT_TITLE_STYLE.preset;
  return TITLE_PRESETS.some((option) => option.value === raw) ? raw : DEFAULT_TITLE_STYLE.preset;
}

function normalizeMotion(value: string | undefined, preset: string): string {
  const aliases: Record<string, string> = {
    fade_slide_up: "cinematic_reveal",
    soft_zoom_in: "postcard_drift",
    pop_bounce: "playful_bounce",
    quick_zoom_punch: "impact_slam",
    slow_fade_zoom: "film_burn",
    fade_only: "editorial_fade",
  };
  const raw = value ? aliases[value] || value : titleTemplateForPreset(preset).motion;
  if (TITLE_MOTIONS.some((option) => option.value === raw)) return raw;
  return titleTemplateForPreset(preset).motion;
}

export function TitlePreviewStage({
  title,
  subtitle,
  style,
  replayKey = 0,
  compact = false,
  background = "travel",
}: {
  title: string;
  subtitle?: string | null;
  style: V5TitleStyle;
  replayKey?: number;
  compact?: boolean;
  background?: string;
}) {
  const normalized = normalizeTitleStyle(style);

  return (
    <div className={`title-preview-stage${compact ? " compact" : ""}`}>
      <div className={`title-preview-backdrop preset-${normalized.preset} bg-${background || "travel"}`} />
      <div
        key={`${normalized.preset}-${normalized.motion}-${replayKey}`}
        className={`title-preview-layer preset-${normalized.preset} motion-${normalized.motion}`}
      >
        <span className="title-preview-kicker">{titlePresetLabel(normalized.preset)}</span>
        <strong>{title || "章节标题"}</strong>
        {subtitle && <small>{subtitle}</small>}
      </div>
    </div>
  );
}

export function TitleStylePreviewDialog({
  section,
  style,
  onClose,
}: {
  section: V5StorySection;
  style: V5TitleStyle;
  onClose: () => void;
}) {
  const [replayKey, setReplayKey] = useState(0);
  const normalized = normalizeTitleStyle(style);

  return (
    <div className="title-preview-overlay" onClick={onClose}>
      <div className="title-preview-dialog" onClick={(event) => event.stopPropagation()}>
        <header className="title-preview-dialog-header">
          <div>
            <span>章节文字预览</span>
            <h3>{section.title || "章节标题"}</h3>
          </div>
          <button className="title-preview-close" type="button" onClick={onClose}>
            <X size={18} /> 关闭
          </button>
        </header>

        <TitlePreviewStage title={section.title} subtitle={section.subtitle} style={normalized} replayKey={replayKey} />

        <footer className="title-preview-dialog-footer">
          <div>
            <strong>{titleTemplateLabel(normalized)}</strong>
            <span>这是前端即时预览，用来快速判断方向；最终成片会由渲染引擎生成。</span>
          </div>
          <button className="secondary-action" type="button" onClick={() => setReplayKey((value) => value + 1)}>
            <RotateCcw size={16} /> 重播
          </button>
        </footer>
      </div>
    </div>
  );
}

export function TitleStyleLab({
  currentSection,
  initialStyle,
  onApplyCurrent,
  onApplySameType,
  onApplyAll,
  onSaveDefault,
  onClose,
}: {
  currentSection: V5StorySection | null;
  initialStyle: V5TitleStyle;
  onApplyCurrent: (style: V5TitleStyle) => void;
  onApplySameType: (style: V5TitleStyle) => void;
  onApplyAll: (style: V5TitleStyle) => void;
  onSaveDefault: (style: V5TitleStyle) => void;
  onClose: () => void;
}) {
  const [style, setStyle] = useState<V5TitleStyle>(normalizeTitleStyle(initialStyle));
  const [sampleTitle, setSampleTitle] = useState(currentSection?.title || "厦门漫游");
  const [replayKey, setReplayKey] = useState(0);
  const [background, setBackground] = useState("travel");
  const [notice, setNotice] = useState("选择完整模板包后，可以继续微调动效，再应用到蓝图。");
  const [realPreviewPath, setRealPreviewPath] = useState<string | null>(null);
  const [isRenderingPreview, setIsRenderingPreview] = useState(false);
  const normalized = normalizeTitleStyle(style);

  useEffect(() => {
    setStyle(normalizeTitleStyle(initialStyle));
    setSampleTitle(currentSection?.title || "厦门漫游");
    setRealPreviewPath(null);
    setReplayKey((value) => value + 1);
  }, [currentSection?.section_id, initialStyle?.preset, initialStyle?.motion]);

  const patchStyle = (patch: Partial<V5TitleStyle>) => {
    setStyle((previous) => ({ ...normalizeTitleStyle(previous), ...patch }));
    setRealPreviewPath(null);
    setReplayKey((value) => value + 1);
  };

  const applyTemplate = (preset: string, motion: string) => {
    patchStyle({ preset, motion });
  };

  const applyAndNotice = (action: () => void, message: string) => {
    action();
    setNotice(message);
  };

  const renderRealPreview = async () => {
    setIsRenderingPreview(true);
    setNotice("正在调用真实渲染引擎生成 3 秒低清预览...");
    try {
      const outputPath = await previewTitleV5({
        title: sampleTitle || currentSection?.title || "章节标题",
        subtitle: currentSection?.subtitle,
        style: normalized,
        background,
      });
      setRealPreviewPath(outputPath);
      setNotice("真实引擎预览已生成。这个效果会比上方即时预览更接近最终成片。");
    } catch (error) {
      setNotice(`真实预览生成失败：${error}`);
    } finally {
      setIsRenderingPreview(false);
    }
  };

  return (
    <div className="title-lab-overlay">
      <div className="title-lab-shell">
        <header className="title-lab-header">
          <div>
            <span><FlaskConical size={16} /> 文字动效实验室</span>
            <h3>选择有质感的标题模板包，满意后应用到蓝图</h3>
          </div>
          <button className="title-preview-close" type="button" onClick={onClose}>
            <X size={18} /> 关闭
          </button>
        </header>

        <main className="title-lab-body">
          <aside className="title-lab-panel">
            <div className="title-lab-panel-title">推荐组合</div>
            <div className="title-lab-combo-grid">
              {RECOMMENDED_COMBOS.map((combo) => (
                <button
                  key={combo.name}
                  type="button"
                  className={normalized.preset === combo.preset && normalized.motion === combo.motion ? "active" : ""}
                  onClick={() => applyTemplate(combo.preset, combo.motion)}
                >
                  {combo.name}
                </button>
              ))}
            </div>
            <div className="title-lab-panel-title">标题模板包</div>
            <div className="title-lab-option-list">
              {TITLE_PRESETS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={normalized.preset === option.value ? "active" : ""}
                  onClick={() => applyTemplate(option.value, option.motion)}
                >
                  <strong>{option.label}</strong>
                  <span>{option.hint}</span>
                </button>
              ))}
            </div>
          </aside>

          <section className="title-lab-stage-panel">
            <div className="title-lab-stage-toolbar">
              <label>
                测试标题
                <input
                  value={sampleTitle}
                  onChange={(event) => {
                    setSampleTitle(event.target.value);
                    setRealPreviewPath(null);
                  }}
                />
              </label>
              <div className="title-lab-bg-switcher" aria-label="预览背景">
                {PREVIEW_BACKGROUNDS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={background === option.value ? "active" : ""}
                    onClick={() => {
                      setBackground(option.value);
                      setRealPreviewPath(null);
                      setReplayKey((value) => value + 1);
                    }}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
              <button className="secondary-action" type="button" onClick={() => setReplayKey((value) => value + 1)}>
                <Play size={16} /> 播放
              </button>
              <button className="secondary-action" type="button" disabled={isRenderingPreview} onClick={renderRealPreview}>
                <Sparkles size={16} /> {isRenderingPreview ? "生成中" : "真实预览"}
              </button>
            </div>
            <div className="title-lab-preview-stack">
              <TitlePreviewStage
                title={sampleTitle}
                subtitle={currentSection?.subtitle}
                style={normalized}
                replayKey={replayKey}
                background={background}
              />
              {realPreviewPath && (
                <div className="title-lab-real-preview">
                  <div className="title-lab-real-preview-header">
                    <strong>真实引擎低清预览</strong>
                    <span>MoviePy 生成</span>
                  </div>
                  <video key={realPreviewPath} src={convertFileSrc(realPreviewPath)} controls autoPlay muted loop />
                </div>
              )}
            </div>
            <div className="title-lab-current-combo">
              <Sparkles size={16} />
              当前模板：{titleTemplateLabel(normalized)}
            </div>
            <div className="title-lab-notice">{notice}</div>
          </section>

          <aside className="title-lab-panel">
            <div className="title-lab-panel-title">动效覆盖</div>
            <div className="title-lab-option-list compact">
              {TITLE_MOTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={normalized.motion === option.value ? "active" : ""}
                  onClick={() => patchStyle({ motion: option.value })}
                >
                  <strong>{option.label}</strong>
                  <span>{option.hint}</span>
                </button>
              ))}
            </div>
            <div className="title-lab-apply-card">
              <strong>应用范围</strong>
              <button
                type="button"
                disabled={!currentSection}
                onClick={() => applyAndNotice(() => onApplyCurrent(normalized), "已应用到当前章节。")}
              >
                <Check size={15} /> 应用当前章节
              </button>
              <button
                type="button"
                disabled={!currentSection}
                onClick={() => applyAndNotice(() => onApplySameType(normalized), "已应用到同类章节。")}
              >
                <Check size={15} /> 应用同类章节
              </button>
              <button type="button" onClick={() => applyAndNotice(() => onApplyAll(normalized), "已应用到全部章节。")}>
                <Check size={15} /> 应用全部章节
              </button>
              <button type="button" onClick={() => applyAndNotice(() => onSaveDefault(normalized), "已保存为默认组合，后续打开实验室会优先使用。")}>
                <Save size={15} /> 保存为默认组合
              </button>
            </div>
          </aside>
        </main>
      </div>
    </div>
  );
}
