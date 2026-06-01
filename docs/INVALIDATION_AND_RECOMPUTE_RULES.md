# 局部失效与重算规则 V1

## 目的

这份文档定义项目当前阶段的第一版“局部失效与重算规则”。

它要解决的问题不是“渲染调度选哪条路径”，而是：

- 当用户改了某些内容时，到底应该重新算什么
- 哪些缓存还可以复用
- 什么时候只需要重做 preview
- 什么时候必须重编译 `render_plan`
- 什么时候才真的需要整条 final render 失效

这份规则与 [TIMELINE_SCHEMA_V1.md](./TIMELINE_SCHEMA_V1.md) 配套使用：

- `timeline schema` 定义结构
- 本文定义改动后的失效边界

相关文档：

- [对标达芬奇路线的 P0 可执行任务清单](./DAVINCI_P0_EXECUTION_TASKLIST.md)
- [时间线数据模型 V1 设计稿](./TIMELINE_SCHEMA_V1.md)
- [渲染调度策略](./RENDER_SCHEDULER_STRATEGY.md)
- [视频生成性能与稳定性优化方案](./VIDEO_RENDER_PERFORMANCE_STRATEGY.md)

---

## 一、文档范围

当前 V1 规则优先覆盖：

1. 标题、字幕、章节卡修改
2. 单段顺序与启用状态修改
3. 单段视觉参数修改
4. 音频蓝图与音频参数修改
5. preview / final 导出参数修改
6. 素材变更与项目迁移导致的失效

第一版不试图覆盖：

- effect stack 全量失效规则
- nested timeline / compound clip
- 多后端并行执行的全部边界
- 调色链路

---

## 二、核心原则

### 1. 先缩小失效范围，再决定执行路径

本规则关注的是“需要失效什么”，不是“具体怎么渲染”。

也就是说：

- 先判断 `clip_only / track_only / timeline_compile / full_rebuild`
- 再由调度与 backend 选择层决定是否走 FFmpeg、stable renderer 或 MoviePy fallback

### 2. 内容变化和导出参数变化要分开

不是所有改动都等价：

- 改标题文字，是内容变化
- 改 preview 高度，是执行参数变化
- 改 chunk 秒数，是执行策略变化

这三者不应一律触发同样的失效范围。

### 3. 音频改动不默认拖累视觉轨

后续时间线成熟后，必须逐步接近这样的行为：

- 改音乐，不默认让画面全量重算
- 改 BGM 节点，不默认让标题卡和图片段都失效

### 4. 预览与正式导出允许不同失效层级

某些改动只需要先重做 preview，不一定立刻让 final render 全量失效。

### 5. 无法精确判断时，宁可保守扩大一档

第一版规则应优先可信，不追求激进最小化。

例如：

- 如果某种转场跨两个 clip 且实现层还不稳定
- 那就先从 `clip_only` 提升到 `timeline_compile`

---

## 三、统一术语

建议后续前后端、日志、诊断包统一使用下面这组术语。

### 1. 失效层级

```text
none
preview_only
clip_only
track_only
timeline_compile
final_render_only
full_rebuild
```

### 2. 术语含义

#### `none`

没有实际内容变化，不应触发任何重算。

#### `preview_only`

只需要更新当前预览结果，不要求重编译 timeline 或 `render_plan`。

#### `clip_only`

只失效一个 clip，理论上可复用同 track 大部分其他 clip。

#### `track_only`

只失效一条 track，例如音频轨，其他轨尽量不动。

#### `timeline_compile`

需要重新从 timeline 生成 `render_plan` 或局部编排结果，但不等于素材缓存全部失效。

#### `final_render_only`

内容结构不变，但正式导出结果需要重新生成，例如输出编码参数变化。

#### `full_rebuild`

需要视为项目结构性变化，相关缓存、计划和最终输出都应重新检查。

---

## 四、失效判断分层

建议把所有改动先归入这四层语义，再映射到最终失效等级。

### 1. 结构层改动

例如：

- 调整 clip 顺序
- 启用/禁用 clip
- 修改章节边界
- 改 section 到 asset 的组织关系

通常至少是：

- `timeline_compile`

### 2. 内容层改动

例如：

- 改标题文字
- 改字幕内容
- 改背景图
- 改某段的显示时长

通常落在：

- `clip_only`
- 或保守提升到 `timeline_compile`

### 3. 表现层改动

例如：

- 改 `title_style`
- 改转场类型
- 改 motion 配置
- 改 BGM 混音包络

通常落在：

- `clip_only`
- `track_only`
- `timeline_compile`

### 4. 执行层改动

例如：

- 改 preview 高度
- 改质量档位
- 改硬件编码器
- 改 chunk 秒数

通常落在：

- `preview_only`
- `final_render_only`
- 或保守提升到 `timeline_compile`

---

## 五、V1 规则总表

| 改动类型 | 例子 | 推荐失效层级 | 是否需要重编译 `render_plan` | 视觉缓存是否可复用 | 音频缓存是否可复用 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| 无内容变化 | 只是重新打开项目 | `none` | 否 | 是 | 是 | 仅恢复状态 |
| 只切换当前预览播放位置 | 在 UI 里切换看片位置 | `preview_only` | 否 | 是 | 是 | 不应触发编译 |
| 修改标题文字 | 改章节标题主文本 | `clip_only` | 否，第一版可保守为否 | 大多可复用 | 是 | 主要失效标题或 overlay clip |
| 修改副标题 | 改 `subtitle` | `clip_only` | 否，必要时保守提升 | 大多可复用 | 是 | 与标题文字类似 |
| 修改标题样式 | 改 `title_style.preset/motion` | `clip_only` | 否，跨段 overlay 时可提升 | 相关文字缓存失效 | 是 | 不应默认全量失效 |
| 修改章节背景图 | 改 `background.custom_path` | `clip_only` | 否，跨段 bridge 时可提升 | 相关背景缓存失效 | 是 | 只影响相关 section |
| 启用/禁用单个 clip | 关掉一个素材段 | `timeline_compile` | 是 | 部分可复用 | 是 | 因为前后时序变化 |
| 调整单个 clip 顺序 | 拖动素材顺序 | `timeline_compile` | 是 | 邻近 clip 可复用视实现 | 是 | 时序变化影响 segment 排列 |
| 调整单段时长 | 改 `custom_duration` | `timeline_compile` | 是 | 原素材缓存常可复用 | 是 | 但 segment 边界会变 |
| 修改转场类型 | `cut -> soft_crossfade` | `timeline_compile` | 是 | 部分缓存失效 | 是 | 相邻段关系发生变化 |
| 修改转场时长 | `0.2s -> 0.8s` | `timeline_compile` | 是 | 部分缓存失效 | 是 | 至少相邻段受影响 |
| 修改图片 motion | `soft_zoom -> none` | `clip_only` | 否，第一版可保守提升为 `timeline_compile` | 图片段缓存可能失效 | 是 | 如果 motion 已入 cache key，则只需局部 |
| 修改视频 motion | `still_hold -> gentle_push` | `clip_only` 或 `timeline_compile` | 视路由实现而定 | fitted/motion cache 可能失效 | 是 | 第一版建议保守升到 `timeline_compile` |
| 修改 overlay 文案 | 视频上的 overlay title | `clip_only` | 否，跨段覆盖时可提升 | overlay 缓存失效 | 是 | 不应拖累音频 |
| 修改 BGM 音量 | `bgm_volume` | `track_only` | 否 | 是 | 否 | 只影响音频轨 |
| 修改原声音量 | `source_audio_volume` | `track_only` | 否 | 是 | 否 | 不该拖累视觉轨 |
| 修改 ducking | `auto_ducking` 或强度 | `track_only` | 否 | 是 | 否 | 音频重新布局 |
| 修改音乐入点/出点 | 调整 cue | `track_only` | 否，必要时可重编译音频布局 | 是 | 否 | 只动音频时间线 |
| 修改音乐素材 | 切换 BGM 文件 | `track_only` | 否 | 是 | 否 | 音频缓存大概率失效 |
| 修改 preview 高度 | `preview_height` | `preview_only` | 否 | preview 缓存可能失效 | 是 | 不应连带 final 失效 |
| 修改 preview 开关 | preview -> final | `final_render_only` | 否 | preview/final 各自判断 | preview 可复用部分音频中间结果 | 内容未改，只是导出目标不同 |
| 修改质量档位 | `draft -> high` | `final_render_only` | 否，若影响 route 可提升 | 部分执行缓存失效 | 部分失效 | 若 cache key 绑定质量，需重出 final |
| 修改性能档位 | `stable -> balanced` | `timeline_compile` | 是，保守处理 | 部分缓存可复用 | 部分可复用 | 因为 route 和 chunk 可能变化 |
| 修改硬件编码器 | `auto -> nvenc` | `final_render_only` | 否 | 是 | 是 | 主要影响输出执行层 |
| 修改 chunk 秒数 | `120 -> 180` | `timeline_compile` | 是 | segment 缓存可复用，chunk 缓存常失效 | 是 | chunk 组织会变化 |
| 修改 render backend 选择 | `auto -> ffmpeg_concat` | `timeline_compile` 或 `final_render_only` | 取决于是否重排 route | 视 backend 而定 | 视 backend 而定 | 第一版建议保守用 `timeline_compile` |
| 素材文件 mtime/size 改变 | 用户替换原素材 | `full_rebuild` | 是 | 相关素材缓存失效 | 相关音频缓存失效 | 需要重新验证源事实 |
| 素材路径丢失/重连 | 重新定位缺失素材 | `full_rebuild` | 是 | 路径相关缓存需重检 | 需重检 | 至少触发健康检查与重编译 |
| 项目 schema migration | 升级老项目 | `full_rebuild` | 是 | 尽量保留素材缓存 | 尽量保留 | 迁移后必须重新核对 |

---

## 六、第一版推荐的保守边界

为了让 V1 先可信，下面这些场景建议一律保守扩大一级：

### 1. 跨段关系不稳定的转场

例如：

- 非直切
- 有 overlap
- 会改变相邻段边界

建议：

- 统一按 `timeline_compile`

### 2. 视频 motion 会改变 route 的场景

如果视频段从：

- `video_fit`

切到：

- `video_motion_fit`
- 或 `moviepy_required`

建议：

- 先按 `timeline_compile`

### 3. 依赖 bridge 背景或前后帧的章节卡

例如：

- `auto_bridge`
- 依赖前段最后一帧和后段第一帧

建议：

- 如果上游段变了，相关章节卡也至少 `clip_only`
- 若边界关系变了，提升到 `timeline_compile`

### 4. 音频蓝图重新生成

如果不是单纯调音量，而是：

- 重新应用 `audio_blueprint`
- 改了章节 cue 结构

建议：

- 按 `track_only`
- 若 cue 影响标题显示或节奏结构，提升到 `timeline_compile`

---

## 七、与 cache 的关系

局部失效不等于缓存全部作废。

建议把两层语义分开：

### 1. 失效范围

回答：

- 需要重新算哪些逻辑单元

### 2. 缓存复用

回答：

- 被重新算的逻辑单元里，哪些底层结果还能复用

例如：

- 调整单段时长可能是 `timeline_compile`
- 但底层图片 EXIF 缓存、视频 fitted cache、音频归一化缓存仍可复用

### 第一版缓存判断建议

#### 大概率可继续复用

- scan proxy
- thumbnail
- 图片基础修正缓存
- 视频 fitted 基础缓存
- 音频 normalize 缓存

#### 需要重新判断

- chunk cache
- title overlay 缓存
- 章节背景桥接缓存
- build report summary

#### 大概率失效

- 与 `transition_config / motion_config / rhythm_config / keep_audio / python_quality` 强绑定的 chunk 结果

这也与现有性能文档中已经写入 cache key 的策略保持一致。

---

## 八、与 preview / final 的关系

V1 规则建议明确：

### 1. preview 是独立失效面

以下改动通常只需要：

- `preview_only`

例如：

- 改 preview 高度
- 改当前预览段
- 切换预览播放范围

### 2. final export 不等于必须重编译

以下改动通常是：

- `final_render_only`

例如：

- 改编码器
- 改导出质量
- 改封装层参数

### 3. 当执行策略变化影响 route 时，再提升

例如：

- 改性能档位
- 改 chunk 秒数
- 改 backend 偏好

这类改动更容易影响：

- runtime route
- chunk 组织
- fallback 行为

因此第一版建议保守提升到：

- `timeline_compile`

---

## 九、与 `timeline_schema_v1` 的映射

建议每个 `V5TimelineClip` 都允许携带：

```ts
invalidation_hint?: {
  primary_scope: V5TimelineRecomputeScope;
  affected_track_ids?: string[] | null;
  affected_clip_ids?: string[] | null;
  cache_reuse_expected?: boolean | null;
  requires_render_plan_recompile?: boolean;
  requires_audio_relayout?: boolean;
  reason?: string | null;
}
```

但要注意：

- `timeline schema` 存的是“静态提示”
- 真正执行时仍由当前参数、调度和 backend 选择层做最终判断

也就是说：

- schema 负责可解释
- runtime 负责最终执行

---

## 十、建议优先接入的代码位置

第一阶段不要求立即全部实现，但建议后续实现时优先从这些位置接：

### 文档与类型层

- [TIMELINE_SCHEMA_V1.md](D:/Automatic/video_create/docs/TIMELINE_SCHEMA_V1.md:1)
- [src/lib/engine.ts](D:/Automatic/video_create/src/lib/engine.ts:240)

### 编译层

- [video_engine_v5.py](D:/Automatic/video_create/video_engine_v5.py:2955)
- [src/App.tsx](D:/Automatic/video_create/src/App.tsx:1895)

### 调度与执行层

- [video_engine_v5.py](D:/Automatic/video_create/video_engine_v5.py:4045)
- [video_engine_v5.py](D:/Automatic/video_create/video_engine_v5.py:6773)

### UI 与解释层

- [src/App.tsx](D:/Automatic/video_create/src/App.tsx:2419)
- [src/App.tsx](D:/Automatic/video_create/src/App.tsx:3362)
- [src/lib/progress.ts](D:/Automatic/video_create/src/lib/progress.ts:214)

---

## 十一、第一批建议进入测试的规则

建议优先把下面这些规则做成 regression case：

1. 修改标题文字
目标：只失效标题相关 clip，不影响音频缓存。

2. 修改单段顺序
目标：触发 `timeline_compile`，但不要求 scan cache 全失效。

3. 修改 BGM 音量
目标：只失效音频轨，不影响视觉轨。

4. 修改 preview 高度
目标：只触发 `preview_only`。

5. 修改 chunk 秒数
目标：触发 `timeline_compile`，chunk cache 重建，但素材基础缓存保留。

6. 素材文件被替换
目标：触发 `full_rebuild`。

7. 项目 migration 后恢复
目标：至少触发重新核对和重编译，不静默沿用不可信旧输出。

---

## 十二、第一版不该做的事

当前不建议在这份规则里直接做：

- 过细的 GPU 资源失效判断
- effect stack 节点级失效
- 实时播放引擎帧级失效
- 跨 backend 的所有特例表

这些内容应该在 P1/P2 再逐步加。

---

## 十三、验收标准

这份规则文档达到可执行基线的标准是：

1. 已定义统一失效层级
2. 已覆盖至少 `20+` 类常见改动
3. 已明确 preview、audio、timeline、final export 的不同边界
4. 已说明和缓存复用不是同一概念
5. 已说明和 `timeline_schema_v1` 的关系
6. 已给出第一批代码接入点和测试建议

---

## 十四、结论

局部失效规则的价值，不在于第一天就做到最细，而在于先让系统停止“改一点就全部重来”的思维方式。

只要 V1 先把：

- 术语
- 失效层级
- 常见编辑操作边界
- preview / final 区分
- 音频与视觉分轨原则

这些事情定下来，后续无论做时间线 UI、局部重算还是更细的缓存策略，都会有一套统一的判断基线。
