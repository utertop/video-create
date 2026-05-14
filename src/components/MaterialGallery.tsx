import { useMemo } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { FileWarning, PlayCircle, X } from "lucide-react";
import { VideoEvent } from "../types/studio";

export function MaterialGallery({
  materials,
  onSelect,
  viewMode,
}: {
  materials: VideoEvent[];
  onSelect: (m: VideoEvent) => void;
  viewMode: "chapter" | "type" | "time";
}) {
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
            {items.map((item, i) => (
              <div
                className={`material-card ${item.error ? "has-error" : ""}`}
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
            {material.width && <span>分辨率: {material.width}x{material.height}</span>}
            {material.duration && <span>时长: {material.duration.toFixed(1)}s</span>}
            {material.error && <span className="error-text">错误: {material.error}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
