# Video-Create V5.6 Timeline Editor 最终优化规划方案

> 文档版本：V1.1  
> 适用项目版本：Video Create Studio V5.6.x  
> 目标演进方向：V5.7+ Timeline Editor 数据内核与编辑闭环

## 一、文档定位

本文档是在《Video-Create Timeline Editor 企业级成熟优化规划方案 V1.0》的基础上，结合当前 `video_create` 项目代码状态和已有路线图后形成的最终执行版。

它的目标不是把项目立刻改造成完整通用 NLE，而是让项目从当前的“自动化视频生成工具”稳步升级为：

> 可编辑、可恢复、可解释、性能可控、画质有保障的视频生产系统。

本方案遵循四个原则：

1. 不推翻当前 `scan -> plan -> compile -> render` 主链路。
2. 先补真实 Timeline 数据层，再做复杂编辑 UI。
3. Preview 性能优化不能污染 Final Render 画质。
4. 所有新能力必须可迁移、可诊断、可回退。

## 二、当前判断

当前项目已经具备较扎实的自动化生成和渲染基础：

- `scan -> media_library.json`
- `plan -> story_blueprint.json`
- `compile -> render_plan.json`
- `render -> final mp4 / build_report.json`
- Python V5 渲染引擎
- FFmpeg stable backend
- MoviePy fallback
- proxy media
- segment / chunk / visual base / audio cache
- Render Queue
- Render Preflight
- Recovery Summary
- 诊断导出

但当前前端状态仍主要围绕：

- `v5Library`
- `v5Blueprint`
- `v5RenderPlan`

缺少一个承载用户编辑意图的核心对象：

- `v5Timeline`

当前 UI 中的时间线本质上仍是 `render_plan.segments` 的展示视图，而不是真正可编辑、可持久化、可局部重算的 Timeline Editor。

因此，下一阶段最关键的架构补强是：

> 在 `story_blueprint` 与 `render_plan` 之间新增 Timeline 数据层。

## 三、最终目标架构

推荐主链路升级为：

```text
scan
  -> media_library.json

plan
  -> story_blueprint.json

timeline-generate / timeline-edit
  -> timeline.json

compile
  -> render_plan.json

preview / render
  -> build_report.json + final mp4
```

各层职责如下：

| 数据层 | 职责 | 用户可编辑 | 渲染直接执行 |
| --- | --- | --- | --- |
| `media_library.json` | 素材事实层 | 否 | 否 |
| `story_blueprint.json` | 叙事结构层 | 部分可编辑 | 否 |
| `timeline.json` | 时间线编辑意图层 | 是 | 否 |
| `render_plan.json` | 渲染执行计划层 | 不建议直接编辑 | 是 |
| `build_report.json` | 执行解释、恢复、诊断 | 否 | 否 |

核心边界：

- `timeline.json` 保存用户编辑意图。
- `render_plan.json` 保存渲染执行细节。
- 用户编辑不应直接修改 `render_plan.segments`。
- `compile` 阶段负责从 timeline 生成或更新 render plan。

## 四、Timeline Schema V1.1

### 4.1 V5Timeline

```ts
interface V5Timeline {
  schema_version: string;
  document_type: "timeline";
  timeline_version: "v1";
  project_ref: V5TimelineProjectRef;
  source_ref: V5TimelineSourceRef;
  tracks: V5TimelineTrack[];
  clip_index: Record<string, V5TimelineClip>;
  dependency_graph?: V5TimelineDependency[];
  invalidation_rules_version?: string;
  performance_policy?: V5TimelinePerformancePolicy;
  metadata?: V5TimelineMetadata;
}
```

说明：

- `schema_version` 跟随现有 V5 项目文档版本。
- `timeline_version` 独立描述 Timeline 层结构演进。
- `tracks` 表达多轨结构。
- `clip_index` 用于稳定查询 clip。
- `dependency_graph` 为局部重算提供依据。
- `performance_policy` 表达 preview/final/cache 约束。

### 4.2 V5TimelineTrack

```ts
type V5TimelineTrackKind =
  | "video"
  | "audio"
  | "title"
  | "subtitle"
  | "overlay";

interface V5TimelineTrack {
  track_id: string;
  kind: V5TimelineTrackKind;
  name: string;
  order_index: number;
  enabled: boolean;
  locked?: boolean;
  lane_mode?: "single" | "stacked";
  clip_ids: string[];
  metadata?: Record<string, unknown>;
}
```

第一阶段至少支持：

- `video`
- `audio`
- `title`

`subtitle` 和 `overlay` 可以先进入 schema，但不要求第一阶段完整 UI。

### 4.3 V5TimelineClip

```ts
type V5TimelineClipKind =
  | "video_asset"
  | "image_asset"
  | "title_card"
  | "chapter_card"
  | "subtitle_overlay"
  | "audio_bgm"
  | "audio_source"
  | "audio_effect";

interface V5TimelineClip {
  clip_id: string;
  kind: V5TimelineClipKind;
  track_id: string;

  timeline_start: number;
  timeline_duration: number;
  timeline_end: number;

  source_in?: number | null;
  source_out?: number | null;
  playback_rate?: number | null;

  enabled: boolean;
  source_ref?: V5TimelineClipSourceRef | null;
  content_ref?: V5TimelineContentRef | null;
  edit_state?: V5TimelineEditState;
  presentation?: V5TimelinePresentation;
  execution?: V5TimelineExecutionHint;
  invalidation_hint?: V5TimelineInvalidationHint;
  cache_policy?: V5TimelineClipCachePolicy;
  metadata?: Record<string, unknown>;
}
```

与 V1.0 相比，本版明确区分：

- `timeline_start / timeline_duration / timeline_end`：clip 在时间线中的位置。
- `source_in / source_out`：clip 在源素材内部的裁剪范围。
- `playback_rate`：为未来变速、慢放、快放预留。

这样可以避免未来实现 `trim / split / ripple edit` 时破坏第一版 schema。

### 4.4 clip_id 稳定规则

`clip_id` 是 Timeline 层最重要的稳定主键，不能简单依赖数组下标。

推荐规则：

1. 第一次生成 timeline 时创建稳定 `clip_id`。
2. 保存 timeline 后，后续编辑必须沿用已有 `clip_id`。
3. 重新从 blueprint/render_plan 生成时，优先通过以下字段匹配旧 clip：
   - `section_id`
   - `asset_id`
   - `segment_id`
   - `kind`
   - `content_ref`
   - occurrence index
4. 匹配不到时才生成新 `clip_id`。
5. 拖拽、禁用、改时长、改标题都不能改变 `clip_id`。

### 4.5 Invalidation Hint

```ts
type V5TimelineRecomputeScope =
  | "none"
  | "preview_only"
  | "clip_only"
  | "track_only"
  | "timeline_compile"
  | "final_render_only"
  | "full_rebuild";

interface V5TimelineInvalidationHint {
  primary_scope: V5TimelineRecomputeScope;
  affected_track_ids?: string[] | null;
  affected_clip_ids?: string[] | null;
  cache_reuse_expected?: boolean | null;
  requires_render_plan_recompile?: boolean;
  requires_audio_relayout?: boolean;
  reason?: string | null;
}
```

第一版规则不追求完美，但必须稳定、可解释、可测试。

推荐最小规则：

| 编辑动作 | Recompute Scope |
| --- | --- |
| 修改标题文字 | `clip_only` |
| 修改标题样式 | `clip_only` |
| 修改字幕文字 | `clip_only` |
| 禁用 / 启用 clip | `timeline_compile` |
| 拖拽排序 | `timeline_compile` |
| 修改图片时长 | `timeline_compile` |
| 修改 BGM 音量 | `track_only` |
| 修改 BGM cue 起止 | `track_only` |
| 修改 preview 分辨率 | `preview_only` |
| 修改输出质量 | `final_render_only` |
| 修改画幅 | `full_rebuild` |

### 4.6 Performance Policy

V1.0 中 `cache_namespace` 是单值，容易造成 preview/final 混淆。本版建议改成策略对象。

```ts
interface V5TimelinePerformancePolicy {
  preview: {
    mode: "proxy" | "low_res" | "original";
    height?: number;
    fps?: number;
    cache_namespace: "preview";
    preferred_backend?: string | null;
  };

  final: {
    uses_original_source: true;
    allow_proxy: false;
    cache_namespace: "final";
    preferred_backend?: string | null;
  };

  thumbnail?: {
    cache_namespace: "thumbnail";
  };

  proxy?: {
    cache_namespace: "proxy";
  };

  cache_fingerprint_version: string;
}
```

硬约束：

- Final Render 必须使用 original source。
- Proxy 只能用于 UI、thumbnail、preview。
- Preview cache 和 Final cache 必须隔离。
- cache fingerprint 不一致时不得复用。

## 五、最终优先级

V1.0 的 P0 范围过大，本版拆成三个阶段。

### P0a：Timeline 数据内核

目标：让 timeline 成为真实数据层。

任务：

- TypeScript 增加 `V5Timeline` 类型。
- Python 增加 timeline 生成模块。
- 支持从 `story_blueprint.json + render_plan.json` 生成 `timeline.json`。
- 前端 store 增加 `v5Timeline`。
- 项目状态支持保存和恢复 timeline。
- 新增 timeline schema smoke test。

验收：

- 能生成 `timeline.json`。
- 至少包含 `video / audio / title` 三类 track。
- 每个 clip 有稳定 `clip_id`。
- clip 能关联 `section_id / asset_id / segment_id`。
- timeline 能保存并恢复。
- 现有 `npm run check` 不退化。

### P0b：性能与画质护栏

目标：在编辑能力落地前，先防止 preview 优化污染 final 质量。

任务：

- 明确 preview/final 分离策略。
- preview cache 和 final cache 分 namespace。
- final render 禁止使用 proxy。
- cache fingerprint 纳入质量、fps、画幅、engine version。
- build_report 增加兼容式性能摘要字段。
- 新增 preview/final cache isolation 测试。

验收：

- Preview 输出不会进入 Final Render。
- Final Render 使用原始素材。
- 不同质量档位不会误复用 cache。
- build_report 能解释 preview/final 差异。

### P0c：最小 Invalidation 与 Report 扩展

目标：先定义最小重算语义，而不是等编辑 UI 做完才补。

任务：

- 增加最小 invalidation rule table。
- 编辑操作能输出 recompute scope。
- build_report 兼容扩展 `recompute_summary`。
- 前端能展示本次操作影响范围。

验收：

- 主要编辑动作都有明确 scope。
- 修改标题不会默认触发 full rebuild。
- 修改音频不会默认触发视觉轨重算。
- report 字段缺失时前端不崩。

## 六、P1：Timeline UI 与基础编辑

P1 的目标是让用户真正感受到“时间线可编辑”，但仍控制能力范围。

任务顺序：

1. 新增只读 Timeline Editor。
2. 用 `v5Timeline.tracks` 替换现有 `render_plan.segments` 展示。
3. 新增 Timeline Inspector。
4. 支持 clip 选中。
5. 支持 clip 禁用 / 启用。
6. 支持标题文字编辑。
7. 支持标题样式编辑。
8. 支持图片 clip 时长编辑。
9. 支持 video track 基础拖拽排序。
10. 支持 BGM cue 可视化和基础参数编辑。

验收：

- RENDER 阶段不再直接以 `render_plan.segments` 作为时间线 UI 数据源。
- 点击 clip 能看到来源素材、章节、segment。
- 禁用 clip 后 compile 不进入 render_plan。
- 修改标题后 preview/final 能体现变化。
- 修改图片时长后总时长正确变化。
- 拖拽过程不触发 compile，拖拽完成后才标记 dirty。
- 100 个 clip 初次渲染不明显卡顿。

## 七、P1 后半：Timeline 到 Render Plan 编译

目标：让 timeline 真正成为 render_plan 的上游。

任务：

- 新增 `compile_from_timeline()`。
- compile 阶段读取 `timeline.json`。
- disabled clip 不进入 render_plan。
- 拖拽顺序影响 `render_plan.segments`。
- duration 修改影响 segment duration。
- title 修改影响 title segment。
- audio cue 修改影响 audio blueprint。
- 输出 `timeline_compile_elapsed_ms`。
- 输出 `recompute_summary`。

验收：

- timeline 编辑后能生成新的 render_plan。
- render_plan 变化符合用户编辑。
- cache 可复用片段不被无意义重算。
- final render 仍使用原始素材。

## 八、P2：成熟增强项

P2 不建议在 P0/P1 稳定前启动。

包括：

- split 分割
- trim 裁剪
- ripple edit
- subtitle track 完整工作流
- SRT 导入导出
- 音频波形
- 音量包络
- effect stack

这些能力价值很高，但会显著增加 schema、UI、compile、cache、preview 的复杂度。

## 九、P3：长期方向

P3 是专业 NLE 方向，不应短期投入过多。

- nested timeline
- adjustment layer
- color pipeline
- LUT
- plugin system
- collaboration
- cloud render
- AI 自动重剪

## 十、建议目录结构

第一阶段不建议大规模搬家，只新增必要结构。

推荐新增：

```text
src/features/timeline/
  TimelineEditor.tsx
  TimelineTrack.tsx
  TimelineClip.tsx
  TimelineInspector.tsx
  timelineOps.ts
  timelineInvalidation.ts

video_engine/
  timeline.py
  timeline_compile.py

tests/
  smoke_v5_timeline_schema.py
  smoke_v5_timeline_generate.py
  smoke_v5_timeline_invalidation.py
  smoke_v5_preview_final_cache_isolation.py
  smoke_v5_final_render_original_source.py
```

注意：

- 不要第一阶段重构整个 `src/App.tsx`。
- 不要一次性迁移所有组件目录。
- Timeline 相关能力可以先局部模块化。

## 十一、Build Report V2 原则

当前项目已经有 build report、recovery summary、fallback、cache stats、backend decision 等能力。

因此 Build Report V2 应该是：

> 兼容扩展，而不是重做一套。

推荐新增字段：

```json
{
  "timeline_summary": {},
  "route_summary": {},
  "fallback_summary": {},
  "cache_summary": {},
  "recompute_summary": {},
  "performance_summary": {},
  "quality_summary": {},
  "recovery_summary": {},
  "migration_notes": []
}
```

前端要求：

- 字段缺失时不崩。
- 老项目 build_report 仍可读取。
- 新字段优先展示，旧字段作为 fallback。

## 十二、测试计划

P0 必须新增：

- `smoke_v5_timeline_schema.py`
- `smoke_v5_timeline_generate.py`
- `smoke_v5_timeline_invalidation.py`
- `smoke_v5_preview_final_cache_isolation.py`
- `smoke_v5_final_render_original_source.py`

P1 必须新增：

- `smoke_v5_timeline_edit_ops.py`
- `smoke_v5_timeline_compile.py`
- `smoke_v5_build_report_v2.py`
- `smoke_v5_project_recovery.py`
- `smoke_v5_schema_migration.py`

覆盖矩阵：

| 测试项 | P0 | P1 | P2 |
| --- | --- | --- | --- |
| timeline schema parse | 必须 | 必须 | 必须 |
| timeline generate | 必须 | 必须 | 必须 |
| clip id stable | 必须 | 必须 | 必须 |
| timeline save/load | 必须 | 必须 | 必须 |
| preview/final cache isolation | 必须 | 必须 | 必须 |
| final render original source | 必须 | 必须 | 必须 |
| invalidation rules | 必须 | 必须 | 必须 |
| readonly timeline UI | 可选 | 必须 | 必须 |
| clip disable | 否 | 必须 | 必须 |
| clip reorder | 否 | 必须 | 必须 |
| duration edit | 否 | 必须 | 必须 |
| split/trim | 否 | 否 | 必须 |

## 十三、风险与控制

### 风险一：P0 过大导致长期无法合并

控制：

- 拆成 P0a / P0b / P0c。
- 每个阶段都能独立验收。
- 先只读，再编辑。

### 风险二：Timeline UI 看起来完成，但底层仍是 render_plan

控制：

- RENDER 阶段 UI 必须改为读取 `v5Timeline.tracks`。
- `render_plan.segments` 只作为执行层数据。

### 风险三：Preview cache 被 Final Render 误用

控制：

- preview/final 分 namespace。
- final 固定 `allow_proxy = false`。
- smoke test 强制覆盖。

### 风险四：clip_id 不稳定导致编辑丢失

控制：

- 不用数组下标做 id。
- 保存后 id 不变。
- 重新生成时先匹配旧 clip。

### 风险五：build_report V2 破坏旧诊断链路

控制：

- 只做兼容扩展。
- 旧字段保留。
- 前端读取容错。

## 十四、最终执行顺序

建议严格按以下顺序推进：

1. `V5Timeline` TypeScript 类型落地。
2. Python `timeline.py` 生成器落地。
3. 从 blueprint/render_plan 生成 `timeline.json`。
4. 前端 store 增加 `v5Timeline`。
5. timeline 保存/恢复。
6. preview/final/cache 画质护栏。
7. 最小 invalidation rule table。
8. 只读 Timeline UI 替换 segments timeline。
9. Timeline Inspector。
10. clip disable / enable。
11. title edit / title style edit。
12. image duration edit。
13. basic reorder。
14. `compile_from_timeline()`。
15. build_report 兼容式 V2 扩展。
16. Render Explainability Panel。
17. Recovery / Migration 闭环增强。
18. Timeline + Performance 专项回归测试补齐。

短期不要先做：

- split
- trim
- ripple edit
- 完整字幕系统
- 音频波形
- effect stack
- 调色
- 插件
- nested timeline

## 十五、最终结论

项目下一阶段最正确的方向不是继续堆更多自动化参数，也不是立刻模仿专业剪辑软件的完整交互，而是先补一层稳定的 Timeline 数据内核。

只要 `timeline.json / v5Timeline` 站稳，后续所有编辑能力都会更可控：

- clip 可以稳定识别
- 用户编辑可以持久化
- render_plan 可以从 timeline 编译
- cache 可以判断是否复用
- preview/final 可以清晰分离
- build_report 可以解释为什么这么渲染
- 失败后可以知道怎么恢复

最终路线是：

> 先让 Timeline 成为真实数据层，再让 UI 可编辑，再让局部重算和渲染解释形成闭环。

这是当前项目从“自动化出片工具”升级为“成熟视频生产系统”的最稳妥路径。
