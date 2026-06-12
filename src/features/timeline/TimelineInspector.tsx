import type { V5TimelineClip, V5TimelinePresentation } from "../../lib/engine";
import { formatTimelineTime } from "./TimelineRuler";

interface TimelineInspectorProps {
  clip: V5TimelineClip | null;
  editable: boolean;
  trackClipIds: string[];
  onUpdateEnabled: (clipId: string, enabled: boolean) => void;
  onUpdateContent: (clipId: string, patch: { title_text?: string | null; subtitle_text?: string | null }) => void;
  onUpdatePresentation: (clipId: string, patch: Partial<V5TimelinePresentation>) => void;
  onUpdateDuration: (clipId: string, duration: number) => void;
  onUpdateBgmVolume: (clipId: string, volume: number) => void;
  onMoveClip: (clipId: string, targetIndex: number) => void;
}

const TITLE_PRESETS = [
  "cinematic_bold",
  "travel_postcard",
  "minimal_editorial",
  "film_subtitle",
  "documentary_lower_third",
];

export function TimelineInspector({
  clip,
  editable,
  trackClipIds,
  onUpdateEnabled,
  onUpdateContent,
  onUpdatePresentation,
  onUpdateDuration,
  onUpdateBgmVolume,
  onMoveClip,
}: TimelineInspectorProps) {
  if (!clip) {
    return (
      <aside className="timeline-inspector empty">
        <strong>Clip Inspector</strong>
        <span>Select a timeline clip to inspect source, timing, cache, and recompute hints.</span>
      </aside>
    );
  }

  const clipIndex = trackClipIds.indexOf(clip.clip_id);
  const isTitleClip = ["title_card", "chapter_card", "subtitle_overlay"].includes(clip.kind);
  const isDurationEditable = ["image_asset", "title_card", "chapter_card"].includes(clip.kind);
  const isAudioClip = clip.kind === "audio_bgm";
  const currentPreset = clip.presentation?.title_style?.preset || "";
  const bgmVolume = typeof clip.metadata?.bgm_volume === "number" ? clip.metadata.bgm_volume : 0.28;

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

      {editable ? (
        <div className="timeline-edit-controls">
          <label className="timeline-checkbox-row">
            <input
              type="checkbox"
              checked={clip.enabled}
              onChange={(event) => onUpdateEnabled(clip.clip_id, event.currentTarget.checked)}
            />
            <span>Enabled</span>
          </label>

          {isTitleClip ? (
            <>
              <label>
                <span>Title</span>
                <input
                  value={clip.content_ref?.title_text || ""}
                  onChange={(event) => onUpdateContent(clip.clip_id, { title_text: event.currentTarget.value })}
                />
              </label>
              <label>
                <span>Subtitle</span>
                <input
                  value={clip.content_ref?.subtitle_text || ""}
                  onChange={(event) => onUpdateContent(clip.clip_id, { subtitle_text: event.currentTarget.value })}
                />
              </label>
              <label>
                <span>Style</span>
                <select
                  value={currentPreset}
                  onChange={(event) =>
                    onUpdatePresentation(clip.clip_id, {
                      title_style: {
                        ...(clip.presentation?.title_style || {}),
                        preset: event.currentTarget.value,
                      },
                    })
                  }
                >
                  <option value="">Default</option>
                  {TITLE_PRESETS.map((preset) => (
                    <option key={preset} value={preset}>{preset}</option>
                  ))}
                </select>
              </label>
            </>
          ) : null}

          {isDurationEditable ? (
            <label>
              <span>Duration</span>
              <input
                type="number"
                min="0.1"
                step="0.1"
                value={clip.timeline_duration}
                onChange={(event) => onUpdateDuration(clip.clip_id, Number(event.currentTarget.value))}
              />
            </label>
          ) : null}

          {isAudioClip ? (
            <label>
              <span>BGM Volume</span>
              <input
                type="range"
                min="0"
                max="1"
                step="0.01"
                value={bgmVolume}
                onChange={(event) => onUpdateBgmVolume(clip.clip_id, Number(event.currentTarget.value))}
              />
            </label>
          ) : null}

          {trackClipIds.length > 1 ? (
            <div className="timeline-move-controls">
              <button type="button" disabled={clipIndex <= 0} onClick={() => onMoveClip(clip.clip_id, clipIndex - 1)}>
                Move Up
              </button>
              <button
                type="button"
                disabled={clipIndex < 0 || clipIndex >= trackClipIds.length - 1}
                onClick={() => onMoveClip(clip.clip_id, clipIndex + 1)}
              >
                Move Down
              </button>
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}

function TimelineInspectorRow({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value == null || value === "" ? "-" : value}</dd>
    </div>
  );
}
