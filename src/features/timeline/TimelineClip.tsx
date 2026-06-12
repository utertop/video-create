import { Wand2 } from "lucide-react";
import type { V5TimelineClip } from "../../lib/engine";
import { formatTimelineTime } from "./TimelineRuler";

interface TimelineClipProps {
  clip: V5TimelineClip;
  left: number;
  width: number;
  selected: boolean;
  active: boolean;
  linked: boolean;
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
  const tooltip = [
    title,
    `${formatTimelineTime(clip.timeline_start)} - ${formatTimelineTime(clip.timeline_end)} (${clip.timeline_duration.toFixed(1)}s)`,
    clip.source_ref?.asset_id ? `Asset: ${clip.source_ref.asset_id}` : null,
    clip.source_ref?.section_id ? `Section: ${clip.source_ref.section_id}` : null,
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
      <span className="timeline-clip-label">
        {active ? <Wand2 size={11} className="spin" /> : clip.kind.replace("_", " ")}
      </span>
      <strong>{title}</strong>
      <span>{formatTimelineTime(clip.timeline_start)} · {clip.timeline_duration.toFixed(1)}s</span>
    </button>
  );
}
