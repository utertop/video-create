import { useEffect, useMemo, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { ImagePlus, PlayCircle, X } from "lucide-react";
import { V5Asset, V5MediaLibrary } from "../lib/engine";
import { BackgroundPickerTarget } from "../types/studio";
import { SectionTitle } from "./common";

const SECTION_OTHER_ASSET_LIMIT = 160;

export function BackgroundAssetPicker({
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
  const [showAllAssets, setShowAllAssets] = useState(false);

  useEffect(() => {
    setShowAllAssets(false);
  }, [target]);

  const visualAssets = useMemo(() => {
    return (library?.assets || [])
      .filter((asset) => (asset.type === "image" || asset.type === "video") && assetStatusState(asset) !== "error")
      .sort((a, b) => a.relative_path.localeCompare(b.relative_path));
  }, [library]);

  const preferredAssetIds = useMemo(
    () => new Set(target.kind === "section" ? target.assetIds || [] : []),
    [target],
  );

  const relatedAssets = useMemo(() => {
    if (target.kind !== "section" || preferredAssetIds.size === 0) return [];
    return visualAssets.filter((asset) => preferredAssetIds.has(asset.asset_id));
  }, [preferredAssetIds, target.kind, visualAssets]);

  const otherAssets = useMemo(() => {
    if (target.kind !== "section" || preferredAssetIds.size === 0) return visualAssets;
    return visualAssets.filter((asset) => !preferredAssetIds.has(asset.asset_id));
  }, [preferredAssetIds, target.kind, visualAssets]);

  const visibleOtherAssets = useMemo(() => {
    if (showAllAssets || target.kind !== "section") return otherAssets;
    return otherAssets.slice(0, SECTION_OTHER_ASSET_LIMIT);
  }, [otherAssets, showAllAssets, target.kind]);

  const hiddenOtherCount = Math.max(0, otherAssets.length - visibleOtherAssets.length);

  const title = target.kind === "title"
    ? "选择片头文案背景"
    : target.kind === "end"
      ? "选择片尾文案背景"
      : `选择章节「${target.sectionTitle}」背景`;

  const defaultHint = target.kind === "title"
    ? "不手动选择时，默认使用成片第一段画面的首帧或首图做虚化背景。"
    : target.kind === "end"
      ? "不手动选择时，默认使用成片最后一段画面的尾帧或末图做虚化背景。"
      : "章节背景优先推荐本章节自身素材；如果素材很多，会先展示本章节相关项，再按需展开全部素材。";

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
          <div className="background-picker-empty">正在扫描素材库，请稍候…</div>
        ) : visualAssets.length === 0 ? (
          <div className="background-picker-empty">素材库里还没有可用图片或视频。请先确认素材目录下包含 JPG / PNG / WEBP / MP4 / MOV 等素材。</div>
        ) : (
          <div className="background-picker-sections">
            {relatedAssets.length > 0 && (
              <BackgroundAssetSection
                title={`本章节相关素材 (${relatedAssets.length})`}
                assets={relatedAssets}
                selectedPath={selectedPath}
                onSelect={onSelect}
              />
            )}

            <BackgroundAssetSection
              title={relatedAssets.length > 0 ? `其他可用素材 (${otherAssets.length})` : `全部素材 (${visualAssets.length})`}
              assets={relatedAssets.length > 0 ? visibleOtherAssets : visualAssets}
              selectedPath={selectedPath}
              onSelect={onSelect}
            />

            {relatedAssets.length > 0 && hiddenOtherCount > 0 && (
              <div className="background-picker-more">
                <span>已先展示前 {visibleOtherAssets.length} 个其他素材，剩余 {hiddenOtherCount} 个未展开。</span>
                <button type="button" className="secondary-action" onClick={() => setShowAllAssets(true)}>
                  展开全部素材
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function BackgroundAssetSection({
  title,
  assets,
  selectedPath,
  onSelect,
}: {
  title: string;
  assets: V5Asset[];
  selectedPath: string | null;
  onSelect: (asset: V5Asset) => void;
}) {
  return (
    <section className="background-picker-section">
      <div className="background-picker-section-header">
        <strong>{title}</strong>
      </div>
      <div className="background-picker-grid">
        {assets.map((asset) => {
          const selected = selectedPath === asset.absolute_path;
          return (
            <button
              type="button"
              key={asset.asset_id}
              className={`background-asset-card${selected ? " selected" : ""}`}
              onClick={() => onSelect(asset)}
              title={asset.relative_path}
            >
              <BackgroundAssetThumb asset={asset} />
              <div className="background-asset-info">
                <strong>{asset.file.name}</strong>
                <span>{asset.media.width || "?"}x{asset.media.height || "?"}</span>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

function BackgroundAssetThumb({ asset }: { asset: V5Asset }) {
  const candidates = useMemo(() => {
    const paths = [asset.thumbnail_path, asset.thumbnail, asset.type === "image" ? asset.absolute_path : null];
    return paths.filter((value): value is string => typeof value === "string" && value.length > 0);
  }, [asset.absolute_path, asset.thumbnail, asset.thumbnail_path, asset.type]);
  const [candidateIndex, setCandidateIndex] = useState(0);
  const currentSrc = candidates[candidateIndex] || null;

  const onImageError = () => {
    if (candidateIndex < candidates.length - 1) {
      setCandidateIndex((prev) => prev + 1);
      return;
    }
    setCandidateIndex(candidates.length);
  };

  return (
    <div className="background-asset-thumb">
      {currentSrc ? (
        <img src={convertFileSrc(currentSrc)} alt={asset.file.name} loading="lazy" onError={onImageError} />
      ) : (
        <div className="background-asset-thumb-fallback">
          {asset.type === "video" ? <PlayCircle size={22} /> : <ImagePlus size={22} />}
        </div>
      )}
      {asset.type === "video" && <span className="background-video-badge">VIDEO</span>}
    </div>
  );
}

export function shortPathName(path: string | null | undefined): string {
  if (!path) return "";
  return path.split(/[\\/]/).pop() || path;
}

function assetStatusState(asset: V5Asset): string {
  if (!asset.status) return "ready";
  if (typeof asset.status === "string") return asset.status;
  return asset.status.state || "ready";
}
