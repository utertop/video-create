import { spawnSync } from "node:child_process";
import process from "node:process";

const full = process.argv.includes("--full");

const coreSmokeTests = [
  "tests/smoke_v5_timeline_schema.py",
  "tests/smoke_v5_timeline_generate.py",
  "tests/smoke_v5_timeline_invalidation.py",
  "tests/smoke_v5_preview_final_cache_isolation.py",
  "tests/smoke_v5_final_render_original_source.py",
  "tests/smoke_v5_edit_strategy_compile.py",
  "tests/smoke_v5_render_scheduler.py",
  "tests/smoke_v5_video_geometry.py",
  "tests/smoke_v5_6_long_video_stability.py",
];

const fullSmokeTests = [
  "tests/smoke_v5_4.py",
  "tests/smoke_v5_4_2_directory_strategy.py",
  "tests/smoke_v5_5_1_moviepy_opacity.py",
  "tests/smoke_v5_5_title_style.py",
  "tests/smoke_v5_audio_auto_select.py",
  "tests/smoke_v5_audio_blueprint.py",
  "tests/smoke_v5_audio_visual_cache.py",
  "tests/smoke_v5_bgm_mix.py",
  "tests/smoke_v5_cache_cleanup.py",
  "tests/smoke_v5_card_segment_cache.py",
  "tests/smoke_v5_edit_strategy_compile.py",
  "tests/smoke_v5_edit_strategy_render.py",
  "tests/smoke_v5_ffmpeg_priority.py",
  "tests/smoke_v5_low_res_preview.py",
  "tests/smoke_v5_music_playlist.py",
  "tests/smoke_v5_photo_segment_cache.py",
  "tests/smoke_v5_preview_final_cache_isolation.py",
  "tests/smoke_v5_render_cache.py",
  "tests/smoke_v5_render_scheduler.py",
  "tests/smoke_v5_template_matching.py",
  "tests/smoke_v5_timeline_schema.py",
  "tests/smoke_v5_timeline_generate.py",
  "tests/smoke_v5_timeline_invalidation.py",
  "tests/smoke_v5_final_render_original_source.py",
  "tests/smoke_v5_video_geometry.py",
  "tests/smoke_v5_worker_protocol.py",
  "tests/smoke_v5_6_long_video_stability.py",
];

const fullOnlySteps = [
  {
    label: "Compile diagnostic bundle helpers",
    command: npmCommand(),
    args: ["exec", "--", "tsc", "-p", "./tsconfig.diagnostic-check.json"],
  },
  {
    label: "Assert diagnostic bundle payload",
    command: "node",
    args: ["./tests/diagnostic_bundle_assert.mjs"],
  },
  {
    label: "Print diagnostic error code summary",
    command: "node",
    args: ["./scripts/error-code-summary.mjs", "./tests/.generated-diagnostic-check/diagnostic_bundle_fixture.json"],
  },
  {
    label: "Run Tauri regression tests",
    command: "cargo",
    args: ["test", "--manifest-path", "./src-tauri/Cargo.toml"],
  },
];

const steps = [
  {
    label: "Build web frontend",
    command: npmCommand(),
    args: ["run", "build:web"],
  },
  {
    label: "Check Tauri backend",
    command: "cargo",
    args: ["check", "--manifest-path", "./src-tauri/Cargo.toml"],
  },
  {
    label: "Compile Python engine files",
    command: "python",
    args: ["-m", "py_compile", "./video_engine_v5.py", "./video_engine_worker.py"],
  },
  {
    label: "Check Python engine CLI",
    command: "python",
    args: ["./video_engine_v5.py", "--help"],
  },
  ...(full ? fullOnlySteps : []),
  ...smokeTestSteps(full ? fullSmokeTests : coreSmokeTests),
];

for (const [index, step] of steps.entries()) {
  const title = `[${index + 1}/${steps.length}] ${step.label}`;
  console.log(`\n${title}`);
  console.log(`> ${[step.command, ...step.args].join(" ")}`);

  const result = spawnStep(step);

  if (result.error) {
    console.error(`\n${title} failed to start: ${result.error.message}`);
    process.exit(1);
  }

  if (result.status !== 0) {
    console.error(`\n${title} failed with exit code ${result.status}.`);
    process.exit(result.status ?? 1);
  }
}

console.log(`\nProduct check passed (${full ? "full" : "core"} suite).`);

function spawnStep(step) {
  const env = {
    ...process.env,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
  };

  if (process.platform === "win32" && step.command.endsWith(".cmd")) {
    return spawnSync(process.env.ComSpec || "cmd.exe", ["/d", "/c", step.command, ...step.args], {
      cwd: process.cwd(),
      env,
      stdio: "inherit",
    });
  }

  return spawnSync(step.command, step.args, {
    cwd: process.cwd(),
    env,
    stdio: "inherit",
  });
}

function smokeTestSteps(files) {
  return files.map((file) => ({
    label: `Run ${file}`,
    command: "python",
    args: [file],
  }));
}

function npmCommand() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}
