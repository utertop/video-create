import { CheckCircle2, ExternalLink, ListChecks, RotateCcw, TriangleAlert } from "lucide-react";

import { openInExplorer } from "../lib/engine";
import type { GenerateVideoResult, RenderRecoverySummary } from "../lib/engine";
import { resolveResultError } from "../lib/renderResult";

export function ResultCard({
  result,
  onResumeRetry,
}: {
  result: GenerateVideoResult;
  onResumeRetry?: () => void;
}) {
  const resolution = resolveResultError(result);
  const recovery = result.recovery || null;
  const actionSuggestion = result.actionSuggestion || resolution.actionSuggestion || null;
  const showRecovery =
    Boolean(recovery) &&
    (
      recovery!.resumable ||
      recovery!.resumedFromManifest ||
      recovery!.reusedChunkCount > 0 ||
      recovery!.completedChunkCount > 0 ||
      recovery!.failedChunkCount > 0
    );
  return (
    <div className={`result-card ${result.ok ? "success" : "warning"}`}>
      <div className="result-card-header">
        {result.ok ? <CheckCircle2 size={20} /> : <TriangleAlert size={20} />}
        <strong>{result.isDryRun ? (result.ok ? "预检完成" : "预检失败") : (result.ok ? "生成完成" : "生成失败")}</strong>
      </div>
      {result.code ? <div className="result-code-row"><span className="error-code-badge">{result.code}</span></div> : null}
      <p className="result-card-message">
        {result.message}
        {result.isDryRun && result.ok && (
          <span style={{ display: 'block', marginTop: '4px', opacity: 0.8, fontSize: '0.9em' }}>
            提示：素材状态良好，您可以点击右上角的“生成视频”开始正式合成。
          </span>
        )}
      </p>
      {false && !result.ok && actionSuggestion ? (
        <div className="result-action-note">建议操作：{resolution.actionSuggestion}</div>
      ) : null}
      {!result.ok && actionSuggestion ? (
        <div className="result-action-note">建议操作：{actionSuggestion}</div>
      ) : null}
      {showRecovery && recovery ? (
        <div className="result-recovery-card">
          <div className="result-recovery-header">
            <RotateCcw size={16} />
            <strong>{result.ok ? "Stable Render 复用摘要" : "Stable Render 恢复点"}</strong>
          </div>
          <p className="result-recovery-message">
            {result.ok
              ? recovery.reusedChunkCount > 0
                ? `本次渲染复用了 ${recovery.reusedChunkCount} 个已完成分段，不需要从头开始。`
                : recovery.resumedFromManifest
                  ? "本次渲染接续了上一次 stable render 的进度。"
                  : "本次渲染已记录 stable render 恢复信息。"
              : recovery.resumable && recovery.retryable
                ? "当前失败可直接恢复重试，系统会尽量复用已经完成的 stable chunks。"
                : "当前失败已生成 stable render 恢复摘要，便于定位失败段和支持排障。"}
          </p>
          <div className="result-recovery-metrics">
            <span>已完成 {recovery.completedChunkCount}</span>
            <span>已复用 {recovery.reusedChunkCount}</span>
            <span>失败 {recovery.failedChunkCount}</span>
            {recovery.chunkCount ? <span>总分段 {recovery.chunkCount}</span> : null}
            {typeof recovery.segmentFastPathRate === "number" ? <span>段快路径 {Math.round(recovery.segmentFastPathRate * 100)}%</span> : null}
            {typeof recovery.chunkFastPathRate === "number" ? <span>块快路径 {Math.round(recovery.chunkFastPathRate * 100)}%</span> : null}
          </div>
          {(recovery.selectedBackend || recovery.actualBackend || recovery.fallbackUsed || recovery.segmentRouteDifferenceCount || recovery.failedStage || recovery.failedChunk || recovery.failureCode) ? (
            <div className="result-recovery-meta">
              {recovery.selectedBackend ? (
                <span>
                  后端：{recovery.actualBackend && recovery.actualBackend !== recovery.selectedBackend
                    ? `${recovery.selectedBackend} -> ${recovery.actualBackend}`
                    : recovery.selectedBackend}
                </span>
              ) : null}
              {recovery.fallbackUsed ? <span>回退：{recovery.fallbackUsed}</span> : null}
              {recovery.fallbackReason ? <span>回退原因：{recovery.fallbackReason}</span> : null}
              {recovery.segmentRouteDifferenceCount ? <span>运行期路由变化：{recovery.segmentRouteDifferenceCount}</span> : null}
              {recovery.failedStage ? <span>失败阶段：{recovery.failedStage}</span> : null}
              {recovery.failedChunk ? <span>失败分段：{recovery.failedChunk}</span> : null}
              {recovery.failureCode ? <span>失败标识：{recovery.failureCode}</span> : null}
            </div>
          ) : null}
          {!result.ok && onResumeRetry && recovery.resumable && recovery.retryable ? (
            <div className="result-card-actions">
              <button className="result-open-btn result-resume-btn" onClick={onResumeRetry}>
                <RotateCcw size={15} />
                恢复并重试
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
      <BuildReportV2Panel recovery={recovery} />
      {result.ok && result.outputPath && (
        <div className="result-card-actions">
          <button className="result-open-btn" onClick={() => openInExplorer(result.outputDir || result.outputPath!)}>
            <ExternalLink size={15} />
            打开输出目录
          </button>
        </div>
      )}
    </div>
  );
}

function asReportObject(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function reportString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function reportNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function reportBool(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

function reportPercent(value: unknown): string | null {
  const number = reportNumber(value);
  return number === null ? null : `${Math.round(number * 100)}%`;
}

function buildReportSuggestions(value: unknown): Array<{ id?: string; priority?: string; message: string }> {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asReportObject(item))
    .map((item) => ({
      id: reportString(item.id) || undefined,
      priority: reportString(item.priority) || undefined,
      message: reportString(item.message) || "",
    }))
    .filter((item) => item.message)
    .slice(0, 4);
}

function BuildReportV2Panel({ recovery }: { recovery: RenderRecoverySummary | null }) {
  if (!recovery) return null;
  const timeline = asReportObject(recovery.timelineSummary);
  const route = asReportObject(recovery.routeSummary);
  const fallback = asReportObject(recovery.fallbackSummary);
  const cache = asReportObject(recovery.cacheSummary);
  const recompute = asReportObject(recovery.recomputeSummary);
  const quality = asReportObject(recovery.qualitySummary);
  const performance = asReportObject(recovery.performanceSummary);
  const recoveryV2 = asReportObject(recovery.recoverySummary);
  const cachePolicy = asReportObject(cache.policy);
  const suggestions = buildReportSuggestions(recovery.reportSuggestions);
  const hasV2 =
    recovery.buildReportVersion === "v2" ||
    Object.keys(timeline).length > 0 ||
    Object.keys(route).length > 0 ||
    Object.keys(cache).length > 0 ||
    Object.keys(quality).length > 0;
  if (!hasV2) return null;

  const source = reportString(timeline.source) || "render_plan";
  const renderIntent = reportString(quality.render_intent) || reportString(cachePolicy.render_intent) || recovery.renderIntent || "final";
  const actualBackend = reportString(route.actual_backend) || recovery.actualBackend || recovery.selectedBackend || "auto";
  const fallbackApplied = reportBool(fallback.applied) ?? Boolean(recovery.fallbackApplied);
  const usesOriginalSource = reportBool(quality.uses_original_source);
  const allowProxy = reportBool(quality.allow_proxy);
  const elapsedSeconds = reportNumber(performance.elapsed_seconds);
  const outputSize = reportNumber(performance.output_size_bytes);

  const facts = [
    ["Timeline", source === "timeline" ? "compiled" : source],
    ["Intent", renderIntent],
    ["Backend", actualBackend],
    ["Fallback", fallbackApplied ? (reportString(fallback.used) || recovery.fallbackUsed || "applied") : "none"],
    ["Cache", reportString(cachePolicy.cache_namespace) || "default"],
    ["Recompute", reportBool(recompute.timeline_dirty) ? "dirty" : "clean"],
    ["Source", usesOriginalSource === null ? "unknown" : usesOriginalSource ? "original" : "proxy/derived"],
    ["Proxy", allowProxy === null ? "unknown" : allowProxy ? "allowed" : "blocked"],
  ];

  return (
    <div className="build-report-v2-panel">
      <div className="build-report-v2-header">
        <ListChecks size={16} />
        <strong>Build Report V2</strong>
        <span>{recovery.buildReportVersion || "compatible"}</span>
      </div>
      <div className="build-report-v2-grid">
        {facts.map(([label, value]) => (
          <div className="build-report-v2-item" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="build-report-v2-meta">
        {reportPercent(route.segment_fast_path_rate) ? <span>Segment fast path {reportPercent(route.segment_fast_path_rate)}</span> : null}
        {reportPercent(route.chunk_fast_path_rate) ? <span>Chunk fast path {reportPercent(route.chunk_fast_path_rate)}</span> : null}
        {elapsedSeconds !== null ? <span>Elapsed {elapsedSeconds.toFixed(2)}s</span> : null}
        {outputSize !== null ? <span>Output {(outputSize / 1024 / 1024).toFixed(1)} MB</span> : null}
        {reportString(recoveryV2.failure_code) ? <span>Failure {reportString(recoveryV2.failure_code)}</span> : null}
      </div>
      {suggestions.length > 0 ? (
        <div className="build-report-v2-suggestions">
          {suggestions.map((item) => (
            <span key={item.id || item.message}>
              {item.priority ? `${item.priority}: ` : ""}
              {item.message}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}

