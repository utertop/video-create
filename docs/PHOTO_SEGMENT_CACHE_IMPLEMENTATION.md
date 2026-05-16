# Video Create Studio V5 照片段专项缓存与预烘焙实施方案

## 1. 目标

这份文档是 `docs/RENDER_ENGINE_GAP_AND_ROADMAP.md` 中 P1 的落地实施版。

目标不是抽象讨论，而是明确：

- 当前照片段已经缓存了什么
- 还缺哪一层缓存
- 第一轮代码应该怎么做
- 如何验证它真的提升了长视频场景

本轮聚焦的问题是：

- 长视频中有大量照片时，正式渲染耗时明显偏长
- 同一张照片在相同参数下，仍可能重复走“修正 -> 缩放 -> 模糊背景 -> 动效 -> 合成”
- 当前已经有素材级缓存，但还缺“照片段级缓存”

## 2. 当前已有基础

当前项目已经具备以下照片相关缓存能力：

- `fixed_images`
  - 作用：缓存 EXIF 修正和 RGB 化后的图片
- `blur_backgrounds`
  - 作用：缓存补边模糊背景图
- `video_frames`
  - 作用：缓存视频中间帧
- `text_frames`
  - 作用：缓存标题卡背景帧

这些已经很好，但仍然停留在“素材预处理级别”。

缺失的是：

- 把“一个完整照片段”直接缓存为可复用的短视频片段

也就是说，当前虽然不会每次都重新读原图和重新做背景模糊，但还是会在渲染阶段反复创建：

- `ImageClip`
- `CompositeVideoClip`
- 轻微运动
- 最终帧写出

这在长视频里会累计成明显开销。

## 3. 新增能力：照片段级预烘焙

### 3.1 核心思路

把这类段：

- `type = image`
- 无额外复杂叠加
- 只有标准背景补边和轻量 motion

直接预烘焙成缓存 `.mp4`。

后续再次渲染时：

- 不再重新构建 `ImageClip + CompositeVideoClip`
- 直接 `VideoFileClip(cache.mp4)` 复用

### 3.2 这层缓存解决什么

它解决的是“照片段重复渲染”问题，而不是“素材预处理”问题。

前后层级应当这样理解：

- 素材级缓存：
  - 修正原图
  - 生成模糊背景
- 段级缓存：
  - 在给定分辨率、时长、motion、fps 下，直接缓存最终照片段视频

## 4. 第一轮实施范围

为了控制风险，第一轮只做下面这类照片段：

- 普通 `image` 段
- 无音频
- 使用现有 `_compose_with_blur_bg`
- 使用现有轻量 motion：
  - `none`
  - `still_hold`
  - `gentle_push`
  - `slow_push`
  - `ken_burns`
  - `subtle_ken_burns`
  - `punch_zoom`
  - `micro_zoom`

第一轮不处理：

- 带复杂文字叠加的照片段
- 章节文字卡
- 多层特效
- 更高级的转场预烘焙

## 5. 缓存 key 设计

照片段缓存 key 必须绑定：

- 源图片路径
- 文件大小
- mtime
- 目标分辨率
- 时长
- fps
- motion_config
- 引擎版本

这样保证：

- 同图不同运动不会误复用
- 同图不同分辨率不会误复用
- 素材变了会自动失效

## 6. 触发策略

第一轮建议只在这些场景优先启用：

- `performance_mode = stable`
- 或 `render_mode = long_stable`
- 或总时长 >= 600 秒
- 或 segment 数量 >= 80

理由：

- 这些正是照片段累计成本最明显的场景
- 避免短视频首次生成时，为了缓存反而增加额外等待

后续如果验证效果稳定，再考虑扩大到更多中型项目。

## 7. 技术实现步骤

### Step 1. 增加照片段预烘焙判断

新增类似：

- `_should_prerender_image_segment()`

判断当前项目是否值得把照片段先烘焙成缓存视频。

### Step 2. 增加照片段缓存路径

新增 cache bucket：

- `.video_create_project/render_cache/photo_segments`

用于存储照片段缓存视频。

### Step 3. 增加照片段预烘焙函数

新增类似：

- `_prerender_image_segment()`

内部流程：

1. 基于 `fixed_images + blur_backgrounds` 构建照片段
2. 应用轻量 motion
3. 写出缓存 mp4
4. 校验缓存文件是否有效
5. 返回缓存路径

### Step 4. 在 `_image_clip()` 中接入复用

处理顺序建议为：

1. 先拿 `fixed_image`
2. 判断是否应该预烘焙
3. 如果命中缓存，直接返回 `VideoFileClip(cache.mp4)`
4. 如果没有命中缓存，先预烘焙，再返回 `VideoFileClip(cache.mp4)`
5. 不满足条件时，继续走现有 `ImageClip + blur + motion` 路径

## 8. 预期收益

### 8.1 对长视频

当项目中有大量照片时，二次渲染和失败重跑速度会明显改善。

### 8.2 对稳定模式

chunk 渲染时，每个图片段不必重复构建复杂 clip 结构，能减轻 Python 时间线压力。

### 8.3 对最终导出

照片段越多，收益越明显。

## 9. 风险与控制

### 风险 1

首次渲染可能因为先烘焙缓存片段而增加一点前置时间。

控制方式：

- 第一轮只对长视频/稳定模式启用

### 风险 2

缓存 key 不完整，可能导致误复用旧段。

控制方式：

- motion、duration、fps、target_size、engine_version 都进入 key

### 风险 3

缓存写出失败反而影响正常渲染。

控制方式：

- 预烘焙失败必须自动回退现有路径
- 不允许因缓存失败而阻断正常导出

## 10. 验证方案

至少验证以下内容：

- 首次渲染会生成 `photo_segments` 缓存
- 第二次相同参数渲染直接复用缓存
- 缓存文件存在且有效
- 不同 motion 或 duration 会生成不同缓存
- 稳定模式下长视频逻辑仍然正常

建议验证命令：

- `npm.cmd exec tsc -- --noEmit`
- `python -m py_compile video_engine_v5.py`
- `python tests\\smoke_v5_photo_segment_cache.py`
- `python tests\\smoke_v5_6_long_video_stability.py`

## 11. 第一轮实施结论

第一轮不追求把照片渲染彻底 GPU 化，也不追求一次覆盖所有特效。

第一步只做一件高收益的事：

- 把照片段从“每次实时组合”升级成“可缓存、可复用的预烘焙片段”

这是当前项目从“已有素材级缓存”升级到“真正段级缓存”的关键一步。

## 12. 第二轮扩展：缓存命中可视化与适用范围放宽

第二轮的目标不是推翻第一轮，而是在保持低风险的前提下，让这套缓存更“看得见”、也更“用得上”。

### 12.1 新增缓存命中可视化

渲染器现在会记录照片段缓存的四类统计：

- `eligible`
- `hit`
- `created`
- `fallback`

它们会通过两种方式暴露出来：

- 渲染日志里输出 `Photo segment cache hit / created / summary`
- 长视频稳定渲染的 `build_report.json` 增加 `photo_segment_cache`

这样后续做性能分析时，就能明确回答：

- 这次项目里有多少照片段符合预烘焙条件
- 命中了多少缓存
- 新建了多少缓存
- 有没有因为异常回退到实时拼装

### 12.2 适用范围从“超长项目”扩大到“中大型项目”

第一轮只在这些场景默认触发：

- `performance_mode = stable`
- `render_mode = long_stable`
- 总时长 `>= 600s`
- 分段数 `>= 80`

第二轮在保留上述条件的同时，额外向下覆盖：

- `performance_mode in {"balanced", "quality"}`
- 且总时长 `>= 240s` 或分段数 `>= 30`

这样做的原因是：

- 很多 4 到 10 分钟的中视频项目，照片段已经足够多
- 这些项目虽然还不到“超长视频”，但重复渲染图片段的成本已经明显
- 提前让平衡档和质感档也能命中缓存，更符合真实创作场景

### 12.3 仍然保持的安全边界

第二轮没有放开到所有图片段，而是继续限制在低风险 motion：

- `none`
- `still_hold`
- `gentle_push`
- `slow_push`
- `ken_burns`
- `subtle_ken_burns`
- `punch_zoom`
- `micro_zoom`

也就是说，这一轮扩大的是“项目规模适用范围”，不是“高风险复杂特效范围”。

### 12.4 第二轮验收重点

至少再确认以下内容：

- 相同照片段第二次渲染时，`hit` 计数会增加
- 中大型 `balanced` 项目也会触发 `photo_segments` 缓存
- `build_report.json` 中能看到 `photo_segment_cache`
- 失败时仍能安全回退到实时拼装，不阻断最终导出

## 13. 第三轮扩展：收益量化与轻量叠字图片段缓存

第三轮的目标是把“照片段缓存”从基础命中能力，继续推进成：

- 可以量化收益
- 可以覆盖更多真实创作里的图片段

### 13.1 新增收益量化字段

在原有统计基础上，继续增加：

- `saved_live_composes`
- `saved_render_seconds`
- `overlay_eligible`
- `overlay_hit`
- `overlay_created`

其中：

- `saved_live_composes` 表示这次少做了多少次照片段实时拼装
- `saved_render_seconds` 表示大约少做了多少秒照片段实时合成路径
- `overlay_*` 表示带轻量章节文字/标题叠加的图片段命中情况

### 13.2 扩展到轻量叠字图片段

第三轮不直接开放所有复杂叠字，而是只允许安全边界内的轻量 overlay 图片段进入缓存：

- overlay 文案较短
- overlay 时长较短
- overlay motion 属于低风险集合
- overlay position 属于常规位置

这样做的目的是：

- 提高真实项目命中率
- 保持缓存 key 稳定
- 不把复杂文本动效的不确定性一口气引进来

### 13.3 第三轮前端呈现

除了顶部状态条外，引擎卡片中的照片缓存摘要还应继续展示：

- 这次复用了多少段
- 少做了多少次实时拼装
- 估算节省了多少秒实时照片合成
- 其中有多少段轻量叠字图片也命中了缓存

### 13.4 第三轮验收重点

- 纯照片段二次渲染时，`saved_live_composes` 与 `saved_render_seconds` 会增加
- 轻量叠字图片段可以生成并复用 `photo_segments` 缓存
- 前端引擎卡片能看到节省时长和叠字命中数
