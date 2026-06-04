import { Clock, History, Loader2, RotateCcw, Square } from "lucide-react";
import { RenderRecoverySummary, RenderV5Params } from "../lib/engine";

export type RenderQueueStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export interface RenderQueueItem {
  id: string;
  label: string;
  status: RenderQueueStatus;
  position: number;
  progress: number;
  message?: string;
  planPath?: string;
  outputPath?: string;
  outputDir?: string;
  commandPreview?: string;
  params?: RenderV5Params;
  createdAt: number;
  startedAt?: number;
  finishedAt?: number;
  retryCount: number;
  recovery?: RenderRecoverySummary | null;
}

export const ACTIVE_RENDER_QUEUE_STATUSES = new Set<RenderQueueStatus>(["queued", "running"]);

export function RenderQueuePanel({
  queue,
  onCancel,
  onRetry,
}: {
  queue: RenderQueueItem[];
  onCancel: (jobId: string) => void;
  onRetry: (item: RenderQueueItem) => void;
}) {
  const current = queue.find((item) => item.status === "running") || null;
  const waiting = queue.filter((item) => item.status === "queued");
  const history = queue
    .filter((item) => !ACTIVE_RENDER_QUEUE_STATUSES.has(item.status))
    .slice()
    .reverse();

  return (
    <div className="render-queue-panel">
      <div className="render-queue-header">
        <div>
          <strong>Render queue</strong>
          <span>
            {waiting.length} waiting, {history.length} finished
          </span>
        </div>
      </div>

      <div className="render-queue-grid">
        <div className="render-queue-section current">
          <div className="render-queue-section-title">
            <Loader2 size={16} className={current ? "spin" : undefined} />
            Current
          </div>
          {current ? (
            <RenderQueueRow item={current} onCancel={onCancel} onRetry={onRetry} />
          ) : (
            <div className="render-queue-empty">No active render</div>
          )}
        </div>

        <div className="render-queue-section">
          <div className="render-queue-section-title">
            <Clock size={16} />
            Waiting
          </div>
          {waiting.length > 0 ? (
            waiting.map((item) => <RenderQueueRow key={item.id} item={item} onCancel={onCancel} onRetry={onRetry} />)
          ) : (
            <div className="render-queue-empty">Queue is empty</div>
          )}
        </div>

        <div className="render-queue-section history">
          <div className="render-queue-section-title">
            <History size={16} />
            History
          </div>
          {history.length > 0 ? (
            history.map((item) => <RenderQueueRow key={item.id} item={item} onCancel={onCancel} onRetry={onRetry} />)
          ) : (
            <div className="render-queue-empty">No completed jobs yet</div>
          )}
        </div>
      </div>
    </div>
  );
}

function RenderQueueRow({
  item,
  onCancel,
  onRetry,
}: {
  item: RenderQueueItem;
  onCancel: (jobId: string) => void;
  onRetry: (item: RenderQueueItem) => void;
}) {
  const canCancel = ACTIVE_RENDER_QUEUE_STATUSES.has(item.status);
  const canRetry = item.status === "failed";

  return (
    <div className={`render-queue-row ${item.status}`}>
      <div className="render-queue-main">
        <div className="render-queue-name">
          <span className={`render-queue-status-dot ${item.status}`} />
          <strong>{item.label}</strong>
          {item.retryCount > 0 && <span className="render-queue-retry-badge">retry {item.retryCount}</span>}
        </div>
        <div className="render-queue-meta">
          <span>{queueStatusLabel(item.status)}</span>
          <span>{shortJobId(item.id)}</span>
          {item.position > 0 && <span>#{item.position}</span>}
          <span>{formatQueueTime(item.finishedAt || item.startedAt || item.createdAt)}</span>
        </div>
        {item.message && <div className="render-queue-message">{item.message}</div>}
        {item.status === "running" && (
          <div className="render-queue-progress">
            <div style={{ width: `${Math.max(2, item.progress)}%` }} />
          </div>
        )}
      </div>
      <div className="render-queue-actions">
        {canCancel && (
          <button className="render-queue-icon-btn danger" type="button" onClick={() => onCancel(item.id)} title="Cancel render">
            <Square size={14} />
          </button>
        )}
        {canRetry && (
          <button className="render-queue-icon-btn" type="button" onClick={() => onRetry(item)} title="Retry failed render">
            <RotateCcw size={14} />
          </button>
        )}
      </div>
    </div>
  );
}

export function normalizeQueueStatus(status: string): RenderQueueStatus {
  if (status === "running" || status === "done" || status === "failed" || status === "cancelled") return status;
  return "queued";
}

function queueStatusLabel(status: RenderQueueStatus): string {
  return {
    queued: "Waiting",
    running: "Rendering",
    done: "Done",
    failed: "Failed",
    cancelled: "Cancelled",
  }[status];
}

export function shortJobId(jobId: string): string {
  return jobId.length > 8 ? jobId.slice(0, 8) : jobId;
}

function formatQueueTime(timestamp?: number): string {
  if (!timestamp) return "";
  return new Date(timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}
