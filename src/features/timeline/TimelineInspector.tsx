import type { V5TimelineClip } from "../../lib/engine";
import { formatTimelineTime } from "./TimelineRuler";

interface TimelineInspectorProps {
  clip: V5TimelineClip | null;
}

export function TimelineInspector({ clip }: TimelineInspectorProps) {
  if (!clip) {
    return (
      <aside className="timeline-inspector empty">
        <strong>Clip Inspector</strong>
        <span>Select a timeline clip to inspect source, timing, cache, and recompute hints.</span>
      </aside>
    );
  }

  return (
    <aside className="timeline-inspector">
      <div className="timeline-inspector-head">
        <strong>{clip.kind.replace("_", " ")}</strong>
        <span>{clip.clip_id}</span>
      </div>
      <dl>
        <TimelineInspectorRow label="Track" value={clip.track_id} />
        <TimelineInspectorRow label="Section" value={clip.source_ref?.section_id} />
        <TimelineInspectorRow label="Asset" value={clip.source_ref?.asset_id} />
        <TimelineInspectorRow label="Segment" value={clip.source_ref?.segment_id} />
        <TimelineInspectorRow label="Source" value={clip.content_ref?.source_path} />
        <TimelineInspectorRow label="Title" value={clip.content_ref?.title_text} />
        <TimelineInspectorRow label="Start" value={formatTimelineTime(clip.timeline_start)} />
        <TimelineInspectorRow label="Duration" value={`${clip.timeline_duration.toFixed(1)}s`} />
        <TimelineInspectorRow label="End" value={formatTimelineTime(clip.timeline_end)} />
        <TimelineInspectorRow label="Scope" value={clip.invalidation_hint?.primary_scope} />
        <TimelineInspectorRow label="Recompile" value={String(Boolean(clip.invalidation_hint?.requires_render_plan_recompile))} />
        <TimelineInspectorRow label="Audio Relayout" value={String(Boolean(clip.invalidation_hint?.requires_audio_relayout))} />
        <TimelineInspectorRow label="Cache" value={clip.cache_policy?.cache_namespace} />
        <TimelineInspectorRow label="Route" value={clip.execution?.preferred_route} />
      </dl>
    </aside>
  );
}

function TimelineInspectorRow({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value == null || value === "" ? "—" : value}</dd>
    </div>
  );
}
