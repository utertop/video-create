# Video Create Studio

Video Create Studio is a Tauri + React desktop app backed by a Python V5 video engine.

Current baseline: **V5.6.0**  
Current V5 JSON schema: **5.5**

## Main Pipeline

```text
scan -> media_library.json
plan -> story_blueprint.json
compile -> render_plan.json
render -> final mp4
```

The primary engine is `video_engine_v5.py`. The Tauri backend in `src-tauri/src/lib.rs`
invokes the Python engine and streams JSON progress events to the frontend.

## Project Layout

```text
src/                 React frontend
src/lib/engine.ts    Frontend engine types and Tauri invoke helpers
src-tauri/           Tauri/Rust desktop shell
video_engine_v5.py   Python V5 scan/plan/compile/render engine
tests/               Smoke tests and lightweight fixtures
archive/             Historical patches, backups, and design notes
```

## Requirements

- Node.js 20+
- Rust stable
- Python 3.11 recommended
- Python packages from `requirements.txt`

Install dependencies:

```powershell
npm install
python -m pip install -r .\requirements.txt
```

## Common Commands

```powershell
npm.cmd run build
cargo check --manifest-path .\src-tauri\Cargo.toml
python -m py_compile .\video_engine_v5.py
python .\video_engine_v5.py --help
python .\tests\smoke_v5_6_long_video_stability.py
```

Use `npm.cmd` on Windows PowerShell if script execution policy blocks `npm.ps1`.

## Cleanup Notes

Historical `.bak` files, hotfix scripts, and older design documents are kept under
`archive/2026-05-cleanup/` for traceability. Generated files such as `dist/`,
`__pycache__/`, local scratch data, and rendered media are intentionally ignored.
