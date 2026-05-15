import { useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import {
  Calendar,
  CheckCircle2,
  Eye,
  EyeOff,
  Layers,
  MapPin,
  Maximize2,
  Minimize2,
  Palmtree,
  Pencil,
  PlayCircle,
  Sparkles,
  X,
} from "lucide-react";
import {
  V5ChapterBackgroundMode,
  V5MediaLibrary,
  V5StoryBlueprint,
  V5StorySection,
  V5TitleStyle,
} from "../lib/engine";
import { updateBlueprintSection } from "../lib/blueprint";
import {
  normalizeTitleStyle,
  TITLE_MOTIONS,
  TITLE_PRESETS,
  titleTemplateLabel,
  TitleStyleLab,
  TitleStylePreviewDialog,
} from "./TitleStylePreview";

export function BlueprintEditor({
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
  const [previewSection, setPreviewSection] = useState<V5StorySection | null>(null);
  const [isLabOpen, setIsLabOpen] = useState(false);
  const [labSection, setLabSection] = useState<V5StorySection | null>(null);

  const updateSection = (id: string, updatedSection: V5StorySection) => {
    onUpdate(updateBlueprintSection(blueprint, id, () => updatedSection));
  };

  const openLab = (section: V5StorySection | null) => {
    setLabSection(section);
    setIsLabOpen(true);
  };

  const applyTitleStyle = (
    style: V5TitleStyle,
    predicate: (section: V5StorySection) => boolean,
  ) => {
    onUpdate({
      ...blueprint,
      sections: applyTitleStyleToSections(blueprint.sections || [], style, predicate),
      metadata: {
        ...(blueprint.metadata || {}),
        updated_at: new Date().toISOString(),
      },
    });
  };

  const applyToCurrent = (style: V5TitleStyle) => {
    if (!labSection) return;
    applyTitleStyle(style, (section) => section.section_id === labSection.section_id);
    setLabSection({ ...labSection, title_style: { ...(labSection.title_style || {}), ...style } });
  };

  const applyToSameType = (style: V5TitleStyle) => {
    if (!labSection) return;
    applyTitleStyle(style, (section) => section.section_type === labSection.section_type);
    setLabSection({ ...labSection, title_style: { ...(labSection.title_style || {}), ...style } });
  };

  const applyToAll = (style: V5TitleStyle) => {
    applyTitleStyle(style, () => true);
    if (labSection) setLabSection({ ...labSection, title_style: { ...(labSection.title_style || {}), ...style } });
  };

  const saveDefaultTitleStyle = (style: V5TitleStyle) => {
    onUpdate({
      ...blueprint,
      metadata: {
        ...(blueprint.metadata || {}),
        default_title_style: normalizeTitleStyle(style),
        updated_at: new Date().toISOString(),
      },
    });
  };

  return (
    <div className="blueprint-editor">
      <div className="blueprint-header">
        <div className="blueprint-title-row">
          <input
            className="blueprint-main-title"
            value={blueprint.title}
            onChange={(e) => onUpdate({ ...blueprint, title: e.target.value })}
          />
          <button className="secondary-action title-lab-entry" type="button" onClick={() => openLab(firstSection(blueprint.sections))}>
            <Sparkles size={16} /> 文字动效实验室
          </button>
        </div>
      </div>
      <div className="blueprint-sections">
        {blueprint.sections.map((section) => (
          <SectionCard
            key={section.section_id}
            section={section}
            library={library}
            chapterBackgroundMode={chapterBackgroundMode}
            onPickBackground={onPickSectionBackground}
            onPreview={setPreviewSection}
            onOpenLab={openLab}
            onUpdate={(upd) => updateSection(section.section_id, upd)}
          />
        ))}
      </div>
      {previewSection && (
        <TitleStylePreviewDialog
          section={previewSection}
          style={normalizeTitleStyle(previewSection.title_style)}
          onClose={() => setPreviewSection(null)}
        />
      )}
      {isLabOpen && (
        <TitleStyleLab
          currentSection={labSection}
          initialStyle={normalizeTitleStyle(labSection?.title_style || blueprint.metadata?.default_title_style)}
          onApplyCurrent={applyToCurrent}
          onApplySameType={applyToSameType}
          onApplyAll={applyToAll}
          onSaveDefault={saveDefaultTitleStyle}
          onClose={() => setIsLabOpen(false)}
        />
      )}
    </div>
  );
}

function SectionCard({
  section,
  library,
  chapterBackgroundMode,
  onPickBackground,
  onPreview,
  onOpenLab,
  onUpdate,
}: {
  section: V5StorySection;
  library: V5MediaLibrary;
  chapterBackgroundMode: V5ChapterBackgroundMode;
  onPickBackground: (section: V5StorySection) => void;
  onPreview: (section: V5StorySection) => void;
  onOpenLab: (section: V5StorySection) => void;
  onUpdate: (updated: V5StorySection) => void;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const icon = section.section_type === "city" ? <MapPin size={16} /> :
    section.section_type === "date" ? <Calendar size={16} /> :
      section.section_type === "scenic_spot" ? <Palmtree size={16} /> : <Layers size={16} />;

  const getAssetById = (id: string) => library?.assets.find((a) => a.asset_id === id);
  const bgState = sectionBackgroundLabel(section, chapterBackgroundMode);
  const titleStyle = normalizeTitleStyle(section.title_style);

  const toggleSection = () => onUpdate({ ...section, enabled: !section.enabled });
  const handleTitleChange = (newTitle: string) => onUpdate({ ...section, title: newTitle });
  const updateTitleStyle = (patch: Partial<V5TitleStyle>) => {
    onUpdate({
      ...section,
      title_style: { ...(section.title_style || {}), ...titleStyle, ...patch },
      user_overridden: true,
    });
  };

  const updateChild = (childId: string, updatedChild: V5StorySection) => {
    const newChildren = section.children.map((c) => c.section_id === childId ? updatedChild : c);
    onUpdate({ ...section, children: newChildren });
  };

  const toggleAsset = (assetId: string) => {
    const newRefs = section.asset_refs.map((ref) =>
      ref.asset_id === assetId ? { ...ref, enabled: !ref.enabled } : ref
    );
    onUpdate({ ...section, asset_refs: newRefs });
  };

  return (
    <div className={`section-card ${section.section_type}${!section.enabled ? " disabled" : ""}`}>
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
        <div className="section-title-style-controls" aria-label="章节文字动效">
          <button className="section-style-template-btn" type="button" onClick={() => onOpenLab(section)}>
            <Sparkles size={14} />
            <span>{titleTemplateLabel(titleStyle)}</span>
          </button>
          <label>
            风格
            <select value={titleStyle.preset} onChange={(e) => updateTitleStyle({ preset: e.target.value })}>
              {TITLE_PRESETS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <label>
            动效
            <select value={titleStyle.motion} onChange={(e) => updateTitleStyle({ motion: e.target.value })}>
              {TITLE_MOTIONS.map((option) => (
                <option key={option.value} value={option.value}>{option.label}</option>
              ))}
            </select>
          </label>
          <button className="section-style-preview-btn" type="button" onClick={() => onPreview(section)}>
            <PlayCircle size={14} /> 预览
          </button>
          <button className="section-style-preview-btn subtle" type="button" onClick={() => onOpenLab(section)}>
            实验室
          </button>
        </div>
        <div className="section-bg-actions">
          <span className={`section-bg-badge ${bgState.kind}`} title={bgState.description}>背景：{bgState.label}</span>
          <button className="section-bg-btn" type="button" onClick={() => onPickBackground(section)}>选择背景</button>
          {section.background?.user_overridden && (
            <button
              className="section-bg-btn muted"
              type="button"
              onClick={() => onUpdate({ ...section, background: { mode: chapterBackgroundMode, custom_asset_id: null, custom_path: null, user_overridden: false } })}
            >
              默认
            </button>
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
          {section.children.map((child) => (
            <SectionCard
              key={child.section_id}
              section={child}
              library={library}
                chapterBackgroundMode={chapterBackgroundMode}
                onPickBackground={onPickBackground}
                onPreview={onPreview}
                onOpenLab={onOpenLab}
                onUpdate={(upd) => updateChild(child.section_id, upd)}
              />
          ))}
        </div>
      )}

      {section.enabled && section.asset_refs.length > 0 && !section.children.length && (
        <div className={`section-assets-preview${isExpanded ? " expanded-grid" : ""}`}>
          {section.asset_refs.slice(0, isExpanded ? 50 : 15).map((ref) => {
            const asset = getAssetById(ref.asset_id);
            return (
              <div
                key={ref.asset_id}
                className={`asset-mini-thumb${!ref.enabled ? " asset-disabled" : ""}`}
                title={asset ? `${asset.file.name}\n点击${ref.enabled ? "禁用" : "启用"}` : ""}
              >
                <div className="asset-click-area" onClick={() => toggleAsset(ref.asset_id)}>
                  {asset && (getAssetThumbnailPath(asset) || asset.type === "image") ? (
                    <img src={convertFileSrc(getAssetThumbnailPath(asset) || asset.absolute_path)} alt={asset.file.name} />
                  ) : asset?.type === "video" ? (
                    <div className="video-placeholder">
                      <PlayCircle size={isExpanded ? 24 : 14} />
                      <span className="video-tag">{asset.file.extension.replace(".", "").toUpperCase()}</span>
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

function firstSection(sections: V5StorySection[] | undefined): V5StorySection | null {
  for (const section of sections || []) {
    return section;
  }
  return null;
}

function applyTitleStyleToSections(
  sections: V5StorySection[],
  style: V5TitleStyle,
  predicate: (section: V5StorySection) => boolean,
): V5StorySection[] {
  return sections.map((section) => {
    const nextSection = predicate(section)
      ? {
          ...section,
          title_style: { ...(section.title_style || {}), ...normalizeTitleStyle(style) },
          user_overridden: true,
        }
      : section;

    return {
      ...nextSection,
      children: applyTitleStyleToSections(nextSection.children || [], style, predicate),
    };
  });
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
