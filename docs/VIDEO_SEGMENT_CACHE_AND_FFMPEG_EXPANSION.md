# Video Create Studio V5 视频段专项缓存与 FFmpeg 路径扩展方案

## 1. 目标

这一轮不新增一个“第四渲染引擎”，而是升级现有视频段执行路径，让更多视频段尽量留在：

- `FFmpeg fitted video cache`
- `FFmpeg chunk direct output`
- `FFmpeg concat`

减少它们反复进入：

- `VideoFileClip`
- `CompositeVideoClip`
- `MoviePy timeline compose`

最终目标是两件事：

- 长视频里减少视频段重复适配与重编码
- 让这部分收益像照片段缓存一样可见、可量化

## 2. 当前基础

项目现在已经有视频段相关基础能力：

- `_ffmpeg_fit_video_segment()`
  - 把视频统一适配到目标画幅、fps、像素格式和音频轨
- `_can_use_ffmpeg_fitted_video()`
  - 对简单视频段优先走 FFmpeg fitted 路径
- `_v56_write_chunk_video()`
  - 对轻量 chunk 尽量走 FFmpeg 直出
- `fitted_videos` render cache
  - 已经可以存储适配后的视频段缓存

但还缺两件关键能力：

- 没有像照片段缓存那样的完整“命中 / 新建 / 回退 / 节省时长”统计
- 前端看不到这部分收益，导致视频段缓存虽然存在，但像黑盒

## 3. 第一轮实施范围

第一轮只做高收益、低风险的事：

### 3.1 补齐视频段缓存统计

新增：

- `eligible`
- `hit`
- `created`
- `fallback`
- `saved_live_fits`
- `saved_render_seconds`

用于回答：

- 这次有多少视频段符合 FFmpeg fitted 条件
- 其中多少直接复用了缓存
- 多少是首次新建
- 多少最后仍回退到 MoviePy/实时适配
- 少做了多少次实时视频适配
- 大致节省了多少秒视频段实时适配路径

### 3.2 输出结构化事件

新增：

- `video_cache` 结构化事件

用于：

- 日志可读
- 前端状态卡可读
- 后续 build report 和 UI 扩展一致

### 3.3 build_report.json 补齐字段

在稳定渲染完成或失败时，把：

- `video_segment_cache`

写入 `build_report.json`。

### 3.4 前端引擎卡片展示

在“性能档位”下方增加视频段缓存摘要卡，展示：

- 复用了多少段视频缓存
- 省掉了多少次实时适配
- 节省了多少秒视频适配
- 本次新建多少段
- 安全回退多少段

## 4. 第一轮安全边界

第一轮不扩复杂特效，只统计和放大当前已经能安全走 FFmpeg fitted 的视频段：

- `type = video`
- 无 `overlay_text`
- 转场仅 `cut / none`
- transition duration 极小
- motion 仅 `none / still_hold`

也就是说，这一轮主要是：

- 把当前已有视频段缓存能力“显性化”
- 给后续扩大 FFmpeg 覆盖率打基础

而不是立刻把复杂视频段全扔给 FFmpeg。

## 5. 后续轮次

### 第二轮

扩大 FFmpeg fitted 适用范围，例如：

- 轻量视频淡化
- 更保守的简单 motion
- 简单统一音轨的视频段

### 第三轮

继续推进到：

- 更细的 segment 级局部失效
- chunk 级路径统计
- “哪些段仍被 MoviePy 接管”的可视化

## 6. 第一轮验收

至少验证：

- 视频段第一次渲染会生成 `fitted_videos` 缓存
- 第二次相同参数渲染会命中缓存
- `video_segment_cache_stats` 的 `eligible / created / hit / saved_render_seconds` 会变化
- 前端引擎卡片能显示视频段缓存收益
- 稳定长视频渲染链路不受破坏

建议命令：

- `python -m py_compile video_engine_v5.py`
- `python tests\\smoke_v5_ffmpeg_priority.py`
- `python tests\\smoke_v5_6_long_video_stability.py`
- `npm.cmd exec tsc -- --noEmit`

## 7. P2 第二轮：扩大 fitted 覆盖，保持 direct chunk 保守

第二轮的核心不是直接放宽所有 FFmpeg 直出条件，而是把两层能力拆开：

- `FFmpeg fitted video`
  - 目标：让更多视频段先完成目标画幅适配、音轨标准化和缓存复用
  - 这些段后续仍可继续进入 MoviePy 时间线，保留叠字和转场表现
- `FFmpeg direct chunk`
  - 目标：只处理最轻量、最确定的纯拼接段
  - 这条路径仍保持更严格，避免跳过必要的时间线处理

### 7.1 fitted 覆盖扩大到哪些范围

第二轮允许这些视频段走 `fitted_videos` 缓存：

- 轻量 overlay title
  - 文案长度受控
  - overlay 时长受控
  - overlay motion / position 只允许安全集合
- 轻量时间线转场
  - `soft_crossfade`
  - `fade_through_dark`
  - `fade_through_white`
  - `quick_zoom`
  - `flash_cut`
- 静态或持镜 motion
  - `none`
  - `still_hold`

这一步的判断原则是：

- 只要段本体可以先安全做 FFmpeg fit，就优先把“画幅适配 + 音频标准化”前置并缓存
- 后续叠字、转场仍然交给时间线层处理，不把表达直接砍掉

### 7.2 direct chunk 为什么继续保守

`direct chunk` 目前仍只接受：

- 无 overlay
- `cut / none`
- 极短或无 transition duration
- `none / still_hold`

原因很直接：

- direct chunk 现在是 concat copy / concat reencode 直出
- 如果把需要 overlay 或时间线转场的段放进去，会跳过这些表现层处理
- 所以第二轮只扩大 fitted 覆盖，不冒进扩大 direct chunk 语义

### 7.3 第二轮新增验证

新增两类冒烟保护：

- 轻量 overlay + `soft_crossfade` 的视频段
  - 可以命中 fitted cache
  - 但不能误进 direct chunk
- 不安全 overlay 或带真实 motion 的视频段
  - 仍然拒绝 fitted 扩张条件

这样可以确保这一轮的收益是：

- 更多视频段复用 FFmpeg fitted cache
- direct chunk 仍然只做最轻的安全场景
- 不牺牲原有 overlay / transition 表达

## 8. P2 第三轮：简单视频 motion 预适配缓存

第三轮继续扩大“先吃缓存、再决定是否进入时间线”的范围，但先只覆盖最简单、最稳定的一组：

- `gentle_push`
- `slow_push`

这组 motion 当前本质都是中心缩放，不涉及真实位移、路径动画或多层合成，所以适合单独拆成：

- `fitted_videos`
  - 负责目标画幅适配、音轨标准化
- `motion_fitted_videos`
  - 在 fitted 基础上，再烘焙一层简单 motion

### 8.1 为什么单独拆 motion 层

这样做有两个好处：

- motion 缓存命中时，后续可直接复用整段“已适配 + 已带轻 motion”的视频
- motion 缓存失败时，只回退这一层，仍然保持原来的 MoviePy 路径，不会偷偷把镜头动感做没

### 8.2 第三轮边界

第三轮仍然不放开这些场景：

- `ken_burns / subtle_ken_burns`
- `micro_zoom / punch_zoom`
- 需要复杂 overlay 的视频段
- 需要 direct chunk 直出的 motion 段

也就是说，这轮的目标不是让 motion 段直接 pure FFmpeg 拼完整条时间线，而是：

- 先把“简单缩放型视频 motion”缓存掉
- 再让时间线层决定是否继续做转场、叠字和后续组合

### 8.3 第三轮验证

新增验证点：

- `gentle_push` 视频段会生成 `motion_fitted_videos` 缓存
- 第二次相同参数会命中 `motion_hit`
- 带 simple motion 的视频段仍然不会误进 `direct chunk`
