# Video Create Studio

Video Create Studio 是一个基于 `Tauri + React + Python V5` 的视频生成桌面应用。

当前版本：`V5.6.0`  
当前 V5 Schema：`5.5`

## 主流程

```text
scan -> media_library.json
plan -> story_blueprint.json
compile -> render_plan.json
render -> final mp4
```

## 项目结构

```text
src/                 React 前端
src/lib/engine.ts    前端到 Tauri 的调用封装
src-tauri/           Tauri / Rust 桌面壳
video_engine_v5.py   Python V5 引擎
video_engine_worker.py
tests/               冒烟测试
scripts/             构建与打包脚本
```

## 环境要求

- Node.js 20+
- Rust stable
- Python 3.11（推荐）
- `requirements.txt` 中的 Python 依赖

安装依赖：

```powershell
npm install
python -m pip install -r .\requirements.txt
```

如果需要打包桌面版 worker，还需要：

```powershell
python -m pip install -r .\requirements-worker-build.txt
```

## 开发模式

开发联调时仍然使用：

```powershell
npm run dev:desktop
```

这等价于 `npm run tauri dev`，适合改前端、改 Tauri 命令、看实时日志。

## 桌面分发

如果目标是不再每次都跑 `tauri dev`，而是产出可直接安装/启动的桌面应用，请使用：

```powershell
npm run build:desktop
```

这个流程会自动完成：

1. 构建前端静态资源
2. 打包 Python worker 到 `src-tauri/bin/`
3. 执行 `tauri build`
4. 生成当前平台的桌面安装包

常用相关命令：

```powershell
npm run build:worker
npm run verify:worker-packaged
npm run build:desktop
npm run build:desktop:msi
```

说明：

- `npm run build:desktop` 会按平台自动选更稳的默认 bundler
- Windows 默认走 `NSIS`，避免被本机 `WiX/MSI` 环境卡住
- 如果你明确需要 `MSI`，再手动使用 `npm run build:desktop:msi`

## 当前跨平台结论

- `Windows`：支持桌面打包
- `macOS`：支持桌面打包，worker 现在会自动生成无扩展名可执行文件
- `iOS`：当前架构暂不支持直接落地

原因很直接：现在桌面端依赖 `Tauri/Rust` 启动本地 Python worker 子进程，而 iOS 不适合这种本地子进程执行模型。要上 iOS，下一步需要在下面两条路里选一条：

1. 把渲染核心改成原生 Rust / Swift 可调用模块
2. 把 Python 渲染能力迁到远端服务，由 iOS 只负责项目编辑和任务提交

所以这版代码的合理“下一步”是先把 `Windows/macOS` 桌面分发做稳，再单独规划 iOS 架构。

## 常用检查命令

```powershell
npm run build
cargo check --manifest-path .\src-tauri\Cargo.toml
python -m py_compile .\video_engine_v5.py
python .\video_engine_v5.py --help
python .\tests\smoke_v5_6_long_video_stability.py
```

如果 Windows PowerShell 拦截了 `npm.ps1`，请改用 `npm.cmd`。
