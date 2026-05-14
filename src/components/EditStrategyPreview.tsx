import { useState } from "react";
import { EditStrategy } from "../lib/engine";

type StrategyEffect = {
  label: string;
  bestFor: string;
  transition: string;
  motion: string;
  rhythm: string;
  note: string;
  sampleClass: string;
};

const STRATEGY_EFFECTS: Record<EditStrategy, StrategyEffect> = {
  smart_director: {
    label: "智能导演",
    bestFor: "素材类型混合、不想手动调参",
    transition: "按章节自动选择柔和淡化、桥接模糊或直切",
    motion: "图片默认轻微 Ken Burns，视频保持原始运动",
    rhythm: "自动平衡，兼顾顺滑和信息清晰",
    note: "适合作为默认方案，先让系统帮你做第一版剪辑判断。",
    sampleClass: "smart",
  },
  fast_assembly: {
    label: "快速成片",
    bestFor: "大量素材快速审片、批量出草稿",
    transition: "以直切为主，几乎不做复杂转场",
    motion: "静态图保持稳定，减少额外运动计算",
    rhythm: "偏快，重效率和稳定输出",
    note: "适合几千张图片先快速看整体内容，不追求花哨效果。",
    sampleClass: "fast",
  },
  travel_soft: {
    label: "旅拍柔和",
    bestFor: "旅行、风景、生活记录、氛围向视频",
    transition: "柔和交叉淡化，章节边界偏亮调过渡",
    motion: "图片轻推镜头，增强流动感",
    rhythm: "中速柔和，观看压力小",
    note: "最适合风景照片和短视频混剪，整体观感更舒服。",
    sampleClass: "travel",
  },
  beat_cut: {
    label: "节奏卡点",
    bestFor: "运动、潮流、活动集锦、高能短视频",
    transition: "快切、闪切、短促冲击缩放",
    motion: "图片冲击缩放，视频微缩放进场",
    rhythm: "更快更有冲击力",
    note: "适合短视频和高能素材，不建议长片全程使用。",
    sampleClass: "beat",
  },
  documentary: {
    label: "纪录叙事",
    bestFor: "人文、探店、城市漫游、故事型内容",
    transition: "克制直切和柔和淡化",
    motion: "图片慢推，帮助观众阅读画面",
    rhythm: "稳定叙事，段落感更清楚",
    note: "适合需要信息表达的视频，不会让转场抢戏。",
    sampleClass: "doc",
  },
  long_stable: {
    label: "长片稳定",
    bestFor: "中长视频、长旅行记录、大批量素材",
    transition: "低复杂度直切或轻淡化",
    motion: "轻微变化为主，降低长片疲劳",
    rhythm: "一致、克制、稳定优先",
    note: "适合几十分钟以上项目，优先保证可靠合成。",
    sampleClass: "long",
  },
};

const STRATEGY_OPTIONS: EditStrategy[] = [
  "smart_director",
  "fast_assembly",
  "travel_soft",
  "beat_cut",
  "documentary",
  "long_stable",
];

export function editStrategyLabel(strategy: EditStrategy): string {
  return STRATEGY_EFFECTS[strategy]?.label || "智能导演";
}

export function EditStrategyPreview({
  value,
  onChange,
}: {
  value: EditStrategy;
  onChange: (value: EditStrategy) => void;
}) {
  const [previewKey, setPreviewKey] = useState(0);
  const effect = STRATEGY_EFFECTS[value] || STRATEGY_EFFECTS.smart_director;

  return (
    <div className="edit-strategy-card">
      <div className="edit-strategy-card-header">
        <label>
          剪辑策略
          <select value={value} onChange={(event) => onChange(event.target.value as EditStrategy)}>
            {STRATEGY_OPTIONS.map((strategy) => (
              <option key={strategy} value={strategy}>
                {STRATEGY_EFFECTS[strategy].label}
              </option>
            ))}
          </select>
        </label>
        <div className="edit-strategy-summary">
          <span>适合</span>
          <strong>{effect.bestFor}</strong>
        </div>
      </div>

      <div className="edit-strategy-body">
        <div className={`strategy-mini-preview ${effect.sampleClass}`} key={`${value}-${previewKey}`}>
          <div className="strategy-shot shot-a">
            <span>素材 A</span>
          </div>
          <div className="strategy-shot shot-b">
            <span>素材 B</span>
          </div>
          <div className="strategy-playhead" />
        </div>

        <div className="strategy-effect-grid">
          <EffectPill label="转场" value={effect.transition} />
          <EffectPill label="镜头" value={effect.motion} />
          <EffectPill label="节奏" value={effect.rhythm} />
        </div>
      </div>

      <div className="edit-strategy-footer">
        <span>{effect.note}</span>
        <button type="button" onClick={() => setPreviewKey((current) => current + 1)}>
          重播小样
        </button>
      </div>
    </div>
  );
}

function EffectPill({ label, value }: { label: string; value: string }) {
  return (
    <div className="strategy-effect-pill">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}
