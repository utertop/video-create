interface TimelineRulerProps {
  duration: number;
  pixelsPerSecond: number;
}

export function TimelineRuler({ duration, pixelsPerSecond }: TimelineRulerProps) {
  const safeDuration = Math.max(1, Math.ceil(duration || 0));
  const step = safeDuration > 900 ? 120 : safeDuration > 360 ? 60 : safeDuration > 120 ? 30 : 10;
  const ticks: number[] = [];
  for (let current = 0; current <= safeDuration; current += step) {
    ticks.push(current);
  }
  if (ticks[ticks.length - 1] !== safeDuration) ticks.push(safeDuration);

  return (
    <div className="timeline-ruler" style={{ width: Math.max(720, safeDuration * pixelsPerSecond) }}>
      {ticks.map((tick) => (
        <div
          key={tick}
          className="timeline-ruler-tick"
          style={{ left: `${tick * pixelsPerSecond}px` }}
        >
          <span>{formatTimelineTime(tick)}</span>
        </div>
      ))}
    </div>
  );
}

export function formatTimelineTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds || 0));
  const minutes = Math.floor(total / 60);
  const remain = total % 60;
  return `${minutes}:${String(remain).padStart(2, "0")}`;
}
