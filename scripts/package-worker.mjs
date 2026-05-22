import { spawnSync } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
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
const targetDir = path.join(repoRoot, "src-tauri", "bin");
const workerBinaryName = process.platform === "win32" ? "video-create-worker.exe" : "video-create-worker";
const targetBinary = path.join(targetDir, workerBinaryName);

function ensurePath(targetPath) {
  mkdirSync(targetPath, { recursive: true });
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

for (const dir of [distDir, workDir, specDir, fakeAppDataDir, fakeUserBaseDir, targetDir]) {
  ensurePath(dir);
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
console.log(`Packaged worker copied to ${targetBinary}`);
