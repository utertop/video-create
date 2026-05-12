# Video Create Studio

**桌面级旅行视频自动生成器** — Tauri + React + Python

Video Create Studio 将照片、相机视频与旅行素材组织成可审核的故事蓝图，再渲染为适合 B 站 / YouTube 发布的横屏或竖屏视频。

## V5.1 核心定位

V5.1 默认使用新的四阶段工程链路：

```text
素材目录
  ↓ scan
media_library.json
  ↓ plan
story_blueprint.json
  ↓ 用户审核 / 编辑
  ↓ compile
render_plan.json
  ↓ render
最终 mp4 + cover
```

旧版 `make_bilibili_video_v3.py` 仍保留为 Legacy 兼容脚本，但 V5.1 主流程以 `video_engine_v5.py` 为准。

## 功能概览

| 功能 | 状态 |
|------|------|
| 原生文件夹选择（素材目录 / 输出目录） | ✅ |
| V5 素材扫描：城市 / 日期 / 景点目录识别 | ✅ |
| Media Library / Story Blueprint / Render Plan 三层 JSON | ✅ |
| 故事蓝图审核：章节标题、启用/禁用、素材预览 | ✅ |
| Render Plan 时间线预览 | ✅ |
| 最终导出进度回传，避免 98% 假卡住 | ✅ |
| V5 渲染任务取消 | ✅ |
| Legacy V3 一键生成脚本 | ✅ 兼容 |
| AI 配乐蓝图 / 智能选片 / 模板匹配 | 🔜 V6 规划 |

## 运行要求

- Node.js ≥ 18
- Rust stable
- Python ≥ 3.9

Python 依赖：

```powershell
python -m pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg proglog
```

## 快速启动

```powershell
npm install
npm run tauri dev
```

## 推荐使用流程

1. 选择素材目录，例如：

```text
E:\bilibili_create\泉州-厦门
├── 泉州
│   ├── 西街
│   └── 开元寺
└── 厦门
    ├── 鼓浪屿
    └── 曾厝垵
```

2. 选择输出目录。

V5.1 会在输出目录下生成项目工作目录：

```text
<输出目录>\.video_create_project
├── media_library.json
├── story_blueprint.json
└── render_plan.json
```

3. 点击“开始智能编排”。
4. 在“故事蓝图审核”里确认章节、素材和标题。
5. 点击“确认并进入渲染”。
6. 点击“立即开始最终合成”。

最终输出：

```text
<输出目录>\travel_video.mp4
<输出目录>\cover_travel_video.jpg
```

## V5 引擎命令

```powershell
python video_engine_v5.py scan --input_folder "E:\素材" --output "E:\输出\.video_create_project\media_library.json" --recursive
python video_engine_v5.py plan --library "E:\输出\.video_create_project\media_library.json" --output "E:\输出\.video_create_project\story_blueprint.json"
python video_engine_v5.py compile --blueprint "E:\输出\.video_create_project\story_blueprint.json" --library "E:\输出\.video_create_project\media_library.json" --output "E:\输出\.video_create_project\render_plan.json"
python video_engine_v5.py render --plan "E:\输出\.video_create_project\render_plan.json" --output "E:\输出\travel_video.mp4"
```

## 架构

```text
React UI
  ↓ Tauri invoke
Rust Commands
  ├── scan_v5
  ├── plan_v5
  ├── compile_v5
  └── render_v5
      ↓ spawn python
video_engine_v5.py
  ├── scan
  ├── plan
  ├── compile
  └── render
      ↓ MoviePy / FFmpeg
final mp4
```

## 项目结构

```text
video-create/
├── src/
│   ├── App.tsx
│   ├── lib/engine.ts
│   └── styles.css
├── src-tauri/
│   ├── src/lib.rs
│   ├── src/main.rs
│   └── tauri.conf.json
├── video_engine_v5.py
├── make_bilibili_video_v3.py
└── package.json
```

## 开发验证

```powershell
npm run build
cargo check --manifest-path .\src-tauri\Cargo.toml
python -m py_compile .\video_engine_v5.py
python .\video_engine_v5.py --help
```

## 路线图

- V5.1：主流程稳定闭环、进度回传、任务取消、JSON 工作目录规范
- V5.2：更完整的故事蓝图审核页和素材筛选
- V6：AI 配乐蓝图、智能选片、模板匹配、时间线编辑器
