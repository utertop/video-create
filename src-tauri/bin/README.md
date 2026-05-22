`src-tauri/bin` 用来存放随桌面应用一起分发的本地辅助二进制。

当前平台的 worker 由 `npm run build:worker` 生成：

- Windows: `video-create-worker.exe`
- macOS / Linux: `video-create-worker`

这些产物是本地构建结果，按设计不纳入 Git 版本管理。
