# Video Create Studio

Tauri + React + TypeScript desktop GUI for `make_bilibili_video_v3.py`.

## Current State

- React/Vite frontend scaffold is ready.
- The GUI MVP covers material import, render settings, command preview, and the future AI roadmap panel.
- Tauri v2 shell is scaffolded under `src-tauri`.
- The `generate_video` Tauri command is currently a backend placeholder. It validates the IPC path and returns the Python command preview. The next step is spawning the packaged Python engine and streaming progress events.

## Run Frontend Preview

```powershell
npm.cmd install
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:1420
```

You can also open the static preview after building:

```powershell
npm.cmd run build
```

Then open:

```text
dist\index.html
```

## Run Tauri Desktop App

Install Rust first, then run:

```powershell
npm.cmd run tauri -- dev
```

This machine currently has Node.js and npm available, but `cargo` / `rustc` are not on `PATH`, so the desktop shell cannot be compiled yet.

## Architecture

```text
React UI
  -> @tauri-apps/api invoke()
  -> Tauri Rust command
  -> local Python video engine
  -> FFmpeg / MoviePy render output
```

IPC should pass file paths and JSON status only. Large video data should stay on disk and be handled by Python/FFmpeg.
