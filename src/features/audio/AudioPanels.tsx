import { Music, Sparkles, Volume2 } from "lucide-react";

import { shortPathName } from "../../components/BackgroundAssetPicker";
import { Toggle } from "../../components/FormControls";
import { withBlueprintMetadata } from "../../lib/blueprint";
import type {
  MusicFitStrategy,
  MusicPlaylistMode,
  V5Asset,
  V5AudioBlueprint,
  V5AudioBlueprintCue,
  V5AudioSettings,
  V5MediaLibrary,
  V5RenderPlan,
} from "../../lib/engine";
import type { StudioState } from "../../store/studio";

export function RenderAudioTimelineCard({
  plan,
  activeSegmentIndex,
  isRendering,
  selectedSectionId,
  onSelectSection,
}: {
  plan: V5RenderPlan;
  activeSegmentIndex: number | null;
  isRendering: boolean;
  selectedSectionId: string | null;
  onSelectSection: (sectionId: string | null) => void;
}) {
  const blueprint = plan.render_settings?.audio_blueprint || null;
  const cues = blueprintCueList(blueprint);
  if (!blueprint || cues.length === 0) return null;

  const activeSectionId =
    activeSegmentIndex !== null && activeSegmentIndex >= 0 ? plan.segments[activeSegmentIndex]?.section_id || null : null;
  const adopted = blueprint.adopted_audio_settings || plan.render_settings?.audio || {};
  const playlistMode = normalizeBlueprintPlaylistMode(
    typeof adopted.music_playlist_mode === "string" ? adopted.music_playlist_mode : null,
    Boolean(adopted.music_chapter_restart),
  );
  const totalDuration = Math.max(0.1, Number(plan.total_duration || 0));
  const originSummary = blueprint.origin_summary || "本次编译后的章节配乐执行结果。";

  return (
    <section className="render-audio-timeline-card">
      <div className="render-audio-timeline-head">
        <div>
          <strong>本次实际采用的章节配乐时间线</strong>
          <span>{originSummary}</span>
        </div>
        <span className="render-audio-timeline-badge">{musicPlaylistModeLabel(playlistMode)}</span>
      </div>

      <div className="render-audio-timeline-summary">
        {blueprint.music_profile ? <span>{blueprint.music_profile}</span> : null}
        {adopted.music_fit_strategy ? <span>{adopted.music_fit_strategy}</span> : null}
        {typeof adopted.bgm_volume === "number" ? <span>BGM {Math.round(adopted.bgm_volume * 100)}%</span> : null}
        {typeof adopted.source_audio_volume === "number" ? <span>原声 {Math.round(adopted.source_audio_volume * 100)}%</span> : null}
        {adopted.auto_ducking ? <span>自动 Ducking</span> : null}
        {adopted.music_chapter_restart ? <span>章节切点重启</span> : null}
      </div>

      <div className="render-audio-timeline-list">
        {cues.map((cue, index) => {
          const startTime = Math.max(0, Number(cue.start_time || 0));
          const duration = Math.max(0, Number(cue.duration || 0));
          const widthPercent = Math.max(3, Math.min(100, (duration / totalDuration) * 100));
          const offsetPercent = Math.max(0, Math.min(100, (startTime / totalDuration) * 100));
          const isActive = Boolean(activeSectionId) && activeSectionId === cue.section_id;
          const isSelected = Boolean(selectedSectionId) && selectedSectionId === cue.section_id;

          return (
            <div
              className={`render-audio-cue${isActive ? " active" : ""}${isSelected ? " selected" : ""}`}
              key={`${cue.section_id || cue.title || index}-${index}`}
              role={cue.section_id ? "button" : undefined}
              tabIndex={cue.section_id ? 0 : undefined}
              onClick={() => {
                if (!cue.section_id) return;
                onSelectSection(selectedSectionId === cue.section_id ? null : cue.section_id);
              }}
              onKeyDown={(event) => {
                if (!cue.section_id) return;
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelectSection(selectedSectionId === cue.section_id ? null : cue.section_id);
                }
              }}
            >
              <div className="render-audio-cue-main">
                <div className="render-audio-cue-title-row">
                  <strong>{cue.title || cue.section_id || `章节 ${index + 1}`}</strong>
                  <span>
                    {formatDurationLabel(startTime)} - {formatDurationLabel(Number(cue.end_time || startTime))}
                  </span>
                </div>
                <div className="render-audio-cue-rail">
                  <span
                    className="render-audio-cue-bar"
                    style={{ left: `${offsetPercent}%`, width: `${Math.max(widthPercent, 4)}%` }}
                  />
                </div>
              </div>
              <div className="render-audio-cue-meta">
                <span>{cue.phase || "sustain"}</span>
                <span>{cue.energy || "medium"}</span>
                <span>{cue.ducking_hint || "medium ducking"}</span>
                {isSelected ? <span>已联动片段</span> : null}
              </div>
              <p>{cue.reason || "保持音乐连续性并跟随章节节奏变化。"}</p>
              {isRendering && isActive ? <div className="render-audio-cue-live">当前渲染中</div> : null}
            </div>
          );
        })}
      </div>
    </section>
  );
}


export function buildAudioSettings(state: StudioState, library: V5MediaLibrary | null, plan: V5RenderPlan | null): V5AudioSettings {
  const resolved = resolveMusicSelection(state, library, plan);
  return {
    music_mode: state.musicMode,
    music_path: resolved.primaryPath,
    music_playlist_mode: state.musicPlaylistMode,
    music_playlist_paths: resolved.paths,
    music_chapter_restart: state.musicPlaylistMode === "chapter_restart",
    music_fit_strategy: state.musicFitStrategy,
    estimated_video_duration: Number(plan?.total_duration || 0),
    music_source:
      state.musicMode === "manual" && resolved.paths.length > 0
        ? "manual"
        : state.musicMode === "auto" && resolved.paths.length > 0
          ? "library"
          : "none",
    bgm_volume: clampNumber(state.bgmVolume, 0, 1, 0.28),
    source_audio_volume: clampNumber(state.sourceAudioVolume, 0, 1, 1),
    keep_source_audio: Boolean(state.keepSourceAudio),
    auto_ducking: Boolean(state.autoDucking),
    fade_in_seconds: clampNumber(state.musicFadeInSeconds, 0, 10, 1.5),
    fade_out_seconds: clampNumber(state.musicFadeOutSeconds, 0, 20, 3),
    normalize_audio: false,
  };
}

type AudioBlueprintApplyScope = "source" | "mix" | "timing" | "all";

export function resolveAudioBlueprint(state: StudioState): V5AudioBlueprint | null {
  return state.v5RenderPlan?.render_settings?.audio_blueprint || state.v5Blueprint?.metadata?.audio_blueprint || null;
}

function resolveEditableAudioBlueprint(state: StudioState): V5AudioBlueprint | null {
  return state.v5Blueprint?.metadata?.audio_blueprint || resolveAudioBlueprint(state);
}

function normalizeStringList(values: string[] | null | undefined): string[] {
  return Array.isArray(values) ? values.map((item) => String(item || "").trim()).filter(Boolean) : [];
}

export function normalizeBlueprintPlaylistMode(mode: string | null | undefined, chapterRestart?: boolean | null): MusicPlaylistMode {
  if (chapterRestart || mode === "chapter_restart") return "chapter_restart";
  if (mode === "auto_playlist" || mode === "manual_playlist" || mode === "single") return mode;
  return "single";
}

export function musicPlaylistModeLabel(mode: MusicPlaylistMode): string {
  return {
    single: "单曲",
    auto_playlist: "自动多曲",
    manual_playlist: "手动歌单",
    chapter_restart: "章节重启",
  }[mode];
}

export function blueprintCueList(blueprint: V5AudioBlueprint | null) {
  const raw = blueprint?.timeline_cues?.length ? blueprint.timeline_cues : blueprint?.section_cues;
  return Array.isArray(raw) ? raw.filter((item) => item && (item.section_id || item.title)) : [];
}

function normalizeEditableCueList(blueprint: V5AudioBlueprint | null): V5AudioBlueprintCue[] {
  const raw = blueprint?.section_cues?.length ? blueprint.section_cues : blueprintCueList(blueprint);
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((item) => item && item.section_id)
    .map((item, index) => ({
      ...item,
      order: typeof item.order === "number" ? item.order : index,
      phase: item.phase || "sustain",
      energy: item.energy || "medium",
      ducking_hint: item.ducking_hint || "medium",
      reason: item.reason || "",
      title: item.title || item.section_id || `section_${index + 1}`,
    }))
    .sort((a, b) => {
      const orderA = typeof a.order === "number" ? a.order : Number.MAX_SAFE_INTEGER;
      const orderB = typeof b.order === "number" ? b.order : Number.MAX_SAFE_INTEGER;
      if (orderA !== orderB) return orderA - orderB;
      return String(a.section_id || "").localeCompare(String(b.section_id || ""));
    });
}

function syncTimelineCuesWithSectionEdits(
  timelineCues: V5AudioBlueprintCue[] | null | undefined,
  sectionCues: V5AudioBlueprintCue[],
): V5AudioBlueprintCue[] | null | undefined {
  if (!Array.isArray(timelineCues)) return timelineCues;
  const overrideMap = new Map(sectionCues.map((item) => [String(item.section_id || ""), item]));
  return timelineCues.map((item) => {
    const override = overrideMap.get(String(item.section_id || ""));
    if (!override) return item;
    return {
      ...item,
      title: override.title || item.title,
      phase: override.phase || item.phase,
      energy: override.energy || item.energy,
      ducking_hint: override.ducking_hint || item.ducking_hint,
      reason: override.reason || item.reason,
    };
  });
}

function patchAudioBlueprintCue(
  state: StudioState,
  sectionId: string,
  patch: Partial<Pick<V5AudioBlueprintCue, "phase" | "energy" | "ducking_hint" | "reason">>,
): void {
  if (!state.v5Blueprint) return;
  const editableBlueprint = resolveEditableAudioBlueprint(state);
  if (!editableBlueprint) return;

  const nextSectionCues = normalizeEditableCueList(editableBlueprint).map((item) =>
    item.section_id === sectionId
      ? {
          ...item,
          ...patch,
        }
      : item,
  );

  const nextAudioBlueprint: V5AudioBlueprint = {
    ...editableBlueprint,
    section_cues: nextSectionCues,
    timeline_cues: syncTimelineCuesWithSectionEdits(editableBlueprint.timeline_cues, nextSectionCues),
  };

  const nextBlueprint = withBlueprintMetadata(state.v5Blueprint, {
    audio_blueprint: nextAudioBlueprint,
  });

  const nextPatch: Partial<StudioState> = {
    v5Blueprint: nextBlueprint,
    v5Timeline: null,
    v5TimelinePreviewManifest: null,
  };

  if (state.v5RenderPlan?.render_settings?.audio_blueprint) {
    nextPatch.v5RenderPlan = {
      ...state.v5RenderPlan,
      render_settings: {
        ...(state.v5RenderPlan.render_settings || {}),
        audio_blueprint: {
          ...state.v5RenderPlan.render_settings.audio_blueprint,
          section_cues: nextSectionCues,
          timeline_cues: syncTimelineCuesWithSectionEdits(
            state.v5RenderPlan.render_settings.audio_blueprint.timeline_cues,
            nextSectionCues,
          ),
        },
      },
    };
  }

  state.patch(nextPatch);
}

function restoreCompiledAudioBlueprintCues(state: StudioState): void {
  if (!state.v5Blueprint || !state.v5RenderPlan?.render_settings?.audio_blueprint) return;
  const compiledBlueprint = state.v5RenderPlan.render_settings.audio_blueprint;
  const nextAudioBlueprint: V5AudioBlueprint = {
    ...(resolveEditableAudioBlueprint(state) || compiledBlueprint),
    section_cues: normalizeEditableCueList(compiledBlueprint),
    timeline_cues: compiledBlueprint.timeline_cues || null,
  };
  state.patch({
    v5Blueprint: withBlueprintMetadata(state.v5Blueprint, {
      audio_blueprint: nextAudioBlueprint,
    }),
    v5Timeline: null,
    v5TimelinePreviewManifest: null,
  });
}

function audioBlueprintCueEditsPending(state: StudioState): boolean {
  const editable = normalizeEditableCueList(resolveEditableAudioBlueprint(state));
  const compiled = normalizeEditableCueList(state.v5RenderPlan?.render_settings?.audio_blueprint || null);
  if (compiled.length === 0 || editable.length !== compiled.length) return false;
  return editable.some((item, index) => {
    const baseline = compiled[index];
    return (
      item.phase !== baseline.phase ||
      item.energy !== baseline.energy ||
      item.ducking_hint !== baseline.ducking_hint ||
      String(item.reason || "") !== String(baseline.reason || "")
    );
  });
}

function blueprintCandidatePaths(blueprint: V5AudioBlueprint | null): string[] {
  return normalizeStringList(
    (blueprint?.candidate_assets || []).map((item) => item?.absolute_path || ""),
  );
}

function buildAudioBlueprintPatch(blueprint: V5AudioBlueprint | null, scope: AudioBlueprintApplyScope): Partial<StudioState> {
  const recommended = blueprint?.recommended_audio_settings;
  if (!recommended) return {};

  const patch: Partial<StudioState> = {};
  if (scope === "source" || scope === "all") {
    const recommendedMode = recommended.music_mode === "off" ? "off" : "auto";
    const recommendedPlaylistMode = normalizeBlueprintPlaylistMode(
      recommended.music_playlist_mode,
      recommended.music_chapter_restart,
    );
    const recommendedPaths = normalizeStringList(recommended.music_playlist_paths);
    const playlistPaths = recommendedPaths.length > 0 ? recommendedPaths : blueprintCandidatePaths(blueprint);
    const primaryPath = String(recommended.music_path || "").trim() || playlistPaths[0] || null;
    const explicitPaths = playlistPaths.length > 0 ? playlistPaths : primaryPath ? [primaryPath] : [];

    patch.musicMode = recommendedMode;
    patch.musicPlaylistMode = recommendedMode === "off" ? "single" : recommendedPlaylistMode;
    patch.musicPath = recommendedMode === "off" ? null : primaryPath;
    patch.musicPlaylistPaths = recommendedMode === "off" ? [] : explicitPaths;
  }

  if (scope === "mix" || scope === "all") {
    if (typeof recommended.bgm_volume === "number") patch.bgmVolume = clampNumber(recommended.bgm_volume, 0, 1, 0.28);
    if (typeof recommended.source_audio_volume === "number") {
      patch.sourceAudioVolume = clampNumber(recommended.source_audio_volume, 0, 1, 1);
    }
    if (typeof recommended.keep_source_audio === "boolean") patch.keepSourceAudio = recommended.keep_source_audio;
    if (typeof recommended.auto_ducking === "boolean") patch.autoDucking = recommended.auto_ducking;
  }

  if (scope === "timing" || scope === "all") {
    if (
      recommended.music_fit_strategy === "auto" ||
      recommended.music_fit_strategy === "loop" ||
      recommended.music_fit_strategy === "trim" ||
      recommended.music_fit_strategy === "intro_loop_outro" ||
      recommended.music_fit_strategy === "once"
    ) {
      patch.musicFitStrategy = recommended.music_fit_strategy;
    }
    if (typeof recommended.fade_in_seconds === "number") {
      patch.musicFadeInSeconds = clampNumber(recommended.fade_in_seconds, 0, 10, 1.5);
    }
    if (typeof recommended.fade_out_seconds === "number") {
      patch.musicFadeOutSeconds = clampNumber(recommended.fade_out_seconds, 0, 20, 3);
    }
  }

  return patch;
}

function audioBlueprintScopeApplied(
  state: StudioState,
  blueprint: V5AudioBlueprint | null,
  scope: AudioBlueprintApplyScope,
): boolean {
  const recommended = blueprint?.recommended_audio_settings;
  if (!recommended) return false;

  const sourcePatch = buildAudioBlueprintPatch(blueprint, "source");
  const mixPatch = buildAudioBlueprintPatch(blueprint, "mix");
  const timingPatch = buildAudioBlueprintPatch(blueprint, "timing");

  if (scope === "source" || scope === "all") {
    const sameSource =
      state.musicMode === sourcePatch.musicMode &&
      state.musicPlaylistMode === sourcePatch.musicPlaylistMode &&
      state.musicPath === sourcePatch.musicPath &&
      sameStringArray(state.musicPlaylistPaths, sourcePatch.musicPlaylistPaths || []);
    if (scope === "source" && !sameSource) return false;
    if (scope === "all" && !sameSource) return false;
  }

  if (scope === "mix" || scope === "all") {
    const sameMix =
      numbersClose(state.bgmVolume, mixPatch.bgmVolume) &&
      numbersClose(state.sourceAudioVolume, mixPatch.sourceAudioVolume) &&
      state.keepSourceAudio === mixPatch.keepSourceAudio &&
      state.autoDucking === mixPatch.autoDucking;
    if (scope === "mix" && !sameMix) return false;
    if (scope === "all" && !sameMix) return false;
  }

  if (scope === "timing" || scope === "all") {
    const sameTiming =
      state.musicFitStrategy === timingPatch.musicFitStrategy &&
      numbersClose(state.musicFadeInSeconds, timingPatch.musicFadeInSeconds) &&
      numbersClose(state.musicFadeOutSeconds, timingPatch.musicFadeOutSeconds);
    if (scope === "timing" && !sameTiming) return false;
    if (scope === "all" && !sameTiming) return false;
  }

  return true;
}

function numbersClose(current: number | undefined, next: number | undefined): boolean {
  if (current === undefined || next === undefined) return false;
  return Math.abs(current - next) < 0.001;
}

function sameStringArray(current: string[] | undefined, next: string[] | undefined): boolean {
  const a = normalizeStringList(current || []);
  const b = normalizeStringList(next || []);
  if (a.length !== b.length) return false;
  return a.every((item, index) => item === b[index]);
}

function buildAudioBlueprintAdoptionState(state: StudioState, blueprint: V5AudioBlueprint | null) {
  const source = audioBlueprintScopeApplied(state, blueprint, "source");
  const mix = audioBlueprintScopeApplied(state, blueprint, "mix");
  const timing = audioBlueprintScopeApplied(state, blueprint, "timing");
  const appliedScopes = [
    source ? "source" : null,
    mix ? "mix" : null,
    timing ? "timing" : null,
  ].filter(Boolean) as string[];

  return {
    source,
    mix,
    timing,
    all: source && mix && timing,
    applied_scopes: appliedScopes,
    updated_at: new Date().toISOString(),
  };
}

function buildAudioBlueprintOriginSummary(state: StudioState, blueprint: V5AudioBlueprint | null): string | null {
  if (!blueprint?.recommended_audio_settings) return null;
  const adoption = buildAudioBlueprintAdoptionState(state, blueprint);
  const labels = [
    adoption.source ? "曲目" : null,
    adoption.mix ? "混音" : null,
    adoption.timing ? "节奏" : null,
  ].filter(Boolean);
  const appliedText = labels.length > 0 ? labels.join(" / ") : "尚未采纳";
  const source = blueprint.template_id || blueprint.music_profile || "audio_blueprint";
  return `来自 ${source} 的 AI 配乐建议，当前已采纳：${appliedText}`;
}

export function decorateAudioBlueprintForPersist(
  state: StudioState,
  blueprint: V5AudioBlueprint | null,
  plan: V5RenderPlan | null,
): V5AudioBlueprint | null {
  if (!blueprint) return null;
  return {
    ...blueprint,
    ui_adoption_state: buildAudioBlueprintAdoptionState(state, blueprint),
    adopted_audio_settings: buildAudioSettings(state, state.v5Library, plan),
    origin_summary: buildAudioBlueprintOriginSummary(state, blueprint),
  };
}

function AudioBlueprintPanel({ state }: { state: StudioState }) {
  const blueprint = resolveEditableAudioBlueprint(state) || resolveAudioBlueprint(state);
  const recommended = blueprint?.recommended_audio_settings;
  const cues = blueprintCueList(blueprint);
  const editableCues = normalizeEditableCueList(blueprint);
  const candidateAssets = (blueprint?.candidate_assets || []).filter((item) => item?.absolute_path || item?.relative_path);
  if (!blueprint || !recommended) return null;

  const sourceApplied = audioBlueprintScopeApplied(state, blueprint, "source");
  const mixApplied = audioBlueprintScopeApplied(state, blueprint, "mix");
  const timingApplied = audioBlueprintScopeApplied(state, blueprint, "timing");
  const allApplied = sourceApplied && mixApplied && timingApplied;
  const cueEditsPending = state.v5Stage === "RENDER" && audioBlueprintCueEditsPending(state);
  const playlistMode = normalizeBlueprintPlaylistMode(recommended.music_playlist_mode, recommended.music_chapter_restart);
  const primaryLabel = shortPathName(
    String(recommended.music_path || blueprint.selected_candidate?.absolute_path || blueprint.selected_candidate?.relative_path || ""),
  );
  const keywords = normalizeStringList(blueprint.search_keywords).slice(0, 5);
  const phaseSummary = cues.slice(0, 4).map((item) => item.phase || item.title || "section").join(" / ");
  const originSummary = buildAudioBlueprintOriginSummary(state, blueprint) || blueprint.origin_summary;
  const applyScope = (scope: AudioBlueprintApplyScope) => {
    const patch = buildAudioBlueprintPatch(blueprint, scope);
    if (Object.keys(patch).length > 0) state.patch(patch);
  };

  return (
    <section className="audio-blueprint-panel">
      <div className="audio-blueprint-head">
        <div className="audio-blueprint-title">
          <Sparkles size={16} />
          <div>
            <strong>AI 配乐蓝图</strong>
            <span>
              {blueprint.timeline_cues?.length
                ? "已进入渲染计划，可看到章节时间线建议。"
                : "已根据模板和素材节奏生成配乐建议。"}
            </span>
          </div>
        </div>
        <div className="audio-blueprint-head-actions">
          <span className={`audio-blueprint-badge${allApplied ? " active" : ""}`}>
            {allApplied ? "已全部采纳" : blueprint.timeline_cues?.length ? "编译后建议" : "蓝图建议"}
          </span>
          <button
            className={`audio-blueprint-apply-btn${allApplied ? " active" : ""}`}
            disabled={allApplied}
            type="button"
            onClick={() => applyScope("all")}
          >
            {allApplied ? "当前已同步" : "一键采纳"}
          </button>
        </div>
      </div>

      <div className="audio-blueprint-chip-row">
        {blueprint.template_id ? <span>{blueprint.template_id}</span> : null}
        {blueprint.music_profile ? <span>{blueprint.music_profile}</span> : null}
        {playlistMode ? <span>{musicPlaylistModeLabel(playlistMode)}</span> : null}
        {blueprint.longform_project ? <span>长视频策略</span> : null}
        {allApplied ? <span>当前参数已与 AI 对齐</span> : null}
        {keywords.map((item) => (
          <span key={item}>{item}</span>
        ))}
      </div>

      {originSummary ? <p className="audio-blueprint-origin">{originSummary}</p> : null}

      {state.v5Stage === "RENDER" ? (
        <p className={`audio-blueprint-origin${cueEditsPending ? " pending" : ""}`}>
          {cueEditsPending
            ? "章节微调已写入蓝图预览，重新点击“确认并进入渲染”后正式应用到新的 render plan。"
            : "可以先微调章节配乐，再重新编译 render plan 查看正式结果。"}
        </p>
      ) : null}

      <div className="audio-blueprint-grid">
        <div className="audio-blueprint-card">
          <div className="audio-blueprint-card-head">
            <strong>曲目与播放方式</strong>
            <span className={sourceApplied ? "applied" : ""}>{sourceApplied ? "已采纳" : "建议可采纳"}</span>
          </div>
          <p>
            {recommended.music_mode === "off"
              ? "当前建议关闭 BGM，保留原声表达。"
              : `${musicPlaylistModeLabel(playlistMode)} · ${primaryLabel || "未命名曲目"}`}
          </p>
          <div className="audio-blueprint-stats">
            <span>候选 {candidateAssets.length || normalizeStringList(recommended.music_playlist_paths).length || 1} 首</span>
            <span>{cues.length > 0 ? `${cues.length} 个章节提示` : "以素材匹配结果为主"}</span>
          </div>
          <button disabled={sourceApplied} type="button" onClick={() => applyScope("source")}>
            {sourceApplied ? "已采用曲目建议" : "采纳曲目建议"}
          </button>
        </div>

        <div className="audio-blueprint-card">
          <div className="audio-blueprint-card-head">
            <strong>混音层级</strong>
            <span className={mixApplied ? "applied" : ""}>{mixApplied ? "已采纳" : "建议可采纳"}</span>
          </div>
          <p>
            BGM {Math.round(Number(recommended.bgm_volume || 0) * 100)}% · 原声{" "}
            {Math.round(Number(recommended.source_audio_volume || 0) * 100)}%
          </p>
          <div className="audio-blueprint-stats">
            <span>{recommended.keep_source_audio ? "保留原声" : "弱化原声"}</span>
            <span>{recommended.auto_ducking ? "启用自动压低 BGM" : "关闭自动压低"}</span>
          </div>
          <button disabled={mixApplied} type="button" onClick={() => applyScope("mix")}>
            {mixApplied ? "已采用混音建议" : "采纳混音建议"}
          </button>
        </div>

        <div className="audio-blueprint-card">
          <div className="audio-blueprint-card-head">
            <strong>节奏与时长</strong>
            <span className={timingApplied ? "applied" : ""}>{timingApplied ? "已采纳" : "建议可采纳"}</span>
          </div>
          <p>
            {recommended.music_fit_strategy || "auto"} · 淡入 {Number(recommended.fade_in_seconds || 0).toFixed(1)}s · 淡出{" "}
            {Number(recommended.fade_out_seconds || 0).toFixed(1)}s
          </p>
          <div className="audio-blueprint-stats">
            <span>{blueprint.energy_curve_style || "balanced_story"}</span>
            <span>{phaseSummary || "保持段落起伏与收束感"}</span>
          </div>
          <button disabled={timingApplied} type="button" onClick={() => applyScope("timing")}>
            {timingApplied ? "已采用节奏建议" : "采纳节奏建议"}
          </button>
        </div>
      </div>

      {candidateAssets.length > 0 && (
        <div className="audio-blueprint-shelf">
          <strong>候选曲目</strong>
          <div className="audio-blueprint-candidate-list">
            {candidateAssets.slice(0, 4).map((item, index) => {
              const isSelected =
                item.absolute_path &&
                item.absolute_path === (blueprint.selected_candidate?.absolute_path || recommended.music_path || null);
              return (
                <div className={`audio-blueprint-candidate${isSelected ? " selected" : ""}`} key={`${item.absolute_path || item.relative_path || index}`}>
                  <div>
                    <strong>{shortPathName(item.relative_path || item.absolute_path || `候选曲目 ${index + 1}`)}</strong>
                    <span>
                      {typeof item.duration_seconds === "number" && item.duration_seconds > 0
                        ? formatDurationLabel(item.duration_seconds)
                        : "时长待检测"}
                    </span>
                  </div>
                  <span>{typeof item.score === "number" ? `score ${Math.round(item.score)}` : isSelected ? "主推荐" : "候选"}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {cues.length > 0 && (
        <div className="audio-blueprint-timeline">
          <strong>章节节奏提示</strong>
          <div className="audio-blueprint-cue-list">
            {cues.slice(0, 6).map((item, index) => (
              <div className="audio-blueprint-cue" key={`${item.section_id || item.title || index}-${index}`}>
                <div className="audio-blueprint-cue-main">
                  <span className="audio-blueprint-cue-title">{item.title || item.section_id || `章节 ${index + 1}`}</span>
                  <span className="audio-blueprint-cue-meta">
                    {[item.phase, item.energy, typeof item.duration === "number" ? formatDurationLabel(item.duration) : null]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </div>
                <p>{item.reason || "保持音乐连续性并跟随章节节奏变化。"}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {editableCues.length > 0 ? (
        <div className="audio-blueprint-editor">
          <div className="audio-blueprint-editor-head">
            <div>
              <strong>章节级配乐微调</strong>
              <span>按章节调整节奏、能量与 ducking，修改会写回蓝图元数据。</span>
            </div>
            {state.v5RenderPlan?.render_settings?.audio_blueprint ? (
              <button type="button" onClick={() => restoreCompiledAudioBlueprintCues(state)}>
                恢复上次编译结果
              </button>
            ) : null}
          </div>

          <div className="audio-blueprint-editor-list">
            {editableCues.map((cue, index) => (
              <div className="audio-blueprint-editor-card" key={`${cue.section_id || index}-${index}`}>
                <div className="audio-blueprint-editor-card-head">
                  <strong>{cue.title || cue.section_id || `章节 ${index + 1}`}</strong>
                  <span>{cue.section_type || "section"}</span>
                </div>

                <div className="audio-blueprint-editor-grid">
                  <label>
                    <span>阶段</span>
                    <select
                      value={cue.phase || "sustain"}
                      onChange={(event) => patchAudioBlueprintCue(state, String(cue.section_id), { phase: event.target.value })}
                    >
                      <option value="intro">开场</option>
                      <option value="sustain">承接</option>
                      <option value="peak">高潮</option>
                      <option value="outro">收束</option>
                    </select>
                  </label>
                  <label>
                    <span>能量</span>
                    <select
                      value={cue.energy || "medium"}
                      onChange={(event) => patchAudioBlueprintCue(state, String(cue.section_id), { energy: event.target.value })}
                    >
                      <option value="low">低</option>
                      <option value="medium">中</option>
                      <option value="high">高</option>
                    </select>
                  </label>
                  <label>
                    <span>Ducking</span>
                    <select
                      value={cue.ducking_hint || "medium"}
                      onChange={(event) => patchAudioBlueprintCue(state, String(cue.section_id), { ducking_hint: event.target.value })}
                    >
                      <option value="off">关闭</option>
                      <option value="light">轻</option>
                      <option value="medium">中</option>
                      <option value="high">强</option>
                    </select>
                  </label>
                </div>

                <label className="audio-blueprint-editor-reason">
                  <span>说明</span>
                  <textarea
                    rows={2}
                    value={cue.reason || ""}
                    onChange={(event) => patchAudioBlueprintCue(state, String(cue.section_id), { reason: event.target.value })}
                  />
                </label>
              </div>
            ))}
          </div>
        </div>
      ) : null}
    </section>
  );
}

export function MusicAudioPanel({
  state,
  onPickMusicFile,
  onPickMusicFiles,
}: {
  state: StudioState;
  onPickMusicFile: () => void;
  onPickMusicFiles: () => void;
}) {
  const audioBlueprint = resolveAudioBlueprint(state);
  const sourceAligned = audioBlueprintScopeApplied(state, audioBlueprint, "source");
  const mixAligned = audioBlueprintScopeApplied(state, audioBlueprint, "mix");
  const timingAligned = audioBlueprintScopeApplied(state, audioBlueprint, "timing");
  const resolved = resolveMusicSelection(state, state.v5Library, state.v5RenderPlan);
  const resolvedMusicPath = resolved.primaryPath;
  const musicEnabled = state.musicMode !== "off" && resolved.paths.length > 0;
  const bgmPercent = Math.round(clampNumber(state.bgmVolume, 0, 1, 0.28) * 100);
  const sourcePercent = Math.round(clampNumber(state.sourceAudioVolume, 0, 1, 1) * 100);
  const summary = buildMusicPlanSummarySafe(state, resolved, state.v5RenderPlan);
  const statusText =
    state.musicMode === "auto"
      ? resolved.paths.length > 0
        ? state.musicPlaylistMode === "chapter_restart"
          ? `章节重启 ${resolved.paths.length} 首`
          : state.musicPlaylistMode === "auto_playlist"
            ? `自动多曲 ${resolved.paths.length} 首`
            : "自动匹配 BGM"
        : "未找到可用音频"
      : musicEnabled
        ? state.musicPlaylistMode === "manual_playlist"
          ? `歌单 ${resolved.paths.length} 首`
          : "已启用 BGM"
        : "未添加 BGM";
  const musicHint =
    state.musicMode === "auto"
      ? resolved.paths.length > 0
        ? state.musicPlaylistMode === "chapter_restart"
          ? `章节重启会按章节切点重新进入推荐曲目：${resolved.labels.slice(0, 3).join(" / ")}${resolved.labels.length > 3 ? " ..." : ""}`
          : state.musicPlaylistMode === "auto_playlist"
            ? `自动模式将按顺序使用 ${resolved.paths.length} 首候选：${resolved.labels.slice(0, 3).join(" / ")}${resolved.labels.length > 3 ? " ..." : ""}`
            : `自动模式将使用：${shortPathName(resolvedMusicPath || "")}`
        : "当前素材目录里还没有可用的 BGM 候选，至少需要一首 15 秒以上的音频文件。"
      : resolved.paths.length > 0
        ? state.musicPlaylistMode === "manual_playlist"
          ? `当前歌单：${resolved.labels.slice(0, 3).join(" / ")}${resolved.labels.length > 3 ? ` 等 ${resolved.labels.length} 首` : ""}`
          : shortPathName(resolvedMusicPath || "")
        : "选择本地音乐后，低清小样和最终视频会听到同一套混音与时长适配策略。";

  return (
    <div className={`music-audio-card${musicEnabled ? " has-music" : ""}`}>
      <div className="music-audio-head">
        <div className="music-audio-title">
          <Music size={18} />
          <div>
            <strong>音乐与原声</strong>
            <span>BGM、视频原声、淡入淡出与长视频适配都在这里统一控制。</span>
          </div>
        </div>
        <span className="music-status-badge">{statusText}</span>
      </div>

      {audioBlueprint ? (
        <div className="music-ai-status-row">
          <span className={sourceAligned ? "active" : ""}>曲目建议 {sourceAligned ? "已生效" : "未完全采纳"}</span>
          <span className={mixAligned ? "active" : ""}>混音建议 {mixAligned ? "已生效" : "未完全采纳"}</span>
          <span className={timingAligned ? "active" : ""}>节奏建议 {timingAligned ? "已生效" : "未完全采纳"}</span>
        </div>
      ) : null}

      <div className="music-mode-buttons">
        <button
          className={state.musicMode === "off" ? "active" : ""}
          type="button"
          onClick={() => state.patch({ musicMode: "off", musicPath: null, musicPlaylistPaths: [], musicPlaylistMode: "single" })}
        >
          无音乐
        </button>
        <button
          className={state.musicMode === "manual" ? "active" : ""}
          type="button"
          onClick={onPickMusicFile}
        >
          手动选择
        </button>
        <button
          className={state.musicMode === "auto" ? "active" : ""}
          type="button"
          onClick={() => state.patch({ musicMode: "auto", musicPath: null, musicPlaylistPaths: [] })}
        >
          自动选择
        </button>
      </div>

      {state.musicMode !== "off" && (
        <div className="music-submode-row">
          <div className={`music-submode-group${sourceAligned ? " ai-aligned" : ""}`}>
            <span>配乐方式</span>
            <div className="music-submode-buttons">
              <button
                className={state.musicPlaylistMode === "single" ? "active" : ""}
                type="button"
                onClick={() => state.patch({ musicPlaylistMode: "single", musicPlaylistPaths: state.musicPlaylistPaths })}
              >
                单曲
              </button>
              <button
                className={state.musicPlaylistMode === "auto_playlist" ? "active" : ""}
                disabled={state.musicMode !== "auto"}
                type="button"
                onClick={() => state.patch({ musicMode: "auto", musicPlaylistMode: "auto_playlist", musicPath: null, musicPlaylistPaths: [] })}
              >
                自动多曲
              </button>
              <button
                className={state.musicPlaylistMode === "chapter_restart" ? "active" : ""}
                disabled={state.musicMode !== "auto"}
                type="button"
                onClick={() => state.patch({ musicMode: "auto", musicPlaylistMode: "chapter_restart", musicPath: null, musicPlaylistPaths: [] })}
              >
                章节重启
              </button>
              <button
                className={state.musicPlaylistMode === "manual_playlist" ? "active" : ""}
                type="button"
                onClick={onPickMusicFiles}
              >
                手动歌单
              </button>
            </div>
          </div>
          <div className={`music-submode-group${timingAligned ? " ai-aligned" : ""}`}>
            <span>时长适配</span>
            <div className="music-fit-select-wrap">
              <select
                disabled={!musicEnabled}
                value={state.musicFitStrategy}
                onChange={(event) => state.patch({ musicFitStrategy: event.target.value as MusicFitStrategy })}
              >
                <option value="auto">自动适配</option>
                <option value="intro_loop_outro">首尾保留，中间循环</option>
                <option value="loop">循环铺满</option>
                <option value="trim">智能裁切</option>
                <option value="once">仅播放一次</option>
              </select>
            </div>
          </div>
        </div>
      )}

      <div className={`music-file-row${sourceAligned ? " ai-aligned" : ""}`}>
        <Volume2 size={16} />
        <span title={resolvedMusicPath || ""}>{musicHint}</span>
        {state.musicPlaylistMode === "manual_playlist" && state.musicMode !== "off" ? (
          <button type="button" onClick={onPickMusicFiles}>管理歌单</button>
        ) : state.musicMode === "manual" ? (
          <button type="button" onClick={onPickMusicFile}>更换</button>
        ) : null}
        {resolved.paths.length > 0 && (
          <button
            type="button"
            onClick={() => state.patch({ musicMode: "off", musicPath: null, musicPlaylistPaths: [], musicPlaylistMode: "single" })}
          >
            移除
          </button>
        )}
      </div>

      {audioBlueprint ? <AudioBlueprintPanel state={state} /> : null}

      {state.musicMode !== "off" && (
        <div className="music-plan-grid">
          <div>
            <strong>预计视频</strong>
            <span>{summary.videoDurationLabel}</span>
          </div>
          <div>
            <strong>音乐总长</strong>
            <span>{summary.musicDurationLabel}</span>
          </div>
          <div>
            <strong>当前策略</strong>
            <span>{summary.strategyLabel}</span>
          </div>
          <div>
            <strong>预计执行</strong>
            <span>{summary.executionLabel}</span>
          </div>
        </div>
      )}

      <div className={`music-slider-grid${mixAligned ? " ai-aligned" : ""}`}>
        <label>
          <span>BGM 音量 <strong>{bgmPercent}%</strong></span>
          <input
            disabled={!musicEnabled}
            max={100}
            min={0}
            type="range"
            value={bgmPercent}
            onChange={(event) => state.patch({ bgmVolume: Number(event.target.value) / 100 })}
          />
        </label>
        <label>
          <span>视频原声 <strong>{sourcePercent}%</strong></span>
          <input
            max={100}
            min={0}
            type="range"
            value={sourcePercent}
            onChange={(event) => state.patch({ sourceAudioVolume: Number(event.target.value) / 100 })}
          />
        </label>
      </div>

      <div className={`music-mix-options${mixAligned ? " ai-aligned" : ""}`}>
        <Toggle
          checked={state.keepSourceAudio}
          label="保留视频原声"
          onChange={(keepSourceAudio) => state.patch({ keepSourceAudio })}
        />
        <Toggle
          checked={state.autoDucking}
          label="有原声时自动压低 BGM"
          onChange={(autoDucking) => state.patch({ autoDucking })}
        />
      </div>

      <div className={`music-fade-grid${timingAligned ? " ai-aligned" : ""}`}>
        <label>
          淡入秒数
          <input
            disabled={!musicEnabled}
            max={10}
            min={0}
            step={0.5}
            type="number"
            value={state.musicFadeInSeconds}
            onChange={(event) => state.patch({ musicFadeInSeconds: Number(event.target.value) })}
          />
        </label>
        <label>
          淡出秒数
          <input
            disabled={!musicEnabled}
            max={20}
            min={0}
            step={0.5}
            type="number"
            value={state.musicFadeOutSeconds}
            onChange={(event) => state.patch({ musicFadeOutSeconds: Number(event.target.value) })}
          />
        </label>
      </div>

      <p className="music-audio-note">
        性能档位只会影响混音执行路径，不会默认牺牲 BGM 存在感、视频原声保留和整体情绪表达；长视频场景下会优先用更稳的 FFmpeg 与缓存路径完成混音。
      </p>
    </div>
  );
}

function resolveMusicSelection(state: StudioState, library: V5MediaLibrary | null, plan: V5RenderPlan | null) {
  const videoDuration = Number(plan?.total_duration || 0);
  const autoMusicAssets = selectAutoMusicAssets(library, videoDuration);
  const autoMusicAsset = autoMusicAssets[0] || null;

  if (state.musicMode === "manual") {
    if (state.musicPlaylistMode === "manual_playlist") {
      const paths = state.musicPlaylistPaths.filter(Boolean);
      return {
        primaryPath: paths[0] || state.musicPath || null,
        paths,
        labels: paths.map((item) => shortPathName(item)),
      };
    }
    const path = state.musicPath || null;
    return {
      primaryPath: path,
      paths: path ? [path] : [],
      labels: path ? [shortPathName(path)] : [],
    };
  }

  if (state.musicMode === "auto") {
    const explicitPaths = state.musicPlaylistPaths.filter(Boolean);
    const explicitPrimary = explicitPaths[0] || null;
    if (state.musicPlaylistMode === "auto_playlist" || state.musicPlaylistMode === "chapter_restart") {
      const paths = explicitPaths.length > 0 ? explicitPaths : autoMusicAssets.map((asset) => asset.absolute_path);
      return {
        primaryPath: explicitPrimary || paths[0] || null,
        paths,
        labels: paths.map((item) => shortPathName(item)),
      };
    }
    if (explicitPrimary) {
      return {
        primaryPath: explicitPrimary,
        paths: [explicitPrimary],
        labels: [shortPathName(explicitPrimary)],
      };
    }
    const assets = autoMusicAsset ? [autoMusicAsset] : [];
    return {
      primaryPath: assets[0]?.absolute_path || null,
      paths: assets.map((asset) => asset.absolute_path),
      labels: assets.map((asset) => asset.file.name || shortPathName(asset.absolute_path)),
    };
  }

  return { primaryPath: null, paths: [], labels: [] };
}

function selectAutoMusicAsset(library: V5MediaLibrary | null): V5Asset | null {
  return selectAutoMusicAssets(library, 0)[0] || null;
}

function selectAutoMusicAssets(library: V5MediaLibrary | null, targetDuration: number): V5Asset[] {
  const audioAssets = (library?.assets || []).filter((asset) => asset.type === "audio" && assetStatusState(asset) !== "error");
  if (audioAssets.length === 0) return [];

  const ranked = audioAssets
    .map((asset) => ({ asset, score: autoMusicScore(asset) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      const durationA = Number(a.asset.media.duration_seconds || 0);
      const durationB = Number(b.asset.media.duration_seconds || 0);
      if (durationB !== durationA) return durationB - durationA;
      return a.asset.relative_path.localeCompare(b.asset.relative_path);
    })
    .map((entry) => entry.asset);

  if (targetDuration <= 0) return ranked.slice(0, 1);
  if (targetDuration < 600) return ranked.slice(0, 1);

  const selected: V5Asset[] = [];
  let totalDuration = 0;
  for (const asset of ranked) {
    selected.push(asset);
    totalDuration += Number(asset.media.duration_seconds || asset.media.duration || 0);
    if (selected.length >= 4 || totalDuration >= targetDuration * 0.72) break;
  }
  return selected.length > 0 ? selected : ranked.slice(0, 1);
}

function autoMusicScore(asset: V5Asset): number {
  const duration = Number(asset.media.duration_seconds || asset.media.duration || 0);
  if (duration < 15) return 0;

  const rawHaystack = `${asset.file.name} ${asset.relative_path}`;
  const haystack = rawHaystack.toLowerCase();
  const ext = asset.file.extension.toLowerCase();
  let score = duration >= 45 ? 12 : 6;

  if (/(^|[^a-z])(bgm|music|soundtrack|instrumental|score|theme|ambient|travel)([^a-z]|$)/.test(haystack)) score += 40;
  if (/配乐|音乐|伴奏|纯音乐|背景音乐|旅拍|轻音乐/.test(rawHaystack)) score += 40;
  if (/effect|sfx|hit|whoosh|click|音效|提示音|转场音/.test(rawHaystack)) score -= 25;
  if (duration >= 90) score += 18;
  else if (duration >= 45) score += 10;
  else if (duration >= 25) score += 4;

  score += {
    ".wav": 6,
    ".m4a": 5,
    ".mp3": 4,
    ".flac": 4,
    ".aac": 3,
    ".ogg": 2,
  }[ext] || 0;

  return score;
}

function buildMusicPlanSummary(state: StudioState, resolved: { paths: string[] }, plan: V5RenderPlan | null) {
  const videoDuration = Number(plan?.total_duration || 0);
  const assetMap = new Map((state.v5Library?.assets || []).map((asset) => [asset.absolute_path, asset]));
  const musicDuration = resolved.paths.reduce((sum, item) => {
    const asset = assetMap.get(item);
    return sum + Number(asset?.media.duration_seconds || asset?.media.duration || 0);
  }, 0);
  const loops = musicDuration > 0 && videoDuration > musicDuration ? Math.ceil(videoDuration / musicDuration) : 1;

  const fitLabel: Record<MusicFitStrategy, string> = {
    auto: "自动适配",
    loop: "循环铺满",
    trim: "智能裁切",
    intro_loop_outro: "首尾保留，中间循环",
    once: "仅播放一次",
  };
  const playlistLabel: Record<string, string> = {
    single: "单曲",
    auto_playlist: "自动多曲",
    manual_playlist: "手动歌单",
  };

  let executionLabel = playlistLabel[state.musicPlaylistMode];
  if (state.musicPlaylistMode === "single") {
    executionLabel = loops > 1 ? `预计循环 ${loops} 次` : "单曲完整使用";
  } else if (resolved.paths.length > 0) {
    executionLabel = `${playlistLabel[state.musicPlaylistMode]} ${resolved.paths.length} 首接力`;
  }

  return {
    videoDurationLabel: formatDurationLabel(videoDuration),
    musicDurationLabel: musicDuration > 0 ? formatDurationLabel(musicDuration) : "待选择",
    strategyLabel: fitLabel[state.musicFitStrategy],
    executionLabel,
  };
}

function buildMusicPlanSummarySafe(state: StudioState, resolved: { paths: string[] }, plan: V5RenderPlan | null) {
  const videoDuration = Number(plan?.total_duration || 0);
  const assetMap = new Map((state.v5Library?.assets || []).map((asset) => [asset.absolute_path, asset]));
  const musicDuration = resolved.paths.reduce((sum, item) => {
    const asset = assetMap.get(item);
    return sum + Number(asset?.media.duration_seconds || asset?.media.duration || 0);
  }, 0);
  const loops = musicDuration > 0 && videoDuration > musicDuration ? Math.ceil(videoDuration / musicDuration) : 1;

  const fitLabel: Record<MusicFitStrategy, string> = {
    auto: "自动适配",
    loop: "循环铺满",
    trim: "智能裁切",
    intro_loop_outro: "首尾保留，中间循环",
    once: "仅播放一次",
  };
  const playlistLabel: Record<MusicPlaylistMode, string> = {
    single: "单曲",
    auto_playlist: "自动多曲",
    manual_playlist: "手动歌单",
    chapter_restart: "章节重启",
  };

  let executionLabel = playlistLabel[state.musicPlaylistMode];
  if (state.musicPlaylistMode === "single") {
    executionLabel = loops > 1 ? `音乐循环 ${loops} 次` : "单曲完整使用";
  } else if (state.musicPlaylistMode === "chapter_restart") {
    executionLabel = resolved.paths.length > 0 ? `章节重启 ${resolved.paths.length} 首轮换` : "按章节切点重新进入";
  } else if (resolved.paths.length > 0) {
    executionLabel = `${playlistLabel[state.musicPlaylistMode]} ${resolved.paths.length} 首接力`;
  }

  return {
    videoDurationLabel: formatDurationLabel(videoDuration),
    musicDurationLabel: musicDuration > 0 ? formatDurationLabel(musicDuration) : "待选择",
    strategyLabel: fitLabel[state.musicFitStrategy],
    executionLabel,
  };
}

export function formatDurationLabel(duration: number): string {
  if (!Number.isFinite(duration) || duration <= 0) return "待生成";
  const totalSeconds = Math.max(0, Math.round(duration));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function assetStatusState(asset: V5Asset): string {
  if (!asset.status) return "ready";
  if (typeof asset.status === "string") return asset.status;
  return asset.status.state || "ready";
}

function clampNumber(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback;
  return Math.min(max, Math.max(min, value));
}
