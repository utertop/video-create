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

## V5.3.2 稳定收口

V5.3.2 的目标不是继续堆叠新剪辑能力，而是把 V5.3 已经具备的能力收口成可验证、可排查、可维护的工程版本。

当前主流程：

```text
scan -> media_library.json -> plan -> story_blueprint.json -> compile -> render_plan.json -> render -> final mp4
```

关键能力：

- 片头 / 片尾默认使用首帧 / 尾帧虚化背景。
- 片头 / 片尾支持用户手动选择背景图片。
- 投稿封面默认复用片头卡的虚化背景与标题布局。
- 章节卡支持智能过渡背景、章节首图背景、纯色背景、自定义背景。
- 景点章节默认使用标题叠加，减少完整章节卡造成的视频割裂感。
- CI 增加 Python 依赖安装与 scan / plan / compile 最小烟测。

V3 `make_bilibili_video_v3.py` 仅作为 Legacy 兼容路径保留；V5 主流程以 `video_engine_v5.py` 为准。

## V5.4.2 目录识别策略增强

V5.4.2 将目录识别从简单关键词命中升级为“层级上下文 + 同级一致性 + 强/中/弱关键词 + 置信度解释”的策略。

核心规则：

- 根目录下一层素材目录默认作为 `chapter`，避免 `登山` 因单字 `山` 被误判为 `scenic_spot`。
- `scenic_spot` 更依赖父级上下文：父目录是城市或日期时，子目录才更容易识别为景点。
- 景点关键词分为强景点名、景点后缀、弱关键词；弱关键词不会单独决定类型。
- 扫描后执行同级目录一致性修正，避免同一级目录出现一个 `SCENIC_SPOT`、其他都是 `CHAPTER` 的割裂结果。
- `directory_nodes` 增加 `raw_detected_type` 与 `signals`，便于 GUI 展示识别依据，也方便用户覆盖自动识别结果。

## V5.5 章节文字动效与模板系统

V5.5 将文字渲染从静态图片升级为动态模板系统，实现了：

- **基于模板的视觉风格 (Presets)**: `cinematic_bold`, `travel_postcard`, `playful_pop`, `impact_flash`, `minimal_editorial`, `nature_documentary`。
- **丰富的动效 (Motions)**: `fade_only`, `fade_slide_up`, `soft_zoom_in`, `pop_bounce`, `quick_zoom_punch`, `slow_fade_zoom`。
- **智能样式推荐**: 扫描引擎根据素材内容（如“猫咪”、“雪山”、“美食”）自动匹配最合适的文字样式与动效。
- **高级渲染引擎**: 使用 Pillow 生成分层文字图层，结合 MoviePy 的时间相关 Lambda 表达式实现平滑的属性动画。
