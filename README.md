# Video Create Studio

Video Create Studio 是一个基于 `Tauri + React + Python V5` 的桌面视频生成应用。

当前版本：`V5.6.2`  
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
src/                       React 前端
src/lib/engine.ts          前端到 Tauri 命令的调用封装
src-tauri/                 Tauri / Rust 桌面壳
video_engine_v5.py         Python V5 渲染引擎
video_engine_worker.py     本地 JSON-line worker
render_backends/           可选渲染后端
tests/                     冒烟测试和少量固定夹具
scripts/                   检查、清理、打包脚本
docs/                      设计、发布、迁移和性能文档
```

## 环境要求

- Node.js 20+
- Rust stable
- Python 3.11 推荐
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

## 开发

桌面联调：

```powershell
npm run dev:desktop
```

这等价于 `npm run tauri dev`，适合调前端、Tauri 命令和本地 worker 日志。

只构建前端：

```powershell
npm run build:web
```

## 检查与测试

成熟产品基线检查：

```powershell
npm run check
```

完整冒烟测试：

```powershell
npm run check:full
```

手动拆分检查：

```powershell
npm run build
cargo check --manifest-path .\src-tauri\Cargo.toml
python -m py_compile .\video_engine_v5.py .\video_engine_worker.py
python .\video_engine_v5.py --help
```

清理测试运行产物：

```powershell
npm run clean:test-artifacts
```

预览将删除哪些目录：

```powershell
npm run clean:test-artifacts -- --dry-run
```

说明：

- `tests/tmp_vcs_*` 默认视为测试运行产物。
- `tests/tmp_vcs_p3_render_smoke` 内有少量历史固定夹具，清理脚本默认保留。
- 扫描、预览和渲染生成的 `.cache_video_create_v5`、`.video_create_project`、`chunks`、`build_report.json` 不应提交。

## 渲染性能

引擎会复用多层缓存来减少重复工作：

- scan metadata cache：重复扫描未变化素材时复用尺寸、时长、缩略图等元数据。
- scan proxy cache：为预览生成低清代理素材。
- render cache：复用图片段、视频 fitted 段、卡片段和 visual base chunks。
- audio cache：复用归一化音频和音乐床。

缓存 key 绑定源文件路径、大小、mtime、引擎版本和关键渲染参数。素材或策略变化后会自动失效。

## 桌面分发

默认桌面打包：

```powershell
npm run build:desktop
```

该流程会：

1. 构建前端静态资源。
2. 打包 Python worker 到 `src-tauri/bin/`。
3. 执行 `tauri build`。
4. 生成当前平台的桌面安装包。

常用发布命令：

```powershell
npm run build:worker
npm run verify:worker-packaged
npm run build:desktop
npm run build:desktop:msi
```

Windows 默认使用 `NSIS`，避免普通发布流程被本机 `WiX/MSI` 环境卡住。明确需要 MSI 时再运行 `npm run build:desktop:msi`。

发布前请同时查看：

- `CHANGELOG.md`
- `docs/INSTALLER_TEST_CHECKLIST.md`
- `docs/PYTHON_WORKER_PACKAGING.md`

## 跨平台结论

- Windows：支持桌面打包。
- macOS：支持桌面打包，worker 会生成无扩展名可执行文件。
- iOS：当前架构不支持直接落地。

iOS 不适合当前“桌面端启动本地 Python worker 子进程”的模型。后续如果要支持 iOS，需要选择：

1. 将渲染核心迁移为原生 Rust / Swift 可调用模块。
2. 将 Python 渲染能力迁移到远端服务，iOS 只负责项目编辑和任务提交。

因此当前合理路线是先把 Windows/macOS 桌面分发做稳，再单独规划 iOS 架构。

## PowerShell 提示

如果 Windows PowerShell 拦截 `npm.ps1`，请改用：

```powershell
npm.cmd run check
```
