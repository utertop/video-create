# Video Create Studio V5 Python Worker 打包方案

## 目标

桌面端用户不应该再手动安装 Python。Python 引擎需要被打包成本地可执行文件，并通过一个轻量 Worker 协议由 Tauri 调用。

## 当前实现

- `video_engine_worker.py` 是一个基于 JSON 行协议的本地 Worker。
- Worker 只接受路径和 JSON 参数，不直接传输视频字节数据。
- Tauri 侧的 V5 `scan` / `plan` / `compile` / `preview` / `render` 已优先走本地 Worker，并在应用生命周期内尽量复用同一个 Worker 进程。
- 如果 Worker 被取消或异常退出，Tauri 会清理 Worker 句柄，下一次任务再重新启动新的 Worker。
- 当前支持的任务类型如下：
  - `health`：返回引擎版本和探测到的硬件编码器。
  - `scan`：生成 `media_library.json`。
  - `plan`：生成 `story_blueprint.json`。
  - `compile`：生成 `render_plan.json`。
  - `render`：根据完整渲染计划输出最终视频。
  - `preview-render`：基于同一份渲染计划输出真实低清预览。
  - `preview-title`：输出低清标题风格预览。
  - `stop` / `shutdown`：结束 Worker 进程。

单次健康检查示例：

```powershell
python video_engine_worker.py --health
```

单次预览任务示例：

```powershell
'{"type":"preview-render","plan_path":"D:\\project\\.video_create_project\\render_plan.json","output_path":"D:\\project\\.video_create_project\\preview.mp4","params":{"aspect_ratio":"16:9"},"height":540,"fps":15,"max_duration":20,"max_segments":8}' | python video_engine_worker.py --once
```

## 打包策略

### 第一阶段：生成 Worker 可执行文件

将 `video_engine_worker.py` 打包为独立可执行文件：

```powershell
npm run build:worker
```

打包结果输出到 `src-tauri/bin/video-create-worker.exe`。

打包机上建议重点验证以下依赖和资源是否完整：

- `moviepy`
- `imageio_ffmpeg`
- `PIL`
- `numpy`
- `proglog`

### 第二阶段：接入 Tauri 资源查找

Tauri 查找 Worker 的顺序应为：

- 已打包随应用分发的资源可执行文件：`video-create-worker.exe`
- 开发环境回退：`python video_engine_worker.py`
- 最终回退：旧的 `video_engine_v5.py` CLI 命令

当前 Tauri 集成方式会保持 Worker 常驻，并通过标准输入发送 JSON 行任务。旧的直接 CLI 调用逻辑仅保留为兜底参考路径，后续应继续收敛到 Worker 协议。

### 第三阶段：任务队列与协议稳定化

Worker 协议继续保持 JSON 行模式：

- Tauri 每次发送一行 JSON 任务。
- Worker 每次返回一行 JSON 事件或结果。
- 大文件始终只通过绝对路径引用。
- 现有引擎输出的进度事件可以原样透传。

## 安全规则

- 不通过 IPC 传输视频或图片字节。
- 不在前端长期持有完整长视频时间线。
- 长视频最终渲染仍然优先使用分块和缓存策略。
- 低清预览必须复用同一份渲染计划，只降低分辨率、帧率和时长。
- 所有 FFmpeg 路径都必须坚持等比缩放、补边和 `setsar=1`，禁止拉伸变形。
