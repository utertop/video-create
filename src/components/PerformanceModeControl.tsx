import { AlertTriangle, Gauge } from "lucide-react";
import { PerformanceMode } from "../lib/engine";

export type PerformanceRecommendation = {
  recommended: PerformanceMode;
  level: "low" | "medium" | "high";
  reason: string;
  summary: string;
  estimatedChunkSeconds: number;
  shouldWarn: boolean;
};

const MODE_COPY: Record<PerformanceMode, { label: string; description: string }> = {
  stable: {
    label: "稳定优先",
    description: "优先保证长视频和大批量素材稳定完成，保留 BGM 与原声存在感，同时尽量改走更稳的缓存、分段和 FFmpeg 路径。",
  },
  balanced: {
    label: "平衡推荐",
    description: "默认推荐，兼顾效果、速度和稳定性，保留主要画面表现与音频层次。",
  },
  quality: {
    label: "质感优先",
    description: "尽量保留更完整的转场、镜头和混音细节，适合中小项目或你明确愿意承担更高耗时与风险时使用。",
  },
};

export function performanceModeLabel(mode: PerformanceMode): string {
  return MODE_COPY[mode]?.label || "平衡推荐";
}

export function PerformanceModeControl({
  value,
  recommendation,
  onChange,
}: {
  value: PerformanceMode;
  recommendation: PerformanceRecommendation;
  onChange: (value: PerformanceMode) => void;
}) {
  const selectedCopy = MODE_COPY[value];
  const isOverride = value !== recommendation.recommended;
  const riskyQuality = value === "quality" && recommendation.level === "high";

  return (
    <div className={`performance-mode-card risk-${recommendation.level}`}>
      <div className="performance-mode-head">
        <div>
          <span className="performance-kicker">
            <Gauge size={13} /> 性能档位
          </span>
          <strong>{selectedCopy.label}</strong>
        </div>
        <span className="performance-recommendation">
          当前建议：{performanceModeLabel(recommendation.recommended)}
        </span>
      </div>

      <div className="performance-mode-options">
        {(Object.keys(MODE_COPY) as PerformanceMode[]).map((mode) => (
          <button
            key={mode}
            type="button"
            className={mode === value ? "active" : ""}
            onClick={() => onChange(mode)}
          >
            <strong>{MODE_COPY[mode].label}</strong>
            <span>{MODE_COPY[mode].description}</span>
          </button>
        ))}
      </div>

      <div className="performance-mode-note">
        <span>{recommendation.summary}</span>
        <small>{selectedCopy.description}</small>
      </div>

      {(recommendation.shouldWarn || isOverride || riskyQuality) && (
        <div className="performance-risk-note">
          <AlertTriangle size={15} />
          <span>
            {riskyQuality
              ? "当前项目较大，质感优先可能显著增加内存占用和最终收尾耗时。系统会尽量保留音乐与原声表达，但生成失败风险会更高。"
              : isOverride
                ? `你当前手动选择了不同于系统建议的性能档位。${recommendation.reason}`
                : recommendation.reason}
          </span>
        </div>
      )}
    </div>
  );
}
