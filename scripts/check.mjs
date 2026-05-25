import { spawnSync } from "node:child_process";
import process from "node:process";

const full = process.argv.includes("--full");

const coreSmokeTests = [
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
  "tests/smoke_v5_render_cache.py",
  "tests/smoke_v5_render_scheduler.py",
  "tests/smoke_v5_template_matching.py",
  "tests/smoke_v5_video_geometry.py",
  "tests/smoke_v5_worker_protocol.py",
  "tests/smoke_v5_6_long_video_stability.py",
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
  ...smokeTestSteps(full ? fullSmokeTests : coreSmokeTests),
];

for (const [index, step] of steps.entries()) {
  const title = `[${index + 1}/${steps.length}] ${step.label}`;
  console.log(`\n${title}`);
  console.log(`> ${[step.command, ...step.args].join(" ")}`);

  const result = spawnSync(step.command, step.args, {
    cwd: process.cwd(),
    env: {
      ...process.env,
      PYTHONUTF8: "1",
      PYTHONIOENCODING: "utf-8",
    },
    stdio: "inherit",
    shell: process.platform === "win32" && step.command.endsWith(".cmd"),
  });

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
