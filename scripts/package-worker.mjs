import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const workerScript = path.join(repoRoot, "video_engine_worker.py");
const distDir = path.join(repoRoot, "scratch", "pyinstaller-dist");
const workDir = path.join(repoRoot, "scratch", "pyinstaller-build");
const specDir = path.join(repoRoot, "scratch", "pyinstaller-spec");
const fakeAppDataDir = path.join(repoRoot, "scratch", "pyinstaller-appdata");
const fakeUserBaseDir = path.join(repoRoot, "scratch", "pyinstaller-user-base");
const manifestPath = path.join(repoRoot, "scratch", "worker-build-manifest.json");
const targetDir = path.join(repoRoot, "src-tauri", "bin");
const workerBinaryName = process.platform === "win32" ? "video-create-worker.exe" : "video-create-worker";
const targetBinary = path.join(targetDir, workerBinaryName);
const forceRebuild = process.env.VCS_FORCE_WORKER_REBUILD === "1";

function ensurePath(targetPath) {
  mkdirSync(targetPath, { recursive: true });
}

function walkFiles(rootDir) {
  if (!existsSync(rootDir)) return [];
  const results = [];

  for (const entry of readdirSync(rootDir, { withFileTypes: true })) {
    const absolutePath = path.join(rootDir, entry.name);
    if (entry.isDirectory()) {
      results.push(...walkFiles(absolutePath));
      continue;
    }
    results.push(absolutePath);
  }

  return results;
}

function trackedInputFiles() {
  return [
    path.join(repoRoot, "scripts", "package-worker.mjs"),
    path.join(repoRoot, "video_engine_worker.py"),
    path.join(repoRoot, "video_engine_v5.py"),
    path.join(repoRoot, "requirements.txt"),
    path.join(repoRoot, "requirements-worker-build.txt"),
    ...walkFiles(path.join(repoRoot, "video_engine")).filter((filePath) => filePath.endsWith(".py")),
    ...walkFiles(path.join(repoRoot, "render_backends")).filter((filePath) => filePath.endsWith(".py")),
  ]
    .filter((filePath) => existsSync(filePath))
    .sort((left, right) => left.localeCompare(right));
}

function computeFingerprint(files) {
  const hash = crypto.createHash("sha256");

  for (const filePath of files) {
    hash.update(path.relative(repoRoot, filePath));
    hash.update("\n");
    hash.update(readFileSync(filePath));
    hash.update("\n");
  }

  return hash.digest("hex");
}

function readPreviousManifest() {
  if (!existsSync(manifestPath)) return null;

  try {
    return JSON.parse(readFileSync(manifestPath, "utf8"));
  } catch {
    return null;
  }
}

function runPython(args, label) {
  const env = { ...process.env };
  env.PYTHONNOUSERSITE = "1";
  env.APPDATA = fakeAppDataDir;
  env.PYTHONUSERBASE = fakeUserBaseDir;
  delete env.PYTHONPATH;

  const result = spawnSync("python", args, {
    cwd: repoRoot,
    env,
    encoding: "utf8",
    stdio: "pipe",
  });

  if (result.status !== 0) {
    const detail = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    throw new Error(`${label} failed.${detail ? `\n${detail}` : ""}`);
  }

  return result;
}

if (!existsSync(workerScript)) {
  throw new Error(`Cannot find worker script: ${workerScript}`);
}

for (const dir of [distDir, workDir, specDir, fakeAppDataDir, fakeUserBaseDir, targetDir, path.dirname(manifestPath)]) {
  ensurePath(dir);
}

const trackedFiles = trackedInputFiles();
const fingerprint = computeFingerprint(trackedFiles);
const previousManifest = readPreviousManifest();

if (
  !forceRebuild &&
  existsSync(targetBinary) &&
  previousManifest?.fingerprint === fingerprint
) {
  console.log(`Worker packaging skipped; no relevant changes detected for ${targetBinary}`);
  process.exit(0);
}

runPython(["-I", "-m", "PyInstaller", "--version"], "PyInstaller check");

const pyInstallerArgs = [
  "-I",
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name",
  "video-create-worker",
  "--distpath",
  distDir,
  "--workpath",
  workDir,
  "--specpath",
  specDir,
  "--collect-all",
  "moviepy",
  "--collect-all",
  "imageio",
  "--collect-all",
  "imageio_ffmpeg",
  "--collect-all",
  "proglog",
  "--collect-all",
  "pilmoji",
  "--collect-all",
  "PIL",
  "--collect-all",
  "requests",
  "--copy-metadata",
  "moviepy",
  "--copy-metadata",
  "imageio",
  "--copy-metadata",
  "imageio-ffmpeg",
  "--copy-metadata",
  "proglog",
  workerScript,
];

const build = runPython(pyInstallerArgs, "PyInstaller worker packaging");
if (build.stdout.trim()) {
  process.stdout.write(build.stdout);
}
if (build.stderr.trim()) {
  process.stderr.write(build.stderr);
}

const builtBinary = path.join(distDir, workerBinaryName);
if (!existsSync(builtBinary)) {
  throw new Error(`Expected packaged worker was not created: ${builtBinary}`);
}

copyFileSync(builtBinary, targetBinary);
writeFileSync(
  manifestPath,
  JSON.stringify(
    {
      fingerprint,
      workerBinaryName,
      targetBinary,
      trackedFiles: trackedFiles.map((filePath) => path.relative(repoRoot, filePath)),
      builtAt: new Date().toISOString(),
    },
    null,
    2,
  ),
  "utf8",
);
console.log(`Packaged worker copied to ${targetBinary}`);
