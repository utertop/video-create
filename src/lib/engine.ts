import { invoke } from "@tauri-apps/api/core";
import { V5_SCHEMA_VERSION } from "./v5Types";
import type {
  AspectRatio,
  EditStrategy,
  PerformanceMode,
  PythonQuality,
  Quality,
  RenderEngine,
  V5Asset,
  V5AudioBlueprint,
  V5AudioSettings,
  V5ChapterBackgroundMode,
  V5DocumentType,
  V5MediaLibrary,
  V5RenderPlan,
  V5RenderSettings,
  V5StoryBlueprint,
  V5Timeline,
  V5TimelinePreviewManifest,
  V5TitleStyle,
} from "./v5Types";

import type {
  AppErrorInfo,
  AppErrorResolution,
  DiagnosticBundlePayload,
  GenerateVideoResult,
  ProjectDocumentsLoadResult,
  ProjectStatePayload,
  RenderRecoverySummary,
  RenderV5Params,
  SessionSnapshotPayload,
  StartupDiagnostics,
  TelemetryEventPayload,
  TelemetrySessionStartResponse,
  TelemetrySettingsPayload,
  TelemetrySummary,
} from "./engineContracts";

export type {
  AppErrorInfo,
  AppErrorResolution,
  BuildReportJsonObject,
  BuildReportSuggestion,
  DiagnosticBundlePayload,
  GenerateVideoResult,
  ProjectDocumentsLoadResult,
  ProjectStatePayload,
  RenderRecoverySummary,
  RenderV5Params,
  SessionSnapshotPayload,
  StartupCheckItem,
  StartupDiagnostics,
  TelemetryCountEntry,
  TelemetryEventPayload,
  TelemetrySessionStartResponse,
  TelemetrySettingsPayload,
  TelemetrySummary,
} from "./engineContracts";

export { V5_SCHEMA_VERSION, V5_TIMELINE_VERSION } from "./v5Types";
export type {
  AspectRatio,
  EditStrategy,
  MusicFitStrategy,
  MusicMode,
  MusicPlaylistMode,
  PerformanceMode,
  PythonQuality,
  Quality,
  RenderEngine,
  V5Asset,
  V5AssetRef,
  V5AssetRole,
  V5AssetType,
  V5AudioBlueprint,
  V5AudioBlueprintAdoptionState,
  V5AudioBlueprintCandidateAsset,
  V5AudioBlueprintCue,
  V5AudioSettings,
  V5CacheEntry,
  V5CachePolicy,
  V5ChapterBackgroundMode,
  V5DirectoryNode,
  V5DirectoryType,
  V5DocumentType,
  V5DurationPolicy,
  V5MediaLibrary,
  V5MotionConfig,
  V5Orientation,
  V5RenderPlan,
  V5RenderSchedulerSummary,
  V5RenderSegment,
  V5RenderSegmentType,
  V5RenderSettings,
  V5RhythmConfig,
  V5SectionBackground,
  V5SectionTitleMode,
  V5StoryBlueprint,
  V5StorySection,
  V5StorySectionType,
  V5Timeline,
  V5TimelineCacheNamespace,
  V5TimelineClip,
  V5TimelineClipCachePolicy,
  V5TimelineClipKind,
  V5TimelineClipSourceRef,
  V5TimelineContentRef,
  V5TimelineDependency,
  V5TimelineDependencyKind,
  V5TimelineEditState,
  V5TimelineExecutionHint,
  V5TimelineInvalidationHint,
  V5TimelineMetadata,
  V5TimelinePerformancePolicy,
  V5TimelinePresentation,
  V5TimelinePreviewArtifact,
  V5TimelinePreviewManifest,
  V5TimelinePreviewManifestClip,
  V5TimelinePreviewMode,
  V5TimelinePreviewQualityProfile,
  V5TimelineProjectRef,
  V5TimelineRecomputeScope,
  V5TimelineSourceRef,
  V5TimelineTrack,
  V5TimelineTrackKind,
  V5TimelineVersion,
  V5TitleMotion,
  V5TitlePreset,
  V5TitleStyle,
  V5TransitionConfig,
} from "./v5Types";

export async function cancelVideo(jobId: string): Promise<GenerateVideoResult> {
  try {
    return await invoke<GenerateVideoResult>("cancel_video", { jobId });
  } catch (error) {
    return {
      ok: false,
      message: formatInvokeError(error, "无法取消任务：Tauri 后端尚未响应。"),
      commandPreview: "",
    };
  }
}

export async function openInExplorer(path: string): Promise<void> {
  try {
    await invoke("open_in_explorer", { path });
  } catch (error) {
    console.error("Failed to open in explorer:", error);
  }
}

export async function startupSelfCheck(): Promise<StartupDiagnostics> {
  try {
    return await invoke<StartupDiagnostics>("startup_self_check");
  } catch (error) {
    return {
      ok: false,
      summary: formatInvokeError(error, "Startup self-check is unavailable."),
      checks: [
        {
          id: "startup_self_check",
          label: "Startup self-check",
          ok: false,
          message: formatInvokeError(error, "Tauri backend did not respond."),
          detail: null,
        },
      ],
    };
  }
}

export async function preflightRenderV5({
  inputFolder,
  outputDir,
  planPath,
  outputPath,
}: {
  inputFolder: string;
  outputDir: string;
  planPath: string;
  outputPath: string;
}): Promise<StartupDiagnostics> {
  try {
    return await invoke<StartupDiagnostics>("preflight_render_v5", {
      inputFolder,
      outputDir,
      planPath,
      outputPath,
    });
  } catch (error) {
    return {
      ok: false,
      summary: formatInvokeError(error, "渲染前预检不可用。"),
      checks: [
        {
          id: "preflight_render_v5",
          label: "渲染前预检",
          ok: false,
          message: formatInvokeError(error, "Tauri 后端未响应。"),
          detail: null,
        },
      ],
    };
  }
}

export async function saveSessionSnapshot(snapshot: SessionSnapshotPayload): Promise<void> {
  await invoke("save_session_snapshot", { snapshotJson: JSON.stringify(snapshot) });
}

export async function loadSessionSnapshot(): Promise<SessionSnapshotPayload | null> {
  const raw = await invoke<string | null>("load_session_snapshot");
  if (!raw) return null;
  const parsed = JSON.parse(raw) as SessionSnapshotPayload;
  if (!parsed || typeof parsed !== "object" || typeof parsed.savedAt !== "string" || !parsed.data || typeof parsed.data !== "object") {
    throw new Error("会话快照格式无效。");
  }
  return parsed;
}

export async function clearSessionSnapshot(): Promise<void> {
  await invoke("clear_session_snapshot");
}

export async function saveProjectState(projectDir: string, payload: ProjectStatePayload): Promise<void> {
  await invoke("save_project_state", {
    projectDir,
    payloadJson: JSON.stringify(payload),
  });
}

export async function loadProjectState(projectDir: string): Promise<ProjectStatePayload | null> {
  const raw = await invoke<string | null>("load_project_state", { projectDir });
  if (!raw) return null;
  return parseSnapshotPayload<ProjectStatePayload>(raw, "project state");
}

export async function exportDiagnosticBundle(outputPath: string, payload: DiagnosticBundlePayload): Promise<string> {
  return await invoke<string>("export_diagnostic_bundle", {
    outputPath,
    payloadJson: JSON.stringify(payload, null, 2),
  });
}

export async function loadProjectDocumentsV5(projectDir: string): Promise<ProjectDocumentsLoadResult> {
  const payload = await invoke<{
    projectDir: string;
    migrated: boolean;
    migrationNotes?: string[] | null;
    library?: unknown;
    blueprint?: unknown;
    renderPlan?: unknown;
    render_plan?: unknown;
    timeline?: unknown;
    timelinePreviewManifest?: unknown;
    timeline_preview_manifest?: unknown;
  }>("load_project_documents_v5", { projectDir });

  return {
    projectDir: payload.projectDir,
    migrated: Boolean(payload.migrated),
    migrationNotes: Array.isArray(payload.migrationNotes) ? payload.migrationNotes.filter((item): item is string => typeof item === "string") : [],
    library: payload.library ? parseV5Value<V5MediaLibrary>(payload.library, "media_library") : null,
    blueprint: payload.blueprint ? parseV5Value<V5StoryBlueprint>(payload.blueprint, "story_blueprint") : null,
    renderPlan: (payload.renderPlan || payload.render_plan) ? parseV5Value<V5RenderPlan>(payload.renderPlan || payload.render_plan, "render_plan") : null,
    timeline: payload.timeline ? parseV5Value<V5Timeline>(payload.timeline, "timeline") : null,
    timelinePreviewManifest: (payload.timelinePreviewManifest || payload.timeline_preview_manifest)
      ? parseV5Value<V5TimelinePreviewManifest>(payload.timelinePreviewManifest || payload.timeline_preview_manifest, "timeline_preview_manifest")
      : null,
  };
}

export async function loadBuildReportSummary(projectDir: string): Promise<RenderRecoverySummary> {
  return await invoke<RenderRecoverySummary>("load_build_report_summary", { projectDir });
}

export async function startTelemetrySession(telemetryEnabled: boolean): Promise<TelemetrySessionStartResponse> {
  return await invoke<TelemetrySessionStartResponse>("start_telemetry_session", { telemetryEnabled });
}

export async function finishTelemetrySession(sessionId: string, cleanExit: boolean): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("finish_telemetry_session", { sessionId, cleanExit });
}

export async function recordTelemetryEvent(payload: TelemetryEventPayload): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("record_telemetry_event", {
    payloadJson: JSON.stringify(payload),
  });
}

export async function loadTelemetrySummary(): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("load_telemetry_summary");
}

export async function clearTelemetryHistory(): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("clear_telemetry_history");
}

export async function updateTelemetrySettings(payload: TelemetrySettingsPayload): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("update_telemetry_settings", {
    payloadJson: JSON.stringify(payload),
  });
}

export async function flushRemoteTelemetryQueue(): Promise<TelemetrySummary> {
  return await invoke<TelemetrySummary>("flush_remote_telemetry_queue");
}

// =========================
// V5 engine calls
// =========================

/** Scan a folder and return Media Library JSON. V5.1 writes project JSON into projectDir. */
export async function scanV5(inputFolder: string, projectDir?: string, recursive: boolean = true): Promise<V5MediaLibrary> {
  const jsonStr = await invoke<string>("scan_v5", { inputFolder, projectDir: projectDir || null, recursive });
  return parseV5Json<V5MediaLibrary>(jsonStr, "media_library");
}

/** Generate a Story Blueprint from a Media Library JSON file. */
export async function planV5(libraryPath: string, outputPath?: string): Promise<V5StoryBlueprint> {
  const jsonStr = await invoke<string>("plan_v5", { libraryPath, outputPath: outputPath || null });
  return parseV5Json<V5StoryBlueprint>(jsonStr, "story_blueprint");
}

/** Save edited Story Blueprint JSON to disk. */
export async function saveBlueprintV5(path: string, content: string): Promise<void> {
  await invoke("save_blueprint_v5", { path, content });
}

/** Compile Story Blueprint + Media Library into Render Plan. */
export async function compileV5(blueprintPath: string, libraryPath: string, outputPath?: string): Promise<V5RenderPlan> {
  const jsonStr = await invoke<string>("compile_v5", { blueprintPath, libraryPath, outputPath: outputPath || null });
  return parseV5Json<V5RenderPlan>(jsonStr, "render_plan");
}

export async function saveTimelineV5(path: string, content: string): Promise<void> {
  await invoke("save_timeline_v5", { path, content });
}

export async function timelineGenerateV5({
  renderPlanPath,
  outputPath,
  blueprintPath,
  libraryPath,
  existingTimelinePath,
  projectDir,
}: {
  renderPlanPath: string;
  outputPath: string;
  blueprintPath?: string | null;
  libraryPath?: string | null;
  existingTimelinePath?: string | null;
  projectDir?: string | null;
}): Promise<V5Timeline> {
  const jsonStr = await invoke<string>("timeline_generate_v5", {
    renderPlanPath,
    outputPath,
    blueprintPath: blueprintPath || null,
    libraryPath: libraryPath || null,
    existingTimelinePath: existingTimelinePath || null,
    projectDir: projectDir || null,
  });
  return parseV5Json<V5Timeline>(jsonStr, "timeline");
}

export async function timelineCompileV5(timelinePath: string, baseRenderPlanPath: string, outputPath: string): Promise<V5RenderPlan> {
  const jsonStr = await invoke<string>("timeline_compile_v5", { timelinePath, baseRenderPlanPath, outputPath });
  return parseV5Json<V5RenderPlan>(jsonStr, "render_plan");
}

export async function timelinePreviewManifestV5({
  timelinePath,
  outputPath,
  libraryPath,
  proxyManifestPath,
  projectDir,
}: {
  timelinePath: string;
  outputPath: string;
  libraryPath?: string | null;
  proxyManifestPath?: string | null;
  projectDir?: string | null;
}): Promise<V5TimelinePreviewManifest> {
  const jsonStr = await invoke<string>("timeline_preview_manifest_v5", {
    timelinePath,
    outputPath,
    libraryPath: libraryPath || null,
    proxyManifestPath: proxyManifestPath || null,
    projectDir: projectDir || null,
  });
  return parseV5Json<V5TimelinePreviewManifest>(jsonStr, "timeline_preview_manifest");
}

export async function timelinePreviewAssetsV5({
  timelinePath,
  outputPath,
  libraryPath,
  proxyManifestPath,
  projectDir,
  batchSize = 8,
}: {
  timelinePath: string;
  outputPath: string;
  libraryPath?: string | null;
  proxyManifestPath?: string | null;
  projectDir?: string | null;
  batchSize?: number;
}): Promise<V5TimelinePreviewManifest> {
  const jsonStr = await invoke<string>("timeline_preview_assets_v5", {
    timelinePath,
    outputPath,
    libraryPath: libraryPath || null,
    proxyManifestPath: proxyManifestPath || null,
    projectDir: projectDir || null,
    batchSize,
  });
  return parseV5Json<V5TimelinePreviewManifest>(jsonStr, "timeline_preview_manifest");
}

/** Execute final V5 render. */
export async function renderV5(planPath: string, outputPath: string, params: RenderV5Params, jobId?: string): Promise<void> {
  await invoke("render_v5", {
    planPath,
    outputPath,
    paramsJson: JSON.stringify(params),
    jobId: jobId || null,
  });
}

/** Render a short, real low-resolution preview from the same V5 render plan. */
export async function previewRenderV5({
  planPath,
  params,
  maxDuration = 20,
  maxSegments = 8,
  height = 540,
  fps = 15,
}: {
  planPath: string;
  params: RenderV5Params;
  maxDuration?: number;
  maxSegments?: number;
  height?: number;
  fps?: number;
}): Promise<string> {
  return await invoke<string>("preview_render_v5", {
    planPath,
    paramsJson: JSON.stringify(params),
    maxDuration,
    maxSegments,
    height,
    fps,
  });
}

/** Render a short low-resolution MP4 using the real Python/MoviePy title renderer. */
export async function previewTitleV5({
  title,
  subtitle,
  style,
  aspectRatio = "16:9",
  background = "travel",
}: {
  title: string;
  subtitle?: string | null;
  style: V5TitleStyle;
  aspectRatio?: AspectRatio | "1:1";
  background?: string;
}): Promise<string> {
  return await invoke<string>("preview_title_v5", {
    title,
    subtitle: subtitle || null,
    styleJson: JSON.stringify(style),
    aspectRatio,
    background,
  });
}

// =========================
// Command preview helpers
// =========================

export function buildV5RenderCommandPreview({
  planPath,
  outputPath,
  params,
}: {
  planPath: string;
  outputPath: string;
  params?: RenderV5Params;
}): string {
  const args = [
    "python",
    "video_engine_v5.py",
    "render",
    "--plan",
    quote(planPath),
    "--output",
    quote(outputPath),
  ];

  if (params && Object.keys(params).length > 0) {
    args.push("--params", quote(JSON.stringify(params)));
  }

  return args.join(" ");
}

function quote(value: string): string {
  return `"${value.split('"').join('\\"')}"`;
}

function parseSnapshotPayload<T extends { savedAt?: string; data?: Record<string, unknown> }>(
  raw: string,
  label: string,
): T {
  const parsed = JSON.parse(raw) as T;
  if (!parsed || typeof parsed !== "object" || typeof parsed.savedAt !== "string" || !parsed.data || typeof parsed.data !== "object") {
    throw new Error(`${label} payload is invalid.`);
  }
  return parsed;
}

function parseV5Json<T extends { document_type?: V5DocumentType; schema_version?: string }>(
  jsonStr: string,
  expectedType: V5DocumentType,
): T {
  let parsed: unknown;

  try {
    parsed = JSON.parse(jsonStr);
  } catch (error) {
    throw new Error(`V5 JSON 解析失败：${formatUnknownError(error)}`);
  }

  return parseV5Value<T>(parsed, expectedType);
}

function parseV5Value<T extends { document_type?: V5DocumentType; schema_version?: string }>(
  parsed: unknown,
  expectedType: V5DocumentType,
): T {
  const migrated = migrateV5Document(parsed, expectedType);

  if (!migrated || typeof migrated !== "object") {
    throw new Error(`V5 返回结果不是有效对象，期望 document_type=${expectedType}`);
  }

  const doc = migrated as { document_type?: unknown; schema_version?: unknown };
  if (doc.document_type !== expectedType) {
    throw new Error(`V5 返回 document_type 不匹配：期望 ${expectedType}，实际 ${String(doc.document_type)}`);
  }

  if (typeof doc.schema_version !== "string" || doc.schema_version.length === 0) {
    throw new Error(`V5 返回结果缺少 schema_version，document_type=${expectedType}`);
  }

  return migrated as T;
}

function migrateV5Document(parsed: unknown, expectedType: V5DocumentType): unknown {
  if (!parsed || typeof parsed !== "object") return parsed;
  const doc = structuredClone(parsed) as Record<string, unknown>;
  if (doc.document_type !== expectedType) return parsed;

  if (expectedType === "media_library") {
    if (!doc.project || typeof doc.project !== "object") doc.project = {};
    const project = doc.project as Record<string, unknown>;
    if (!("project_title" in project)) project.project_title = null;
    if (!Array.isArray(doc.directory_nodes)) doc.directory_nodes = [];
    if (!Array.isArray(doc.assets)) doc.assets = [];
    if (!doc.summary || typeof doc.summary !== "object") doc.summary = {};
    for (const asset of doc.assets as Record<string, unknown>[]) {
      if (!asset || typeof asset !== "object") continue;
      if (asset.thumbnail_path == null && asset.thumbnail != null) asset.thumbnail_path = asset.thumbnail;
      if (asset.thumbnail == null && asset.thumbnail_path != null) asset.thumbnail = asset.thumbnail_path;
      if (asset.status == null) asset.status = "ready";
    }
  } else if (expectedType === "story_blueprint") {
    if (typeof doc.subtitle !== "string") doc.subtitle = String(doc.subtitle || "");
    if (!Array.isArray(doc.sections)) doc.sections = [];
    if (!doc.metadata || typeof doc.metadata !== "object") doc.metadata = {};
    const metadata = doc.metadata as Record<string, unknown>;
    if (metadata.chapter_background_mode == null) metadata.chapter_background_mode = "auto_bridge";
    migrateStorySections(doc.sections as Record<string, unknown>[]);
  } else if (expectedType === "render_plan") {
    if (!Array.isArray(doc.segments)) doc.segments = [];
    if (typeof doc.output_path !== "string") doc.output_path = "";
    for (const segment of doc.segments as Record<string, unknown>[]) {
      if (!segment || typeof segment !== "object") continue;
      if (!Array.isArray(segment.render_route_tags)) segment.render_route_tags = [];
    }
  }

  doc.schema_version = V5_SCHEMA_VERSION;
  return doc;
}

function migrateStorySections(sections: Record<string, unknown>[]) {
  for (const section of sections) {
    if (!section || typeof section !== "object") continue;
    if (!Array.isArray(section.asset_refs)) section.asset_refs = [];
    if (!Array.isArray(section.children)) section.children = [];
    migrateStorySections(section.children as Record<string, unknown>[]);
  }
}

export function parseAppError(error: unknown): AppErrorInfo {
  const raw = formatUnknownError(error);
  const match = raw.match(/^\[([A-Z0-9_]+)\]\s*(.*)$/s);
  if (match) {
    const guidance = errorGuidanceForCode(match[1]);
    return {
      code: match[1],
      message: match[2] || match[1],
      userMessage: guidance?.userMessage || null,
      actionSuggestion: guidance?.actionSuggestion || null,
      raw,
    };
  }
  return {
    code: null,
    message: raw || "未知错误",
    userMessage: null,
    actionSuggestion: null,
    raw,
  };
}

export function resolveAppError(error: unknown): AppErrorResolution {
  const parsed = parseAppError(error);
  const guidance = parsed.code ? errorGuidanceForCode(parsed.code) : null;
  const fallback = fallbackErrorResolution(parsed.message);
  return {
    code: parsed.code || null,
    technicalMessage: parsed.message,
    userMessage: guidance?.userMessage || fallback.userMessage,
    actionSuggestion: guidance?.actionSuggestion || fallback.actionSuggestion || null,
  };
}

function errorGuidanceForCode(code: string): { userMessage: string; actionSuggestion?: string } | null {
  const map: Record<string, { userMessage: string; actionSuggestion?: string }> = {
    E_OUTPUT_DIR_REQUIRED: {
      userMessage: "缺少输出目录：请先选择输出目录后再继续。",
      actionSuggestion: "在“生成参数”区域选择一个明确可写的输出目录。",
    },
    E_OUTPUT_NOT_WRITABLE: {
      userMessage: "输出目录不可写：请换到桌面、文档或其他可写目录后重试。",
      actionSuggestion: "避免写入系统目录、只读目录或云盘受限目录。",
    },
    E_MEDIA_SOURCE_MISSING: {
      userMessage: "素材缺失：请确认素材没有被移动或删除，然后重新扫描并编译。",
      actionSuggestion: "恢复原素材路径，或重新扫描素材并重新生成 render_plan.json。",
    },
    E_RENDER_PLAN_INVALID_JSON: {
      userMessage: "渲染计划损坏：请重新确认蓝图并生成新的 render_plan.json。",
      actionSuggestion: "不要手工修改 render_plan.json；若已修改，请重新编译。",
    },
    E_PROJECT_DIR_MISSING: {
      userMessage: "项目目录不存在：最近项目对应的 .video_create_project 已丢失或不可访问。",
      actionSuggestion: "确认输出目录仍在原位置；若已丢失，请重新扫描素材创建新项目。",
    },
    E_PROJECT_DOC_INVALID_JSON: {
      userMessage: "项目文档损坏：项目 JSON 无法解析，建议重新扫描和编译。",
      actionSuggestion: "优先保留仍可读取的 JSON，损坏文件建议重新生成。",
    },
    E_PROJECT_DOC_TYPE_MISMATCH: {
      userMessage: "项目文档类型异常：项目目录中的 JSON 与当前步骤不匹配。",
      actionSuggestion: "检查 media_library.json、story_blueprint.json、render_plan.json 是否被错误覆盖。",
    },
    E_PROJECT_DOC_REWRITE_FAILED: {
      userMessage: "项目迁移失败：旧项目已识别，但无法写回迁移结果。",
      actionSuggestion: "确认 .video_create_project 可写后，再重新恢复最近项目。",
    },
    E_WORKER_ENTRYPOINT_MISSING: {
      userMessage: "Worker 不可用：请先运行 npm run check，确认桌面 worker 已正确打包。",
      actionSuggestion: "重点检查打包资源、src-tauri/bin 和安装目录完整性。",
    },
    E_WORKER_HEALTH_FAILED: {
      userMessage: "Worker 健康检查失败：请先运行 npm run check，确认渲染依赖正常。",
      actionSuggestion: "重点查看 FFmpeg、Python worker、编码器检测和环境权限。",
    },
    E_TASK_ALREADY_RUNNING: {
      userMessage: "已有渲染任务正在运行，请等待完成或先取消当前任务。",
      actionSuggestion: "查看渲染队列，避免重复点击“开始渲染”。",
    },
    E_TASK_CANCELLED: {
      userMessage: "渲染已取消。",
      actionSuggestion: "如果不是主动取消，请导出诊断包并检查最近日志。",
    },
    E_STARTUP_CHECK_FAILED: {
      userMessage: "启动自检未通过：请先修复自检卡中的失败项。",
      actionSuggestion: "优先处理 worker、资源文件和可写目录相关问题。",
    },
    E_PREFLIGHT_CHECK_FAILED: {
      userMessage: "渲染前预检未通过：请先修复预检卡中的失败项。",
      actionSuggestion: "优先处理输出目录、render_plan.json 和素材缺失问题。",
    },
  };
  return map[code] || null;
}

function fallbackErrorResolution(message: string): { userMessage: string; actionSuggestion?: string } {
  const lower = message.toLowerCase();
  if (lower.includes("permission") || message.includes("拒绝访问") || message.includes("access is denied")) {
    return {
      userMessage: "权限不足：请确认素材目录和输出目录可读写。",
      actionSuggestion: "必要时换到桌面或文档目录后重试。",
    };
  }
  if (lower.includes("no such file") || message.includes("系统找不到") || message.includes("找不到")) {
    return {
      userMessage: "文件缺失：请确认素材没有被移动或删除。",
      actionSuggestion: "重新扫描素材并生成新的渲染计划。",
    };
  }
  if (lower.includes("moviepy") || lower.includes("ffmpeg") || lower.includes("pyinstaller")) {
    return {
      userMessage: "渲染依赖异常：请先运行 npm run check。",
      actionSuggestion: "确认 Python worker、MoviePy 和 FFmpeg 都可用。",
    };
  }
  if (lower.includes("json") || lower.includes("render_plan")) {
    return {
      userMessage: "渲染计划异常：请重新确认故事蓝图。",
      actionSuggestion: "重新生成 render_plan.json 后再试。",
    };
  }
  if (lower.includes("cancel")) {
    return {
      userMessage: "渲染已取消。",
      actionSuggestion: "如非主动取消，请导出诊断包继续排查。",
    };
  }
  return {
    userMessage: message || "发生未知错误，请查看日志。",
    actionSuggestion: "如问题可复现，请导出诊断包并附带错误截图。",
  };
}

function formatInvokeError(error: unknown, fallback: string): string {
  const parsed = parseAppError(error);
  const detail = parsed.message;
  return detail ? `${fallback} ${detail}` : fallback;
}

function formatUnknownError(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (error == null) return "";
  try {
    return JSON.stringify(error);
  } catch {
    return String(error);
  }
}
