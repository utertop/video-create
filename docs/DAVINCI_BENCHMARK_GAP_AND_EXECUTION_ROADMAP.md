# 对标达芬奇的能力差距表与执行路线图

## 目的

这份文档回答两个更具体的问题：

1. 如果把 `DaVinci Resolve` 视为专业剪辑软件参考系，当前项目到底差在哪些关键能力上
2. 如果不是空谈“像达芬奇”，而是要在当前仓库基础上持续逼近，应该先补什么、后补什么

本文档默认前提是：

- 当前项目仍应优先服务“自动化长视频生产工具”这个定位
- 对标达芬奇的意义，是借它来识别关键产品能力，而不是机械复制全部 UI 和全部模块
- 任何“更像专业剪辑器”的投入，都必须建立在当前 `scan -> plan -> compile -> render` 主链稳定的前提上

相关文档：

- [路线图总索引](./ROADMAP_INDEX.md)
- [专业剪辑器差距与成熟度路线图](./PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md)
- [对标达芬奇路线的 P0 可执行任务清单](./DAVINCI_P0_EXECUTION_TASKLIST.md)
- [商业产品成熟度评估与落地路线图](./COMMERCIAL_PRODUCT_MATURITY_PLAN.md)
- [模板匹配、配乐蓝图与轻量时间线执行计划](./TEMPLATE_MATCHING_BGM_AND_TIMELINE_EXECUTION_PLAN.md)

---

## 一、当前基线

当前仓库已经具备的、值得保留并继续放大的基础包括：

- 明确的规则化主流程：`scan -> plan -> compile -> render`
- 桌面端承载与 Python worker 协作
- `stable` 长视频渲染路径
- `FFmpeg + cache + hardware encoding + fallback` 的工程护栏
- `preview-render`、render preflight、render queue、recent project、diagnostic bundle
- 标题风格、音频蓝图、代理素材、chunk/segment/cache 扩展路径

也就是说，它已经不是“玩具原型”，而是一个有清晰内核的自动化视频生产工具。

但如果以达芬奇为参考系，它当前仍然更像：

- 一个项目编排器
- 一个规则驱动的自动出片系统
- 一个带少量可视化调节能力的渲染工作台

而不是：

- 一个成熟的实时非线性编辑器
- 一个多轨、可局部编辑、可实时反馈的专业剪辑环境

---

## 二、能力差距总表

| 能力域 | 当前基础 | 与达芬奇的主要差距 | 建议补强方向 | 优先级 | 难度 |
| --- | --- | --- | --- | --- | --- |
| 交互模型 | 已有 `BlueprintEditor`、`EditStrategyPreview`、章节与标题样式编辑 | 仍非实时 NLE；缺拖拽时间线、trim、ripple、snap、逐帧预览、即时反馈 | 先做“轻时间线交互层”：拖拽排序、片段裁剪、局部预览、吸附对齐 | `P1` | 高 |
| 时间线数据模型 | 已有 `story_blueprint`、`render_plan`、`timeline_cues`、`audio_blueprint` | 缺成熟的多轨时间线模型、clip 依赖图、局部重算图 | 增加统一 timeline schema：video/audio/title track、clip id、dependency graph、invalidations | `P0` | 高 |
| 渲染主路径 | 已有 `FFmpeg stable`、chunk route、cache、fallback chain | 大量真实场景仍会回落到 `MoviePy`，快路径覆盖率不够高 | 继续扩张 FFmpeg 快路径，让 `MoviePy` 只承担复杂兜底 | `P0` | 高 |
| 预览与正式导出一致性 | 已有 `preview-render`、preflight、build report、backend selector | 预览与正式导出仍不是同一套用户可理解的“行为契约” | 统一 route 展示、fallback reason、cache hit 说明、性能档位说明 | `P0` | 中高 |
| 媒体池与代理素材 | 已有 `proxy_media_manifest`、scan proxy、thumbnail、cache cleanup | 还不是成熟 media pool；缺 relink、offline media、代理/原片切换、项目级媒体管理 | 做媒体池页、缺失素材重连、代理状态显示、批量健康检查 | `P1` | 中高 |
| 音频系统 | 已有 `audio_blueprint`、`timeline_cues`、BGM 策略和音频缓存 | 缺波形编辑、关键帧、bus/mixer、loudness 工作流、效果链 | 先补波形视图、音量包络、ducking 可视化、统一 loudness | `P1` | 高 |
| 标题与字幕 | 已有 `title_style`、`subtitle`、overlay title、Title Lab | 更像章节牌系统，不是完整字幕轨；缺 SRT 流程、样式批量化、字幕管理 | 增加 subtitle track、SRT 导入导出、样式模板、lower-third 复用 | `P1` | 中高 |
| 稳定性与恢复 | 已有 autosave 雏形、recent project、diagnostic bundle、preflight | 跟专业软件相比，崩溃恢复、版本迁移、恢复引导还不够成熟 | 做 `project_state` 自动恢复闭环、schema migration、恢复向导、崩溃后续跑 | `P0` | 中 |
| 效果栈与非破坏编辑 | 已有策略化 motion/title/background 控制 | 缺 clip-level effect stack、adjustment layer、可组合特效链 | 先做最小 effect stack：transform、crop、opacity、blur、filter | `P2` | 高 |
| 色彩链路 | 当前不以调色为中心 | 缺 color management、LUT、scope、节点式调色、HDR/REC709 管线 | 暂不前置；等时间线和主路径稳定后再评估 color pipeline | `P2` | 很高 |
| 扩展与生态 | 当前更像封闭工具 | 缺脚本化扩展、模板生态、插件边界 | 先做模板 API 和内部 preset 能力，再考虑插件化 | `P2` | 高 |

---

## 三、哪些差距最该先补

如果目标是“尽量接近专业剪辑软件的可信体验”，当前最值得优先投入的不是更多花哨转场，而是下面四件事：

### 1. 时间线模型先于时间线 UI

如果没有统一的 timeline schema、clip 依赖关系和局部失效图，那么即使前端做出拖拽时间线，底层也仍然会退化成：

- 改一点就全局重编译
- 改一点就全局重渲染
- UI 变复杂，但底层行为仍然不可预测

所以“更像达芬奇”的第一步，不是画时间线，而是让时间线成为一个真实的数据模型。

### 2. 高性能主路径先于复杂交互

达芬奇之所以像专业软件，不只是界面专业，更因为大多数常见场景都能稳定跑在高性能后端上。

当前项目也已经在朝这个方向推进，但还没有完全到位。优先级应该继续保持：

1. 扩大 `ffmpeg_direct_chunk / image_chunk / fitted_video_chunk / card_chunk` 命中率
2. 让 build report 对 route、fallback、cache 行为更可解释
3. 把 `MoviePy` 收缩到真正少量的复杂组合场景

### 3. 恢复能力先于高级特效

专业工具的一个关键竞争力，是用户敢把长项目交给它。

这依赖的不是更多动画，而是：

- 自动保存
- 崩溃恢复
- 版本迁移
- 失败后可续跑
- 用户能看懂的错误与建议

这部分对信任建立的价值，远高于再多加几种视觉效果。

### 4. 先补音频和字幕系统，再补炫技效果

对真实创作流程来说，音频和字幕比炫技特效更接近“专业感”：

- 有波形和关键帧的音频时间线，比多一个转场更像剪辑器
- 有 subtitle track 和批量样式管理，比多一种标题动画更像成熟产品

---

## 四、推荐执行路线

## 阶段 A：补齐专业工具最底层的可信能力

目标：

- 让项目从“能跑”升级为“敢长期使用”
- 让复杂项目的行为变得更可解释

核心任务：

- 建立统一 timeline schema 草案
- 引入 clip id、track id、dependency id、局部失效规则
- 让 `build_report.json` 输出 route、fallback、cache、preview/export 差异
- 固化 autosave、恢复入口、schema migration、失败后继续执行链路

阶段产物：

- `timeline_schema_v1`
- `invalidations_and_dependency_rules.md`
- 更结构化的 `build_report.json`
- 项目恢复与迁移 smoke tests

## 阶段 B：做轻量但真实可用的编辑时间线

目标：

- 让用户开始在时间线层面“编辑”，而不是只在参数层面“配置”

核心任务：

- 单轨到多轨的最小可用过渡
- clip 拖拽排序
- clip trim / split / disable
- 吸附与基础对齐
- 局部预览与局部重算

阶段产物：

- 最小时间线 UI
- 基于 schema 的非破坏编辑
- timeline edit regression tests

## 阶段 C：把音频和字幕补成真正的系统

目标：

- 让项目从“自动成片工具”更进一步接近“可编辑生产工具”

核心任务：

- 音频波形视图
- 音量包络与 ducking 曲线
- loudness 标准化与导出说明
- subtitle track
- SRT 导入导出
- lower-third / title preset 批量应用

阶段产物：

- `audio_timeline_v1`
- `subtitle_track_v1`
- 音频与字幕回归样例集

## 阶段 D：再决定是否往更完整的专业剪辑器演进

目标：

- 在底层稳定后，再评估是否进入更高复杂度阶段

可选任务：

- effect stack
- adjustment layer
- nested timeline / compound clip
- 更强 media pool
- 更完整 color pipeline
- 扩展 API / 模板生态

这一阶段不建议提前开启，否则会让系统复杂度上升过快。

---

## 五、建议直接进入主线的 P0 / P1 / P2 任务

### P0

- 定义 `timeline_schema_v1`
- 定义局部重算与 cache 失效规则
- 扩大 FFmpeg 主路径覆盖率
- 结构化输出 preview/export route 与 fallback reason
- 完成 autosave、recovery、migration 闭环

更细的任务拆分见：

- [DAVINCI_P0_EXECUTION_TASKLIST.md](./DAVINCI_P0_EXECUTION_TASKLIST.md)

### P1

- 轻时间线编辑 UI
- 媒体池与缺失素材重连
- 音频波形与包络
- subtitle track 与 SRT 流程
- clip 级基础编辑操作

### P2

- effect stack
- adjustment layer
- nested timeline
- color pipeline
- 模板与插件扩展边界

---

## 六、不建议当前优先投入的方向

以下方向并非不重要，而是不该抢在主线前面：

- 先做完整达芬奇式多页面工作区
- 先做大量复杂转场和炫技特效
- 先做完整调色模块
- 先做插件生态
- 在没有时间线内核的情况下只做更复杂的时间线 UI

如果这些方向过早推进，项目很容易出现“看起来更专业，但底层仍不稳定”的假成熟。

---

## 七、如何判断这条路线是否有效

建议用下面这些问题做阶段验收：

### 架构层

- timeline schema 是否已经能表达未来多轨编辑，而不是继续只靠蓝图拼接
- 一次局部编辑是否可以只触发局部失效和局部重渲染
- fallback 行为是否可以稳定解释

### 用户层

- 用户能否理解当前项目为什么快、为什么慢、为什么回退
- 渲染失败后，用户是否知道下一步该怎么恢复
- 用户是否能在时间线层而不是 JSON/参数层完成更多编辑

### 产品层

- `MoviePy` 是否已退到少量复杂兜底场景
- 是否已经具备“把长项目放心交给它”的基本信任感
- 是否已经开始具备比传统自动化工具更强的人机协作能力

---

## 八、结论

如果希望这个项目未来真的具备一部分“达芬奇式专业感”，正确路线不是：

- 先做得像达芬奇

而是：

1. 先做出真实的时间线内核
2. 再做高命中率、高解释性的高性能主路径
3. 再把恢复能力、音频系统、字幕系统补齐
4. 最后才考虑更完整的专业剪辑器形态

换句话说，当前最值钱的不是“更多功能”，而是“让已有内核更像一个可信赖的专业系统”。
