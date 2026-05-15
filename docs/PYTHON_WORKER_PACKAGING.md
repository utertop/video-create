# Video Create Studio V5 Python Worker / Packaging Plan

## Goal

Desktop users should not install Python manually. The Python engine should be packaged as a local executable and called by Tauri through a small worker protocol.

## Current Implementation

- `video_engine_worker.py` is a JSON-line local worker.
- It only accepts paths and JSON settings, never video bytes.
- Tauri final rendering now calls the local worker first and keeps the worker process alive for the app session.
- If the worker is cancelled or crashes, Tauri clears the worker handle so the next render can start a fresh worker.
- Supported tasks:
  - `health`: returns engine version and detected hardware encoders.
  - `render`: renders a full render plan to an output path.
  - `preview-render`: renders a real low-resolution preview from the same render plan.
  - `stop` / `shutdown`: exits the worker.

Example one-shot health check:

```powershell
python video_engine_worker.py --health
```

Example one-shot preview task:

```powershell
'{"type":"preview-render","plan_path":"D:\\project\\.video_create_project\\render_plan.json","output_path":"D:\\project\\.video_create_project\\preview.mp4","params":{"aspect_ratio":"16:9"},"height":540,"fps":15,"max_duration":20,"max_segments":8}' | python video_engine_worker.py --once
```

## Packaging Strategy

### Phase 1: CLI Worker Executable

Package `video_engine_worker.py` into an executable:

```powershell
python -m PyInstaller --onefile --name video-create-worker video_engine_worker.py
```

Recommended hidden imports/assets should be validated on the packaging machine:

- `moviepy`
- `imageio_ffmpeg`
- `PIL`
- `numpy`
- `proglog`

### Phase 2: Tauri Integration

Tauri should locate the worker in this order:

- Bundled resource executable.
- Development fallback: `python video_engine_worker.py`.
- Final fallback: existing `video_engine_v5.py` CLI commands.

Current Tauri integration keeps the Python worker alive and sends final render tasks through stdin as JSON lines. The older CLI render path remains in the code as a fallback reference while the worker path is hardened.

### Phase 3: Task Queue

The worker protocol should stay JSON-line based:

- Tauri sends one JSON task per line.
- Worker emits one JSON event/result per line.
- Large files are always referenced by absolute path.
- Progress events can be forwarded unchanged from the existing engine JSON events.

## Safety Rules

- Do not pass video/image bytes through IPC.
- Do not keep full long-video timelines in the frontend.
- Long final renders still use chunking and cache.
- Low-resolution previews must use the same render plan logic, only lower resolution/fps/duration.
- Any FFmpeg path must preserve aspect ratio with proportional scale + padding and `setsar=1`.
