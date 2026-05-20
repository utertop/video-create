import { useMemo, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { FileWarning, PlayCircle, X } from "lucide-react";
import { VideoEvent } from "../types/studio";

const MATERIAL_GROUP_LIMIT = 180;

export function MaterialGallery({
  materials,
  onSelect,
  viewMode,
}: {
  materials: VideoEvent[];
  onSelect: (m: VideoEvent) => void;
  viewMode: "chapter" | "type" | "time";
}) {
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});
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

    Object.values(res).forEach((list) => {
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
            {(expandedGroups[groupName] ? items : items.slice(0, MATERIAL_GROUP_LIMIT)).map((item, i) => (
              <div
                className={`material-card ${item.error ? "has-error" : ""}`}
                key={`${item.path || item.rel_path || item.display_name || "item"}-${i}`}
                onClick={() => onSelect(item)}
              >
                <GalleryThumbnail item={item} />
                <div className="material-info">
                  <div className="name-row">
                    <span className="material-name">{item.display_name}</span>
                  </div>
                  <div className="meta-row">
                    {item.width && item.height && <span className="res-tag">{item.width}x{item.height}</span>}
                    {item.item_kind === "image" && <span className="type-tag">IMG</span>}
                    {item.item_kind === "video" && <span className="type-tag">MOV</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
          {items.length > MATERIAL_GROUP_LIMIT && !expandedGroups[groupName] && (
            <div className="gallery-group-more">
              <span>该章节素材较多，先展示前 {MATERIAL_GROUP_LIMIT} 个缩略图。</span>
              <button type="button" className="secondary-action" onClick={() => setExpandedGroups((prev) => ({ ...prev, [groupName]: true }))}>
                展开全部
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function GalleryThumbnail({ item }: { item: VideoEvent }) {
  const candidates = useMemo(() => {
    const paths = [item.thumbnail_path, item.thumbnail, item.item_kind === "image" ? item.path : null];
    return paths.filter((value): value is string => typeof value === "string" && value.length > 0);
  }, [item.item_kind, item.path, item.thumbnail, item.thumbnail_path]);
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
    <div className="thumbnail-container">
      {currentSrc ? (
        <img src={convertFileSrc(currentSrc)} alt={item.display_name} loading="lazy" onError={onImageError} />
      ) : (
        <div className="thumbnail-placeholder">
          {item.item_kind === "video" ? <PlayCircle size={24} /> : <FileWarning size={24} />}
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
  );
}

export function PreviewModal({ material, onClose }: { material: VideoEvent; onClose: () => void }) {
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
            {material.width && <span>分辨率：{material.width}x{material.height}</span>}
            {material.duration && <span>时长：{material.duration.toFixed(1)}s</span>}
            {material.error && <span className="error-text">错误：{material.error}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
