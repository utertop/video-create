export interface DiagnosticCheckLike {
  id: string;
  label: string;
  ok: boolean;
  code?: string | null;
  message: string;
  detail?: string | null;
}

export interface DiagnosticStartupLike {
  ok: boolean;
  code?: string | null;
  summary: string;
  checks: DiagnosticCheckLike[];
}

export interface DiagnosticResultLike {
  ok: boolean;
  code?: string | null;
  message: string;
  commandPreview?: string;
}

export interface DiagnosticRecoveryLike {
  reportPath?: string | null;
  manifestPath?: string | null;
  status?: string | null;
  renderMode?: string | null;
  failedStage?: string | null;
  outputPath?: string | null;
  selectedBackend?: string | null;
  chunkCount?: number | null;
  createdAt?: string | null;
  resumable?: boolean;
  resumedFromManifest?: boolean;
  reusedChunkCount?: number;
  completedChunkCount?: number;
  failedChunkCount?: number;
  reportedChunkCount?: number;
  failedChunk?: string | null;
  failureCode?: string | null;
  failureMessage?: string | null;
  retryable?: boolean;
}

export interface ErrorCodeSummaryEntry {
  code: string;
  count: number;
  sources: string[];
  messages: string[];
  actionSuggestions: string[];
}

export interface ErrorCodeStats {
  totalOccurrences: number;
  uniqueCodes: number;
  topCodes: Array<{
    code: string;
    count: number;
  }>;
}

export interface SupportCaseSummary {
  severity: "info" | "warning" | "high";
  category: string;
  queue: string;
  tags: string[];
  recommendedNextStep: string;
  customerSummary: string;
}

export interface DiagnosticTelemetryLike {
  telemetryEnabled: boolean;
  currentConsentVersion?: string | null;
  consentAcceptedVersion?: string | null;
  remoteUploadEnabled?: boolean;
  remoteEndpointConfigured?: boolean;
  remoteEndpoint?: string | null;
  remoteEndpointHost?: string | null;
  pendingRemoteEvents?: number;
  lastRemoteUploadAt?: string | null;
  lastRemoteUploadError?: string | null;
  sessionsStarted: number;
  sessionsCompletedCleanly: number;
  sessionsCrashed: number;
  crashFreeSessionRate: number;
  firstExportSessions: number;
  firstExportSuccesses: number;
  firstExportSuccessRate: number;
  renderAttempts: number;
  renderSuccesses: number;
  renderFailures: number;
  recoveryResumableEvents: number;
  recoveryRetryableEvents: number;
  topErrorCodes: Array<{ key: string; count: number }>;
  topSupportQueues: Array<{ key: string; count: number }>;
  topTags: Array<{ key: string; count: number }>;
  topSeverities: Array<{ key: string; count: number }>;
  lastUpdatedAt?: string | null;
}

export interface DiagnosticBundleSections {
  app: Record<string, unknown>;
  project: Record<string, unknown>;
  upgrade: Record<string, unknown>;
  workflow: Record<string, unknown>;
  runtime: Record<string, unknown>;
  sessionDraft: unknown;
}

export interface DiagnosticBundlePayload {
  generatedAt: string;
  data: Record<string, unknown> & DiagnosticBundleSections & {
    diagnostics: {
      startup: DiagnosticStartupLike | null;
      preflight: DiagnosticStartupLike | null;
      recoverySummary: DiagnosticRecoveryLike | null;
      errorCodeSummary: ErrorCodeSummaryEntry[];
      errorCodeStats: ErrorCodeStats;
      errorCodeReport: string;
      supportCase: SupportCaseSummary;
      supportCaseReport: string;
      telemetrySummary: DiagnosticTelemetryLike | null;
      telemetryReport: string | null;
    };
  };
}

function normalizeRecoverySummary(recovery: DiagnosticRecoveryLike | null | undefined): DiagnosticRecoveryLike | null {
  if (!recovery || typeof recovery !== "object") return null;
  return {
    reportPath: typeof recovery.reportPath === "string" ? recovery.reportPath : null,
    manifestPath: typeof recovery.manifestPath === "string" ? recovery.manifestPath : null,
    status: typeof recovery.status === "string" ? recovery.status : null,
    renderMode: typeof recovery.renderMode === "string" ? recovery.renderMode : null,
    failedStage: typeof recovery.failedStage === "string" ? recovery.failedStage : null,
    outputPath: typeof recovery.outputPath === "string" ? recovery.outputPath : null,
    selectedBackend: typeof recovery.selectedBackend === "string" ? recovery.selectedBackend : null,
    chunkCount: typeof recovery.chunkCount === "number" ? recovery.chunkCount : null,
    createdAt: typeof recovery.createdAt === "string" ? recovery.createdAt : null,
    resumable: Boolean(recovery.resumable),
    resumedFromManifest: Boolean(recovery.resumedFromManifest),
    reusedChunkCount: Number(recovery.reusedChunkCount || 0),
    completedChunkCount: Number(recovery.completedChunkCount || 0),
    failedChunkCount: Number(recovery.failedChunkCount || 0),
    reportedChunkCount: Number(recovery.reportedChunkCount || 0),
    failedChunk: typeof recovery.failedChunk === "string" ? recovery.failedChunk : null,
    failureCode: typeof recovery.failureCode === "string" ? recovery.failureCode : null,
    failureMessage: typeof recovery.failureMessage === "string" ? recovery.failureMessage : null,
    retryable: Boolean(recovery.retryable),
  };
}

export function buildSupportCaseSummary({
  summary,
  stats,
  result,
  recovery,
  startupDiagnostics,
  preflightDiagnostics,
}: {
  summary: ErrorCodeSummaryEntry[];
  stats: ErrorCodeStats;
  result: DiagnosticResultLike | null;
  recovery?: DiagnosticRecoveryLike | null;
  startupDiagnostics: DiagnosticStartupLike | null;
  preflightDiagnostics: DiagnosticStartupLike | null;
}): SupportCaseSummary {
  const normalizedRecovery = normalizeRecoverySummary(recovery);
  const topCode = summary[0]?.code || result?.code || null;
  const tags = new Set<string>();
  for (const entry of summary.slice(0, 5)) tags.add(entry.code);
  if (normalizedRecovery?.resumable) tags.add("resumable");
  if (normalizedRecovery?.retryable) tags.add("retryable");
  if (normalizedRecovery?.reusedChunkCount) tags.add("partial-reuse");
  if (normalizedRecovery?.renderMode) tags.add(String(normalizedRecovery.renderMode));
  if (normalizedRecovery?.failedStage) tags.add(`stage:${normalizedRecovery.failedStage}`);

  let severity: SupportCaseSummary["severity"] = "info";
  let category = "general";
  let queue = "general-triage";
  let recommendedNextStep = "Review the diagnostic bundle and route the case to the general support queue.";
  let customerSummary = "Diagnostic bundle exported successfully.";

  if (startupDiagnostics && !startupDiagnostics.ok) {
    severity = "high";
    category = "startup-environment";
    queue = "environment";
    recommendedNextStep = "Prioritize startup self-check failures and verify worker, Python, FFmpeg, and bundled resources.";
    customerSummary = "Startup environment checks failed before rendering could begin.";
  } else if (preflightDiagnostics && !preflightDiagnostics.ok) {
    severity = "warning";
    category = "preflight-validation";
    queue = "project-validation";
    recommendedNextStep = "Fix preflight issues first, especially missing assets, invalid plans, or unwritable output paths.";
    customerSummary = "Render preflight blocked the export because required inputs or paths were not ready.";
  }

  if (topCode === "E_MEDIA_SOURCE_MISSING") {
    severity = "warning";
    category = "missing-media";
    queue = "input-assets";
    recommendedNextStep = "Restore missing media paths or rescan the project before rerunning render.";
    customerSummary = "One or more source assets disappeared after the project was compiled.";
  } else if (topCode === "E_DIRECTORY_NOT_WRITABLE" || topCode === "E_OUTPUT_NOT_WRITABLE") {
    severity = "warning";
    category = "filesystem-permission";
    queue = "filesystem";
    recommendedNextStep = "Move the output to a writable local directory and verify permission or sync-lock issues.";
    customerSummary = "The project could not write to the selected output location.";
  } else if (topCode?.startsWith("E_WORKER_")) {
    severity = "high";
    category = "worker-runtime";
    queue = "environment";
    recommendedNextStep = "Validate worker packaging, health probe output, and local runtime dependencies.";
    customerSummary = "The local render worker was unavailable or unhealthy.";
  } else if (topCode?.startsWith("E_PROJECT_DOC_") || topCode === "E_RENDER_PLAN_INVALID_JSON") {
    severity = "warning";
    category = "project-data";
    queue = "project-recovery";
    recommendedNextStep = "Recover or regenerate project JSON files and preserve the broken copy for support analysis.";
    customerSummary = "Project metadata or render plan files were damaged or incompatible.";
  }

  if (normalizedRecovery?.resumable && normalizedRecovery.retryable && !result?.ok) {
    severity = severity === "high" ? "high" : "warning";
    category = "render-recovery";
    queue = "render-recovery";
    const completedChunks = normalizedRecovery.completedChunkCount ?? 0;
    recommendedNextStep = `Use resume retry first; ${completedChunks} chunks are already complete and can be reused.`;
    customerSummary = completedChunks > 0
      ? `Stable render can resume from ${completedChunks} completed chunks.`
      : "Stable render can resume without restarting the full export.";
  }

  if (stats.totalOccurrences === 0 && result?.ok) {
    customerSummary = "No coded errors were captured in this diagnostic bundle.";
  }

  return {
    severity,
    category,
    queue,
    tags: Array.from(tags).sort(),
    recommendedNextStep,
    customerSummary,
  };
}

export function formatSupportCaseReport(summary: SupportCaseSummary): string {
  return [
    "Support Case Summary",
    `Severity: ${summary.severity}`,
    `Category: ${summary.category}`,
    `Queue: ${summary.queue}`,
    `Tags: ${summary.tags.length > 0 ? summary.tags.join(", ") : "none"}`,
    `Customer summary: ${summary.customerSummary}`,
    `Recommended next step: ${summary.recommendedNextStep}`,
  ].join("\n");
}

export function summarizeErrorCodes({
  startupDiagnostics,
  preflightDiagnostics,
  result,
  resultActionSuggestion,
}: {
  startupDiagnostics: DiagnosticStartupLike | null;
  preflightDiagnostics: DiagnosticStartupLike | null;
  result: DiagnosticResultLike | null;
  resultActionSuggestion?: string | null;
}): ErrorCodeSummaryEntry[] {
  const summary = new Map<string, ErrorCodeSummaryEntry>();

  const push = ({
    code,
    source,
    message,
    actionSuggestion,
  }: {
    code: string | null | undefined;
    source: string;
    message?: string | null;
    actionSuggestion?: string | null;
  }) => {
    if (!code) return;
    const current = summary.get(code) || {
      code,
      count: 0,
      sources: [],
      messages: [],
      actionSuggestions: [],
    };
    current.count += 1;
    if (!current.sources.includes(source)) current.sources.push(source);
    if (message && !current.messages.includes(message)) current.messages.push(message);
    if (actionSuggestion && !current.actionSuggestions.includes(actionSuggestion)) {
      current.actionSuggestions.push(actionSuggestion);
    }
    summary.set(code, current);
  };

  push({
    code: startupDiagnostics?.code,
    source: "startup",
    message: startupDiagnostics?.summary,
  });
  for (const check of startupDiagnostics?.checks || []) {
    push({
      code: check.code,
      source: `startup_check:${check.id}`,
      message: `${check.label}: ${check.message}`,
    });
  }

  push({
    code: preflightDiagnostics?.code,
    source: "preflight",
    message: preflightDiagnostics?.summary,
  });
  for (const check of preflightDiagnostics?.checks || []) {
    push({
      code: check.code,
      source: `preflight_check:${check.id}`,
      message: `${check.label}: ${check.message}`,
    });
  }

  push({
    code: result?.code,
    source: "result",
    message: result?.message,
    actionSuggestion: resultActionSuggestion,
  });

  return Array.from(summary.values()).sort((left, right) => {
    if (right.count !== left.count) return right.count - left.count;
    return left.code.localeCompare(right.code);
  });
}

export function buildErrorCodeStats(summary: ErrorCodeSummaryEntry[]): ErrorCodeStats {
  const totalOccurrences = summary.reduce((total, entry) => total + entry.count, 0);
  return {
    totalOccurrences,
    uniqueCodes: summary.length,
    topCodes: summary.slice(0, 5).map((entry) => ({
      code: entry.code,
      count: entry.count,
    })),
  };
}

export function formatErrorCodeReport(
  summary: ErrorCodeSummaryEntry[],
  stats: ErrorCodeStats = buildErrorCodeStats(summary),
): string {
  if (summary.length === 0) {
    return [
      "Error Code Summary",
      "Total coded events: 0",
      "Unique codes: 0",
      "No startup, preflight, or render error codes were captured in this diagnostic bundle.",
    ].join("\n");
  }

  const lines = [
    "Error Code Summary",
    `Total coded events: ${stats.totalOccurrences}`,
    `Unique codes: ${stats.uniqueCodes}`,
    "",
  ];

  for (const entry of summary) {
    lines.push(`- ${entry.code} x${entry.count}`);
    lines.push(`  Sources: ${entry.sources.join(", ")}`);
    if (entry.messages.length > 0) {
      lines.push(`  Messages: ${entry.messages.join(" | ")}`);
    }
    if (entry.actionSuggestions.length > 0) {
      lines.push(`  Suggested actions: ${entry.actionSuggestions.join(" | ")}`);
    }
    lines.push("");
  }

  return lines.join("\n").trimEnd();
}

export function buildDiagnosticBundlePayload({
  generatedAt,
  sections,
  startupDiagnostics,
  preflightDiagnostics,
  result,
  resultActionSuggestion,
  resultRecovery,
  telemetrySummary,
}: {
  generatedAt: string;
  sections: DiagnosticBundleSections;
  startupDiagnostics: DiagnosticStartupLike | null;
  preflightDiagnostics: DiagnosticStartupLike | null;
  result: DiagnosticResultLike | null;
  resultActionSuggestion?: string | null;
  resultRecovery?: DiagnosticRecoveryLike | null;
  telemetrySummary?: DiagnosticTelemetryLike | null;
}): DiagnosticBundlePayload {
  const errorCodeSummary = summarizeErrorCodes({
    startupDiagnostics,
    preflightDiagnostics,
    result,
    resultActionSuggestion,
  });
  const errorCodeStats = buildErrorCodeStats(errorCodeSummary);
  const recoverySummary = normalizeRecoverySummary(resultRecovery);
  const supportCase = buildSupportCaseSummary({
    summary: errorCodeSummary,
    stats: errorCodeStats,
    result,
    recovery: recoverySummary,
    startupDiagnostics,
    preflightDiagnostics,
  });

  return {
    generatedAt,
    data: {
      ...sections,
      diagnostics: {
        startup: startupDiagnostics,
        preflight: preflightDiagnostics,
        recoverySummary,
        errorCodeSummary,
        errorCodeStats,
        errorCodeReport: formatErrorCodeReport(errorCodeSummary, errorCodeStats),
        supportCase,
        supportCaseReport: formatSupportCaseReport(supportCase),
        telemetrySummary: telemetrySummary || null,
        telemetryReport: telemetrySummary ? formatTelemetryReport(telemetrySummary) : null,
      },
    },
  };
}

export function formatTelemetryReport(summary: DiagnosticTelemetryLike): string {
  const lines = ["Telemetry Summary"];
  lines.push(`Enabled: ${summary.telemetryEnabled}`);
  if (summary.currentConsentVersion) {
    lines.push(`Consent version: ${summary.consentAcceptedVersion || "not accepted"} / current ${summary.currentConsentVersion}`);
  }
  if (typeof summary.remoteUploadEnabled === "boolean") {
    lines.push(`Remote upload: ${summary.remoteUploadEnabled}`);
  }
  if (typeof summary.remoteEndpointConfigured === "boolean") {
    lines.push(`Remote endpoint configured: ${summary.remoteEndpointConfigured}`);
  }
  if (summary.remoteEndpointHost) {
    lines.push(`Remote endpoint host: ${summary.remoteEndpointHost}`);
  }
  if (typeof summary.pendingRemoteEvents === "number") {
    lines.push(`Pending remote events: ${summary.pendingRemoteEvents}`);
  }
  lines.push(`Crash-free session rate: ${Math.round(summary.crashFreeSessionRate * 100)}%`);
  lines.push(`Sessions: ${summary.sessionsCompletedCleanly}/${summary.sessionsStarted} clean, ${summary.sessionsCrashed} crashed`);
  lines.push(`First export success rate: ${Math.round(summary.firstExportSuccessRate * 100)}%`);
  lines.push(`First exports: ${summary.firstExportSuccesses}/${summary.firstExportSessions} successful`);
  lines.push(`Render attempts: ${summary.renderAttempts}`);
  lines.push(`Render outcomes: ${summary.renderSuccesses} success, ${summary.renderFailures} failure`);
  lines.push(`Recovery labels: resumable=${summary.recoveryResumableEvents}, retryable=${summary.recoveryRetryableEvents}`);

  const sections: Array<[string, Array<{ key: string; count: number }>]> = [
    ["Top error codes", summary.topErrorCodes],
    ["Top support queues", summary.topSupportQueues],
    ["Top tags", summary.topTags],
    ["Top severities", summary.topSeverities],
  ];
  for (const [title, entries] of sections) {
    if (!entries.length) continue;
    lines.push("");
    lines.push(title);
    for (const entry of entries) {
      lines.push(`- ${entry.key} x${entry.count}`);
    }
  }

  if (summary.lastUpdatedAt) {
    lines.push("");
    lines.push(`Last updated: ${summary.lastUpdatedAt}`);
  }
  if (summary.lastRemoteUploadAt || summary.lastRemoteUploadError) {
    lines.push(`Last remote upload: ${summary.lastRemoteUploadAt || "never"}`);
    lines.push(`Last remote status: ${summary.lastRemoteUploadError || "ok"}`);
  }
  return lines.join("\n").trimEnd();
}
