import { readFileSync } from "node:fs";
import process from "node:process";

const bundlePath = process.argv[2];

if (!bundlePath) {
  console.error("Usage: node ./scripts/error-code-summary.mjs <diagnostic-bundle.json>");
  process.exit(1);
}

let parsed;
try {
  parsed = JSON.parse(readFileSync(bundlePath, "utf8"));
} catch (error) {
  console.error(`Failed to read diagnostic bundle: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
}

const diagnostics = parsed?.data?.diagnostics;
if (!diagnostics || typeof diagnostics !== "object") {
  console.error("Diagnostic bundle is missing data.diagnostics.");
  process.exit(1);
}

if (typeof diagnostics.errorCodeReport === "string" && diagnostics.errorCodeReport.trim()) {
  console.log(diagnostics.errorCodeReport);
  if (typeof diagnostics.supportCaseReport === "string" && diagnostics.supportCaseReport.trim()) {
    console.log("");
    console.log(diagnostics.supportCaseReport);
  } else if (diagnostics.supportCase && typeof diagnostics.supportCase === "object") {
    console.log("");
    console.log("Support Case Summary");
    console.log(`Severity: ${diagnostics.supportCase.severity || "unknown"}`);
    console.log(`Category: ${diagnostics.supportCase.category || "unknown"}`);
    console.log(`Queue: ${diagnostics.supportCase.queue || "unknown"}`);
    if (Array.isArray(diagnostics.supportCase.tags) && diagnostics.supportCase.tags.length > 0) {
      console.log(`Tags: ${diagnostics.supportCase.tags.join(", ")}`);
    }
    if (typeof diagnostics.supportCase.recommendedNextStep === "string") {
      console.log(`Recommended next step: ${diagnostics.supportCase.recommendedNextStep}`);
    }
  }
  if (diagnostics.recoverySummary && typeof diagnostics.recoverySummary === "object") {
    console.log("");
    console.log("Recovery Summary");
    console.log(`Resumable: ${Boolean(diagnostics.recoverySummary.resumable)}`);
    console.log(`Retryable: ${Boolean(diagnostics.recoverySummary.retryable)}`);
    console.log(`Completed chunks: ${Number(diagnostics.recoverySummary.completedChunkCount || 0)}`);
    console.log(`Reused chunks: ${Number(diagnostics.recoverySummary.reusedChunkCount || 0)}`);
    console.log(`Failed chunks: ${Number(diagnostics.recoverySummary.failedChunkCount || 0)}`);
    if (diagnostics.recoverySummary.failedStage) {
      console.log(`Failed stage: ${diagnostics.recoverySummary.failedStage}`);
    }
    if (diagnostics.recoverySummary.failedChunk) {
      console.log(`Failed chunk: ${diagnostics.recoverySummary.failedChunk}`);
    }
  }
  if (typeof diagnostics.telemetryReport === "string" && diagnostics.telemetryReport.trim()) {
    console.log("");
    console.log(diagnostics.telemetryReport);
  }
  process.exit(0);
}

const summary = Array.isArray(diagnostics.errorCodeSummary) ? diagnostics.errorCodeSummary : [];
const totalOccurrences = summary.reduce((total, entry) => total + Number(entry?.count || 0), 0);

console.log("Error Code Summary");
console.log(`Total coded events: ${totalOccurrences}`);
console.log(`Unique codes: ${summary.length}`);

if (summary.length === 0) {
  console.log("No startup, preflight, or render error codes were captured in this diagnostic bundle.");
  process.exit(0);
}

for (const entry of summary) {
  console.log("");
  console.log(`- ${entry.code} x${entry.count}`);
  if (Array.isArray(entry.sources) && entry.sources.length > 0) {
    console.log(`  Sources: ${entry.sources.join(", ")}`);
  }
  if (Array.isArray(entry.messages) && entry.messages.length > 0) {
    console.log(`  Messages: ${entry.messages.join(" | ")}`);
  }
  if (Array.isArray(entry.actionSuggestions) && entry.actionSuggestions.length > 0) {
    console.log(`  Suggested actions: ${entry.actionSuggestions.join(" | ")}`);
  }
}
