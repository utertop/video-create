# Video Create Studio

Video Create Studio 是一个基于 Tauri、React 和 Python V5 引擎的桌面视频生成工具。

当前基线版本：**V5.6.0**  
当前 V5 JSON Schema：**5.5**

## 主流程

```text
scan -> media_library.json
plan -> story_blueprint.json
compile -> render_plan.json
render -> final mp4
```

主引擎文件是 `video_engine_v5.py`。Tauri 后端位于 `src-tauri/src/lib.rs`，负责调用 Python 引擎，并把 JSON 进度事件持续转发给前端。

## 项目结构

```text
src/                 React 前端
src/lib/engine.ts    前端引擎类型与 Tauri 调用封装
src-tauri/           Tauri / Rust 桌面壳层
video_engine_v5.py   Python V5 扫描、规划、编译、渲染引擎
tests/               冒烟测试与轻量级测试夹具
archive/             历史补丁、备份与设计文档归档
```

## 环境要求

- Node.js 20 或更高版本
- Rust stable
- 推荐 Python 3.11
- `requirements.txt` 中列出的 Python 依赖

安装依赖：

```powershell
npm install
python -m pip install -r .\requirements.txt
```

## 常用命令

```powershell
npm.cmd run build
cargo check --manifest-path .\src-tauri\Cargo.toml
python -m py_compile .\video_engine_v5.py
python .\video_engine_v5.py --help
python .\tests\smoke_v5_6_long_video_stability.py
```

如果 Windows PowerShell 的执行策略阻止 `npm.ps1`，请使用 `npm.cmd`。

## 清理说明

历史 `.bak` 文件、一次性热修脚本和旧设计文档被保留在 `archive/2026-05-cleanup/` 中，方便追溯。`dist/`、`__pycache__/`、本地临时数据和渲染产物等生成文件默认忽略，不纳入版本管理。
