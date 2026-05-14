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
    description: "更短分段、较低峰值内存，保留章节动效但降低复杂转场。",
  },
  balanced: {
    label: "平衡推荐",
    description: "默认推荐，保留主要效果并限制超长转场的风险。",
  },
  quality: {
    label: "画质优先",
    description: "尽量保留完整动效和高质量输出，长视频可能占用更多内存。",
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
              ? "当前项目较大，强制画质优先可能占用较多内存，长视频存在生成失败风险。"
              : isOverride
                ? `你当前选择与系统建议不同：${recommendation.reason}`
                : recommendation.reason}
          </span>
        </div>
      )}
    </div>
  );
}
