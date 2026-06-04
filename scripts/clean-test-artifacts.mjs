import { existsSync, readdirSync, rmSync } from "node:fs";
import path from "node:path";
import process from "node:process";

const repoRoot = process.cwd();
const testsDir = path.join(repoRoot, "tests");
const dryRun = process.argv.includes("--dry-run");

const generatedEntries = [
  ".generated-diagnostic-check",
  "tmp_video_geometry_probe",
];
const generatedChildrenInPreservedDirs = [
  "__pycache__",
  ".cache_video_create_v5",
  ".video_create_project",
  "chunks",
  "build_report.json",
  "concat_list.txt",
  "p3_smoke.mp4",
];

// This directory contains tiny tracked fixture images used by older smoke tests.
const preservedTmpDirs = new Set(["tmp_vcs_p3_render_smoke"]);

function removePath(targetPath) {
  const relative = path.relative(repoRoot, targetPath) || targetPath;
  if (!existsSync(targetPath)) return;
  if (dryRun) {
    console.log(`[dry-run] ${relative}`);
    return;
  }
  rmSync(targetPath, { recursive: true, force: true });
  console.log(`removed ${relative}`);
}

if (!existsSync(testsDir)) {
  console.log("No tests directory found.");
  process.exit(0);
}

let count = 0;

for (const entry of readdirSync(testsDir, { withFileTypes: true })) {
  if (!entry.isDirectory()) continue;
  if (!entry.name.startsWith("tmp_vcs_")) continue;
  if (preservedTmpDirs.has(entry.name)) continue;
  removePath(path.join(testsDir, entry.name));
  count += 1;
}

for (const entry of generatedEntries) {
  const targetPath = path.join(testsDir, entry);
  if (!existsSync(targetPath)) continue;
  removePath(targetPath);
  count += 1;
}

for (const dirName of preservedTmpDirs) {
  const dirPath = path.join(testsDir, dirName);
  if (!existsSync(dirPath)) continue;
  for (const child of generatedChildrenInPreservedDirs) {
    const targetPath = path.join(dirPath, child);
    if (!existsSync(targetPath)) continue;
    removePath(targetPath);
    count += 1;
  }
}

for (const targetPath of collectGeneratedChildren(testsDir)) {
  removePath(targetPath);
  count += 1;
}

if (count === 0) {
  console.log("No generated test artifacts found.");
}

function collectGeneratedChildren(rootDir) {
  const targets = [];
  for (const entry of readdirSync(rootDir, { withFileTypes: true })) {
    const absolutePath = path.join(rootDir, entry.name);
    if (generatedChildrenInPreservedDirs.includes(entry.name)) {
      targets.push(absolutePath);
      continue;
    }
    if (entry.isDirectory()) {
      targets.push(...collectGeneratedChildren(absolutePath));
    }
  }
  return targets;
}
