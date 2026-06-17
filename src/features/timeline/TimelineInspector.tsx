import { X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { TITLE_MOTIONS, TITLE_PRESETS } from "../../components/TitleStylePreview";
import type { V5TimelineClip, V5TimelinePresentation } from "../../lib/engine";
import { formatTimelineTime } from "./TimelineRuler";

interface TimelineInspectorProps {
  clip: V5TimelineClip | null;
  editable: boolean;
  source: "timeline" | "render_plan";
  trackClipIds: string[];
  dirty: boolean;
  isApplyingTimeline: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onClose: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onUpdateEnabled: (clipId: string, enabled: boolean) => void;
  onUpdateContent: (clipId: string, patch: { title_text?: string | null; subtitle_text?: string | null }) => void;
  onUpdatePresentation: (clipId: string, patch: Partial<V5TimelinePresentation>) => void;
  onUpdateDuration: (clipId: string, duration: number) => void;
  onUpdateBgmVolume: (clipId: string, volume: number) => void;
  onMoveClip: (clipId: string, targetIndex: number) => void;
}

const TITLE_MAX_LENGTH = 80;
const SUBTITLE_MAX_LENGTH = 160;
const DURATION_MIN_SECONDS = 0.1;
const DURATION_MAX_SECONDS = 300;
const TRANSITION_MAX_SECONDS = 3;

const TITLE_POSITIONS = [
  { value: "center", label: "Center" },
  { value: "lower_center", label: "Lower Center" },
  { value: "lower_left", label: "Lower Left" },
];

const TRANSITION_TYPES = [
  { value: "none", label: "None" },
  { value: "cut", label: "Cut" },
  { value: "soft_crossfade", label: "Soft Crossfade" },
  { value: "fade_through_dark", label: "Fade Through Dark" },
  { value: "fade_through_white", label: "Fade Through White" },
  { value: "bridge_blur", label: "Bridge Blur" },
];

export function TimelineInspector({
  clip,
  editable,
  source,
  trackClipIds,
  dirty,
  isApplyingTimeline,
  canUndo,
  canRedo,
  onClose,
  onUndo,
  onRedo,
  onUpdateEnabled,
  onUpdateContent,
  onUpdatePresentation,
  onUpdateDuration,
  onUpdateBgmVolume,
  onMoveClip,
}: TimelineInspectorProps) {
  const [draftTitle, setDraftTitle] = useState("");
  const [draftSubtitle, setDraftSubtitle] = useState("");
  const [draftDuration, setDraftDuration] = useState("");

  useEffect(() => {
    setDraftTitle(clip?.content_ref?.title_text || "");
    setDraftSubtitle(clip?.content_ref?.subtitle_text || "");
    setDraftDuration(clip ? String(roundDuration(clip.timeline_duration)) : "");
  }, [clip?.clip_id, clip?.content_ref?.title_text, clip?.content_ref?.subtitle_text, clip?.timeline_duration]);

  const clipIndex = clip ? trackClipIds.indexOf(clip.clip_id) : -1;
  const isTitleClip = clip ? ["title_card", "chapter_card", "subtitle_overlay"].includes(clip.kind) : false;
  const isDurationEditable = clip ? ["image_asset", "title_card", "chapter_card"].includes(clip.kind) : false;
  const isAudioClip = clip?.kind === "audio_bgm";
  const currentPreset = clip?.presentation?.title_style?.preset || "";
  const currentMotion = clip?.presentation?.title_style?.motion || "";
  const currentPosition = clip?.presentation?.title_style?.position || "";
  const currentTransitionType = clip?.presentation?.transition_type || "";
  const currentTransitionDuration = safeTransitionDuration(clip?.presentation?.transition_duration);
  const bgmVolume = typeof clip?.metadata?.bgm_volume === "number" ? clip.metadata.bgm_volume : 0.28;
  const controlsDisabled = !editable || isApplyingTimeline;

  const titleError = useMemo(() => {
    if (!isTitleClip) return null;
    if (draftTitle.trim().length === 0) return "Title is required for this clip.";
    if (draftTitle.length > TITLE_MAX_LENGTH) return `Keep title within ${TITLE_MAX_LENGTH} characters.`;
    return null;
  }, [draftTitle, isTitleClip]);

  const subtitleError = useMemo(() => {
    if (!isTitleClip) return null;
    if (draftSubtitle.length > SUBTITLE_MAX_LENGTH) return `Keep subtitle within ${SUBTITLE_MAX_LENGTH} characters.`;
    return null;
  }, [draftSubtitle, isTitleClip]);

  const durationError = useMemo(() => {
    if (!isDurationEditable) return null;
    const value = Number(draftDuration);
    if (!Number.isFinite(value)) return "Duration must be a number.";
    if (value < DURATION_MIN_SECONDS) return `Duration must be at least ${DURATION_MIN_SECONDS}s.`;
    if (value > DURATION_MAX_SECONDS) return `Duration must be ${DURATION_MAX_SECONDS}s or less.`;
    return null;
  }, [draftDuration, isDurationEditable]);

  if (!clip) {
    return (
      <aside className="timeline-inspector empty">
        <strong>Clip Editor</strong>
        <span>Select a Timeline clip to open the editing drawer.</span>
        {source === "render_plan" ? (
          <span className="timeline-inspector-note">Fallback clips are read-only until a Timeline is generated.</span>
        ) : null}
      </aside>
    );
  }

  const handleTitleChange = (value: string) => {
    setDraftTitle(value);
    if (value.trim().length === 0 || value.length > TITLE_MAX_LENGTH) return;
    onUpdateContent(clip.clip_id, { title_text: value });
  };

  const handleSubtitleChange = (value: string) => {
    setDraftSubtitle(value);
    if (value.length > SUBTITLE_MAX_LENGTH) return;
    onUpdateContent(clip.clip_id, { subtitle_text: value || null });
  };

  const handleDurationChange = (value: string) => {
    setDraftDuration(value);
    const numericValue = Number(value);
    if (!isValidDuration(numericValue)) return;
    onUpdateDuration(clip.clip_id, numericValue);
  };

  const handleTransitionTypeChange = (value: string) => {
    const nextDuration = value === "none" || value === "cut"
      ? 0
      : currentTransitionDuration > 0
        ? currentTransitionDuration
        : 0.3;
    onUpdatePresentation(clip.clip_id, {
      transition_type: value,
      transition_duration: nextDuration,
    });
  };

  return (
    <aside className={`timeline-inspector${editable ? "" : " readonly"}`}>
      <div className="timeline-inspector-head">
        <div>
          <strong>{formatClipKind(clip.kind)}</strong>
          <span>{clip.clip_id}</span>
        </div>
        <button type="button" className="timeline-inspector-close" onClick={onClose} aria-label="Close clip editor" title="Close">
          <X size={16} />
        </button>
      </div>
      <div className="timeline-inspector-state">
        <span className={editable ? "editable" : "readonly"}>{editable ? "Editable clip" : "Read-only clip"}</span>
        <span className={isApplyingTimeline ? "applying" : dirty ? "dirty" : "clean"}>
          {isApplyingTimeline ? "Applying" : dirty ? "Unapplied edits" : "Synced"}
        </span>
      </div>
      {!editable ? (
        <p className="timeline-inspector-note">
          This clip is displayed from fallback data and cannot be edited here.
        </p>
      ) : null}
      {isApplyingTimeline ? (
        <p className="timeline-inspector-note">
          Timeline edits are being applied. Controls are locked until compilation finishes.
        </p>
      ) : null}
      {editable ? (
        <div className="timeline-history-controls">
          <button type="button" disabled={controlsDisabled || !canUndo} onClick={onUndo}>
            Undo
          </button>
          <button type="button" disabled={controlsDisabled || !canRedo} onClick={onRedo}>
            Redo
          </button>
        </div>
      ) : null}

      <section className="timeline-inspector-section">
        <strong>Clip details</strong>
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
      </section>

      {editable ? (
        <div className="timeline-edit-controls">
          <section className="timeline-edit-section">
            <div className="timeline-edit-section-head">
              <strong>Basic edits</strong>
              <span>{dirty ? "Needs apply" : "Ready"}</span>
            </div>
            <label className="timeline-checkbox-row">
              <input
                type="checkbox"
                checked={clip.enabled}
                disabled={controlsDisabled}
                onChange={(event) => onUpdateEnabled(clip.clip_id, event.currentTarget.checked)}
              />
              <span>Enabled in final video</span>
            </label>

            {isTitleClip ? (
              <>
                <label>
                  <span>Title</span>
                  <input
                    value={draftTitle}
                    maxLength={TITLE_MAX_LENGTH + 8}
                    disabled={controlsDisabled}
                    aria-invalid={Boolean(titleError)}
                    onChange={(event) => handleTitleChange(event.currentTarget.value)}
                  />
                  <TimelineFieldHint error={titleError} text={`${draftTitle.length}/${TITLE_MAX_LENGTH}`} />
                </label>
                <label>
                  <span>Subtitle</span>
                  <textarea
                    rows={3}
                    value={draftSubtitle}
                    maxLength={SUBTITLE_MAX_LENGTH + 16}
                    disabled={controlsDisabled}
                    aria-invalid={Boolean(subtitleError)}
                    onChange={(event) => handleSubtitleChange(event.currentTarget.value)}
                  />
                  <TimelineFieldHint error={subtitleError} text={`${draftSubtitle.length}/${SUBTITLE_MAX_LENGTH}`} />
                </label>
                <label>
                  <span>Style</span>
                  <select
                    value={currentPreset}
                    disabled={controlsDisabled}
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
                      <option key={preset.value} value={preset.value}>{preset.label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Motion</span>
                  <select
                    value={currentMotion}
                    disabled={controlsDisabled}
                    onChange={(event) =>
                      onUpdatePresentation(clip.clip_id, {
                        title_style: {
                          ...(clip.presentation?.title_style || {}),
                          motion: event.currentTarget.value,
                        },
                      })
                    }
                  >
                    <option value="">Default</option>
                    {TITLE_MOTIONS.map((motion) => (
                      <option key={motion.value} value={motion.value}>{motion.label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Position</span>
                  <select
                    value={currentPosition}
                    disabled={controlsDisabled}
                    onChange={(event) =>
                      onUpdatePresentation(clip.clip_id, {
                        title_style: {
                          ...(clip.presentation?.title_style || {}),
                          position: event.currentTarget.value,
                        },
                      })
                    }
                  >
                    <option value="">Default</option>
                    {TITLE_POSITIONS.map((position) => (
                      <option key={position.value} value={position.value}>{position.label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Transition</span>
                  <select
                    value={currentTransitionType}
                    disabled={controlsDisabled}
                    onChange={(event) => handleTransitionTypeChange(event.currentTarget.value)}
                  >
                    <option value="">Default</option>
                    {TRANSITION_TYPES.map((transition) => (
                      <option key={transition.value} value={transition.value}>{transition.label}</option>
                    ))}
                  </select>
                </label>
                <label>
                  <span>Transition Duration</span>
                  <div className="timeline-duration-control">
                    <input
                      type="number"
                      min="0"
                      max={TRANSITION_MAX_SECONDS}
                      step="0.05"
                      value={currentTransitionDuration}
                      disabled={controlsDisabled || !currentTransitionType || currentTransitionType === "none" || currentTransitionType === "cut"}
                      onChange={(event) =>
                        onUpdatePresentation(clip.clip_id, {
                          transition_duration: clampTransitionDuration(Number(event.currentTarget.value)),
                        })
                      }
                    />
                    <span>seconds</span>
                  </div>
                </label>
              </>
            ) : (
              <p className="timeline-inspector-note">This clip has no editable title or subtitle fields.</p>
            )}
          </section>

          {isDurationEditable ? (
            <section className="timeline-edit-section">
              <div className="timeline-edit-section-head">
                <strong>Timing</strong>
                <span>Recompile required</span>
              </div>
              <label>
                <span>Duration</span>
                <div className="timeline-duration-control">
                  <input
                    type="number"
                    min={DURATION_MIN_SECONDS}
                    max={DURATION_MAX_SECONDS}
                    step="0.1"
                    value={draftDuration}
                    disabled={controlsDisabled}
                    aria-invalid={Boolean(durationError)}
                    onChange={(event) => handleDurationChange(event.currentTarget.value)}
                  />
                  <span>seconds</span>
                </div>
                <TimelineFieldHint error={durationError} text={`${DURATION_MIN_SECONDS}s-${DURATION_MAX_SECONDS}s`} />
              </label>
            </section>
          ) : null}

          {isAudioClip ? (
            <section className="timeline-edit-section">
              <div className="timeline-edit-section-head">
                <strong>Audio</strong>
                <span>{Math.round(bgmVolume * 100)}%</span>
              </div>
              <label>
                <span>BGM Volume</span>
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.01"
                  value={bgmVolume}
                  disabled={controlsDisabled}
                  onChange={(event) => onUpdateBgmVolume(clip.clip_id, Number(event.currentTarget.value))}
                />
              </label>
            </section>
          ) : null}

          {trackClipIds.length > 1 ? (
            <section className="timeline-edit-section">
              <div className="timeline-edit-section-head">
                <strong>Order</strong>
                <span>{clipIndex + 1}/{trackClipIds.length}</span>
              </div>
              <div className="timeline-move-controls">
                <button
                  type="button"
                  disabled={controlsDisabled || clipIndex <= 0}
                  onClick={() => onMoveClip(clip.clip_id, clipIndex - 1)}
                >
                  Move Up
                </button>
                <button
                  type="button"
                  disabled={controlsDisabled || clipIndex < 0 || clipIndex >= trackClipIds.length - 1}
                  onClick={() => onMoveClip(clip.clip_id, clipIndex + 1)}
                >
                  Move Down
                </button>
              </div>
            </section>
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

function TimelineFieldHint({ error, text }: { error?: string | null; text: string }) {
  return <span className={`timeline-field-hint${error ? " error" : ""}`}>{error || text}</span>;
}

function formatClipKind(kind: string): string {
  return kind.replace(/_/g, " ");
}

function roundDuration(value: number): number {
  return Math.round((Number.isFinite(value) ? value : DURATION_MIN_SECONDS) * 10) / 10;
}

function isValidDuration(value: number): boolean {
  return Number.isFinite(value) && value >= DURATION_MIN_SECONDS && value <= DURATION_MAX_SECONDS;
}

function safeTransitionDuration(value: number | null | undefined): number {
  return clampTransitionDuration(Number(value ?? 0));
}

function clampTransitionDuration(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.round(Math.max(0, Math.min(TRANSITION_MAX_SECONDS, value)) * 100) / 100;
}
