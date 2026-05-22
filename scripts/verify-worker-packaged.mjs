import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const workerBinaryName = process.platform === "win32" ? "video-create-worker.exe" : "video-create-worker";
const workerBinary = path.join(repoRoot, "src-tauri", "bin", workerBinaryName);

function run(command, args, label, env = process.env) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    env,
    encoding: "utf8",
    stdio: "pipe",
  });

  if (result.stdout.trim()) {
    process.stdout.write(result.stdout);
  }
  if (result.stderr.trim()) {
    process.stderr.write(result.stderr);
  }

  if (result.status !== 0) {
    throw new Error(`${label} failed with exit code ${result.status}.`);
  }
}

if (!existsSync(workerBinary)) {
  throw new Error(`Packaged worker not found: ${workerBinary}`);
}

run(workerBinary, ["--health"], "Worker health check");

run("python", ["./tests/smoke_v5_worker_protocol.py"], "Worker protocol smoke test", {
  ...process.env,
  VCS_WORKER_EXE: workerBinary,
  PYTHONUTF8: "1",
  PYTHONIOENCODING: "utf-8",
});
