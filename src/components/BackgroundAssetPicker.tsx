import { useMemo } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { ImagePlus, X } from "lucide-react";
import { V5Asset, V5MediaLibrary } from "../lib/engine";
import { BackgroundPickerTarget } from "../types/studio";
import { SectionTitle } from "./common";

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

export function shortPathName(path: string | null | undefined): string {
  if (!path) return "";
  return path.split(/[\\/]/).pop() || path;
}

function assetStatusState(asset: V5Asset): string {
  if (!asset.status) return "ready";
  if (typeof asset.status === "string") return asset.status;
  return asset.status.state || "ready";
}
