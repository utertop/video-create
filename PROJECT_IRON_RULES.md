# Video Create Studio 项目铁律 (Mandatory Rules)

> 本文档定义了项目的核心开发规范与防退化准则。所有后续功能迭代必须严格遵守。

---

## 铁律一：Antigravity 执行优先 (Agent Responsibility)

**规则**：Antigravity 在协助开发时，必须亲自完成代码分析、逻辑重构和 Bug 修复。**禁止**编写任何形式的自动化脚本（如 Python/Node 脚本）来调用外部 AI API 来间接完成本应由 Agent 完成的任务。

**正确做法**：
- ✅ **Agent 亲自操刀**：直接读取代码 → 理解逻辑 → 使用 `replace_file_content` 修复。
- ❌ **外包任务**：写一个脚本把代码发给 Gemini API 处理后写回。

---

## 铁律二：跨进程通信 (IPC) 极简原则

**规则**：Tauri 前端、Rust 后端与 Python 渲染引擎之间的通信必须遵循“**只传路径与状态，不传数据流**”的原则。

- **禁止**：通过 IPC 通信管道传递视频、图片或音频的二进制数据（Buffer/Base64）。
- **强制**：仅传递文件的**绝对路径**。
- **强制**：Python 引擎的进度反馈必须通过标准输出（stdout）以结构化 JSON 字符串形式（`{"progress": 50, ...}`）传递。

---

## 铁律三：保持 UI/UX 的“Premium”质感

**规则**：前端开发严禁使用原生 HTML 默认样式或简单的配色。

- **色彩**：必须使用调和的深色模式（Dark Mode）或经过设计的渐变色（Gradients）。
- **交互**：所有按钮必须有 Hover 状态，所有加载过程必须有进度条或 Skeleton 动画。
- **一致性**：新组件必须沿用 `src/styles.css` 中定义的 CSS 变量（如 `--accent-color`, `--bg-dark`）。

---

## 铁律四：素材显示比例零拉伸、零畸变 (No Stretch / No Distortion)

**规则**：所有照片、视频素材在最终合成视频中的显示比例必须与用户原始看到的显示效果一致。任何渲染路径、性能优化、缓存、FFmpeg 快路径、MoviePy 合成、章节动效、转场策略，都不得造成素材画面横向或纵向拉伸、压扁、人物变形、画面畸变。

**强制要求**：

- 图片必须先做 EXIF 方向修正，再按原始宽高比例缩放。
- 视频必须尊重显示宽高，不得只信任编码宽高。
- 遇到 `rotation / displaymatrix / sample_aspect_ratio / display_aspect_ratio` 等视频显示元数据时，必须先归一化显示几何，再进入 MoviePy 或 FFmpeg 合成。
- 缩放只能使用等比缩放：`min(target_w / source_w, target_h / source_h)` 或 FFmpeg `force_original_aspect_ratio=decrease`。
- 不足画布的区域只能用补边、模糊背景、纯色背景或设计背景填充。
- 禁止为了填满画布直接把素材强制 resize 到目标宽高。
- 任何新的视频快路径必须显式设置 `setsar=1`，避免非方形像素导致最终显示变形。
- 性能优化只能降级转场复杂度或运动强度，不能牺牲素材显示比例。

**正确做法**：

- 横屏素材进入 16:9：等比缩放后居中，不足区域补背景。
- 竖屏素材进入 16:9：等比缩放后左右补模糊背景或设计背景。
- 16:9 素材进入 9:16：等比缩放后上下或左右按规则补背景，不得拉伸填满。
- 带 SAR/DAR/旋转信息的视频：先用 FFmpeg 归一化显示比例，再参与合成。

**禁止做法**：

- `clip.resize((target_w, target_h))` 直接强制拉满画布。
- FFmpeg `scale=target_w:target_h` 但没有 `force_original_aspect_ratio=decrease`。
- 忽略 `sample_aspect_ratio` 后直接按编码宽高合成。
- 为了速度跳过显示比例检测。

**回归验证**：

- 修改渲染、转场、缓存、FFmpeg、MoviePy 相关代码后，必须运行视频几何保护测试：`python tests\smoke_v5_video_geometry.py`。

---

## 历史问题与防退化清单 (Past Bug Registry)

触碰相关模块前必须自检，确保不重蹈覆辙。

### 1. Python 环境依赖缺失 (Runtime Error)
- **风险点**: `make_bilibili_video_v3.py` 依赖 `moviepy`, `ffmpeg`, `PIL`。
- **准则**: 修改 Python 引擎后，必须在 `README.md` 中同步更新依赖要求，且在代码中加入显式的依赖检查逻辑。

### 2. FFmpeg 路径硬编码
- **风险点**: 脚本中曾出现硬编码 `/usr/bin/ffmpeg` 导致 Windows 无法运行。
- **准则**: 必须通过 `shutil.which('ffmpeg')` 动态查找，或在 Tauri 配置中指定打包后的 FFmpeg 路径。

### 3. IPC 消息丢失 (Race Condition)
- **风险点**: Python 启动瞬间输出过快，导致 Rust 还没建立监听就丢失了前几行日志。
- **准则**: Rust 后端在 `spawn` 进程后应立即启动异步读取循环。

---

## 项目核心文件备忘录

| 文件 | 职责 | 注意事项 |
|------|------|---------|
| `make_bilibili_video_v3.py` | **渲染心脏** | 负责音视频剪辑核心算法。改动需考虑性能。 |
| `src-tauri/src/lib.rs` | **中枢指挥** | 处理跨进程调用与权限管理。避免在此写复杂业务逻辑。 |
| `src/lib/engine.ts` | **前端桥接** | 负责解析 Python 输出的 JSON 进度并更新 Store。 |
| `src/styles.css` | **视觉基准** | 定义了项目的全局设计系统。严禁在此随意添加 Ad-hoc 样式。 |
