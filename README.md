# Video Create Studio

**桌面级旅行视频自动生成器** — Tauri + React + Python

Video Create Studio 是一个面向旅行 / Vlog / B站 / YouTube 内容创作者的桌面视频生成工具。它将素材目录中的照片与视频，通过 V5 四阶段引擎自动生成带章节、文案卡、虚化背景、水印和封面的旅行短片。

## 当前版本定位：V5.3

V5.3 的主流程是：

```text
素材目录
  ↓ scan
media_library.json
  ↓ plan
story_blueprint.json
  ↓ 用户审核故事蓝图
  ↓ compile
render_plan.json
  ↓ render
最终 mp4
```

## 功能概览

| 功能 | 状态 |
|---|---|
| 原生文件夹选择：素材目录 / 输出目录 | ✅ |
| V5 四阶段引擎：scan / plan / compile / render | ✅ |
| `media_library.json` 素材事实库 | ✅ |
| `story_blueprint.json` 故事蓝图 | ✅ |
| `render_plan.json` 渲染计划 | ✅ |
| 片头 / 片尾文案卡首帧 / 尾帧虚化背景 | ✅ |
| 片头 / 片尾背景手动选择 | ✅ |
| 章节卡智能过渡背景 | ✅ |
| 章节卡背景手动选择 | ✅ |
| 景点章节默认首素材标题叠加 | ✅ |
| B站封面自动生成 | ✅ |
| V3 脚本兼容模式 `make_bilibili_video_v3.py` | ✅ Legacy |

## V5.3 章节背景策略

在“生成参数”中可以选择：

```text
章节卡背景：
- 智能过渡：上一段尾帧 + 当前章节首帧融合虚化
- 章节首图：当前章节第一个视觉素材虚化
- 纯色极简：品牌纯色背景
```

每个章节还可以在故事蓝图审核页单独点击“选择背景”，从素材库中选择图片或视频缩略图作为该章节文案卡背景。

## 景点章节策略

为了让旅行视频更自然，V5.3 默认：

```text
城市 / 日期 / 普通章节：完整章节卡
景点章节：首素材标题叠加
```

如果你给景点章节手动选择背景，该景点章节会升级为完整章节卡。

## 运行要求

- Node.js >= 18
- Rust stable
- Python >= 3.9

Python 依赖：

```bash
python -m pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg proglog
```

## 快速启动

```powershell
npm install
npm run tauri dev
```

## 项目结构

```text
video-create/
├── src/
│   ├── App.tsx
│   ├── lib/engine.ts
│   ├── styles.css
│   └── v5-background.css
├── src-tauri/
│   ├── src/lib.rs
│   └── tauri.conf.json
├── video_engine_v5.py
├── make_bilibili_video_v3.py
└── package.json
```

## 开发验证

```powershell
python -m py_compile .\video_engine_v5.py
npm run build
cargo check --manifest-path .\src-tauri\Cargo.toml
npm run tauri dev
```
