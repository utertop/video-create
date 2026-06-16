import { CheckCircle2, Clock, Gauge, History, Loader2, PlayCircle, RotateCcw, Settings2, TriangleAlert } from "lucide-react";

import { Toggle } from "./FormControls";
import type { StartupDiagnostics, TelemetrySummary } from "../lib/engine";

function formatTelemetryRate(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function describeTopTelemetryEntry(entries: TelemetrySummary["topErrorCodes"]): string {
  const top = entries[0];
  if (!top) return "No events yet";
  return `${top.key} (${top.count})`;
}

export function TelemetrySummaryCard({
  enabled,
  summary,
  isClearing,
  onClear,
  remoteEndpoint,
  remoteUploadEnabled,
  isSavingSettings,
  isFlushingRemote,
  onRemoteEndpointChange,
  onRemoteUploadEnabledChange,
  onSaveRemoteSettings,
  onFlushRemoteQueue,
}: {
  enabled: boolean;
  summary: TelemetrySummary | null;
  isClearing: boolean;
  onClear: () => void;
  remoteEndpoint: string;
  remoteUploadEnabled: boolean;
  isSavingSettings: boolean;
  isFlushingRemote: boolean;
  onRemoteEndpointChange: (value: string) => void;
  onRemoteUploadEnabledChange: (value: boolean) => void;
  onSaveRemoteSettings: () => void;
  onFlushRemoteQueue: () => void;
}) {
  const recentEvents = summary?.recentEvents || [];
  const recentEvent = recentEvents.length > 0 ? recentEvents[recentEvents.length - 1] : null;

  return (
    <section className="startup-health-card">
      <div className="startup-health-head">
        <div>
          <span className="startup-health-kicker">OPTIONAL TELEMETRY</span>
          <strong>{enabled ? "匿名稳定性指标已启用" : "匿名稳定性指标未启用"}</strong>
        </div>
        <div className="startup-health-badge-group">
          <span className={`startup-health-badge ${enabled ? "ok" : "pending"}`}>
            {enabled ? (
              <>
                <CheckCircle2 size={14} /> Enabled
              </>
            ) : (
              <>
                <Clock size={14} /> Opt-in
              </>
            )}
          </span>
          <button className="secondary-action telemetry-reset-btn" disabled={isClearing} type="button" onClick={onClear}>
            {isClearing ? <Loader2 className="spin" size={16} /> : <RotateCcw size={16} />}
            {isClearing ? "清空中" : "清空本地历史"}
          </button>
        </div>
      </div>

      <div className="startup-health-grid">
        <div className="startup-health-item">
          <div className="startup-health-item-head">
            <Gauge size={16} />
            <strong>Crash-free sessions</strong>
          </div>
          <span>{summary ? formatTelemetryRate(summary.crashFreeSessionRate) : "Waiting for local metrics"}</span>
          <small>
            {summary
              ? `${summary.sessionsCompletedCleanly}/${summary.sessionsStarted} sessions closed cleanly`
              : "Enable telemetry to start measuring app stability."}
          </small>
        </div>

        <div className="startup-health-item">
          <div className="startup-health-item-head">
            <PlayCircle size={16} />
            <strong>First export success</strong>
          </div>
          <span>{summary ? formatTelemetryRate(summary.firstExportSuccessRate) : "Waiting for export attempts"}</span>
          <small>
            {summary
              ? `${summary.firstExportSuccesses}/${summary.firstExportSessions} first exports succeeded`
              : "Tracked once per session after the first render result."}
          </small>
        </div>

        <div className="startup-health-item">
          <div className="startup-health-item-head">
            <TriangleAlert size={16} />
            <strong>Common error code</strong>
          </div>
          <span>{summary ? describeTopTelemetryEntry(summary.topErrorCodes) : "No failures recorded yet"}</span>
          <small>{summary ? `${summary.renderFailures} render failures recorded locally` : "Recent failures will surface here."}</small>
        </div>

        <div className="startup-health-item">
          <div className="startup-health-item-head">
            <History size={16} />
            <strong>Support routing</strong>
          </div>
          <span>{summary ? describeTopTelemetryEntry(summary.topSupportQueues) : "No support events yet"}</span>
          <small>
            {summary
              ? `Recovery resumable: ${summary.recoveryResumableEvents}, retryable: ${summary.recoveryRetryableEvents}`
              : "Queue, severity, tag, and recovery labels stay anonymous."}
          </small>
        </div>
      </div>

      {summary ? (
        <div className="telemetry-summary-footer">
          <span>Render attempts: {summary.renderAttempts}</span>
          <span>Last event: {recentEvent ? `${recentEvent.eventType}${recentEvent.errorCode ? ` [${recentEvent.errorCode}]` : ""}` : "none"}</span>
          <span>Last updated: {summary.lastUpdatedAt ? new Date(summary.lastUpdatedAt).toLocaleString() : "not yet"}</span>
        </div>
      ) : null}

      <div className="telemetry-remote-panel">
        <div className="telemetry-remote-head">
          <strong>Remote Crash Reporting</strong>
          <span>Consent: {summary?.consentAcceptedVersion === summary?.currentConsentVersion ? summary?.currentConsentVersion : "not accepted"}</span>
        </div>
        <label className="telemetry-remote-field">
          <span>Remote endpoint</span>
          <input
            placeholder="https://telemetry.example.com/collect"
            type="url"
            value={remoteEndpoint}
            onChange={(event) => onRemoteEndpointChange(event.target.value)}
          />
        </label>
        <div className="telemetry-remote-actions">
          <Toggle checked={remoteUploadEnabled} label="允许远程匿名上报" onChange={onRemoteUploadEnabledChange} />
          <button className="secondary-action telemetry-remote-btn" disabled={isSavingSettings} type="button" onClick={onSaveRemoteSettings}>
            {isSavingSettings ? <Loader2 className="spin" size={16} /> : <Settings2 size={16} />}
            {isSavingSettings ? "Saving" : "Save remote settings"}
          </button>
          <button className="secondary-action telemetry-remote-btn" disabled={isFlushingRemote || !summary?.pendingRemoteEvents} type="button" onClick={onFlushRemoteQueue}>
            {isFlushingRemote ? <Loader2 className="spin" size={16} /> : <RotateCcw size={16} />}
            {isFlushingRemote ? "Retrying" : `Retry queued uploads${summary?.pendingRemoteEvents ? ` (${summary.pendingRemoteEvents})` : ""}`}
          </button>
        </div>
        <div className="telemetry-summary-footer">
          <span>Endpoint: {summary?.remoteEndpointHost || "not configured"}</span>
          <span>Pending uploads: {summary?.pendingRemoteEvents || 0}</span>
          <span>Last remote upload: {summary?.lastRemoteUploadAt ? new Date(summary.lastRemoteUploadAt).toLocaleString() : "never"}</span>
          <span>Last remote status: {summary?.lastRemoteUploadError || "ok"}</span>
        </div>
      </div>

      <p className="telemetry-summary-note">
        仅记录匿名稳定性标签与聚合计数，不包含素材路径、标题文本或媒体内容；可以随时关闭或清空本地历史。
      </p>
    </section>
  );
}

export function TelemetryConsentDialog({
  consentVersion,
  isSaving,
  onAccept,
  onDecline,
}: {
  consentVersion: string;
  isSaving: boolean;
  onAccept: () => void;
  onDecline: () => void;
}) {
  return (
    <div className="gallery-overlay">
      <div className="telemetry-consent-modal">
        <div className="telemetry-consent-head">
          <strong>Telemetry Consent</strong>
          <span>{consentVersion}</span>
        </div>
        <p>
          Anonymous telemetry helps track crash-free sessions, first export success, common failure codes, and render recovery outcomes.
        </p>
        <p>
          It does not include media content, titles, or raw project text. Remote upload is optional and can stay disabled even after consent.
        </p>
        <p>
          Privacy notice: <code>docs/TELEMETRY_PRIVACY_NOTICE_V2026_05.md</code>
        </p>
        <div className="telemetry-consent-actions">
          <button className="secondary-action" type="button" onClick={onDecline}>
            Not now
          </button>
          <button className="primary-action" disabled={isSaving} type="button" onClick={onAccept}>
            {isSaving ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
            {isSaving ? "Saving consent" : "Accept privacy notice"}
          </button>
        </div>
      </div>
    </div>
  );
}

export function StartupHealthCard({
  diagnostics,
  loading,
}: {
  diagnostics: StartupDiagnostics | null;
  loading: boolean;
}) {
  return (
    <DiagnosticsCard
      title="桌面运行环境"
      kicker="STARTUP SELF-CHECK"
      diagnostics={diagnostics}
      loading={loading}
      loadingText="正在检查 worker、资源文件和可写目录..."
    />
  );
}

export function DiagnosticsCard({
  title,
  kicker,
  diagnostics,
  loading,
  loadingText,
}: {
  title: string;
  kicker: string;
  diagnostics: StartupDiagnostics | null;
  loading: boolean;
  loadingText: string;
}) {
  if (!loading && !diagnostics) return null;

  return (
    <section className={`startup-health-card${diagnostics && !diagnostics.ok ? " failed" : ""}`}>
      <div className="startup-health-head">
        <div>
          <span className="startup-health-kicker">{kicker}</span>
          <strong>{loading ? title : diagnostics?.summary || `${title}不可用。`}</strong>
        </div>
        <div className="startup-health-badge-group">
          {diagnostics?.code ? <span className="error-code-badge">{diagnostics.code}</span> : null}
          <span className={`startup-health-badge ${loading ? "pending" : diagnostics?.ok ? "ok" : "failed"}`}>
            {loading ? (
              <>
                <Loader2 className="spin" size={14} /> 检查中
              </>
            ) : diagnostics?.ok ? (
              <>
                <CheckCircle2 size={14} /> 通过
              </>
            ) : (
              <>
                <TriangleAlert size={14} /> 需处理
              </>
            )}
          </span>
        </div>
      </div>

      <div className="startup-health-grid">
        {loading ? (
          <div className="startup-health-item pending">
            <strong>{title}</strong>
            <span>{loadingText}</span>
          </div>
        ) : (
          diagnostics?.checks.map((check) => (
            <div className={`startup-health-item ${check.ok ? "ok" : "failed"}`} key={check.id}>
              <div className="startup-health-item-head">
                {check.ok ? <CheckCircle2 size={16} /> : <TriangleAlert size={16} />}
                <strong>{check.label}</strong>
              </div>
              {check.code ? <span className="error-code-inline">{check.code}</span> : null}
              <span>{check.message}</span>
              {check.detail ? <small>{check.detail}</small> : null}
            </div>
          ))
        )}
      </div>
    </section>
  );
}

export function ProjectMigrationCard({
  source,
  notes,
}: {
  source: string;
  notes: string[];
}) {
  return (
    <section className="project-migration-card">
      <div className="project-migration-head">
        <div>
          <span className="startup-health-kicker">PROJECT MIGRATION</span>
          <strong>已自动迁移旧版项目文档</strong>
        </div>
        <span className="project-migration-badge">{source}</span>
      </div>
      <div className="project-migration-body">
        <p>当前项目在恢复时检测到旧版 schema，系统已自动升级到当前版本。以下是本次迁移内容：</p>
        <ul>
          {notes.map((note, index) => (
            <li key={`${note}-${index}`}>{note}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}
