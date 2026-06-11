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
  onSelect: (clip: V5TimelineClip) => void;
  onSelectSection: (sectionId: string | null) => void;
}

export function TimelineClip({
  clip,
  left,
  width,
  selected,
  active,
  linked,
  onSelect,
  onSelectSection,
}: TimelineClipProps) {
  const sectionId = clip.source_ref?.section_id || null;
  const title = clip.content_ref?.title_text || clip.content_ref?.source_path?.split(/[/\\]/).pop() || clip.kind;

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
        clip.enabled ? "" : "disabled",
      ].filter(Boolean).join(" ")}
      style={{ left, width }}
      data-section-id={sectionId || undefined}
      data-segment-id={clip.source_ref?.segment_id || undefined}
      onClick={handleActivate}
    >
      <span className="timeline-clip-label">
        {active ? <Wand2 size={11} className="spin" /> : clip.kind.replace("_", " ")}
      </span>
      <strong>{title}</strong>
      <span>{formatTimelineTime(clip.timeline_start)} · {clip.timeline_duration.toFixed(1)}s</span>
    </button>
  );
}
