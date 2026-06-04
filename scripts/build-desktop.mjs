import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const tauriBinary = path.join(
  repoRoot,
  "node_modules",
  ".bin",
  process.platform === "win32" ? "tauri.cmd" : "tauri",
);
const tauriArgs = ["build"];

// Windows default to NSIS so the normal desktop build does not depend on WiX/MSI.
if (process.platform === "win32") {
  tauriArgs.push("--bundles", "nsis");
}

if (!existsSync(tauriBinary)) {
  throw new Error(`Cannot find local tauri CLI: ${tauriBinary}`);
}

const result =
  process.platform === "win32"
    ? spawnSync(process.env.ComSpec || "cmd.exe", ["/d", "/c", tauriBinary, ...tauriArgs], {
        cwd: repoRoot,
        stdio: "inherit",
      })
    : spawnSync(tauriBinary, tauriArgs, {
        cwd: repoRoot,
        stdio: "inherit",
      });

if (result.error) {
  throw result.error;
}

if (result.status !== 0) {
  process.exit(result.status ?? 1);
}
