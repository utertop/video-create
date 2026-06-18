# 自动化剪辑工作台专业化执行方案, 2026-06-17

## 2026-06-18 Implementation Status

已完成：
- Preview quality 档位 UI 与 `performance_policy.preview` 写入。
- `timeline-preview-manifest` V1：
  - Python API：`build_timeline_preview_manifest(...)`
  - CLI：`python video_engine_v5.py timeline-preview-manifest ...`
  - Worker task：`type = "timeline-preview-manifest"`
  - Tauri command / TS bridge：`timelinePreviewManifestV5(...)`
  - Manifest 记录每个 clip 的 `thumbnail`、`proxy`、`waveform`、`preview_segment` 状态、路径、cache namespace、preview profile、height、fps、source fingerprint。
- `timeline-preview-assets` 增量生成器：
  - Python API：`generate_timeline_preview_assets(...)`
  - CLI：`python video_engine_v5.py timeline-preview-assets ...`
  - Worker task：`type = "timeline-preview-assets"`
  - Tauri command / TS bridge：`timelinePreviewAssetsV5(...)`
  - 按 manifest 生成 timeline thumbnail、FFmpeg waveform peak JSON、视频 proxy、local preview segment，并回写 ready/planned/failed 状态。
  - 支持 `batch_size` 分批进度事件，避免大量 clip 时每个资产刷新 UI。
- Timeline preview assets 后台队列 V1：
  - Timeline autosave 后自动延迟触发 preview assets 生成。
  - 新任务开始前会取消旧的 `v5-timeline-preview-assets` worker 任务，避免过期 manifest 覆盖新结果。
  - 生成过程通过 `timeline_preview_assets` 事件上报 `current/total/percent/status/clip_id/artifact_kind/message`。
  - Timeline toolbar 显示 `Assets current/total` 进度，生成中禁用重复刷新。
  - 最终渲染或 Timeline apply 期间不启动 preview assets 任务，避免争用主渲染资源。
- Timeline UI 已消费 manifest：
  - visual clip 显示 thumbnail。
  - audio clip 读取 waveform JSON 并显示峰值条。
  - proxy/preview segment ready 时显示资产状态点。
  - 资产失败时显示 failed 状态点，Toolbar 可手动刷新预览资产。
  - 项目/session 恢复会保留 `timeline_preview_manifest.json`。
- waveform 生成已从 WAV 扩展为 FFmpeg PCM 解码路径，支持 MP3/AAC/M4A 以及带音轨视频的波形峰值生成。
- 测试覆盖：`tests/smoke_v5_timeline_preview_manifest.py`，并已通过 `npm.cmd run check` core suite。

仍待下一阶段实现：
- 更细的后台队列并发限速、失败重试和断点恢复。
- 更精细的 clip range preview segment，包括 source in/out、转场、叠字和音频预览。
- UI 上显示 failed 资产的诊断入口和手动重建按钮。

## 文档定位

这份文档用于回答一个核心问题：

> 当前项目定位是自动化剪辑，但哪些能力应该向专业剪辑软件靠拢，应该为什么做、按什么顺序做、做到什么程度才算有效？

结论先放在前面：

本项目不应该直接复制 `Premiere Pro / DaVinci Resolve / Final Cut Pro` 的完整形态。更实际、也更有竞争力的方向是：

> 自动生成初剪 + 专业化时间轴微调 + 局部重算 + 稳定快速导出

也就是说，项目的主价值仍是自动化生成、批量处理、长视频稳定出片；专业剪辑软件能力应该服务于“用户对自动生成结果进行高效二次调整”，而不是把产品改造成通用 NLE。

相关文档：

- [路线图总索引](./ROADMAP_INDEX.md)
- [专业剪辑器差距与成熟度路线图](./PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md)
- [Timeline Editor 最终优化规划方案](./TIMELINE_EDITOR_FINAL_OPTIMIZATION_PLAN.md)
- [时间线数据模型 V1 设计稿](./TIMELINE_SCHEMA_V1.md)
- [局部失效与重算规则 V1](./INVALIDATION_AND_RECOMPUTE_RULES.md)
- [视频段缓存与 FFmpeg 扩展](./VIDEO_SEGMENT_CACHE_AND_FFMPEG_EXPANSION.md)

---

## 一、当前定位

### 1. 当前项目更像什么

当前项目已经具备一条自动化视频生产主链：

```text
scan
  -> media_library.json
plan
  -> story_blueprint.json
compile
  -> render_plan.json
timeline-generate / timeline-edit
  -> timeline.json
timeline-compile
  -> render_plan.json
render
  -> final mp4 + build_report.json
```

现有基础包括：

- `src/features/timeline/*` 已有基础 Timeline UI、Inspector、Track、Clip、Undo/Redo、编辑操作。
- `src/lib/v5Types.ts` 已有 `V5Timeline / V5TimelineTrack / V5TimelineClip` 类型。
- `video_engine/timeline.py` 已有 timeline 生成、迁移、恢复能力。
- `video_engine/timeline_compile.py` 已有 timeline -> render_plan 编译能力。
- `video_engine_v5.py` 已有 `timeline-generate` 和 `timeline-compile` CLI。
- 渲染侧已有 stable renderer、chunk scheduler、segment cache、audio cache、FFmpeg fast path、MoviePy fallback。
- 近期已经把更多标题/卡片动效迁入“独立预渲染单元 + FFmpeg chunk”路径。

所以项目已经不是只有“生成按钮”的原型，而是有机会演进为：

> 面向自动化视频生产的专业化剪辑工作台。

### 2. 当前不应该变成什么

短期不应该把目标设为完整通用专业剪辑器：

- 不做完整多机位剪辑。
- 不做完整节点式调色。
- 不做大型插件生态。
- 不做复杂三维合成。
- 不追求所有专业快捷键和操作范式一次到位。
- 不把所有工程资源投入“看起来像专业软件”的 UI 表面。

原因很简单：这些能力投入巨大，但对当前最核心的产品价值“自动化初剪、快速稳定出片、用户少量精修”帮助不成比例。

---

## 二、为什么要向专业剪辑软件靠拢

### 1. 用户价值原因

自动化剪辑最大的问题不是“不会生成”，而是：

- 自动生成结果往往只差一点点。
- 用户需要改某个片段顺序。
- 用户需要缩短某张图片停留时间。
- 用户需要删掉一段不合适的素材。
- 用户需要修改标题、字幕、卡片、BGM 音量。
- 用户不希望因为一个小改动重新跑完整生成流程。

如果没有专业化时间轴能力，用户会被迫：

- 回到参数配置重新生成。
- 导出后去其他剪辑软件二次编辑。
- 修改 JSON 或依赖不可视化流程。
- 多次全量渲染，成本高且不稳定。

因此，时间轴编辑不是为了炫技，而是为了让自动化结果变得可控。

### 2. 产品竞争力原因

纯自动化生成工具容易遇到上限：

- 初剪质量再好，也无法完全符合用户主观偏好。
- 用户一旦进入专业软件二次编辑，本项目就失去后续工作流控制权。
- 导出后再外部编辑，会破坏缓存、恢复、诊断、模板和自动化链路。

如果本项目提供轻量但专业的二次调整能力，就可以形成更完整闭环：

```text
自动生成
  -> 时间轴微调
  -> 局部应用
  -> 快速预览
  -> 稳定导出
  -> build_report 可解释
```

这比“只生成”更像一个真正可长期使用的生产工具。

### 3. 工程原因

专业化时间轴不是单纯 UI 功能，它会倒逼工程结构变清晰：

- 用户编辑意图进入 `timeline.json`，不再散落在前端临时状态。
- `render_plan.json` 回到执行计划定位，不再被用户直接修改。
- 局部重算有明确边界。
- cache key 和 invalidation 可以稳定关联 clip。
- build report 可以解释“为什么重算、为什么复用、为什么回退慢路径”。

这和当前正在做的 FFmpeg route、chunk cache、pre-render unit、recovery 是同一条线。

---

## 三、最终目标

### 1. 产品目标

把项目升级为：

> 自动化视频生成 + 专业化时间轴微调 + 可解释稳定渲染的一体化桌面工具。

用户视角的目标：

- 自动生成后能直接在时间轴里调整。
- 基础剪辑操作不需要离开本软件。
- 修改标题、卡片、字幕、音频、片段顺序后，可以明确应用到渲染计划。
- 小改动尽量只触发局部重算。
- 导出失败后能恢复，导出慢时能解释慢在哪里。

### 2. 工程目标

工程侧目标：

- `timeline.json` 成为用户编辑意图的唯一来源。
- `render_plan.json` 只作为渲染执行计划。
- 所有时间轴编辑操作都可 undo/redo、可保存、可恢复。
- 每类编辑操作都有明确 invalidation scope。
- preview 和 final render 的质量、缓存、路径分离。
- 更多常见 clip 走 FFmpeg/pre-render fast path。
- MoviePy 继续作为 fallback，而不是主路径。

### 3. 性能目标

第一阶段不追求实时专业剪辑器性能，但要达到：

- 100 个 clip 内时间轴交互不卡顿。
- 基础编辑操作即时响应。
- 时间轴编辑视图不直接解码或渲染全质量原片。
- 编辑预览使用清晰代理素材或中等分辨率预览，最低应能看清主体、字幕、标题和构图。
- 最终导出必须回到原始素材、正式渲染参数和高质量编码路径。
- 应用 Timeline 编辑时只重新编译 render_plan，不直接全量渲染。
- 能在报告中看到 timeline 编辑导致的重算范围。
- 安全卡片、标题、图片、轻量视频尽量进入 segment/chunk cache。

---

## 四、优化方向

## 方向 A：时间轴成为真正编辑层

### 当前问题

如果时间轴只是 `render_plan.segments` 的展示，它不能承担专业化编辑职责。

用户真正需要编辑的是：

- clip 顺序
- clip 时长
- source in/out
- enabled/disabled
- 标题文字
- 标题样式
- 音频 cue
- subtitle/overlay
- 每个 clip 的重算范围

这些不应该直接写进 `render_plan.segments`。

### 优化目的

让 `timeline.json` 成为中间真相层：

```text
story_blueprint
  -> timeline
  -> render_plan
```

### 执行策略

- 前端所有手工编辑先写 `v5Timeline`。
- `v5Timeline.metadata.dirty = true` 表示有未应用编辑。
- 用户点击“应用 Timeline 编辑”后调用 `timeline-compile`。
- 编译成功后更新 `v5RenderPlan`，并将 timeline dirty 状态清理。
- 渲染阶段继续只吃 `render_plan`，避免渲染器直接依赖 UI 状态。

### 优先级

P0。没有这层，后续所有专业化 UI 都会变成脆弱的临时状态。

---

## 方向 B：基础非线性编辑操作

### 当前问题

专业剪辑器的核心体验不是特效，而是基础剪辑动作足够顺手：

- 移动
- 裁剪
- 分割
- 删除
- 波纹删除
- 吸附
- 撤销/重做

如果这些不稳，用户不会信任这个时间轴。

### 优化目的

让用户可以对自动生成结果做最常见的二次整理。

### P0 编辑能力

第一批必须稳定：

- 选择 clip
- 启用/禁用 clip
- 拖动排序
- 修改 duration
- 修改标题/卡片文本
- 修改标题/卡片 motion/style
- 修改 BGM cue 音量
- undo/redo
- dirty/apply 状态清晰

### P1 编辑能力

第二批再做：

- trim left/right
- split clip
- ripple delete
- snap to clip edge
- snap to chapter cue
- snap to subtitle sentence
- duplicate clip

### P2 编辑能力

后续再做：

- 多轨 overlay 叠加
- 字幕轨编辑
- keyframe
- effect stack
- nested timeline

### 执行策略

- 先用按钮和 Inspector 完成稳定操作，再加复杂拖拽。
- 拖拽要先支持“排序”，再支持“自由时间定位”。
- 初期禁止同轨重叠，避免编译器复杂度暴涨。
- 所有操作必须进入 `useTimelineHistory`，不能绕开 undo/redo。

---

## 方向 C：片段 Inspector 专业化

### 当前问题

自动化工具常见痛点是“参数散、难找、不知道改了什么会影响哪里”。

### 优化目的

让 Inspector 成为用户精修的主入口。

### Inspector 第一阶段字段

通用字段：

- clip 类型
- track
- start
- duration
- source
- segment id
- recompute scope
- preferred route
- cache namespace
- enabled

视觉字段：

- source in/out
- fit/crop mode
- motion type
- transition
- overlay text

标题/卡片字段：

- title text
- subtitle text
- preset
- motion
- background
- position

音频字段：

- volume
- fade in/out
- ducking
- section cue

### 执行策略

- Inspector 中每个编辑动作只改 timeline clip。
- 修改后展示“需要应用 Timeline 编辑”状态。
- 对每个字段标注 recompute scope，但不需要用说明文字堆 UI，可以用状态徽标和 tooltip。
- 第一阶段不做复杂曲线编辑，只做数值和枚举。

### 优先级

P0。因为 Inspector 是最容易稳定落地的专业化入口，比复杂拖拽风险低。

---

## 方向 D：局部重算与缓存复用

### 当前问题

用户做一个小修改，如果系统总是全量重编译或全量重渲染，时间轴编辑的价值会被抵消。

### 优化目的

让时间轴编辑可以稳定映射到最小重算范围：

- 修改标题文字：优先只重做 title/card segment。
- 修改图片时长：重编译 timeline，并尽量复用 source/cache。
- 修改片段顺序：重编译 render_plan，chunk cache 按 key 判断复用。
- 修改 BGM 音量：优先 audio track 重算。
- 修改导出参数：只影响 final render，不污染 preview cache。

### 执行策略

- 复用 `timelineInvalidation.ts` 和 `INVALIDATION_AND_RECOMPUTE_RULES.md`。
- 每个 `V5TimelineClip` 保留 `invalidation_hint`。
- `timeline-compile` 输出 `metadata.recompute_summary`。
- `build_report.json` 继续扩展 timeline/cache/recompute 摘要。
- 对可独立预渲染单元优先生成 segment cache：
  - image segment
  - video motion segment
  - title/card segment
  - safe overlay segment
  - audio cue/mix segment

### 优先级

P0 到 P1。先做到“可解释、可保守重算”，再追求极致局部化。

---

## 方向 E：Preview 与 Final Render 分离

### 当前问题

专业软件强的地方在于 preview 快，final 稳；两者不应该混成同一条不可控路径。

如果时间轴编辑阶段直接使用原始 4K/高码率素材、完整标题动画、完整音频混合和正式导出参数，用户在拖动、裁剪、定位播放头时很容易卡顿。反过来，如果预览质量压得太低，用户又看不清画面细节、字幕、标题和构图，无法做可靠判断。

### 优化目的

建立清晰的双路径：

```text
Timeline Preview
  -> proxy / low_res / cached preview

Final Render
  -> original media / high quality / stable backend
```

核心原则：

- 编辑时可以降分辨率、降 fps、用代理素材、用预渲染缩略图。
- 预览不能低到影响判断，标题、字幕、主体画面必须清楚。
- 用户可以选择编辑预览质量，高性能 PC 可以使用高清甚至原始质量时间轴预览。
- 最终生成不能使用低清代理结果，必须回到原始素材和正式质量参数。

### 执行策略

- `performance_policy.preview.mode` 明确 `proxy / low_res / original`。
- 前端提供预览质量选择：`自动 / 性能 / 平衡 / 高清 / 原始`。
- 质量选择不直接等于最终导出质量，只影响时间轴编辑和局部预览。
- `自动` 模式根据素材分辨率、项目时长、clip 数量、硬件能力和历史卡顿情况选择预览档位。
- preview cache 和 final cache 命名空间分离。
- Inspector 修改后可以先更新时间轴视图，不立刻 final render。
- 后续增加局部 preview render 按时间范围执行。

建议预览质量阶梯：

| UI 档位 | 底层模式 | 用途 | 建议参数 | 约束 |
| --- | --- | --- | --- | --- |
| 缩略图 | `thumbnail` | 时间轴 clip 背景、快速定位 | 关键帧缩略图，宽度按 clip 显示需要生成 | 不用于播放判断 |
| 性能 | `low_res` | 很长项目或低性能机器 | 540p-720p，12-18 fps | 低于 540p 只用于极端省电/低配模式 |
| 平衡 | `proxy` | 常规编辑预览 | 720p，15-24 fps | 默认档位，必须看清字幕、标题和主体 |
| 高清 | `proxy` 或 `original` | 高性能 PC 的清晰编辑 | 1080p 或源素材较低时原尺寸，24-30 fps | 允许较高资源占用，但不能污染 final cache |
| 原始 | `original` | 质量检查、短范围精修 | 原始素材或接近最终参数 | 建议用于短范围或高性能 PC |
| 最终导出 | `final` | 最终生成 | 原始素材、高质量编码、正式音频 | 禁止复用低清 preview cache 作为最终画面 |

推荐默认：

- 普通 1080p 项目：preview 使用 720p proxy。
- 4K 或高码率项目：preview 使用 720p proxy，final 使用原始素材。
- 高性能 PC：允许用户选择 1080p 高清 preview 或 original preview。
- 字幕/标题密集项目：preview 不低于 720p，或局部 title/subtitle 区域保持高清渲染。
- 低配机器：允许 540p preview，但 UI 要提示这是性能预览，不代表最终画质。
- 如果高清或原始预览出现持续卡顿，自动模式应建议降到平衡档，但不强制改变用户手动选择。

### 优先级

P1。P0 先把编辑和 compile 闭环打稳。

---

## 方向 F：时间轴交互性能

### 当前问题

时间轴编辑会卡，通常不是因为最终渲染慢，而是因为编辑界面做了太多不该实时做的事：

- React 一次性渲染大量 clip DOM。
- 每个 clip 都尝试加载视频。
- 波形在前端临时解码。
- 缩略图没有缓存。
- 拖动时频繁写大对象、触发全树重渲染。
- 播放头移动时同步计算过多布局。

如果这些不处理，即使后端渲染很快，用户也会觉得时间轴“卡断”。

### 优化目的

让时间轴编辑阶段做到：

- 拖动、选择、缩放、滚动不卡。
- 长项目只渲染可视范围。
- clip 缩略图、波形、字幕块来自缓存数据。
- 编辑动作只更新必要 clip，不引发整页重渲染。
- 低清预览和高质量最终导出严格分离。

### 执行策略

前端交互层：

- 时间轴 viewport 虚拟化，只渲染可见 clip 和附近缓冲区。
- clip 宽度、轨道高度、ruler 刻度使用稳定尺寸，避免拖动时布局抖动。
- 拖动中只更新轻量 draft 状态，松手后再提交完整 timeline edit。
- `TimelineClip`、`TimelineTrack`、Inspector 输入组件做必要 memo。
- 长列表不要把整个 `timeline.clip_index` 深拷贝传给每个子组件。

媒体预览层：

- clip 背景优先使用缩略图，不直接嵌入视频播放器。
- 视频预览只给当前选中 clip 或当前播放范围。
- 波形使用预计算峰值 JSON，不在 React 渲染过程中解码音频。
- 字幕块、章节 cue、BGM cue 使用轻量结构绘制。

缓存层：

- 生成 `.cache_video_create_v5/timeline_thumbnails`。
- 生成 `.cache_video_create_v5/timeline_waveforms`。
- 生成 `.video_create_project/render_cache/preview_segments`。
- preview cache key 必须包含 preview resolution、fps、timeline clip id、source fingerprint。
- final cache key 必须与 preview cache namespace 分离。

后端策略：

- 增加 timeline preview manifest，记录每个 clip 的 thumbnail、proxy、waveform、preview segment。
- 对当前播放头附近的小范围做后台预热。
- 用户拖动时不触发后端渲染；用户停顿或点击预览时再排队生成 preview。
- 后台 preview 任务可取消，避免用户连续操作造成队列堆积。

### 建议性能指标

| 指标 | P0/P1 目标 |
| --- | --- |
| 100 clip 时间轴初次渲染 | 1 秒内出现可操作 UI |
| 100 clip 内选择/启用/禁用 | 100 ms 内反馈 |
| 拖动排序过程 | 30 fps 以上体感流畅 |
| 横向滚动 | 不因视频解码阻塞 |
| 缩略图缓存命中 | 二次打开项目应复用 |
| preview 生成 | 选中 clip 或 5-10 秒范围优先 |
| final render | 禁止使用低清 preview 作为最终画面 |

### 优先级

P0/P1。编辑性能和数据闭环同等重要；如果时间轴卡，后续功能越多体验越差。

---

## 方向 G：专业化时间轴视觉体验

### 当前问题

只展示 segment 列表无法给用户足够空间感。

### 优化目的

让用户更直观看到：

- 视频轨
- 音频轨
- 标题/字幕轨
- clip 时长比例
- 当前播放头
- 章节/字幕/音乐 cue
- dirty/apply 状态

### 第一阶段 UI

- 固定轨道高度。
- clip 宽度按 duration 映射。
- ruler 显示秒级刻度。
- 选中 clip 高亮。
- disabled clip 降低透明度。
- route/cache 状态用小标识展示。
- 右侧 Inspector 常驻。

### 第二阶段 UI

- 播放头。
- 缩放时间轴。
- 横向滚动。
- 波形预览。
- 字幕句子块。
- snap guide。

### 优先级

P1。视觉体验重要，但不能压过数据层和编辑闭环。

---

## 五、优化优先级总表

| 优先级 | 方向 | 为什么排这里 | 完成标志 |
| --- | --- | --- | --- |
| P0 | Timeline 作为编辑真相层 | 所有专业化能力的底座 | 编辑只写 timeline，应用后编译 render_plan |
| P0 | Inspector 可编辑核心字段 | 低风险、高收益 | title/card/audio/image 基础字段可改 |
| P0 | Undo/Redo + Dirty/Apply | 用户信任基础 | 编辑可撤销，未应用状态清晰 |
| P0 | timeline-compile 稳定闭环 | 编辑必须能进入渲染链 | smoke 覆盖编辑后 render_plan 变化 |
| P0 | 重算范围可解释 | 避免“为什么又全量渲染” | build_report 有 recompute/cache 摘要 |
| P0/P1 | 时间轴交互性能 | 防止编辑阶段卡顿 | 虚拟化、缩略图、波形缓存、轻量 draft edit |
| P1 | Trim/Split/Ripple Delete | 真正接近剪辑软件的核心操作 | 常见删减整理不离开软件 |
| P1 | Preview/Final 分离 | 提升交互速度 | preview cache 不污染 final |
| P1 | 音频波形与 cue 轨 | 提升节奏编辑能力 | BGM/字幕/章节可对齐 |
| P1 | 更多 FFmpeg route | 降低 MoviePy 主路径占比 | fast path rate 提升 |
| P2 | 字幕轨精修 | 专业化体验增强 | 字幕句子可单独编辑和对齐 |
| P2 | Effect stack 轻量版 | 支持更复杂风格 | 每 clip 可挂有限效果 |
| P3 | Keyframe / Nested timeline | 高阶专业功能 | 只有前面稳定后再做 |

---

## 六、阶段执行计划

## Phase 0：现状核对与基线锁定

目标：确认已有 Timeline 能力的真实状态，避免重复建设。

建议周期：0.5 到 1 天。

任务：

1. 盘点前端 Timeline 功能：
   - `TimelineEditor.tsx`
   - `TimelineInspector.tsx`
   - `timelineOps.ts`
   - `timelineInvalidation.ts`
   - `useTimelineHistory.ts`
2. 盘点后端 Timeline 能力：
   - `video_engine/timeline.py`
   - `video_engine/timeline_compile.py`
   - `video_engine_v5.py timeline-generate`
   - `video_engine_v5.py timeline-compile`
3. 记录当前支持的编辑操作。
4. 记录当前无法编译回 render_plan 的字段。
5. 增加或更新一份当前能力 checklist。

验收：

- 能说明“现在已经能编辑什么，不能编辑什么”。
- `python tests\smoke_v5_timeline_generate.py` 通过。
- `python tests\smoke_v5_timeline_compile.py` 通过。
- `npm.cmd run build:web` 通过。

---

## Phase 1：Inspector 驱动的专业化微调 MVP

目标：先不做复杂拖拽，先让用户能在 Inspector 里稳定修改自动生成结果。

建议周期：2 到 4 天。

P0 任务：

| 任务 | 涉及模块 | 说明 |
| --- | --- | --- |
| 编辑 title text/subtitle | `TimelineInspector.tsx`, `timelineOps.ts` | 修改 `content_ref` |
| 编辑 title/card style | `TimelineInspector.tsx`, `timelineOps.ts` | 修改 `presentation` |
| 编辑 clip enabled | `TimelineClip.tsx`, `timelineOps.ts` | 已有能力要补验收 |
| 编辑 duration | `timelineOps.ts`, `timeline_compile.py` | 确认 compile 后生效 |
| 编辑 BGM volume | `TimelineInspector.tsx`, `timelineOps.ts` | 先数值输入 |
| dirty/apply 状态收敛 | `App.tsx`, `TimelineEditor.tsx` | 操作后必须提示可应用 |

验收：

- 用户改标题文字后，`timeline.json` 变化。
- 点击应用后，`render_plan.json` 对应 segment 变化。
- build 不报错。
- timeline dirty 状态在应用成功后清理。
- undo/redo 能撤回 Inspector 修改。

建议新增测试：

- `tests/smoke_v5_timeline_inspector_edits.py`
- 或扩展 `tests/smoke_v5_timeline_compile.py`

---

## Phase 2：基础时间轴编辑操作

目标：让自动生成的初剪可以在时间轴中完成基础整理。

建议周期：3 到 6 天。

P0/P1 任务：

| 任务 | 优先级 | 说明 |
| --- | --- | --- |
| 同轨 clip 排序 | P0 | 当前可先用按钮或简单 drag |
| 修改 clip duration | P0 | 左右 trim 前的保守版本 |
| split clip | P1 | 先支持 video/image/title 的简单分割 |
| ripple delete | P1 | 删除后后续 clip 自动前移 |
| duplicate clip | P1 | 复制标题/卡片/图片片段 |
| snap to edge | P1 | 吸附相邻 clip 边界 |
| timeline zoom | P1 | 解决长视频比例显示 |

执行策略：

- 第一版同轨不允许 overlap。
- 跨轨只允许 title/subtitle/overlay 覆盖 video/audio。
- split 后必须生成新的 stable clip id。
- ripple delete 必须更新 track clip order 和 timeline_start。
- 所有操作写入 metadata last_operation。

验收：

- 排序、删除、split 后 `timeline-compile` 能成功。
- render_plan segment 顺序和时长符合 timeline。
- undo/redo 可以恢复前一版 timeline。
- 不产生负 duration、重复 clip id、断裂 track 引用。

建议新增测试：

- `tests/smoke_v5_timeline_edit_ops.py`
- 覆盖 move、duration、split、ripple delete、compile。

---

## Phase 3：Preview 闭环

目标：用户编辑后能快速看到局部预览，而不是直接等待 final render。

建议周期：4 到 8 天。

任务：

1. 增加 preview render command：
   - 输入 timeline path
   - 输入 time range
   - 输入 preview quality
   - 输出 preview mp4 或 frame thumbnails
2. 增加 preview cache namespace。
3. 前端增加局部预览按钮：
   - 预览选中 clip
   - 预览当前时间范围
   - 预览整个短 timeline
4. build report 增加 preview 摘要。
5. 增加 timeline thumbnail/proxy/waveform manifest：
   - clip 缩略图用于时间轴背景
   - proxy 视频用于编辑预览
   - waveform peak JSON 用于音频轨显示
   - preview segment 用于局部播放
6. 增加 preview/final cache namespace 校验：
   - preview 只能用于编辑和局部预览
   - final render 必须读取原始素材或正式缓存
   - build report 记录本次使用的是 preview cache 还是 final cache
7. 增加时间轴预览质量选择：
   - 自动
   - 性能
   - 平衡
   - 高清
   - 原始
   - 设置写入 timeline performance policy 或项目偏好

执行策略：

- 第一版 preview 可以低分辨率、低 fps。
- 默认 preview 不低于 720p；低配或超长项目可降到 540p，但必须保证字幕、标题和主体可辨认。
- 高性能 PC 可手动选择 1080p 高清 preview 或 original preview。
- 自动模式可以根据卡顿情况建议降档，但用户手动选择优先。
- preview 不影响 final cache。
- preview 失败不阻断 final render。
- 使用 FFmpeg fast path 优先，MoviePy fallback 只兜底。
- 拖动时间轴时不实时生成 preview，用户停顿、选中 clip 或点击预览后再后台生成。
- 后台 preview 任务必须可取消，避免连续编辑导致队列堆积。

验收：

- 修改 title 后可快速生成该 title 周边预览。
- preview cache 命中时日志可见。
- final render 仍使用原始素材和正式参数。
- 时间轴 clip 背景来自缩略图缓存，而不是直接加载原视频。
- 二次打开项目时缩略图和 waveform 可以复用。
- build report 能区分 preview cache 和 final cache。
- 用户可以选择高清或原始时间轴预览。
- 最终导出画质不受时间轴预览档位影响。

---

## Phase 4：音频与字幕专业化

目标：让时间轴真正支持节奏编辑，而不只是视觉段落排列。

建议周期：5 到 10 天。

任务：

| 能力 | 优先级 | 说明 |
| --- | --- | --- |
| 音频波形显示 | P1 | 可用预计算峰值 JSON |
| BGM cue 可视化 | P1 | 显示 section cue / timeline cue |
| 音量包络简化版 | P2 | 先支持 clip volume + fade |
| 字幕句子块 | P2 | 来自 subtitle/caption 数据 |
| 字幕块拖动对齐 | P2 | 先只允许小范围偏移 |
| ducking 可视化 | P2 | 显示 narration/BGM 关系 |

执行策略：

- 不在第一版做 DAW 级音频编辑。
- 波形数据走缓存，不在 React render 中实时解码。
- 字幕轨先做句子级，不做逐字级。
- 音频变更优先走 audio cache。

验收：

- 时间轴能显示至少一条音频轨。
- BGM volume/fade 修改能编译到 render_plan。
- 音频相关修改不会触发不必要的视觉重算。

---

## Phase 5：局部重算与恢复增强

目标：让专业化编辑真正带来效率收益。

建议周期：5 到 10 天。

任务：

1. timeline compile 输出 recompute summary。
2. build report 展示 timeline edit summary。
3. chunk cache key 纳入 timeline clip identity。
4. segment cache key 区分 preview/final。
5. 卡片、标题、overlay 优先独立预渲染。
6. 增加“只渲染受影响范围”的内部接口。
7. 恢复流程保存 dirty timeline。

验收：

- 改标题文字后，报告显示 card/title segment 重算。
- 改 BGM 音量后，报告显示 audio 重算。
- 改导出质量后，不复用错误 preview cache。
- 崩溃恢复后未应用 timeline 编辑不丢。

---

## Phase 6：高级专业能力

目标：在底座稳定后再逐步补高阶能力。

候选能力：

- Keyframe position/scale/opacity。
- 轻量 effect stack。
- Adjustment layer。
- Subtitle style track。
- Compound clip。
- 多版本 timeline。
- A/B cut variants。
- Template-driven timeline rewrite。

进入条件：

- P0/P1 时间轴能力稳定。
- timeline compile smoke 覆盖充分。
- build report 能解释编辑、缓存、回退。
- FFmpeg fast path 覆盖率足够高。

---

## 七、技术策略

### 1. 数据边界

严格保持边界：

| 层 | 职责 | 是否用户直接编辑 |
| --- | --- | --- |
| `media_library.json` | 素材事实 | 否 |
| `story_blueprint.json` | 自动化叙事结构 | 部分 |
| `timeline.json` | 用户编辑意图 | 是 |
| `render_plan.json` | 渲染执行计划 | 否 |
| `build_report.json` | 执行解释 | 否 |

原则：

- UI 编辑写 timeline。
- 编译器把 timeline 转 render_plan。
- 渲染器执行 render_plan。
- build report 解释 render_plan 来源和执行情况。

### 2. 编辑操作设计原则

每个操作必须满足：

- deterministic：同输入同输出。
- undoable：能撤销。
- serializable：能保存到 timeline。
- compilable：能编译回 render_plan。
- explainable：能给出 invalidation scope。
- recoverable：崩溃后能恢复。

### 3. 渲染策略

继续沿用当前更实际的方向：

- FFmpeg 优先。
- 预渲染单元优先。
- MoviePy fallback。
- 新引擎只在现有路径无法继续压缩时再评估。

推荐 fast path 顺序：

1. `ffmpeg_direct_chunk`
2. `ffmpeg_image_chunk`
3. `ffmpeg_card_chunk`
4. `ffmpeg_fitted_video_chunk`
5. audio cache / mix cache
6. MoviePy timeline fallback

### 4. UI 策略

专业化 UI 不等于复杂 UI。

第一阶段 UI 原则：

- 工具少，但每个工具可靠。
- 默认自动化结果可直接导出。
- 时间轴用于微调，不强迫用户手工剪完整片。
- 避免复杂嵌套面板。
- Inspector 放关键参数。
- 高风险操作先用按钮，成熟后再做拖拽。

---

## 八、下一批建议执行任务

按收益和风险排序，建议下一批这样做：

### Task 1：Timeline 当前能力审计

输出：

- 以本文件 [附录 A](#附录-a当前-timeline-能力审计-2026-06-17) 为当前基线。
- 后续每轮 Timeline 大改后更新附录 A 的状态表。

内容：

- 当前已支持操作。
- 当前 UI 有但 compile 未生效的字段。
- 当前 compile 支持但 UI 没暴露的字段。
- 当前 dirty/apply/recovery 缺口。

优先级：P0。

### Task 2：Inspector 编辑标题/卡片核心字段

范围：

- title text
- subtitle text
- preset
- motion
- enabled
- duration

涉及：

- `src/features/timeline/TimelineInspector.tsx`
- `src/features/timeline/timelineOps.ts`
- `video_engine/timeline_compile.py`
- `tests/smoke_v5_timeline_compile.py`

优先级：P0。

### Task 3：Timeline compile 对编辑字段补齐

目标：

- 用户改了 timeline 字段后，render_plan 真的变化。

重点：

- `content_ref.title_text`
- `content_ref.subtitle_text`
- `presentation.title_style`
- `timeline_duration`
- `enabled`

优先级：P0。

### Task 4：增加 timeline edit smoke

覆盖：

- 改 title。
- 改 duration。
- disable clip。
- move clip。
- compile 后 render_plan 变化。

优先级：P0。

### Task 5：时间轴操作按钮化

先不要急着复杂拖拽：

- 上移/下移 clip。
- 删除/禁用 clip。
- duration stepper。
- duplicate title/card。
- undo/redo 按钮。

优先级：P0/P1。

### Task 6：Ripple delete

目标：

- 删除 clip 后后续同轨 clip 自动前移。
- compile 后总时长更新。

优先级：P1。

### Task 7：Preview cache namespace

目标：

- 为后续局部预览打基础。
- 确保编辑预览和最终导出的缓存不会混用。
- 保证“编辑时轻量，最终成片高质量”的链路可验证。

优先级：P1。

### Task 8：Timeline 缩略图、代理视频、波形缓存

目标：

- 时间轴编辑界面不直接解码原视频。
- clip 背景使用缩略图。
- 编辑预览使用 720p proxy 或可辨认的低分辨率代理。
- 音频轨使用 waveform peak JSON。

涉及：

- `src/features/timeline/*`
- `video_engine/render_proxy.py`
- `video_engine/timeline.py`
- `.cache_video_create_v5`
- `.video_create_project/render_cache/preview_segments`

优先级：P1。

### Task 9：音频 cue 可视化

目标：

- 先显示 BGM section cue 和音量，不做完整波形。

优先级：P1。

---

## 九、验收标准

### P0 完成标准

P0 阶段完成时，必须满足：

- 自动生成项目后有可保存的 `timeline.json`。
- 时间轴 UI 使用 `v5Timeline`，不是只读 segments fallback。
- Inspector 能修改至少 title/card 文本、style、duration、enabled。
- 修改后 dirty 状态清晰。
- 点击应用后 `timeline-compile` 成功。
- `render_plan.json` 反映 timeline 编辑。
- undo/redo 可用。
- 崩溃恢复不丢 dirty timeline。
- 时间轴界面不直接批量加载原视频，clip 背景至少使用缩略图缓存。
- 编辑预览和最终导出缓存命名空间分离。
- `build:web` 通过。
- timeline generate/compile smoke 通过。

### P1 完成标准

P1 阶段完成时，必须满足：

- 支持 move、trim、split、ripple delete。
- 支持基础 snap。
- 支持 timeline zoom/scroll。
- 支持 clip 或范围预览的第一版。
- 支持 720p proxy 或可辨认低分辨率 preview，final render 仍使用原始素材。
- 支持 timeline thumbnail/waveform/proxy manifest。
- 支持 BGM cue 可视化和基础音量编辑。
- build report 能解释 timeline edit 导致的重算。

### P2 完成标准

P2 阶段完成时，必须满足：

- 字幕轨可编辑。
- overlay/title/card 多轨关系更清晰。
- 局部重渲染范围可控。
- 大多数常见图片、标题、卡片、轻量视频场景不走整段 MoviePy。

---

## 十、验证策略

每个阶段至少跑：

```powershell
npm.cmd run build:web
python -m py_compile video_engine\timeline.py video_engine\timeline_compile.py video_engine_v5.py
python tests\smoke_v5_timeline_generate.py
python tests\smoke_v5_timeline_compile.py
node .\scripts\clean-test-artifacts.mjs
```

涉及渲染路径时再跑：

```powershell
python tests\smoke_v5_render_scheduler.py
python tests\smoke_v5_ffmpeg_priority.py
python tests\smoke_v5_card_segment_cache.py
```

涉及桌面命令时再跑：

```powershell
npm.cmd run check
```

当前已有/建议补齐测试：

- 已有：`tests/smoke_v5_timeline_schema.py`
- 已有：`tests/smoke_v5_timeline_invalidation.py`
- 已有：`tests/smoke_v5_timeline_edit_ops.py`
- 已有：`tests/smoke_v5_timeline_generate.py`
- 已有：`tests/smoke_v5_timeline_compile.py`
- 待补：`tests/smoke_v5_timeline_inspector_edits.py`
- 待补：`tests/smoke_v5_timeline_recompute_summary.py`
- 待补：`tests/smoke_v5_preview_cache_namespace.py`
- 待补：`tests/smoke_v5_timeline_preview_quality_guard.py`
- 已补：`tests/smoke_v5_timeline_preview_manifest.py`

---

## 十一、风险与控制

### 风险 1：时间轴 UI 先行，数据层跟不上

表现：

- UI 能拖，但保存/恢复/编译不稳定。

控制：

- 每个 UI 操作必须先有 timelineOps 和 compile 测试。
- 不直接改 render_plan。

### 风险 2：过早做复杂拖拽

表现：

- 边界条件爆炸，undo/redo、snap、overlap 都不稳。

控制：

- 第一阶段优先 Inspector 和按钮操作。
- 拖拽只做排序，不做自由多轨摆放。

### 风险 3：Preview 和 Final cache 混用

表现：

- 正式导出复用了低质量 preview。

控制：

- cache namespace 强制区分。
- build report 输出 cache namespace。

### 风险 4：MoviePy fallback 继续吞掉主路径

表现：

- 时间轴功能增加后导出更慢。

控制：

- 每新增一种 clip/presentation，都评估能否独立预渲染。
- route diagnostic 统计 fast path rate。

### 风险 5：时间轴编辑卡顿

表现：

- 长项目滚动卡顿。
- 拖动 clip 时掉帧明显。
- 选中片段时触发大范围重渲染。
- 播放头移动导致 UI 阻塞。

控制：

- 时间轴 viewport 虚拟化。
- clip 背景只用缩略图，不直接加载原视频。
- 波形和字幕块走预计算数据。
- 拖动中使用轻量 draft 状态，松手后再提交 timeline edit。
- 大项目默认使用 proxy preview，不用 original preview。

### 风险 6：预览质量过低导致误判

表现：

- 编辑时看不清主体构图。
- 看不清字幕和标题。
- 用户以为最终画质也很差。

控制：

- 默认 preview 使用 720p proxy。
- 540p 只用于低配或超长项目。
- 字幕/标题密集项目 preview 不低于 720p 或保留文字层高清。
- UI 和 build report 明确区分 preview quality 与 final quality。

### 风险 7：产品方向膨胀

表现：

- 做着做着变成通用 NLE，主线变慢。

控制：

- 坚持“自动生成结果的专业化微调”定位。
- P2 之前不做大型调色、复杂合成、插件系统。

### 风险 8：高清时间轴预览拖垮性能

表现：

- 用户选择高清或原始预览后，4K/高码率项目播放卡顿。
- 后台 preview 任务占用过高，影响正常编辑。
- 用户误以为时间轴卡顿代表最终导出也有问题。

控制：

- 默认仍使用平衡档 720p proxy。
- 高清和原始预览作为用户主动选择项。
- UI 显示当前预览档位和资源提示。
- 自动模式检测持续卡顿后建议降档。
- 原始预览优先用于短范围质量检查，不作为长项目默认播放模式。
- build report 和 preview manifest 记录本次预览质量档位，方便诊断。

---

## 十二、决策原则

后续遇到分歧时按这个顺序决策：

1. 是否提升自动化出片后的可控性？
2. 是否减少用户外部二次编辑需求？
3. 是否能保存到 timeline 并编译回 render_plan？
4. 是否能局部重算或解释为什么不能？
5. 是否不破坏 final render 质量？
6. 是否能让编辑阶段更流畅，而不是增加卡顿？
7. 是否不显著增加 MoviePy 主路径占比？
8. 是否能被 smoke test 覆盖？

如果一个功能只是“看起来像专业剪辑软件”，但不能满足以上大部分条件，应推迟。

---

## 十三、推荐近期路线

最推荐的近期路线是：

```text
1. 审计当前 timeline 能力
2. 补 Inspector 编辑字段
3. 补 timeline_compile 字段映射
4. 补 timeline edit smoke
5. 做按钮化 move/delete/duration/duplicate
6. 做 ripple delete
7. 做 preview cache namespace
8. 做 timeline thumbnail/proxy/waveform manifest
9. 做音频 cue 可视化
10. 做局部 preview
11. 再考虑字幕轨和 keyframe
```

这条路线的好处是：

- 不推翻现有自动化主链。
- 不急着换渲染引擎。
- 不把 UI 做成空壳。
- 每一步都能通过测试验证。
- 和当前 FFmpeg route / segment cache / recovery 优化方向一致。

---

## 十四、最终判断

本项目确实应该向专业剪辑软件靠拢，但靠拢的不是“完整复制界面”，而是靠拢这些核心能力：

- 时间轴是真实数据层。
- 编辑操作可保存、可撤销、可恢复。
- 修改后能局部应用。
- 渲染行为可解释。
- 快路径覆盖常见场景。
- preview 和 final 各走自己的质量路径。

如果这条路线做成，项目会从：

> 自动化视频生成器

升级为：

> 自动化剪辑工作台

再往后才有资格讨论更完整的专业剪辑器形态。

---

## 附录 A：当前 Timeline 能力审计, 2026-06-17

### A.1 审计结论

当前 Timeline 已经不是空设计，已经具备可继续推进的基础闭环：

```text
timeline schema
  -> timeline-generate
  -> TimelineEditor / TimelineInspector
  -> timelineOps / invalidation
  -> autosave dirty timeline
  -> timeline-compile
  -> render_plan
  -> build_report recompute summary
```

但它还处在“基础编辑闭环已成形，专业时间轴体验未完成”的阶段。

一句话判断：

> 已具备 P0 数据内核和基础 Inspector 编辑能力，但还缺专业时间轴的高性能预览、trim/split/ripple、缩略图/波形/代理 manifest、局部预览和完整测试矩阵。

### A.2 已有能力总表

| 模块 | 当前能力 | 状态 | 证据/位置 | 备注 |
| --- | --- | --- | --- | --- |
| Timeline 类型 | `V5Timeline / Track / Clip / Dependency / Invalidation / PerformancePolicy` | 已有 | `src/lib/v5Types.ts` | 支持 video/audio/title/subtitle/overlay schema |
| Timeline 生成 | 从 blueprint/render_plan 生成 timeline | 已有 | `video_engine/timeline.py`, `timeline-generate` | smoke 已覆盖 module/CLI/worker |
| Timeline 编译 | 从 timeline 编译回 render_plan | 已有 | `video_engine/timeline_compile.py`, `timeline-compile` | 支持顺序、时长、禁用、标题、音频音量 |
| 前端 Timeline UI | TimelineEditor、Track、Clip、Ruler、Inspector | 已有 | `src/features/timeline/*` | 有 fallback render_plan read-only 模式 |
| Inspector 编辑 | enabled、标题、副标题、style preset、duration、BGM volume、move up/down | 已有 | `TimelineInspector.tsx`, `timelineOps.ts` | motion 还未完整暴露 |
| 拖拽排序 | 同轨 clip 拖拽排序 | 部分已有 | `TimelineEditor.tsx` | 目前主要是 reorder，不是自由时间定位 |
| Undo/Redo | 40 步 timeline history | 已有 | `useTimelineHistory.ts` | 基于 timeline snapshot |
| Dirty/Apply | dirty 状态、autosave、应用 timeline 到 render_plan | 已有 | `App.tsx` | preview/final 前会 ensure apply |
| Invalidation | 编辑操作映射 recompute scope | 已有 | `timelineInvalidation.ts`, `video_engine/timeline.py` | preview/final quality scope 已有规则 |
| Build Report | timeline compile recompute summary | 部分已有 | `timeline_compile.py` | 需要继续扩展 preview/final cache 摘要 |
| Preview Render | 低清小样生成 | 已有但非 timeline 专用 | `previewRenderV5`, worker preview-render | 还不是 clip/range 局部 preview 工作流 |
| Proxy Media | proxy manifest 用于 preview 源选择 | 部分已有 | `render_proxy.py`, render scheduler smoke, `smoke_v5_timeline_preview_manifest.py` | timeline preview manifest V1 已形成，实际 proxy 生成/命中接入待补 |
| Final Render 保护 | final policy 不允许 proxy | schema 已有 | `performance_policy.final.allow_proxy = false` | 还需要 preview/final cache namespace smoke |

### A.3 当前前端编辑能力细分

| 操作 | UI 是否有 | timelineOps 是否有 | compile 是否落地 | 当前状态 |
| --- | --- | --- | --- | --- |
| 选择 clip | 有 | 不需要 | 不需要 | 已有 |
| 左右键切换 clip | 有 | 不需要 | 不需要 | 已有 |
| 启用/禁用 clip | 有 | `updateClipEnabled` | 禁用 clip 会被跳过 | 已有 |
| 修改 title text | 有 | `updateClipContent` | title/chapter/end -> `text` | 已有 |
| 修改 subtitle text | 有 | `updateClipContent` | title/chapter/end -> `subtitle` | 已有 |
| 修改 title preset | 有 | `updateClipPresentation` | `title_style` / `overlay_title_style` | 已有 |
| 修改 title motion | 有 | `updateClipPresentation` 可写 `title_style.motion` | compile 可透传 `title_style` | 已有 |
| 修改 title position | 有 | `updateClipPresentation` 可写 `title_style.position` | compile 可透传 `title_style` | 已有 |
| 修改 transition | 有 | `updateClipPresentation` 可写 `transition_type/duration` | compile 可生成 `transition_config` | 已有 |
| 修改 duration | 有 | `updateClipDuration` | segment duration/start/end 更新 | 已有 |
| move up/down | 有 | `moveClip` | 编译顺序变化 | 已有 |
| 同轨拖拽 reorder | 有 | `moveClip` | 编译顺序变化 | 部分已有 |
| BGM volume | 有 | `updateBgmCueVolume` | `render_settings.audio.bgm_volume` | 已有 |
| undo/redo | 有 | `useTimelineHistory` | 应用后生效 | 已有 |
| trim left/right | 无 | 无 | 无 | 待补 |
| split clip | 无 | 无 | 无 | 待补 |
| ripple delete | 无 | 无 | 无 | 待补 |
| duplicate clip | 无 | 无 | 无 | 待补 |
| subtitle track 编辑 | schema 有 | UI 无 | compile 不完整 | 待补 |
| preview quality 选择 | 有 | `updatePreviewQualityProfile` 写入 `performance_policy.preview` | 不需要 compile，preview-only scope 已有 | 基础 UI、manifest V1、增量资产生成与 UI 消费已补 |
| clip/range preview | UI 无专用入口 | 无 | worker 可预览整小样 | 待补 |

### A.4 当前后端 compile 能力细分

`video_engine/timeline_compile.py` 当前已经支持：

- 过滤 disabled visual clip。
- 按 timeline visual clips 重新生成 `segments`。
- 按 cursor 重新计算 `start_time / end_time / duration`。
- title/chapter/end clip:
  - `content_ref.title_text` -> `segment.text`
  - `content_ref.subtitle_text` -> `segment.subtitle`
  - `presentation.title_style` -> `segment.title_style`
- image/video clip overlay:
  - `content_ref.title_text` -> `overlay_text`
  - `content_ref.subtitle_text` -> `overlay_subtitle`
  - `presentation.title_style` -> `overlay_title_style`
- transition:
  - `presentation.transition_type`
  - `presentation.transition_duration`
- motion/background:
  - `presentation.motion_config`
  - `presentation.background_mode`
  - `presentation.background_source_path`
- audio:
  - audio clip source path -> manual music path
  - `metadata.bgm_volume` -> `render_settings.audio.bgm_volume`
  - audio clips -> `audio_blueprint.timeline_cues`
- metadata:
  - `generated_from = timeline`
  - `timeline_compile_elapsed_ms`
  - `recompute_summary`
  - changed clip ids
  - skipped disabled clip count
  - recompute scope counts

当前 compile 还缺：

- split clip 的稳定 segment id 策略。
- ripple delete 专用操作语义。
- source in/out 的完整 trim 映射。
- preview quality policy 写入和 cache invalidation 输出。
- preview/final cache namespace 的执行报告。
- subtitle track 到字幕渲染链的完整映射。
- overlay track 的跨轨 compositing 规则。

### A.5 当前测试覆盖

已有相关测试：

| 测试 | 覆盖内容 | 状态 |
| --- | --- | --- |
| `tests/smoke_v5_timeline_schema.py` | timeline schema、performance policy、cache namespace | 已有 |
| `tests/smoke_v5_timeline_generate.py` | module/CLI/worker 生成 timeline | 已有 |
| `tests/smoke_v5_timeline_compile.py` | 编辑后 compile 到 render_plan | 已有 |
| `tests/smoke_v5_timeline_edit_ops.py` | Python timeline edit ops | 已有 |
| `tests/smoke_v5_timeline_invalidation.py` | recompute scope 规则 | 已有 |
| `tests/smoke_v5_project_recovery.py` | timeline recovery/migration | 已有 |
| `tests/smoke_v5_render_scheduler.py` | proxy preview、chunk route | 已有 |
| `tests/smoke_v5_ffmpeg_priority.py` | FFmpeg fast path 和 card/image/video chunk | 已有 |

待补测试：

- `tests/smoke_v5_timeline_preview_quality_guard.py`
- `tests/smoke_v5_timeline_preview_manifest.py`
- `tests/smoke_v5_timeline_preview_cache_namespace.py`
- `tests/smoke_v5_timeline_split_ripple.py`
- `tests/smoke_v5_timeline_source_in_out.py`
- `tests/smoke_v5_timeline_subtitle_track.py`

### A.6 当前最应该先补的缺口

按优先级排序：

1. timeline thumbnail/proxy/waveform manifest。
2. preview/final cache namespace smoke。
3. preview quality 档位接入真实局部 preview 任务。
4. title/card background 字段在 Inspector 中暴露。
5. source in/out trim 的数据和 compile 映射。
6. split clip 与 ripple delete。
7. clip/range preview command。
8. 虚拟化和缩略图渲染，避免大时间轴卡顿。

---

## 附录 B：Preview 性能规格

### B.1 设计目标

Preview 性能系统要同时满足三个条件：

1. 时间轴编辑不卡。
2. 预览足够清楚，可以判断主体、字幕、标题、构图和节奏。
3. 最终导出不受预览质量影响，永远回到 original/final 路径。

核心原则：

```text
Timeline Editing / Preview
  -> thumbnail / waveform / proxy / preview segment

Final Render
  -> original source / final cache / stable backend / high-quality encode
```

### B.2 UI 预览质量档位

| UI 档位 | preview.mode | height | fps | 用途 | 默认触发条件 |
| --- | --- | ---: | ---: | --- | --- |
| 自动 | `proxy`/`low_res`/`original` 动态选择 | 动态 | 动态 | 默认推荐 | 根据硬件、素材、项目长度、卡顿历史选择 |
| 性能 | `low_res` | 540-720 | 12-18 | 低配、长项目、省电 | clip 多、4K 多、卡顿明显 |
| 平衡 | `proxy` | 720 | 15-24 | 默认编辑 | 大多数项目 |
| 高清 | `proxy` 或 `original` | 1080 | 24-30 | 高性能 PC 清晰编辑 | 用户主动选择 |
| 原始 | `original` | source | source 或 30 | 短范围质量检查 | 用户主动选择，建议短片段 |

最低质量约束：

- 低于 540p 不作为常规档位。
- 字幕/标题密集项目默认不低于 720p。
- 如果视频源本身低于目标高度，保留源尺寸，不做无意义放大。
- UI 必须显示当前预览档位，避免用户误以为最终画质降低。

### B.3 自动档策略

自动档建议输入：

- `source_max_height`
- `source_avg_bitrate`
- `timeline_duration`
- `clip_count`
- `video_clip_count`
- `subtitle_or_title_density`
- `available_memory`
- `hardware_decode_available`
- `recent_timeline_jank_score`
- `preview_cache_hit_rate`

自动档建议规则：

| 条件 | 推荐档位 |
| --- | --- |
| 项目 <= 3 分钟，clip <= 30，高性能机器 | 高清 |
| 1080p 常规项目，clip <= 120 | 平衡 |
| 4K/高码率项目，clip <= 120 | 平衡，必要时保持文字层高清 |
| clip > 200 或 duration > 30 分钟 | 性能或平衡 |
| 最近 10 秒持续卡顿 | 建议降一档 |
| 用户手动选择高清/原始 | 保持用户选择，只提示资源成本 |

自动降档不应静默改变用户手动选择。推荐 UI 行为：

- 自动模式：可以自动调整。
- 手动模式：只提示“当前预览档位可能导致卡顿”，不强制降档。

### B.4 Cache Namespace

必须分离：

| namespace | 用途 | 可以用于 final render |
| --- | --- | --- |
| `thumbnail` | 时间轴 clip 背景、快速定位 | 否 |
| `proxy` | 编辑预览源素材 | 否 |
| `preview` | 局部预览片段、低/中/高清 preview | 否 |
| `final` | 最终渲染缓存 | 是 |

目录建议：

```text
.cache_video_create_v5/
  timeline_thumbnails/
  timeline_waveforms/
  proxy_media/

.video_create_project/
  render_cache/
    preview_segments/
    final_segments/
    photo_segments/
    video_segments/
    card_segments/
```

注意：

- 现有 `photo_segments / video_segments / card_segments` 可以继续服务 final fast path。
- preview 专用缓存必须在 key 和 manifest 中标记 `cache_namespace = preview`。
- final render 禁止读取 `preview_segments` 作为最终画面源。

### B.5 Preview Cache Key

preview cache key 至少包含：

```text
timeline_version
clip_id
track_id
source_path
source_fingerprint
source_in
source_out
timeline_duration
preview_mode
preview_height
preview_fps
preview_codec
presentation_hash
content_hash
engine_version
cache_fingerprint_version
```

final cache key 至少包含：

```text
clip_id
source_fingerprint
source_in
source_out
timeline_duration
final_quality
final_codec
presentation_hash
content_hash
engine_version
cache_fingerprint_version
```

preview key 和 final key 不能只差一个目录名，必须显式包含 namespace/quality。

### B.6 Timeline Preview Manifest

建议新增：

```json
{
  "document_type": "timeline_preview_manifest",
  "version": 1,
  "timeline_path": "timeline.json",
  "generated_at": "2026-06-17T00:00:00",
  "preview_policy": {
    "ui_profile": "balanced",
    "mode": "proxy",
    "height": 720,
    "fps": 24,
    "cache_namespace": "preview"
  },
  "clips": {
    "clip_001": {
      "thumbnail_path": ".cache_video_create_v5/timeline_thumbnails/clip_001.jpg",
      "proxy_path": ".cache_video_create_v5/proxy_media/clip_001_720p.mp4",
      "waveform_path": null,
      "preview_segment_path": ".video_create_project/render_cache/preview_segments/clip_001.mp4",
      "source_fingerprint": "...",
      "cache_key": "...",
      "status": "ready"
    }
  }
}
```

Manifest 职责：

- 前端不扫描缓存目录猜测文件。
- build report 可以解释 preview 命中。
- recovery 可以恢复未完成 preview 状态。
- final render 可以明确排除 preview namespace。

### B.7 前端交互性能要求

时间轴 UI 需要遵守：

- clip 背景用 thumbnail，不用 `<video>`。
- 只有选中 clip 或当前播放窗口加载 preview video。
- 波形用 peak JSON，不在 React 中解码音频。
- 拖动中使用 draft 状态，松手才 commit timeline。
- 大项目启用 viewport virtualization。
- Inspector 修改使用局部 state，避免每次输入深拷贝全 timeline。

建议性能阈值：

| 指标 | 目标 |
| --- | --- |
| 100 clip 首屏可操作 | <= 1 秒 |
| 选择 clip 反馈 | <= 100 ms |
| Inspector 输入反馈 | <= 100 ms |
| 拖动排序 | >= 30 fps 体感 |
| 横向滚动 | 不因视频解码阻塞 |
| 二次打开缩略图 | 命中缓存 |

### B.8 Preview/Final 质量保护验收

必须可以验证：

- 选择性能预览后，final render 仍读取 original/final cache。
- preview manifest 中 `cache_namespace = preview`。
- build report 中 final summary 不出现 `preview_segments` 作为 final source。
- `final.allow_proxy = false`。
- 更改 preview quality 只触发 `preview_only` invalidation。
- 更改 final quality 触发 `final_render_only`，不要求 timeline compile。

---

## 附录 C：Timeline Edit 操作规格

### C.1 通用操作约束

每个 Timeline 编辑操作必须满足：

- 输入 deterministic。
- 输出完整 `V5Timeline`。
- 修改对应 `clip_index` 或 `tracks`。
- 更新 `edit_state`。
- 更新 `invalidation_hint`。
- 设置 `metadata.dirty = true`。
- 设置 `metadata.last_edit_operation`。
- 可被 undo/redo 保存。
- 可被 `timeline-compile` 编译。
- 不直接修改 `render_plan.json`。

### C.2 操作状态定义

| 状态 | 含义 |
| --- | --- |
| `Implemented` | UI、operation、compile、smoke 基本都有 |
| `Partial` | 有部分链路，但缺 UI/compile/test 中的一部分 |
| `Planned` | schema 或规则有预留，但还未实现 |

### C.3 已实现/部分实现操作规格

#### 1. Enable / Disable Clip

状态：Implemented。

输入：

```ts
{ clip_id: string; enabled: boolean }
```

更新：

- `clip.enabled`
- `clip.edit_state.override_fields += ["enabled"]`
- `invalidation_hint.primary_scope = "timeline_compile"`
- `timeline.metadata.dirty = true`

compile：

- disabled visual clip 不进入 `render_plan.segments`。

测试：

- `tests/smoke_v5_timeline_edit_ops.py`
- `tests/smoke_v5_timeline_compile.py`

#### 2. Update Title / Subtitle Content

状态：Implemented。

输入：

```ts
{ clip_id: string; title_text?: string | null; subtitle_text?: string | null }
```

更新：

- `clip.content_ref.title_text`
- `clip.content_ref.subtitle_text`
- `override_fields += ["content_ref.title_text", "content_ref.subtitle_text"]`
- title/subtitle 修改通常为 `clip_only`

compile：

- title/chapter/end -> `segment.text / segment.subtitle`
- image/video overlay -> `overlay_text / overlay_subtitle`

约束：

- title 当前 UI 上限 80 字符。
- subtitle 当前 UI 上限 160 字符。
- title clip 不允许空 title。

#### 3. Update Title/Card Presentation

状态：Partial。

输入：

```ts
{
  clip_id: string;
  title_style?: V5TitleStyle | null;
  transition_type?: string | null;
  transition_duration?: number | null;
  motion_config?: Record<string, unknown> | null;
  background_mode?: string | null;
  background_source_path?: string | null;
}
```

当前已实现：

- UI 可改 title preset。
- UI 可改 title motion。
- UI 可改 title position。
- UI 可改 transition type。
- UI 可改 transition duration。
- operation 可写 `presentation.title_style`。
- operation 可写 `presentation.transition_type / transition_duration`。
- compile 可透传 `title_style / overlay_title_style`。
- compile 可生成 `transition / transition_config`。
- smoke 已覆盖 preset、motion、position、transition compile。

待补：

- UI 暴露 background mode/source。
- smoke 覆盖 background compile。

#### 4. Update Duration

状态：Implemented for image/title/chapter duration，Partial for video trim。

输入：

```ts
{ clip_id: string; duration: number }
```

更新：

- 当前 clip:
  - `timeline_duration`
  - `timeline_end`
  - 若有 `source_in`，同步更新 `source_out`
- 同轨后续 clip:
  - `timeline_start += delta`
  - `timeline_end += delta`

compile：

- 重新生成 segment duration/start/end。

约束：

- 当前 UI 限制 `0.1s - 300s`。
- 当前更接近右侧 trim，不是完整 left/right trim。

待补：

- video source in/out 边界检查。
- source duration clamp。
- left trim。
- ripple/overwrite 模式选择。

#### 5. Move / Reorder Clip

状态：Implemented for same-track reorder。

输入：

```ts
{ clip_id: string; target_index: number }
```

更新：

- `track.clip_ids` 重新排序。
- 同轨 clip 重新 relayout。
- 被移动 clip 标记 `override_fields += ["track_order", "timeline_start", "timeline_end"]`。
- `invalidation_hint.primary_scope = "timeline_compile"`。

compile：

- 根据 timeline clip order/time 生成新的 segment 顺序。

约束：

- 当前仅同轨。
- 当前不支持自由放置到任意时间点。
- 当前不支持跨轨拖动。

#### 6. BGM Volume

状态：Implemented。

输入：

```ts
{ clip_id: string; volume: number }
```

更新：

- `clip.metadata.bgm_volume`
- clamp 到 `0-1`
- `invalidation_hint.primary_scope = "track_only"`

compile：

- 写入 `render_settings.audio.bgm_volume`。
- audio clips 生成 `audio_blueprint.timeline_cues`。

待补：

- fade in/out。
- ducking 参数。
- cue range 修改。
- 音量包络。

### C.4 待实现操作规格

#### 1. Trim Left / Trim Right

状态：Planned。

输入：

```ts
{
  clip_id: string;
  side: "left" | "right";
  delta_seconds: number;
  mode: "ripple" | "roll" | "overwrite";
}
```

规则：

- right trim:
  - 修改 `timeline_duration / timeline_end / source_out`
  - ripple 模式移动后续 clip
- left trim:
  - 修改 `timeline_start / timeline_duration / source_in`
  - ripple 模式移动当前及后续 clip
- 不允许 duration < 0.1。
- 不允许 source_in/source_out 超出源素材时长。

invalidation：

- visual clip: `timeline_compile`
- audio cue: `track_only` 或 `timeline_compile`，视绑定关系而定。

#### 2. Split Clip

状态：Planned。

输入：

```ts
{
  clip_id: string;
  split_time: number;
}
```

输出：

- 原 clip 变成 left clip。
- 新增 right clip。
- right clip id 使用稳定生成：

```text
{old_clip_id}_split_{safe_ms(split_time)}
```

规则：

- split_time 必须在 clip 内部，不能等于起点或终点。
- left/right 继承 source_ref/content_ref/presentation/execution/cache_policy。
- left/right source range 分开。
- track.clip_ids 在原 clip 后插入 right clip。

invalidation：

- `timeline_compile`
- cache reuse 通常 false，除非未来支持 source range cache slicing。

#### 3. Ripple Delete

状态：Planned。

输入：

```ts
{
  clip_id: string;
  mode: "disable" | "delete";
}
```

规则：

- `disable`：保留 clip，`enabled = false`。
- `delete`：从 `track.clip_ids` 移除，clip_index 可移入 tombstone 或删除。
- 后续同轨 clip 前移。
- 删除 title/overlay 时不一定影响主视频轨；删除主视频轨 clip 会影响 timeline total duration。

建议第一版：

- UI 使用“Disable”作为安全删除。
- 真删除保留 undo/redo 后再开放。

#### 4. Duplicate Clip

状态：Planned。

输入：

```ts
{
  clip_id: string;
  insert_after_clip_id?: string;
}
```

规则：

- 新 clip id:

```text
{old_clip_id}_copy_{counter}
```

- 复制 content/presentation/source/execution。
- edit_state 标记 `origin = "timeline_edit"`。
- 插入后 relayout。

#### 5. Preview Quality Change

状态：Planned in UI，Invalidation 已有。

输入：

```ts
{
  profile: "auto" | "performance" | "balanced" | "high" | "original";
  mode: "low_res" | "proxy" | "original";
  height?: number;
  fps?: number;
}
```

更新：

- `timeline.performance_policy.preview`
- 项目偏好中的 preview profile
- `metadata.last_edit_operation = "preview_quality_change"`

invalidation：

- `preview_only`
- 不需要 render_plan recompile。
- 不影响 final cache。

#### 6. Final Quality Change

状态：已有全局质量 UI，Timeline scope 待接入。

输入：

```ts
{
  quality: "draft" | "standard" | "high" | "ultra";
}
```

invalidation：

- `final_render_only`
- 不应触发 timeline compile。
- 不应清空 preview cache，除非尺寸/比例相关。

### C.5 Source In/Out 规则

未来 trim/split 必须遵守：

```text
0 <= source_in < source_out <= source_duration
timeline_duration = (source_out - source_in) / playback_rate
timeline_end = timeline_start + timeline_duration
```

图片 clip：

- source_in 通常为 0。
- source_out 可以等于 duration。
- 调整 duration 不受源素材时长限制。

视频 clip：

- source_in/source_out 必须受源视频时长约束。
- playback_rate 变化会影响 timeline_duration。

标题/卡片 clip：

- source_in/source_out 可为空。
- duration 直接控制卡片停留时间。

### C.6 Clip ID 与 Tombstone 策略

建议：

- 自动生成 clip id 不随排序变化。
- split/duplicate 生成新 id。
- 删除第一版优先 disable。
- 真删除时可在 `metadata.deleted_clip_ids` 或 tombstone 中记录，便于恢复和诊断。

建议 tombstone：

```json
{
  "clip_id": "clip_001",
  "deleted_at": "2026-06-17T00:00:00",
  "operation": "ripple_delete",
  "previous_track_id": "track_video_main",
  "previous_index": 3
}
```

---

## 附录 D：测试矩阵

### D.1 测试分层

| 层级 | 目标 | 示例 |
| --- | --- | --- |
| Schema | 数据结构稳定 | `smoke_v5_timeline_schema.py` |
| Operation | 单个 edit op 行为 | `smoke_v5_timeline_edit_ops.py` |
| Compile | timeline -> render_plan | `smoke_v5_timeline_compile.py` |
| Worker/CLI | 桌面调用链 | `smoke_v5_timeline_generate.py`, `smoke_v5_timeline_compile.py` |
| Invalidation | 重算范围 | `smoke_v5_timeline_invalidation.py` |
| Preview | 预览质量、manifest、cache namespace | preview quality policy、manifest V1、增量资产生成器与 UI 消费已补 |
| Render Route | FFmpeg/MoviePy 路由 | `smoke_v5_render_scheduler.py`, `smoke_v5_ffmpeg_priority.py` |
| Recovery | 保存、恢复、迁移 | `smoke_v5_project_recovery.py` |

### D.2 P0 测试矩阵

| 功能 | 必测断言 | 现有测试 | 待补 |
| --- | --- | --- | --- |
| timeline schema | `document_type=timeline`, tracks/clip_index/performance_policy 存在 | `smoke_v5_timeline_schema.py` | 无 |
| timeline generate | 生成 video/audio/title tracks，clip id 稳定 | `smoke_v5_timeline_generate.py` | 无 |
| timeline compile | disabled clip 跳过，顺序/时长/标题/BGM 生效 | `smoke_v5_timeline_compile.py` | 补更多 presentation 字段 |
| enable/disable | dirty=true，scope=timeline_compile | `smoke_v5_timeline_edit_ops.py` | 无 |
| title/subtitle edit | scope=clip_only，compile 到 segment | `smoke_v5_timeline_edit_ops.py`, `smoke_v5_timeline_compile.py` | subtitle compile 断言可增强 |
| duration edit | 后续 clip relayout，compile duration | `smoke_v5_timeline_edit_ops.py`, `smoke_v5_timeline_compile.py` | source_in/out clamp 待补 |
| move/reorder | track order 改变，compile 顺序改变 | `smoke_v5_timeline_edit_ops.py`, `smoke_v5_timeline_compile.py` | drag UI 端暂缺自动化 |
| BGM volume | scope=track_only，compile 到 audio settings | `smoke_v5_timeline_edit_ops.py`, `smoke_v5_timeline_compile.py` | audio cue range 待补 |
| preview quality policy | profile 写入 `performance_policy.preview`，final 仍禁用 proxy | `smoke_v5_timeline_edit_ops.py`, `smoke_v5_timeline_invalidation.py` | preview cache namespace 待补 |
| dirty/apply | dirty timeline autosave，apply 后 render_plan 更新 | 部分在前端逻辑中 | 需要前端/worker smoke |

### D.3 Preview/Final 测试矩阵

| 功能 | 必测断言 | 建议测试 |
| --- | --- | --- |
| preview quality change | invalidation=`preview_only`，不触发 render_plan recompile | 已有 `smoke_v5_timeline_edit_ops.py` 基础覆盖；后续补 `smoke_v5_timeline_preview_quality_guard.py` |
| final quality change | invalidation=`final_render_only`，不清 preview manifest | `smoke_v5_timeline_preview_quality_guard.py` |
| preview manifest | 每个 clip 有 thumbnail/proxy/waveform/preview status 字段 | `smoke_v5_timeline_preview_manifest.py` |
| cache namespace | preview cache key 含 preview namespace/height/fps | `smoke_v5_preview_cache_namespace.py` |
| final protection | final report 不使用 `preview_segments` 作为 final source | `smoke_v5_preview_cache_namespace.py` |
| high preview | `profile=high` 写入 1080p 或原尺寸策略 | 已有 `smoke_v5_timeline_edit_ops.py` 基础覆盖；后续补 UI/manifest 覆盖 |
| original preview | `mode=original` 仅影响 preview policy | 已有 `smoke_v5_timeline_edit_ops.py` 基础覆盖；后续补 UI/manifest 覆盖 |
| auto downgrade suggestion | jank input 只产生 suggestion，不覆盖手动选择 | 后续 UI/unit 测试 |

### D.4 Edit 操作扩展测试矩阵

| 操作 | 断言 | 建议测试 |
| --- | --- | --- |
| trim right | duration/source_out 更新，后续 clip relayout | `smoke_v5_timeline_source_in_out.py` |
| trim left | source_in/start/duration 更新 | `smoke_v5_timeline_source_in_out.py` |
| split clip | 新 id 稳定，left/right source range 正确 | `smoke_v5_timeline_split_ripple.py` |
| ripple delete | clip 移除或 disable，后续 clip 前移 | `smoke_v5_timeline_split_ripple.py` |
| duplicate | 新 clip id，插入后 relayout | `smoke_v5_timeline_split_ripple.py` |
| subtitle track edit | subtitle clip compile 到字幕/overlay 渲染链 | `smoke_v5_timeline_subtitle_track.py` |
| overlay track edit | overlay 与主视频依赖关系不丢 | `smoke_v5_timeline_overlay_track.py` |

### D.5 Render Route 回归矩阵

| 场景 | 期望 route/cache | 现有/建议测试 |
| --- | --- | --- |
| 静态/安全动画 card | `ffmpeg_card_chunk`, `card_segments` | `smoke_v5_ffmpeg_priority.py` |
| 图片段 | `ffmpeg_image_chunk`, image/photo segment cache | `smoke_v5_render_scheduler.py`, `smoke_v5_ffmpeg_priority.py` |
| 轻量视频 fit | `ffmpeg_fitted_video_chunk` | `smoke_v5_ffmpeg_priority.py` |
| video motion | video motion cache | `smoke_v5_ffmpeg_priority.py` |
| audio-only edit | audio cache/mix，不重算视觉 | 待补 |
| preview quality change | preview cache only | policy 写入已测，cache namespace 待补 |

### D.6 推荐验证命令

每次改 Timeline 数据/compile：

```powershell
python -m py_compile video_engine\timeline.py video_engine\timeline_compile.py video_engine_v5.py
python tests\smoke_v5_timeline_schema.py
python tests\smoke_v5_timeline_invalidation.py
python tests\smoke_v5_timeline_edit_ops.py
python tests\smoke_v5_timeline_generate.py
python tests\smoke_v5_timeline_compile.py
```

每次改 Timeline UI：

```powershell
npm.cmd run build:web
```

每次改 preview/proxy/cache：

```powershell
python tests\smoke_v5_render_scheduler.py
python tests\smoke_v5_worker_protocol.py
python tests\smoke_v5_timeline_preview_quality_guard.py
python tests\smoke_v5_timeline_preview_manifest.py
```

每次改 FFmpeg route：

```powershell
python tests\smoke_v5_ffmpeg_priority.py
python tests\smoke_v5_card_segment_cache.py
```

清理测试产物：

```powershell
node .\scripts\clean-test-artifacts.mjs
```

### D.7 进入开发前的 Definition of Ready

一个 Timeline 任务进入开发前，应满足：

- 有明确 edit operation 或 preview operation。
- 有输入输出字段。
- 有 recompute scope。
- 有 cache namespace 规则。
- 有 compile 映射或明确说明不需要 compile。
- 有至少一个 smoke 或 unit 验收点。
- 有 preview/final 画质边界说明。

### D.8 完成标准

一个 Timeline 任务完成时，应满足：

- UI 操作可用，或 CLI/worker 操作可用。
- timeline JSON 变化可读。
- dirty/apply/recovery 不破。
- compile 后 render_plan 符合预期。
- preview/final cache 不混用。
- 对应 smoke 通过。
- `node .\scripts\clean-test-artifacts.mjs --dry-run` 无残留。
