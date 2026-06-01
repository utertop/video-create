# 时间线数据模型 V1 设计稿

## 目的

这份文档定义项目未来时间线编辑能力的第一版统一数据模型 `timeline_schema_v1`。

它的目标不是立刻替代当前 `story_blueprint.json` 和 `render_plan.json`，而是先解决一个更基础的问题：

- 让“时间线”成为一个真实、稳定、可迁移、可解释的数据层

这样后续无论要做：

- 轻量时间线微调
- 局部重算
- 多轨编辑
- 字幕轨
- 音频包络
- effect stack

都不需要继续把语义散落在：

- `story_blueprint`
- `render_plan.segments`
- `timeline_cues`
- 前端临时状态
- worker 内部隐式规则

相关文档：

- [对标达芬奇路线的 P0 可执行任务清单](./DAVINCI_P0_EXECUTION_TASKLIST.md)
- [对标达芬奇的能力差距表与执行路线图](./DAVINCI_BENCHMARK_GAP_AND_EXECUTION_ROADMAP.md)
- [局部失效与重算规则 V1](./INVALIDATION_AND_RECOMPUTE_RULES.md)
- [模板匹配、AI 配乐蓝图与时间线微调执行清单](./TEMPLATE_MATCHING_BGM_AND_TIMELINE_EXECUTION_PLAN.md)
- [升级与项目迁移指南](./UPGRADE_AND_MIGRATION_GUIDE.md)

---

## 一、设计目标

`timeline_schema_v1` 第一阶段要满足这几件事：

1. 能稳定表达 `video / audio / title` 三类 track
2. 能把一个项目拆成有稳定 id 的 clip 集合
3. 能表达 clip 来源、编辑状态、依赖关系和失效提示
4. 能与当前 `story_blueprint` 和 `render_plan` 双向关联
5. 能为局部重算和未来时间线 UI 提供基础

第一版不追求：

- 完整多轨专业编辑器能力
- effect stack 全量落地
- 调色节点
- nested timeline / compound clip 完整实现
- 实时逐帧协同渲染

也就是说，这一版是“专业时间线内核的骨架”，不是“专业时间线编辑器的全部”。

---

## 二、当前问题

当前项目已经有很多接近时间线的信息，但它们分散在不同层里：

- `story_blueprint.sections`
- `section.asset_refs`
- `render_plan.segments`
- `render_settings.audio_blueprint.timeline_cues`
- 标题和字幕相关字段
- 前端局部编辑状态

这些结构在“自动化生成”阶段够用，但在“编辑”和“局部重算”阶段存在明显缺口：

### 1. 缺统一 clip 标识

现在有 `section_id`、`asset_id`、`segment_id`，但没有统一时间线 clip id。

### 2. 缺统一 track 抽象

视频、音频、标题、overlay 现在都更像不同分支逻辑，而不是同一时间线里的不同轨道。

### 3. 缺依赖图

当前不容易稳定回答：

- 这个标题段依赖哪个 section
- 这个 overlay 跟哪个主视频片段绑定
- 这个音频 cue 是依附 section 还是依附时间区间

### 4. 缺局部失效语义

当前不容易明确判断：

- 改标题文字，是只重做 title clip，还是要重编译 section
- 改 BGM 入点，是只动 audio track，还是要重出整段 preview
- 改片段顺序，哪些 cache 还能复用

所以第一版 schema 的意义，不只是“把字段排整齐”，而是把这些行为语义正式化。

---

## 三、总体原则

### 1. 不推翻现有主链

当前仍保留：

- `scan -> media_library.json`
- `plan -> story_blueprint.json`
- `compile -> render_plan.json`
- `render -> final mp4`

`timeline_schema_v1` 不替代这个主链，而是插在：

- `story_blueprint`
- `render_plan`

之间，先成为“结构化可编辑层”。

### 2. 时间线先做“中间真相层”

建议把时间线视为：

- 比 `story_blueprint` 更接近执行
- 比 `render_plan` 更适合编辑

也就是：

- `story_blueprint` 负责“叙事结构”
- `timeline` 负责“可编辑排列与依赖关系”
- `render_plan` 负责“渲染执行描述”

### 3. 第一版优先非破坏编辑

第一版所有时间线编辑都应该是非破坏的：

- 不修改原素材
- 尽量不直接重写 scan 结果
- 所有人工调整都以 timeline edit 或 override 形式记录

### 4. 可迁移优先于炫技

第一版 schema 必须从一开始就考虑：

- version
- migration
- backward compatibility
- invalidation hints

---

## 四、文档定位关系

建议未来项目文档层次变成：

### 1. `media_library.json`

表达：

- 素材库事实
- 扫描结果
- 目录结构
- 素材属性

### 2. `story_blueprint.json`

表达：

- 叙事结构
- 章节组织
- 标题与章节级建议
- 音频蓝图建议

### 3. `timeline.json` 或内嵌 `timeline_schema_v1`

表达：

- 可编辑 clip 列表
- track 排布
- clip 依赖关系
- 用户 override
- invalidation hints

### 4. `render_plan.json`

表达：

- 最终执行用的渲染片段与参数
- scheduler
- cache policy
- backend route

第一阶段可以先不单独落一个物理文件，而是：

- 先定义 schema
- 再决定落到 `story_blueprint.metadata.timeline` 还是 `render_plan.metadata.timeline`
- 最终成熟后再独立成 `timeline.json`

---

## 五、核心结构

下面是推荐的第一版核心结构。

## 1. `V5Timeline`

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
  metadata?: V5TimelineMetadata;
}
```

### 设计说明

- `schema_version` 走现有 V5 迁移体系
- `timeline_version` 单独标记时间线层自己的演进版本
- `project_ref` 用于关联当前项目
- `source_ref` 用于关联 blueprint / render_plan / library
- `tracks` 是主要内容
- `clip_index` 用于快速查询 clip
- `dependency_graph` 让局部重算有稳定依据

## 2. `V5TimelineTrack`

```ts
type V5TimelineTrackKind = "video" | "audio" | "title" | "subtitle" | "overlay";

interface V5TimelineTrack {
  track_id: string;
  kind: V5TimelineTrackKind;
  name: string;
  order_index: number;
  enabled: boolean;
  locked?: boolean;
  lane_mode?: "single" | "stacked";
  clip_ids: string[];
  metadata?: {
    generated?: boolean;
    user_created?: boolean;
    source?: string | null;
  };
}
```

### 第一版建议最少支持

- `video`
- `audio`
- `title`

`subtitle` 和 `overlay` 可以先允许 schema 表达，但第一阶段不要求完整 UI。

## 3. `V5TimelineClip`

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
  start_time: number;
  end_time: number;
  duration: number;
  enabled: boolean;
  source_ref?: V5TimelineClipSourceRef | null;
  content_ref?: V5TimelineContentRef | null;
  edit_state?: V5TimelineEditState;
  presentation?: V5TimelinePresentation;
  execution?: V5TimelineExecutionHint;
  invalidation_hint?: V5TimelineInvalidationHint;
  metadata?: Record<string, unknown>;
}
```

### 设计说明

- `clip_id` 是未来时间线层最重要的稳定主键
- `source_ref` 关联 asset、section、segment 等原始来源
- `content_ref` 表达这段 clip 的“内容身份”
- `edit_state` 表达用户是否改过
- `presentation` 表达标题/字幕/视觉表现
- `execution` 表达与 route、cache、preview 有关的执行提示
- `invalidation_hint` 是局部重算入口

## 4. `V5TimelineDependency`

```ts
type V5TimelineDependencyKind =
  | "derived_from_section"
  | "derived_from_asset"
  | "overlay_of"
  | "audio_sync_to"
  | "paired_with"
  | "generated_from_template";

interface V5TimelineDependency {
  dependency_id: string;
  from_clip_id: string;
  to_clip_id?: string | null;
  kind: V5TimelineDependencyKind;
  source_section_id?: string | null;
  source_asset_id?: string | null;
  strict: boolean;
  reason?: string | null;
}
```

### 第一版的意义

第一版不要求做复杂图算法，但必须能表达：

- 某个字幕 clip 依赖某个视频 clip
- 某个章节卡来源于某个 section
- 某个 BGM cue 跟某个 section/time range 对齐

## 5. `V5TimelineInvalidationHint`

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

这不是最终调度结果，而是时间线层给上层系统的稳定提示。

---

## 六、辅助结构

## 1. `V5TimelineProjectRef`

```ts
interface V5TimelineProjectRef {
  project_id?: string | null;
  project_dir?: string | null;
  title?: string | null;
}
```

## 2. `V5TimelineSourceRef`

```ts
interface V5TimelineSourceRef {
  media_library_path?: string | null;
  story_blueprint_path?: string | null;
  render_plan_path?: string | null;
  generated_from_blueprint: boolean;
  generated_at?: string | null;
}
```

## 3. `V5TimelineClipSourceRef`

```ts
interface V5TimelineClipSourceRef {
  section_id?: string | null;
  asset_id?: string | null;
  segment_id?: string | null;
  directory_node_id?: string | null;
}
```

## 4. `V5TimelineContentRef`

```ts
interface V5TimelineContentRef {
  source_path?: string | null;
  title_text?: string | null;
  subtitle_text?: string | null;
  audio_profile?: string | null;
  template_id?: string | null;
}
```

## 5. `V5TimelineEditState`

```ts
interface V5TimelineEditState {
  auto_generated: boolean;
  user_overridden: boolean;
  override_fields?: string[] | null;
  origin?: "plan" | "timeline_edit" | "migration" | "recovery" | string;
  last_edited_at?: string | null;
}
```

## 6. `V5TimelinePresentation`

```ts
interface V5TimelinePresentation {
  title_style?: V5TitleStyle | null;
  transition_type?: string | null;
  transition_duration?: number | null;
  motion_config?: Record<string, unknown> | null;
  background_mode?: string | null;
  background_source_path?: string | null;
}
```

## 7. `V5TimelineExecutionHint`

```ts
interface V5TimelineExecutionHint {
  preferred_route?: string | null;
  route_reason?: string | null;
  cache_key?: string | null;
  preview_supported?: boolean | null;
  final_render_supported?: boolean | null;
}

interface V5TimelineMetadata {
  created_at?: string | null;
  updated_at?: string | null;
  generated_from?: "blueprint" | "migration" | "recovery" | string;
  editor_mode?: "auto" | "guided" | "manual" | string;
  migration_notes?: string[] | null;
}
```

---

## 七、推荐的最小轨道布局

第一版推荐最小布局如下：

### Track A: `video`

承载：

- 图片段
- 视频段
- 章节卡
- 片头片尾卡

### Track B: `title`

承载：

- overlay title
- chapter title overlay
- 未来 lower-third

### Track C: `audio`

承载：

- BGM
- 原视频音频
- 未来音效片段

这样设计的原因是：

- 先让语义清楚
- 暂时不强求完整多轨交叉编辑
- 但为未来 `subtitle`、`overlay`、更多 audio lane 留空间

---

## 八、与现有文档的映射关系

## 1. 从 `story_blueprint` 到 `timeline`

映射建议：

- `section_id` -> `source_ref.section_id`
- `asset_refs` -> 初始 clip 候选
- `title/subtitle/title_style` -> title 或 chapter card clip 的 `content_ref/presentation`
- `audio_blueprint.section_cues` -> audio track clip 或 cue 片段

## 2. 从 `timeline` 到 `render_plan`

映射建议：

- timeline 中每个启用 clip 生成一个或多个 `render_plan.segments`
- 依赖关系决定 overlay/title/audio 的拼接顺序
- `execution.preferred_route` 进入 `render_route` 候选
- `invalidation_hint` 不直接写进最终渲染片段，但用于 compile/recompute 决策

## 3. 与 `render_plan.segments` 的边界

`render_plan.segments` 继续承担：

- 渲染执行
- scheduler
- route 统计
- cache policy

而 `timeline` 更适合承担：

- 编辑意图
- 结构化依赖
- 人工 override
- 局部重算提示

---

## 九、最小 JSON 示例

```json
{
  "schema_version": "5.5",
  "document_type": "timeline",
  "timeline_version": "v1",
  "project_ref": {
    "project_dir": "D:\\Automatic\\video_create\\example\\.video_create_project",
    "title": "旅行相册"
  },
  "source_ref": {
    "media_library_path": "media_library.json",
    "story_blueprint_path": "story_blueprint.json",
    "generated_from_blueprint": true,
    "generated_at": "2026-06-01T10:00:00Z"
  },
  "tracks": [
    {
      "track_id": "track_video_1",
      "kind": "video",
      "name": "主画面",
      "order_index": 0,
      "enabled": true,
      "clip_ids": ["clip_title_1", "clip_video_1", "clip_video_2"]
    },
    {
      "track_id": "track_audio_1",
      "kind": "audio",
      "name": "主音频",
      "order_index": 1,
      "enabled": true,
      "clip_ids": ["clip_bgm_1"]
    }
  ],
  "clip_index": {
    "clip_video_1": {
      "clip_id": "clip_video_1",
      "kind": "image_asset",
      "track_id": "track_video_1",
      "start_time": 3.0,
      "end_time": 7.0,
      "duration": 4.0,
      "enabled": true,
      "source_ref": {
        "section_id": "section_city_01",
        "asset_id": "asset_img_001"
      },
      "edit_state": {
        "auto_generated": true,
        "user_overridden": false,
        "origin": "plan"
      },
      "invalidation_hint": {
        "primary_scope": "clip_only",
        "cache_reuse_expected": true,
        "requires_render_plan_recompile": false
      }
    }
  }
}
```

第一版可以允许：

- `tracks` 保存完整对象
- `clip_index` 保存 clip 对象

而不是强制同时维护额外的 `clips[]` 数组，避免第一版状态同步复杂度过高。

---

## 十、第一版必须支持的编辑语义

为了让 schema 真正有用，第一版至少要能表达下面这些编辑：

### 1. 调整 clip 顺序

- 改动 `track.clip_ids` 顺序
- 不修改素材库事实

### 2. 禁用单个 clip

- 改 `clip.enabled`
- 让 compile 层决定是否跳过

### 3. 修改标题和字幕

- 改 `content_ref.title_text`
- 改 `content_ref.subtitle_text`
- 设置 `edit_state.user_overridden = true`

### 4. 修改标题样式

- 改 `presentation.title_style`

### 5. 修改单段时长

- 改 `start_time/end_time/duration`
- 同时写入 `invalidation_hint`

### 6. 修改 BGM cue 或音频布局

- 改 audio track clip 范围或 metadata

这些都是未来轻量时间线微调最先需要的语义。

---

## 十一、局部失效建议

`timeline_schema_v1` 本身不负责真正执行重算，但应提供稳定提示。

第一版建议约定：

### 1. 文字改动

- `primary_scope = clip_only`
- 通常可复用大部分视觉缓存

### 2. 样式改动

- 章节卡/overlay 改动通常 `clip_only`
- 但若影响跨段 overlay，可提升到 `track_only`

### 3. 顺序改动

- 视觉顺序变化通常至少 `timeline_compile`
- 不一定需要全部 final render 失效

### 4. 音频改动

- 仅改 BGM 节点时优先 `track_only`
- 不应默认触发视觉轨重算

### 5. 输出档位改动

- 仅改 preview/final 参数时可标为 `preview_only` 或 `final_render_only`

这一部分后续会和 `INVALIDATION_AND_RECOMPUTE_RULES.md` 联动细化。

---

## 十二、迁移策略

第一版 schema 从设计之初就需要纳入迁移体系。

### 1. 版本字段

建议同时保留：

- `schema_version`
- `timeline_version`

前者走项目文档大版本兼容；
后者走时间线层自己的结构演进。

### 2. 迁移来源

第一批 timeline 主要会从：

- `story_blueprint.json`
- `render_plan.json`
- `project_state.json`

自动生成。

### 3. 迁移记录

每次迁移建议输出：

- `generated_from_blueprint`
- `migration_notes`
- `origin`

### 4. 失败处理

如果 timeline 生成失败，不应阻断现有主链：

- 先允许继续使用旧 `story_blueprint -> render_plan` 流程
- 但要写明 timeline 生成失败原因

也就是说，timeline 第一阶段应是“增强层”，不是“硬阻断层”。

---

## 十三、对代码层的建议落点

## TypeScript

建议新增类型位置：

- [src/lib/engine.ts](D:/Automatic/video_create/src/lib/engine.ts:25)

建议第一批新增：

- `V5Timeline`
- `V5TimelineTrack`
- `V5TimelineClip`
- `V5TimelineDependency`
- `V5TimelineInvalidationHint`

## Python

建议第一批落点：

- [video_engine_v5.py](D:/Automatic/video_create/video_engine_v5.py:2955)

先做：

- timeline 生成草案函数
- blueprint -> timeline 映射函数
- timeline -> render_plan 的保守映射接口

第一阶段不要求完全把渲染执行建立在 timeline 上。

## Rust / Tauri

建议后续落点：

- [src-tauri/src/lib.rs](D:/Automatic/video_create/src-tauri/src/lib.rs:3130)

后续需要补：

- timeline migration
- timeline summary 读取
- timeline 与 project_state 联动恢复

---

## 十四、明确不做的事

第一版 schema 明确不做：

- 不引入实时播放引擎
- 不引入复杂 effect node graph
- 不做颜色管理结构
- 不直接替代 `render_plan`
- 不一次性覆盖所有未来轨道类型

这样做是为了让第一版尽快可落地，而不是把 schema 本身做成一个巨型设计工程。

---

## 十五、验收标准

`timeline_schema_v1` 可以视为完成设计的最低标准是：

1. 已有正式文档定义结构、边界和术语
2. 已明确与 `story_blueprint`、`render_plan` 的关系
3. 已定义最小 track/clip/dependency/invalidation 结构
4. 已给出最小 JSON 示例
5. 已明确迁移思路和第一批代码落点
6. 已能支撑后续 `Task 2` 的局部失效规则设计

---

## 十六、结论

`timeline_schema_v1` 的价值，不在于它马上让界面变得更像专业剪辑器，而在于它给未来所有“更像专业剪辑器”的能力准备了稳定底座。

如果没有这层底座，后面的时间线 UI、字幕轨、音频包络、多轨编辑都会越来越像“界面升级”，而不是“架构升级”。

反过来，只要这层 schema 先站稳，后续每一步编辑能力扩展都会更可控，也更容易做成真正的非破坏、可恢复、可解释系统。
