# Video Create Studio V5 Python Worker 打包方案

## 目标

桌面端用户不应该再手动安装 Python 来运行应用。当前方案是把 `video_engine_worker.py` 打成随桌面应用一起分发的本地可执行文件，再由 Tauri 通过标准输入输出协议调用它。

## 当前实现

- `video_engine_worker.py` 是本地 JSON 行协议 worker
- Tauri 优先通过 worker 执行 `scan / plan / compile / preview / render`
- worker 会在应用生命周期内尽量复用
- worker 异常退出后，Tauri 会在下次任务时自动重新拉起

## 构建命令

安装打包依赖：

```powershell
python -m pip install -r .\requirements-worker-build.txt
```

打包 worker：

```powershell
npm run build:worker
```

校验打包结果：

```powershell
npm run verify:worker-packaged
```

桌面整包构建：

```powershell
npm run build:desktop
```

如果你在 Windows 上明确需要 `MSI`：

```powershell
npm run build:desktop:msi
```

## 产物位置

当前平台的 worker 会输出到：

- Windows: `src-tauri/bin/video-create-worker.exe`
- macOS / Linux: `src-tauri/bin/video-create-worker`

## Tauri 查找顺序

Tauri 当前会按下面顺序查找 worker：

1. 已打包随应用分发的本地可执行文件
2. 开发环境下的 `python video_engine_worker.py`

这意味着：

- 开发时可以继续 `npm run dev:desktop`
- 分发时默认用 `npm run build:desktop`
- 最终用户不需要再运行 `npm run tauri dev`

默认 bundler 策略：

- Windows 默认使用 `NSIS`
- macOS 保持 Tauri 桌面打包流程
- `MSI` 改为按需手动构建，避免默认流程依赖 WiX

## iOS 说明

这套方案是“桌面优先”方案，不是 iOS 方案。

原因是当前架构依赖本地子进程启动 Python worker，而 iOS 不适合直接沿用这条链路。若要支持 iOS，需要改为：

1. 原生可嵌入引擎
2. 或远端渲染服务

因此当前建议是先把 `Windows/macOS` 桌面分发链路固化，再单独拆出 iOS 版本路线。
