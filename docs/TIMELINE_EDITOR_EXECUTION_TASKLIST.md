# Video-Create V5.7 Timeline Editor 开干执行文档

> 基于：[Video-Create V5.6 Timeline Editor 最终优化规划方案](./TIMELINE_EDITOR_FINAL_OPTIMIZATION_PLAN.md)  
> 当前基线：Video Create Studio V5.6.x  
> 目标版本建议：V5.7 Timeline Kernel，后续 V5.8 Timeline Editor MVP  
> 执行原则：小步合并、每步可验收、不中断现有 V5 主链路

## 一、开干总目标

本阶段不是直接做一个完整专业剪辑器，而是先把项目从“`render_plan.segments` 展示型时间线”升级为“真实 Timeline 数据层驱动的编辑系统”。

最终要达成：

- 项目中存在正式的 `timeline.json`。
- 前端状态存在 `v5Timeline`。
- 时间线 UI 不再直接依赖 `render_plan.segments`。
- 用户编辑写入 timeline，而不是临时改 render_plan。
- timeline 可以重新编译为 render_plan。
- preview/final/cache 有明确隔离，正式导出不被低清预览污染。
- build_report 能解释 timeline、cache、fallback、recompute、quality。

## 二、不要一开始做的事

以下能力暂时不要进入 V5.7：

- split 分割
- trim 裁剪完整交互
- ripple edit
- 完整字幕轨系统
- 音频波形
- 音量包络关键帧
- effect stack
- 调色 / LUT
- nested timeline
- 插件系统
- 大规模重构 `src/App.tsx`
- 大规模迁移目录结构

这些能力等 Timeline Kernel、compile_from_timeline、cache/recompute 闭环稳定后再进入 V5.8/V6。

## 三、阶段 0：施工前基线确认

### 目标

确认当前 V5.6.x 主链路稳定，避免在不清楚基线的情况下开工。

### 任务

- 运行基础检查。
- 确认当前前端状态只有 `v5Library / v5Blueprint / v5RenderPlan`。
- 确认当前 RENDER 阶段时间线仍来自 `render_plan.segments`。
- 确认已有 build_report、cache、recovery、preview 能力不被新方案覆盖。

### 建议检查命令

```powershell
npm run check
```

可选完整检查：

```powershell
npm run check:full
```

### 验收

- 当前主链路可跑通。
- 没有为了 Timeline 改动现有 render 行为。
- 已记录当前失败项，后续不要把历史失败误认为本阶段引入。

## 四、阶段 1：Timeline 类型与 Schema 落地

### 目标

先让代码层正式认识 `V5Timeline`。

### 涉及文件

- `src/lib/engine.ts`
- `docs/TIMELINE_SCHEMA_V1.md`
- `docs/TIMELINE_EDITOR_FINAL_OPTIMIZATION_PLAN.md`
- `tests/smoke_v5_timeline_schema.py`

### 任务

- 在 `src/lib/engine.ts` 新增 Timeline 类型。
- 新增 `V5Timeline`。
- 新增 `V5TimelineTrack`。
- 新增 `V5TimelineClip`。
- 新增 `V5TimelineDependency`。
- 新增 `V5TimelineInvalidationHint`。
- 新增 `V5TimelinePerformancePolicy`。
- 新增 `V5_TIMELINE_VERSION = "v1"`。
- 明确 clip 时间字段：
  - `timeline_start`
  - `timeline_duration`
  - `timeline_end`
  - `source_in`
  - `source_out`
  - `playback_rate`
- 明确 preview/final cache policy 结构。

### 验收

- TypeScript 编译通过。
- 不引入 `any` 滥用。
- Timeline 类型能表达 `video / audio / title` 三类 track。
- Timeline clip 能表达素材来源、内容、展示、执行、失效提示。
- `npm run build:web` 通过。

### 测试

新增：

```text
tests/smoke_v5_timeline_schema.py
```

测试点：

- 最小 timeline JSON 可 parse。
- 缺失可选字段不会报错。
- `timeline_start + timeline_duration = timeline_end` 可校验。
- preview/final policy 默认值正确。

## 五、阶段 2：Python Timeline 生成器

### 目标

从现有 `story_blueprint.json + render_plan.json` 生成 `timeline.json`。

### 涉及文件

- `video_engine/timeline.py`
- `video_engine_v5.py`
- `video_engine_worker.py`
- `tests/smoke_v5_timeline_generate.py`

### 任务

- 新增 `video_engine/timeline.py`。
- 实现 `build_timeline_from_blueprint()`。
- 实现 `build_timeline_from_render_plan()`。
- 实现 `build_timeline_document()`。
- 建立 track 生成规则：
  - `track_video_main`
  - `track_title_main`
  - `track_audio_main`
- 建立 clip_id 生成规则。
- 支持旧 timeline 与新生成 timeline 的 clip 匹配。
- 输出 `timeline.json` 到项目目录。
- 在 CLI 或 worker command 中增加 timeline-generate 能力。

### clip_id 稳定规则

第一次生成：

```text
clip_<kind>_<stable_hash>
```

stable hash 推荐输入：

- `section_id`
- `asset_id`
- `segment_id`
- `clip kind`
- `source path`
- occurrence index

重新生成：

1. 优先读取旧 `timeline.json`。
2. 用 source_ref 和 kind 匹配旧 clip。
3. 匹配成功则沿用旧 `clip_id`。
4. 匹配失败才创建新 `clip_id`。

### 验收

- 相同输入重复生成，clip_id 稳定。
- 每个 render segment 至少能映射到一个 timeline clip。
- audio blueprint 能映射到 audio track。
- title/chapter card 能映射到 title 或 video track。
- timeline JSON 可被前端类型解析。
- timeline 生成失败不阻断旧主链路。

### 测试

新增：

```text
tests/smoke_v5_timeline_generate.py
```

测试点：

- 能从 mock blueprint/render_plan 生成 timeline。
- 至少生成 video/audio/title tracks。
- clip_id 稳定。
- disabled 字段默认 true。
- performance policy 默认 final 不允许 proxy。

## 六、阶段 3：前端 v5Timeline 状态接入

### 目标

前端正式持有 `v5Timeline`，但还不做复杂编辑。

### 涉及文件

- `src/store/studio.ts`
- `src/lib/engine.ts`
- `src/App.tsx`
- `src/lib/blueprint.ts`

### 任务

- `StudioState` 增加 `v5Timeline: V5Timeline | null`。
- `selectStudioAppState` 纳入 `v5Timeline`。
- `setInputFolder()` 清空 `v5Timeline`。
- scan/plan/compile 后尝试加载或生成 timeline。
- 项目恢复时恢复 `v5Timeline`。
- 保存 session snapshot 时包含 `v5Timeline`。

### 验收

- 打开项目后能恢复 timeline。
- 重新扫描会清空旧 timeline。
- 没有 timeline 时仍可使用旧 render_plan 流程。
- 前端不因为旧项目缺少 timeline 崩溃。

### 测试

可先通过现有前端 build 覆盖：

```powershell
npm run build:web
```

## 七、阶段 4：Preview / Final / Cache 画质护栏

### 目标

在编辑能力上线前，先锁死画质边界。

### 涉及文件

- `video_engine/render_cache.py`
- `video_engine/render_diagnostics.py`
- `video_engine/render_proxy.py`
- `video_engine_v5.py`
- `tests/smoke_v5_preview_final_cache_isolation.py`
- `tests/smoke_v5_final_render_original_source.py`

### 任务

- preview cache namespace 固定为 `preview`。
- final cache namespace 固定为 `final`。
- proxy cache namespace 固定为 `proxy`。
- thumbnail cache namespace 固定为 `thumbnail`。
- final render 强制 `allow_proxy = false`。
- cache fingerprint 纳入：
  - engine version
  - quality
  - fps
  - aspect ratio
  - render mode
  - preview/final namespace
  - title style
  - audio settings
- build_report 写入 preview/final/cache 策略摘要。

### 验收

- preview cache 不会被 final render 复用。
- final render 不读取 proxy 作为最终素材源。
- 改质量档位会导致 final cache 正确失效。
- 改 preview 分辨率不会污染 final cache。

### 测试

新增：

```text
tests/smoke_v5_preview_final_cache_isolation.py
tests/smoke_v5_final_render_original_source.py
```

## 八、阶段 5：最小 Invalidation Rules

### 目标

先建立编辑动作到重算范围的稳定规则，避免后续编辑 UI 乱标 dirty。

### 涉及文件

- `src/features/timeline/timelineInvalidation.ts`
- `video_engine/timeline.py`
- `tests/smoke_v5_timeline_invalidation.py`

### 任务

- 定义 `TimelineEditOperation`。
- 定义 `resolveRecomputeScope()`。
- 支持以下操作：
  - title text change
  - title style change
  - subtitle text change
  - clip enable/disable
  - clip reorder
  - image duration change
  - bgm volume change
  - bgm cue range change
  - preview quality change
  - final quality change
  - aspect ratio change
- 输出：
  - primary_scope
  - affected_clip_ids
  - affected_track_ids
  - requires_render_plan_recompile
  - requires_audio_relayout
  - reason

### 验收

- 主要编辑动作都有确定 scope。
- 修改标题不默认 full rebuild。
- 修改音频不默认重算视觉轨。
- 改画幅明确 full rebuild。

### 测试

新增：

```text
tests/smoke_v5_timeline_invalidation.py
```

## 九、阶段 6：只读 Timeline UI 替换 segments timeline

### 目标

先把 UI 数据源从 `render_plan.segments` 切到 `v5Timeline.tracks`。

### 涉及文件

- `src/features/timeline/TimelineEditor.tsx`
- `src/features/timeline/TimelineTrack.tsx`
- `src/features/timeline/TimelineClip.tsx`
- `src/features/timeline/TimelineRuler.tsx`
- `src/features/timeline/TimelineInspector.tsx`
- `src/App.tsx`
- `src/styles.css`

### 任务

- 新增 TimelineEditor。
- 支持 video/title/audio 三轨展示。
- clip 宽度按 `timeline_duration` 计算。
- 支持横向滚动。
- 支持基础 zoom state，但第一版可以固定 zoom。
- 支持选中 clip。
- Inspector 展示：
  - clip id
  - kind
  - track id
  - source path
  - section id
  - asset id
  - segment id
  - timeline start/end/duration
  - invalidation hint
  - cache policy
- 当前渲染片段高亮不能退化。
- 音频章节联动不能退化。

### 验收

- RENDER 阶段不再直接用 `render_plan.segments` 渲染主时间线。
- 没有 timeline 时显示兼容 fallback。
- 点击 clip 能看到来源信息。
- 100 个 clip 初次渲染不明显卡顿。
- UI 不改变 render_plan。

### 检查

```powershell
npm run build:web
```

## 十、阶段 7：Timeline 基础编辑

### 目标

上线第一批真正有价值、低风险的编辑能力。

### 涉及文件

- `src/features/timeline/timelineOps.ts`
- `src/features/timeline/TimelineInspector.tsx`
- `src/features/timeline/TimelineEditor.tsx`
- `src/store/studio.ts`

### 第一批编辑能力

- clip 禁用 / 启用
- 标题文字编辑
- 标题样式编辑
- 图片 clip 时长编辑
- video track 基础拖拽排序
- BGM cue 音量编辑

### 任务

- 实现 `updateClipEnabled()`。
- 实现 `updateClipContent()`。
- 实现 `updateClipPresentation()`。
- 实现 `updateClipDuration()`。
- 实现 `moveClip()`。
- 所有编辑写入：
  - `edit_state.user_overridden = true`
  - `edit_state.override_fields`
  - `edit_state.last_edited_at`
  - `invalidation_hint`
- 拖拽期间只更新 UI preview state。
- 拖拽结束后才提交 timeline patch。
- 编辑后标记 timeline dirty。

### 验收

- 禁用 clip 后 UI 灰显。
- 重新打开项目后禁用状态保持。
- 修改标题后 timeline 保存。
- 修改图片时长后后续 clip 时间顺延。
- 拖拽后 clip 顺序保存。
- 所有编辑都能输出 recompute scope。

### 测试

新增：

```text
tests/smoke_v5_timeline_edit_ops.py
```

## 十一、阶段 8：Timeline 编译为 Render Plan

### 目标

让 timeline 成为 render_plan 的真实上游。

### 涉及文件

- `video_engine/timeline_compile.py`
- `video_engine/compile.py`
- `video_engine_v5.py`
- `video_engine_worker.py`
- `tests/smoke_v5_timeline_compile.py`

### 任务

- 新增 `compile_from_timeline()`。
- compile 阶段支持读取 `timeline.json`。
- disabled clip 不进入 render_plan。
- reorder 影响 render_plan segment 顺序。
- duration 修改影响 segment duration。
- title 修改影响 title segment。
- audio cue 修改影响 render settings audio blueprint。
- 保留可复用 cache key。
- 输出：
  - `timeline_compile_elapsed_ms`
  - `recompute_summary`
  - `timeline_source_path`

### 验收

- timeline 编辑后重新 compile 生成新 render_plan。
- disabled clip 不渲染。
- 改标题后最终视频标题变化。
- 改 duration 后总时长变化。
- 拖拽排序后最终视频顺序变化。
- final render 仍使用原始素材。

### 测试

新增：

```text
tests/smoke_v5_timeline_compile.py
```

## 十二、阶段 9：Build Report V2 兼容扩展

### 目标

让用户不用看日志，也能理解这次为什么这么渲染。

### 涉及文件

- `video_engine/render_diagnostics.py`
- `video_engine/render_cache.py`
- `video_engine/render_stable.py`
- `src/lib/engine.ts`
- `src/components/RenderQueuePanel.tsx`
- `src/features/render/RenderExplainabilityPanel.tsx`
- `tests/smoke_v5_build_report_v2.py`

### 任务

在现有 build_report 上兼容新增：

- `timeline_summary`
- `route_summary`
- `fallback_summary`
- `cache_summary`
- `recompute_summary`
- `performance_summary`
- `quality_summary`
- `recovery_summary`
- `migration_notes`

前端新增解释面板，展示：

- 本次 preview 路径
- 本次 final 路径
- 是否 fallback
- fallback reason
- cache 命中情况
- recompute scope
- 是否使用 original source
- 是否可恢复
- 失败后建议动作

### 验收

- 老 build_report 可继续读取。
- 新字段缺失时前端不崩。
- 用户能看到 backend、fallback、cache、quality、recovery 摘要。
- 诊断包包含 report summary。

### 测试

新增：

```text
tests/smoke_v5_build_report_v2.py
```

## 十三、阶段 10：Recovery / Migration 闭环

### 目标

确保老项目、异常关闭、半成品 timeline 都能安全处理。

### 涉及文件

- `src/App.tsx`
- `src/lib/engine.ts`
- `src-tauri/src/lib.rs`
- `video_engine/timeline.py`
- `tests/smoke_v5_project_recovery.py`
- `tests/smoke_v5_schema_migration.py`

### 任务

- 老项目没有 timeline 时自动生成。
- timeline 生成失败时回退旧流程。
- schema_version 不一致时输出 migration notes。
- timeline_version 不一致时执行迁移。
- 迁移失败不覆盖原文件。
- session snapshot 包含 timeline。
- 恢复 UI 告知恢复来源。

### 验收

- 老项目能打开。
- 老项目能生成 timeline。
- 迁移失败不破坏原文件。
- 异常关闭后能恢复 timeline。
- 用户知道恢复/迁移发生了什么。

### 测试

新增：

```text
tests/smoke_v5_project_recovery.py
tests/smoke_v5_schema_migration.py
```

## 十四、阶段闸门

### 进入 P1 前必须满足

- `V5Timeline` 类型落地。
- `timeline.json` 可生成。
- clip_id 稳定。
- `v5Timeline` 可保存/恢复。
- preview/final/cache 隔离测试通过。
- final original source 测试通过。
- 最小 invalidation rules 测试通过。

### 进入 compile_from_timeline 前必须满足

- 只读 Timeline UI 已经替换 segments timeline。
- Inspector 能展示来源信息。
- timeline 编辑操作能稳定写入 edit_state。
- 每种编辑都能给出 recompute scope。

### 进入 V5.8 前必须满足

- timeline -> render_plan 编译稳定。
- build_report V2 兼容扩展稳定。
- recovery/migration 闭环稳定。
- 基础编辑能力不会破坏 final render。

## 十五、建议提交拆分

推荐 PR / commit 顺序：

1. `docs: add timeline editor execution tasklist`
2. `types: add V5 timeline schema types`
3. `engine: generate timeline from blueprint and render plan`
4. `store: persist v5 timeline state`
5. `render: isolate preview and final cache policies`
6. `timeline: add invalidation rules`
7. `ui: render readonly timeline from v5Timeline`
8. `ui: add timeline inspector`
9. `timeline: add basic edit operations`
10. `engine: compile render plan from timeline`
11. `report: extend build report with timeline summaries`
12. `recovery: add timeline migration and recovery flow`
13. `tests: add timeline regression coverage`

## 十六、最终验收清单

- [ ] `timeline.json` 能生成。
- [ ] `v5Timeline` 能进入前端状态。
- [ ] timeline 能保存和恢复。
- [ ] RENDER 阶段主时间线来自 `v5Timeline.tracks`。
- [ ] clip_id 重复生成稳定。
- [ ] preview cache 不污染 final cache。
- [ ] final render 不使用 proxy。
- [ ] 修改标题只标记 clip 级重算。
- [ ] 修改音频不重算视觉轨。
- [ ] 禁用 clip 后 compile 不进入 render_plan。
- [ ] 拖拽排序后 render_plan 顺序变化。
- [ ] 修改图片时长后总时长变化。
- [ ] build_report 能解释 route/fallback/cache/recompute/quality。
- [ ] 老项目没有 timeline 时可自动迁移。
- [ ] 迁移失败不破坏旧项目。
- [ ] `npm run check` 通过。

## 十七、一句话执行纲领

先做 Timeline Kernel，再做只读 UI，再做基础编辑，再接 compile_from_timeline，最后补 report、recovery、migration。

不要为了看起来像专业剪辑器而过早做复杂交互。V5.7 的成功标准不是功能多，而是 Timeline 数据层站稳、编辑意图可保存、渲染结果可解释、正式导出画质不退化。
