import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const runtimeDir = dirname(fileURLToPath(import.meta.url));
const compiledModulePath = resolve(runtimeDir, ".generated-diagnostic-check", "src", "lib", "diagnostics.js");
const fixturePath = resolve(runtimeDir, ".generated-diagnostic-check", "diagnostic_bundle_fixture.json");

const {
  buildDiagnosticBundlePayload,
  buildErrorCodeStats,
  buildSupportCaseSummary,
  formatErrorCodeReport,
  formatSupportCaseReport,
  formatTelemetryReport,
  summarizeErrorCodes,
} = await import(pathToFileURL(compiledModulePath).href);

const startupDiagnostics = {
  ok: false,
  code: "E_STARTUP_CHECK_FAILED",
  summary: "Startup self-check found 1 problem.",
  checks: [
    {
      id: "worker_entrypoint",
      label: "Worker entrypoint",
      ok: false,
      code: "E_WORKER_ENTRYPOINT_MISSING",
      message: "Worker executable or fallback script is missing.",
      detail: "src-tauri/bin/video-create-worker.exe",
    },
  ],
};

const preflightDiagnostics = {
  ok: false,
  code: "E_PREFLIGHT_CHECK_FAILED",
  summary: "Render preflight found 2 problems.",
  checks: [
    {
      id: "media_sources",
      label: "Media sources",
      ok: false,
      code: "E_MEDIA_SOURCE_MISSING",
      message: "1 source file is missing.",
      detail: "D:/demo/assets/quanzhou/xijie/shot2.jpg",
    },
    {
      id: "output_dir",
      label: "Output directory",
      ok: false,
      code: "E_DIRECTORY_NOT_WRITABLE",
      message: "Output directory is not writable.",
      detail: "D:/demo/output",
    },
  ],
};

const resultActionSuggestion = "Restore the original media path or rescan assets and regenerate render_plan.json.";

const result = {
  ok: false,
  code: "E_MEDIA_SOURCE_MISSING",
  message: "Render stopped because an input asset disappeared after compile.",
  commandPreview: "python video_engine_v5.py render --plan render_plan.json --output final.mp4",
};

const recovery = {
  reportPath: "D:/demo/output/.video_create_project/build_report.json",
  manifestPath: "D:/demo/output/.video_create_project/chunks/final/chunk_manifest.json",
  status: "failed",
  renderMode: "v5.6_long_video_stable",
  failedStage: "chunk_render",
  resumable: true,
  resumedFromManifest: true,
  reusedChunkCount: 2,
  completedChunkCount: 4,
  failedChunkCount: 1,
  reportedChunkCount: 5,
  failedChunk: "chunk_003.mp4",
  failureCode: "chunk_render_failed",
  failureMessage: "chunk_003 failed",
  retryable: true,
};

const telemetrySummary = {
  telemetryEnabled: true,
  sessionsStarted: 5,
  sessionsCompletedCleanly: 4,
  sessionsCrashed: 1,
  crashFreeSessionRate: 0.8,
  firstExportSessions: 4,
  firstExportSuccesses: 3,
  firstExportSuccessRate: 0.75,
  renderAttempts: 6,
  renderSuccesses: 3,
  renderFailures: 3,
  recoveryResumableEvents: 2,
  recoveryRetryableEvents: 2,
  topErrorCodes: [{ key: "E_MEDIA_SOURCE_MISSING", count: 2 }],
  topSupportQueues: [{ key: "render-recovery", count: 3 }],
  topTags: [{ key: "resumable", count: 2 }],
  topSeverities: [{ key: "warning", count: 3 }],
  lastUpdatedAt: "2026-05-26T12:00:00.000Z",
};

const summary = summarizeErrorCodes({
  startupDiagnostics,
  preflightDiagnostics,
  result,
  resultActionSuggestion,
});

assert.equal(summary.length, 5, "expected five unique error codes in the synthetic bundle");
assert.equal(summary[0].code, "E_MEDIA_SOURCE_MISSING", "most frequent error code should sort first");
assert.equal(summary[0].count, 2, "missing source code should aggregate preflight + result");
assert(summary[0].sources.includes("preflight_check:media_sources"));
assert(summary[0].sources.includes("result"));
assert(summary[0].actionSuggestions.includes(resultActionSuggestion));

const stats = buildErrorCodeStats(summary);
assert.equal(stats.totalOccurrences, 6, "expected six coded events in total");
assert.equal(stats.uniqueCodes, 5, "expected five unique error codes");

const report = formatErrorCodeReport(summary, stats);
assert(report.includes("Error Code Summary"));
assert(report.includes("E_MEDIA_SOURCE_MISSING x2"));
assert(report.includes("Suggested actions: Restore the original media path"));

const supportCase = buildSupportCaseSummary({
  summary,
  stats,
  result,
  recovery,
  startupDiagnostics,
  preflightDiagnostics,
});
assert.equal(supportCase.queue, "render-recovery");
assert(supportCase.tags.includes("resumable"));
assert(formatSupportCaseReport(supportCase).includes("Support Case Summary"));
assert(formatTelemetryReport(telemetrySummary).includes("Telemetry Summary"));

const bundle = buildDiagnosticBundlePayload({
  generatedAt: "2026-05-26T12:00:00.000Z",
  sections: {
    app: {
      product: "Video Create Studio",
      exportedAtLocal: "2026/5/26 20:00:00",
    },
    project: {
      inputFolder: "D:/demo/assets",
      outputFolder: "D:/demo/output",
      projectDir: "D:/demo/output/.video_create_project",
      stage: "RENDER",
      title: "Quanzhou Trip",
      outputName: "quanzhou-trip",
    },
    upgrade: {
      migrationSource: "recent_project_restore",
      migrationNotes: ["render_plan.json: schema_version 5.4 -> 5.5"],
    },
    workflow: {
      phase: "Render failed",
      result,
    },
    runtime: {
      logs: ["Worker boot failed", "Missing source detected"],
      renderQueue: [],
    },
    sessionDraft: {
      savedAt: "2026-05-26T11:58:00.000Z",
    },
  },
  startupDiagnostics,
  preflightDiagnostics,
  result,
  resultActionSuggestion,
  resultRecovery: recovery,
  telemetrySummary,
});

assert.equal(bundle.data.diagnostics.errorCodeSummary.length, 5);
assert.equal(bundle.data.diagnostics.errorCodeStats.totalOccurrences, 6);
assert(bundle.data.diagnostics.errorCodeReport.includes("Unique codes: 5"));
assert.equal(bundle.data.diagnostics.recoverySummary?.completedChunkCount, 4);
assert.equal(bundle.data.diagnostics.supportCase.queue, "render-recovery");
assert(bundle.data.diagnostics.supportCaseReport.includes("Queue: render-recovery"));
assert.equal(bundle.data.diagnostics.telemetrySummary?.sessionsStarted, 5);
assert(bundle.data.diagnostics.telemetryReport.includes("Crash-free session rate: 80%"));
assert.deepEqual(bundle.data.upgrade.migrationNotes, ["render_plan.json: schema_version 5.4 -> 5.5"]);

mkdirSync(dirname(fixturePath), { recursive: true });
writeFileSync(fixturePath, JSON.stringify(bundle, null, 2));

console.log(`Diagnostic bundle assertion passed: ${fixturePath}`);
