export type ProgressTone = "idle" | "running" | "done" | "failed" | "cancelled";

export function ProgressBar({
  percent,
  phase,
  isDryRun,
  status,
  detail,
}: {
  percent: number;
  phase: string;
  isDryRun: boolean;
  status: ProgressTone;
  detail?: string | null;
}) {
  const toneClass =
    status === "failed" ? "failed" : status === "cancelled" ? "cancelled" : status === "done" ? "done" : isDryRun ? "dry-run" : "rendering";

  return (
    <div className={`progress-container progress-container-${status}`}>
      <div className="progress-header">
        <div className="phase-info">
          <div className={`phase-dot ${toneClass}`} />
          <span>{phase}</span>
        </div>
        <span className="percent-number">{percent}%</span>
      </div>
      <div className="progress-track">
        <div className={`progress-fill ${toneClass}`} style={{ width: `${percent}%` }}>
          <div className="progress-glow" />
        </div>
      </div>
      {detail ? <div className={`progress-detail progress-detail-${status}`}>{detail}</div> : null}
    </div>
  );
}
