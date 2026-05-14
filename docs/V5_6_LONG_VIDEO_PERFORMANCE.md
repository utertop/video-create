
# Video Create Studio V5.6 长视频性能与稳定性优化

## 背景

30 分钟视频如果继续使用“一次性 MoviePy 大合成”，容易出现：

- 内存越来越高；
- UI 卡死；
- `write_videofile` 中途失败；
- 最终 mp4 写了一半，文件损坏；
- 失败后只能从头再来。

V5.6 改为 **分段渲染 + FFmpeg 拼接 + 原子输出 + 可恢复缓存**。

## 核心能力

### 1. 原子输出

不直接写最终文件：

```text
travel_video.rendering.tmp.mp4
  -> 校验通过
  -> travel_video.mp4
```

失败时不会覆盖旧成品。

### 2. 自动长视频稳定模式

默认 `render_mode=auto`：

- 短视频：继续标准渲染；
- 长视频：自动启用分段稳定渲染。

触发条件：

```text
total_duration >= 600 秒
或 segment 数 >= 80
```

### 3. 分段渲染

默认每段约 240 秒：

```text
chunks/
├── chunk_000.mp4
├── chunk_001.mp4
└── chunk_002.mp4
```

### 4. manifest 可恢复

```json
{
  "chunks": {
    "chunk_000.mp4": {
      "status": "done",
      "cache_key": "...",
      "duration": 238.5
    }
  }
}
```

下次渲染时已完成分段会复用。

### 5. FFmpeg concat

优先使用 `imageio-ffmpeg` 的 ffmpeg：

```bash
ffmpeg -f concat -safe 0 -i concat_list.txt -c copy final.rendering.tmp.mp4
```

失败时回退 MoviePy 拼接。

### 6. build_report.json

输出：

```text
.video_create_project/build_report.json
```

记录 chunk 数、渲染耗时、输出路径、失败原因等。

## 使用建议

30 分钟视频建议：

```text
quality: high 或 standard
fps: 24/25/30 均可，优先 24/25
chunk_seconds: 180~300
输出目录使用本地 SSD
磁盘剩余空间至少是预计视频大小 5 倍
```

## 验证

```powershell
python -m py_compile .\video_engine_v5.py
python .\tests\smoke_v5_6_long_video_stability.py
npm run build
cargo check --manifest-path .\src-tauri\Cargo.toml
```
