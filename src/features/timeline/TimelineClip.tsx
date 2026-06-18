import { Wand2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import type { V5TimelineClip, V5TimelinePreviewManifestClip } from "../../lib/engine";
import { formatTimelineTime } from "./TimelineRuler";

interface TimelineClipProps {
  clip: V5TimelineClip;
  left: number;
  width: number;
  selected: boolean;
  active: boolean;
  linked: boolean;
  previewEntry?: V5TimelinePreviewManifestClip | null;
  draggable: boolean;
  dragging: boolean;
  dropTarget: boolean;
  onSelect: (clip: V5TimelineClip) => void;
  onSelectSection: (sectionId: string | null) => void;
  onDragStart: (clipId: string) => void;
  onDragOver: (clipId: string) => void;
  onDrop: (clipId: string) => void;
  onDragEnd: () => void;
}

export function TimelineClip({
  clip,
  left,
  width,
  selected,
  active,
  linked,
  previewEntry,
  draggable,
  dragging,
  dropTarget,
  onSelect,
  onSelectSection,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: TimelineClipProps) {
  const sectionId = clip.source_ref?.section_id || null;
  const title = clip.content_ref?.title_text || clip.content_ref?.source_path?.split(/[/\\]/).pop() || clip.kind;
  const thumbnailPath = previewEntry?.thumbnail?.status === "ready" ? previewEntry.thumbnail.path || null : null;
  const waveformPath = previewEntry?.waveform?.status === "ready" ? previewEntry.waveform.path || null : null;
  const assetReady = previewEntry?.preview_segment?.status === "ready" || previewEntry?.proxy?.status === "ready";
  const assetFailed = [
    previewEntry?.thumbnail?.status,
    previewEntry?.proxy?.status,
    previewEntry?.waveform?.status,
    previewEntry?.preview_segment?.status,
  ].some((status) => status === "failed");
  const waveformPeaks = useWaveformPeaks(waveformPath);
  const tooltip = [
    title,
    `${formatTimelineTime(clip.timeline_start)} - ${formatTimelineTime(clip.timeline_end)} (${clip.timeline_duration.toFixed(1)}s)`,
    clip.source_ref?.asset_id ? `Asset: ${clip.source_ref.asset_id}` : null,
    clip.source_ref?.section_id ? `Section: ${clip.source_ref.section_id}` : null,
    previewEntry?.preview_segment?.status ? `Preview: ${previewEntry.preview_segment.status}` : null,
    previewEntry?.proxy?.status && previewEntry.proxy.status !== "not_applicable" ? `Proxy: ${previewEntry.proxy.status}` : null,
    previewEntry?.waveform?.status && previewEntry.waveform.status !== "not_applicable" ? `Waveform: ${previewEntry.waveform.status}` : null,
  ].filter(Boolean).join("\n");

  const handleActivate = () => {
    onSelect(clip);
    if (sectionId) onSelectSection(sectionId);
  };

  return (
    <button
      type="button"
      className={[
        "timeline-clip",
        `kind-${clip.kind}`,
        selected ? "selected" : "",
        active ? "active-rendering" : "",
        linked ? "linked-audio-section" : "",
        assetReady ? "preview-asset-ready" : "",
        assetFailed ? "preview-asset-failed" : "",
        dragging ? "dragging" : "",
        dropTarget ? "drop-target" : "",
        clip.enabled ? "" : "disabled",
      ].filter(Boolean).join(" ")}
      style={{ left, width }}
      data-section-id={sectionId || undefined}
      data-segment-id={clip.source_ref?.segment_id || undefined}
      title={tooltip}
      onClick={handleActivate}
      draggable={draggable}
      onDragStart={(event) => {
        if (!draggable) return;
        event.dataTransfer.effectAllowed = "move";
        event.dataTransfer.setData("text/plain", clip.clip_id);
        onDragStart(clip.clip_id);
      }}
      onDragOver={(event) => {
        if (!draggable) return;
        event.preventDefault();
        onDragOver(clip.clip_id);
      }}
      onDrop={(event) => {
        if (!draggable) return;
        event.preventDefault();
        onDrop(clip.clip_id);
      }}
      onDragEnd={onDragEnd}
    >
      {thumbnailPath ? (
        <img className="timeline-clip-thumbnail" src={convertFileSrc(thumbnailPath)} alt="" loading="lazy" draggable={false} />
      ) : null}
      {waveformPath ? (
        <span className="timeline-clip-waveform" aria-hidden="true">
          {waveformPeaks.map((peak, index) => (
            <i key={`${index}-${peak}`} style={{ height: `${Math.max(10, Math.round(peak * 100))}%` }} />
          ))}
        </span>
      ) : null}
      {assetReady || assetFailed ? <span className="timeline-clip-asset-dot" aria-hidden="true" /> : null}
      <span className="timeline-clip-label">
        {active ? <Wand2 size={11} className="spin" /> : clip.kind.replace("_", " ")}
      </span>
      <strong>{title}</strong>
      <span>{formatTimelineTime(clip.timeline_start)} · {clip.timeline_duration.toFixed(1)}s</span>
    </button>
  );
}

function useWaveformPeaks(path: string | null): number[] {
  const [peaks, setPeaks] = useState<number[]>([]);
  const fallback = useMemo(() => Array.from({ length: 24 }, (_, index) => 0.18 + ((index * 7) % 11) / 16), []);

  useEffect(() => {
    if (!path) {
      setPeaks([]);
      return;
    }
    let cancelled = false;
    fetch(convertFileSrc(path))
      .then((response) => response.json())
      .then((data) => {
        if (cancelled) return;
        const raw = Array.isArray(data?.peaks) ? data.peaks : [];
        const stride = Math.max(1, Math.ceil(raw.length / 32));
        const next = raw
          .filter((_: unknown, index: number) => index % stride === 0)
          .slice(0, 32)
          .map((value: unknown) => Math.max(0.05, Math.min(1, Number(value) || 0.05)));
        setPeaks(next.length > 0 ? next : fallback);
      })
      .catch(() => {
        if (!cancelled) setPeaks(fallback);
      });
    return () => {
      cancelled = true;
    };
  }, [fallback, path]);

  return peaks.length > 0 ? peaks : fallback;
}
