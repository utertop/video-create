# 对标达芬奇路线的 P0 可执行任务清单

## 目的

这份文档把 [对标达芬奇的能力差距表与执行路线图](./DAVINCI_BENCHMARK_GAP_AND_EXECUTION_ROADMAP.md) 里的 `P0` 进一步拆成可直接排期和落地的任务清单。

这里不再讨论“要不要做”，而是回答：

1. 当前最该先做的 `P0` 到底有哪些具体任务
2. 每项任务应该优先落在哪些模块和文件
3. 任务之间的依赖顺序是什么
4. 每项任务做完以后，如何判断算真正完成

适用范围：

- 当前阶段的主目标仍然是“成熟的自动化长视频生产工具”
- 希望未来具备更强的时间线编辑能力和更专业的产品可信度
- 但暂时不提前进入完整专业剪辑器 UI、大规模特效、调色模块和插件生态

相关文档：

- [路线图总索引](./ROADMAP_INDEX.md)
- [对标达芬奇的能力差距表与执行路线图](./DAVINCI_BENCHMARK_GAP_AND_EXECUTION_ROADMAP.md)
- [商业产品成熟度评估与落地路线图](./COMMERCIAL_PRODUCT_MATURITY_PLAN.md)
- [升级与迁移指南](./UPGRADE_AND_MIGRATION_GUIDE.md)

---

## 一、P0 总目标

当前 `P0` 不是为了让界面立刻更像达芬奇，而是为了补齐三类底层可信能力：

1. 让“时间线”先成为真实的数据模型，而不是只停留在蓝图和渲染计划之间的隐式结构
2. 让高性能渲染主路径、预览路径和 fallback 行为变得更可解释、更可预测
3. 让项目恢复、版本迁移和失败续跑真正形成闭环

用一句话概括：

`P0` 的目标是把当前项目从“能跑的大型自动化工具”，推进到“行为稳定、可恢复、可解释的专业级生产内核”。

---

## 二、P0 任务总表

| P0 任务 | 目标 | 主要落点 | 依赖 | 预估复杂度 |
| --- | --- | --- | --- | --- |
| Task 1. `timeline_schema_v1` | 定义未来时间线编辑的统一数据骨架 | `src/lib/engine.ts`、`video_engine_v5.py`、`docs/` | 无 | 高 |
| Task 2. 局部失效与重算规则 | 明确哪些改动触发哪些重编译/重渲染 | `video_engine_v5.py`、`docs/` | Task 1 | 高 |
| Task 3. build_report 结构化增强 | 让 route、fallback、cache、preview/export 差异可解释 | `video_engine_v5.py`、`src-tauri/src/lib.rs`、`src/lib/engine.ts` | Task 1 | 中高 |
| Task 4. preview/export 行为契约统一 | 让预览和正式导出使用更一致的描述体系 | `render_backends/`、`video_engine_v5.py`、`src/App.tsx` | Task 3 | 中高 |
| Task 5. autosave / recovery 闭环 | 让项目能恢复，而不是只有“保存过状态” | `src/App.tsx`、`src-tauri/src/lib.rs`、`src/lib/engine.ts` | 无 | 中 |
| Task 6. schema migration 完整化 | 为 `media_library / story_blueprint / render_plan / project_state` 建立稳定迁移机制 | `src-tauri/src/lib.rs`、`src/lib/engine.ts`、`docs/` | Task 1、Task 5 | 中高 |
| Task 7. fallback 可视化与用户解释 | 把“为什么回退”从日志提升到用户可理解层 | `src/App.tsx`、`src/lib/progress.ts`、`src/lib/diagnostics.ts` | Task 3、Task 4 | 中 |
| Task 8. P0 回归测试网 | 给 timeline、migration、report、recovery 建立专项回归 | `tests/`、`src-tauri/src/lib.rs` | 上述任务逐步完成后接入 | 中 |

---

## 三、建议执行顺序

建议按下面顺序推进，而不是并行散打：

1. `Task 1` 定义 `timeline_schema_v1`
2. `Task 2` 定义局部失效与重算规则
3. `Task 3` 扩展 `build_report.json`
4. `Task 4` 打通 preview/export 行为契约
5. `Task 5` 补全 autosave / recovery 闭环
6. `Task 6` 补全 schema migration
7. `Task 7` 做 fallback 用户解释层
8. `Task 8` 把这些任务都纳入专项回归测试

原因很简单：

- 没有 schema，后面的局部重算和编辑语义会漂
- 没有 report，后面的用户解释和诊断会空心
- 没有 recovery 和 migration，时间线内核以后越复杂，风险越高

---

## 四、分任务拆解

## Task 1. 定义 `timeline_schema_v1`

### 目标

在不推翻现有 `story_blueprint` 和 `render_plan` 的前提下，引入一个未来可扩展的时间线数据层。

### 为什么现在必须做

当前项目已经有：

- `story_blueprint`
- `render_plan`
- `timeline_cues`
- `audio_blueprint`

但这些结构还不足以支撑未来的：

- 多轨编辑
- clip 级非破坏编辑
- 局部重算
- 时间线 UI

如果不先补这一层，后面做时间线 UI 时会非常容易变成“界面像时间线，底层还是全局编译”。

### 建议产物

- 新文档：[`docs/TIMELINE_SCHEMA_V1.md`](./TIMELINE_SCHEMA_V1.md)
- 新类型定义：
  - `V5Timeline`
  - `V5TimelineTrack`
  - `V5TimelineClip`
  - `V5TimelineDependency`
  - `V5TimelineInvalidationHint`

### 建议落点

- [src/lib/engine.ts](D:/Automatic/video_create/src/lib/engine.ts:25)
- [video_engine_v5.py](D:/Automatic/video_create/video_engine_v5.py:3274)
- [TIMELINE_SCHEMA_V1.md](D:/Automatic/video_create/docs/TIMELINE_SCHEMA_V1.md:1)

### 最低验收标准

- 时间线结构能表达 `video / audio / title` 三类 track
- 每个 clip 都有稳定 id
- 能表达 clip 来源、编辑状态、依赖关系、局部失效提示
- 不要求第一版立刻进入渲染执行，但必须能被文档和类型系统稳定表示

---

## Task 2. 定义局部失效与重算规则

### 目标

明确“改了什么，应该重新算什么”，避免一切编辑都回落到全局重编译或全局重渲染。

### 建议先覆盖的改动类型

- 修改标题文字
- 修改 `title_style`
- 修改 `subtitle`
- 禁用/启用片段
- 调整单个 clip 顺序
- 修改背景图
- 修改音频 cue
- 修改导出参数但不改内容

### 建议产物

- 新文档：`docs/INVALIDATION_AND_RECOMPUTE_RULES.md`
- 规则表：
  - 仅重编译 blueprint
  - 仅重建 render_plan
  - 仅重建局部 cache
  - 仅重导出 preview
  - 必须全量 final render

### 建议落点

- [video_engine_v5.py](D:/Automatic/video_create/video_engine_v5.py:2955)
- [src/App.tsx](D:/Automatic/video_create/src/App.tsx:1895)
- [INVALIDATION_AND_RECOMPUTE_RULES.md](D:/Automatic/video_create/docs/INVALIDATION_AND_RECOMPUTE_RULES.md:1)

### 最低验收标准

- 至少 `8-12` 种常见编辑操作有明确定义的重算范围
- 文档与代码使用相同术语
- 不再只依赖“经验判断”是否需要重编译/重渲染

---

## Task 3. 增强 `build_report.json`

### 目标

让 `build_report.json` 从“技术日志摘要”升级为“可用于产品解释、恢复和支持排障的结构化报告”。

### 当前基础

项目已经有：

- `build_report.json` 写入
- backend decision / fallback chain
- cache stats
- route/fallback 统计基础

### 建议新增字段

- `timeline_summary`
- `preview_route`
- `final_render_route`
- `route_differences`
- `backend_selected`
- `fallback_chain`
- `fallback_used`
- `fallback_reason`
- `cache_hit_summary`
- `recompute_scope`
- `resume_recovery_summary`
- `migration_notes`

### 建议落点

- [video_engine_v5.py](D:/Automatic/video_create/video_engine_v5.py:6773)
- [render_backends/backend_selector.py](D:/Automatic/video_create/render_backends/backend_selector.py:174)
- [src-tauri/src/lib.rs](D:/Automatic/video_create/src-tauri/src/lib.rs:2982)
- [src/lib/engine.ts](D:/Automatic/video_create/src/lib/engine.ts:803)

### 最低验收标准

- 一次 render 完成后，报告能回答：
  - 最终走了哪个 backend
  - 有没有 fallback
  - 为什么 fallback
  - preview 和 final 是否走了不同路径
  - 哪些 cache 命中，哪些没有命中
  - 若支持恢复，本次是否从恢复点继续

---

## Task 4. 统一 preview/export 行为契约

### 目标

让“低清预览”和“正式导出”不再只是两个独立命令，而是同一套渲染语义的不同档位。

### 当前基础

- `preview-render` 命令已经存在
- backend selector 已经有 preview/final 区分
- preflight 已经存在

### 建议做法

- 在 UI 上明确显示：
  - 当前是 preview 还是 final
  - 各自的 backend 选择逻辑
  - 哪些效果会降级
  - 哪些 cache 会复用
- 在 report 中写清 preview/final 差异
- 在错误与日志中统一使用同一套 route/fallback 术语

### 建议落点

- [video_engine_v5.py](D:/Automatic/video_create/video_engine_v5.py:8600)
- [render_backends/backend_selector.py](D:/Automatic/video_create/render_backends/backend_selector.py:121)
- [src/App.tsx](D:/Automatic/video_create/src/App.tsx:1033)

### 最低验收标准

- 用户可以知道 preview 和 final 是否同路
- 如果不同路，界面能解释为什么不同
- preview 失败或回退时，说明文字和 final 保持一致风格

---

## Task 5. 完成 autosave / recovery 闭环

### 目标

把“保存过 `project_state.json`”升级为真正可恢复的项目闭环。

### 当前基础

- 已有 `save_project_state`
- 已有 `load_project_state`
- 已有 recent project
- 已有 build report summary

### 还缺什么

- 恢复点定义不够清晰
- 恢复后差异提示不够明确
- 中途失败后继续执行语义不完整
- 对未完成 render 的恢复策略还不够产品化

### 建议补充

- 明确保存时机：
  - scan 后
  - plan 后
  - compile 后
  - render queue 入队前
  - render 中关键节点
- 增加恢复来源区分：
  - 从 autosave 恢复
  - 从 recent project 恢复
  - 从未完成 render 恢复
- 增加恢复对比卡片：
  - 当前素材路径变化
  - blueprint/render_plan 是否被迁移
  - 是否存在缺失素材

### 建议落点

- [src/App.tsx](D:/Automatic/video_create/src/App.tsx:1360)
- [src-tauri/src/lib.rs](D:/Automatic/video_create/src-tauri/src/lib.rs:2398)
- [src/lib/engine.ts](D:/Automatic/video_create/src/lib/engine.ts:762)

### 最低验收标准

- 异常关闭后能稳定恢复最近工作状态
- 恢复时用户能看懂恢复来源和风险
- render 中断后，至少能恢复到可继续检查和重新发起的位置

---

## Task 6. 补齐 schema migration

### 目标

让版本升级不再依赖“凑巧兼容”，而是有明确的文档和代码迁移策略。

### 当前基础

- Rust 侧已有 `render_plan` 等文档迁移基础
- 前端已有 schema version 常量
- 文档已有升级与迁移指南

### 建议覆盖范围

- `media_library.json`
- `story_blueprint.json`
- `render_plan.json`
- `project_state.json`
- 后续的 `timeline_schema_v1`

### 建议补充内容

- migration notes 结构化输出
- 前端对迁移结果的提示
- 迁移失败时的稳定错误码
- 测试样本目录

### 建议落点

- [src-tauri/src/lib.rs](D:/Automatic/video_create/src-tauri/src/lib.rs:3130)
- [src/lib/engine.ts](D:/Automatic/video_create/src/lib/engine.ts:1089)
- [UPGRADE_AND_MIGRATION_GUIDE.md](D:/Automatic/video_create/docs/UPGRADE_AND_MIGRATION_GUIDE.md:1)

### 最低验收标准

- 四类核心文档都有明确 version 和 migration 入口
- 升级后用户能看到“已迁移哪些内容”
- 迁移失败时能给出稳定错误码和恢复建议

---

## Task 7. 把 fallback 提升为用户可理解的产品能力

### 目标

让 fallback 不再只是日志里的技术概念，而是 UI 可解释、支持可复盘、用户可理解的行为。

### 当前基础

- 已有 fallback 统计
- 已有 cache fallback 说明
- 已有 backend fallback chain

### 建议补强

- UI 增加统一的“本次导出如何执行”面板
- 统一使用术语：
  - selected backend
  - fallback used
  - fallback reason
  - preview route
  - final route
- 诊断包里附带最近一次 route/fallback 摘要

### 建议落点

- [src/App.tsx](D:/Automatic/video_create/src/App.tsx:2209)
- [src/lib/progress.ts](D:/Automatic/video_create/src/lib/progress.ts:214)
- [src/lib/diagnostics.ts](D:/Automatic/video_create/src/lib/diagnostics.ts:1)

### 最低验收标准

- 用户在不看原始日志的情况下，也能知道这次为什么慢、为什么回退
- 支持人员能根据诊断包快速判断卡在 route 选择、cache、还是 backend fallback

---

## Task 8. 建立 P0 专项回归测试

### 目标

让 P0 不只是设计完成，而是具备长期可防回归的工程护栏。

### 建议新增测试类型

- timeline schema 解析与兼容测试
- invalidation rule 测试
- build report 字段完整性测试
- preview/final route 差异测试
- project_state 恢复测试
- migration regression 测试
- fallback explanation regression 测试

### 建议落点

- [tests/](D:/Automatic/video_create/tests)
- [src-tauri/src/lib.rs](D:/Automatic/video_create/src-tauri/src/lib.rs:3421)
- `scripts/check.mjs`

### 最低验收标准

- `npm run check` 或 `check:full` 能覆盖至少一部分 P0 专项测试
- 新增 route/report/recovery/migration 改动不会轻易无声回归

---

## 五、建议拆成的首批开发批次

为避免把 P0 做成一个巨大混合提交，建议按下面批次推进：

### Batch 1

- `timeline_schema_v1` 文档
- `invalidations_and_recompute_rules` 文档
- 前端/类型层 timeline 草案定义

### Batch 2

- `build_report.json` 字段增强
- Tauri summary extractor 对应增强
- 前端 diagnostics summary 对应增强

### Batch 3

- autosave / recovery 闭环
- 恢复提示 UI
- 未完成 render 恢复策略

### Batch 4

- schema migration 完整化
- migration notes 展示
- 回归测试补齐

### Batch 5

- preview/final 契约统一
- fallback 用户解释层
- 统一术语和 UI 卡片

---

## 六、当前不建议混在 P0 里的工作

下面这些内容即使未来要做，也不建议和 P0 混在同一批推进：

- 多轨完整时间线 UI
- 复杂 effect stack
- 音频 mixer 深化
- subtitle track 全功能化
- LUT / scope / 调色页
- 插件系统

这些方向都依赖 P0 的 schema、report、recovery、migration 先收口。

---

## 七、P0 完成后的标志

当下面这些条件基本成立时，可以认为 P0 进入完成状态：

- 时间线已有稳定 schema，而不是继续只靠隐式结构
- 常见编辑操作已定义局部失效范围
- `build_report.json` 已能解释 route、fallback、cache、preview/export 差异
- autosave、recovery、migration 已经形成闭环
- fallback 已经对用户可解释，而不只对开发者可见
- P0 专项测试已进入常规检查流程

---

## 八、结论

`P0` 的本质不是“加功能”，而是给未来更专业的编辑能力打地基。

如果这层地基不先做稳，后面的时间线 UI、字幕轨、音频系统、effect stack 都会越来越像“假成熟”。

反过来，如果 `P0` 做扎实了，哪怕短期内还没有完整达芬奇式界面，项目也会明显更像一个可靠的专业生产系统。
