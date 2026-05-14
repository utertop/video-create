import { useEffect, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { Check, FlaskConical, Play, RotateCcw, Save, Sparkles, X } from "lucide-react";
import { previewTitleV5, V5StorySection, V5TitleStyle } from "../lib/engine";

export const TITLE_PRESETS = [
  { value: "cinematic_bold", label: "大片粗体", hint: "高对比白字，适合山川、城市、大场面。" },
  { value: "travel_postcard", label: "旅行明信片", hint: "边框与纸感，适合旅拍、美食、古镇。" },
  { value: "playful_pop", label: "活力弹跳", hint: "圆润鲜活，适合宠物、日常、轻松内容。" },
  { value: "impact_flash", label: "冲击闪切", hint: "强对比和压迫感，适合运动、滑雪、转场。" },
  { value: "minimal_editorial", label: "极简杂志", hint: "克制排版，适合人物、摄影集、安静叙事。" },
  { value: "nature_documentary", label: "自然纪录", hint: "自然色和厚重感，适合森林、雪山、湖泊。" },
  { value: "romantic_soft", label: "浪漫柔光", hint: "柔和粉调，适合婚礼、生日、派对。" },
  { value: "tech_future", label: "科技未来", hint: "冷色霓虹，适合科技、城市夜景、未来感。" },
] as const;

export const TITLE_MOTIONS = [
  { value: "fade_slide_up", label: "淡入上移", hint: "稳妥自然，适合多数章节。" },
  { value: "soft_zoom_in", label: "柔和推近", hint: "有轻微呼吸感，适合旅行和人物。" },
  { value: "pop_bounce", label: "弹跳出现", hint: "轻快活泼，适合宠物和日常。" },
  { value: "quick_zoom_punch", label: "快速冲击", hint: "节奏强，适合运动和高能片段。" },
  { value: "slow_fade_zoom", label: "慢速淡入推近", hint: "舒展沉稳，适合自然风景。" },
  { value: "fade_only", label: "纯淡入淡出", hint: "最克制，适合极简和纪实。" },
] as const;

const RECOMMENDED_COMBOS = [
  { name: "旅行记录", preset: "travel_postcard", motion: "soft_zoom_in" },
  { name: "自然风景", preset: "nature_documentary", motion: "slow_fade_zoom" },
  { name: "宠物日常", preset: "playful_pop", motion: "pop_bounce" },
  { name: "运动高能", preset: "impact_flash", motion: "quick_zoom_punch" },
  { name: "安静纪实", preset: "minimal_editorial", motion: "fade_only" },
  { name: "城市科技", preset: "tech_future", motion: "quick_zoom_punch" },
] as const;

const PREVIEW_BACKGROUNDS = [
  { value: "travel", label: "旅行" },
  { value: "nature", label: "自然" },
  { value: "city", label: "城市" },
  { value: "clean", label: "浅色" },
] as const;

export const DEFAULT_TITLE_STYLE: Required<Pick<V5TitleStyle, "preset" | "motion">> = {
  preset: "cinematic_bold",
  motion: "fade_slide_up",
};

export function normalizeTitleStyle(style: V5TitleStyle | null | undefined): Required<Pick<V5TitleStyle, "preset" | "motion">> {
  return {
    preset: style?.preset || DEFAULT_TITLE_STYLE.preset,
    motion: style?.motion || DEFAULT_TITLE_STYLE.motion,
  };
}

export function titlePresetLabel(value: string | undefined): string {
  return TITLE_PRESETS.find((option) => option.value === value)?.label || value || TITLE_PRESETS[0].label;
}

export function titleMotionLabel(value: string | undefined): string {
  return TITLE_MOTIONS.find((option) => option.value === value)?.label || value || TITLE_MOTIONS[0].label;
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
            <strong>{titlePresetLabel(normalized.preset)} + {titleMotionLabel(normalized.motion)}</strong>
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
  const [sampleTitle, setSampleTitle] = useState(currentSection?.title || "雪山徒步");
  const [replayKey, setReplayKey] = useState(0);
  const [background, setBackground] = useState("travel");
  const [notice, setNotice] = useState("选择风格和动效后，可以先播放确认，再应用到蓝图。");
  const [realPreviewPath, setRealPreviewPath] = useState<string | null>(null);
  const [isRenderingPreview, setIsRenderingPreview] = useState(false);
  const normalized = normalizeTitleStyle(style);

  useEffect(() => {
    setStyle(normalizeTitleStyle(initialStyle));
    setSampleTitle(currentSection?.title || "雪山徒步");
    setRealPreviewPath(null);
    setReplayKey((value) => value + 1);
  }, [currentSection?.section_id, initialStyle?.preset, initialStyle?.motion]);

  const patchStyle = (patch: Partial<V5TitleStyle>) => {
    setStyle((previous) => ({ ...normalizeTitleStyle(previous), ...patch }));
    setRealPreviewPath(null);
    setReplayKey((value) => value + 1);
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
            <h3>组合风格和动效，满意后再应用到蓝图</h3>
          </div>
          <button className="title-preview-close" type="button" onClick={onClose}>
            <X size={18} /> 关闭
          </button>
        </header>

        <main className="title-lab-body">
          <aside className="title-lab-panel">
            <div className="title-lab-panel-title">文字风格</div>
            <div className="title-lab-combo-grid">
              {RECOMMENDED_COMBOS.map((combo) => (
                <button
                  key={combo.name}
                  type="button"
                  className={normalized.preset === combo.preset && normalized.motion === combo.motion ? "active" : ""}
                  onClick={() => patchStyle({ preset: combo.preset, motion: combo.motion })}
                >
                  {combo.name}
                </button>
              ))}
            </div>
            <div className="title-lab-option-list">
              {TITLE_PRESETS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={normalized.preset === option.value ? "active" : ""}
                  onClick={() => patchStyle({ preset: option.value })}
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
              当前组合：{titlePresetLabel(normalized.preset)} + {titleMotionLabel(normalized.motion)}
            </div>
            <div className="title-lab-notice">{notice}</div>
          </section>

          <aside className="title-lab-panel">
            <div className="title-lab-panel-title">入场动效</div>
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
                <Check size={15} /> 应用到当前章节
              </button>
              <button
                type="button"
                disabled={!currentSection}
                onClick={() => applyAndNotice(() => onApplySameType(normalized), "已应用到同类章节。")}
              >
                <Check size={15} /> 应用到同类章节
              </button>
              <button type="button" onClick={() => applyAndNotice(() => onApplyAll(normalized), "已应用到全部章节。")}>
                <Check size={15} /> 应用到全部章节
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
