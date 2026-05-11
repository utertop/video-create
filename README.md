# Video Create Studio

**桌面级旅行视频自动生成器** — Tauri + React + Python

将照片与视频素材一键合成为 B 站 / YouTube 风格的旅行视频，支持横屏 / 竖屏、章节标题卡、水印、交叉淡化、封面图自动生成。

## 功能概览

| 功能 | 状态 |
|------|------|
| 原生文件夹选择（素材目录 / 输出目录） | ✅ |
| 参数面板（标题、副标题、片尾、水印、画幅、质量、引擎） | ✅ |
| 命令预览 + 实时终端日志 | ✅ |
| 百分比进度条 + 阶段指示器 | ✅ |
| 结果卡片 + 一键打开输出目录 | ✅ |
| Python 引擎调用（`make_bilibili_video_v3.py`） | ✅ |
| AI 配乐蓝图 / 模板匹配 | 🔜 规划中 |

## 运行要求

- **Node.js** ≥ 18
- **Rust** (stable)
- **Python** ≥ 3.9，需安装依赖：
  ```bash
  pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg
  ```

## 快速启动

```powershell
npm install
npm run tauri dev
```

> 如果终端找不到 `cargo`，先执行 `$env:Path += ";$HOME\.cargo\bin"`

## 架构

```text
┌──────────────┐     invoke()      ┌──────────────┐    spawn()    ┌─────────────────────────┐
│  React UI    │ ──────────────▶   │  Rust 后端   │ ──────────▶  │  Python 渲染引擎        │
│  (Vite)      │ ◀────────────── │  (Tauri v2)  │ ◀────────── │  make_bilibili_video_v3 │
│              │   event stream    │              │   stdout     │  FFmpeg / MoviePy       │
└──────────────┘                   └──────────────┘              └─────────────────────────┘
```

- **前端 → 后端**：通过 Tauri `invoke` 传递 JSON 参数
- **后端 → Python**：`std::process::Command` 启动子进程，stdout/stderr 通过 `emit("video-progress")` 实时推送
- **文件**：大文件（视频、图片）始终留在磁盘，IPC 只传路径

## 项目结构

```text
video_create/
├── src/                    # React 前端
│   ├── App.tsx             # 主界面
│   ├── lib/engine.ts       # Tauri IPC 桥接层
│   └── styles.css          # 全局样式
├── src-tauri/              # Rust 后端
│   ├── src/lib.rs          # Tauri 命令 (generate_video, open_in_explorer)
│   ├── tauri.conf.json     # 应用配置
│   └── capabilities/       # 权限声明
├── make_bilibili_video_v3.py  # Python 视频引擎
└── package.json
```

## 开发路线图

1. ~~GUI MVP 全流程闭环~~ ✅
2. ~~进度反馈 + UI 打磨~~ ✅
3. 🔜 AI 配乐蓝图 — 素材情绪分析
4. 🔜 Python 引擎打包（PyInstaller / Nuitka）
5. 🔜 时间线可视化编辑器
