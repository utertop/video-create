import type { V5TimelineClip, V5TimelinePreviewManifest, V5TimelineTrack } from "../../lib/engine";
import { TimelineClip } from "./TimelineClip";

interface TimelineTrackProps {
  track: V5TimelineTrack;
  clips: V5TimelineClip[];
  duration: number;
  pixelsPerSecond: number;
  selectedClipId: string | null;
  activeSegmentId: string | null;
  selectedSectionId: string | null;
  previewManifest?: V5TimelinePreviewManifest | null;
  editable: boolean;
  draggingClipId: string | null;
  dragOverClipId: string | null;
  onSelectClip: (clip: V5TimelineClip) => void;
  onSelectSection: (sectionId: string | null) => void;
  onDragStart: (clipId: string) => void;
  onDragOver: (clipId: string) => void;
  onDrop: (targetClipId: string) => void;
  onDragEnd: () => void;
}

export function TimelineTrack({
  track,
  clips,
  duration,
  pixelsPerSecond,
  selectedClipId,
  activeSegmentId,
  selectedSectionId,
  previewManifest,
  editable,
  draggingClipId,
  dragOverClipId,
  onSelectClip,
  onSelectSection,
  onDragStart,
  onDragOver,
  onDrop,
  onDragEnd,
}: TimelineTrackProps) {
  const railWidth = Math.max(720, Math.ceil(duration || 1) * pixelsPerSecond);

  return (
    <div className={`timeline-track kind-${track.kind}${track.enabled ? "" : " disabled"}`}>
      <div className="timeline-track-label">
        <strong>{track.name}</strong>
        <span>{track.kind} · {clips.length}</span>
      </div>
      <div className="timeline-track-rail" style={{ width: railWidth }}>
        {clips.map((clip) => {
          const left = Math.max(0, clip.timeline_start * pixelsPerSecond);
          const width = Math.max(48, clip.timeline_duration * pixelsPerSecond);
          const segmentId = clip.source_ref?.segment_id || null;
          const sectionId = clip.source_ref?.section_id || null;
          return (
            <TimelineClip
              key={clip.clip_id}
              clip={clip}
              left={left}
              width={width}
              selected={selectedClipId === clip.clip_id}
              active={Boolean(activeSegmentId && segmentId === activeSegmentId)}
              linked={Boolean(selectedSectionId && sectionId === selectedSectionId)}
              previewEntry={previewManifest?.clips?.[clip.clip_id] || null}
              draggable={editable && track.kind === "video"}
              dragging={draggingClipId === clip.clip_id}
              dropTarget={Boolean(draggingClipId && dragOverClipId === clip.clip_id && draggingClipId !== clip.clip_id)}
              onSelect={onSelectClip}
              onSelectSection={onSelectSection}
              onDragStart={onDragStart}
              onDragOver={onDragOver}
              onDrop={onDrop}
              onDragEnd={onDragEnd}
            />
          );
        })}
      </div>
    </div>
  );
}
