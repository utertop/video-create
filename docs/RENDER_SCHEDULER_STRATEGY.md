# Video Create Studio V5 渲染调度策略

## 1. 目标

当前项目已经具备多条可执行路径：

- `photo_segments`
- `fitted_videos`
- `motion_fitted_videos`
- `FFmpeg direct chunk`
- `MoviePy timeline`

下一阶段的重点，不再是继续零散增加单点优化，而是先让系统在渲染前回答一个更基础的问题：

- 每一段应该走哪条路径
- 哪些段可以先吃缓存
- 哪些段可以整块交给 FFmpeg
- 哪些段必须保留在 MoviePy 时间线

这就是渲染调度层。

## 2. 为什么先做调度，不先做局部失效

“局部失效和段级复用”解决的是：

- 改一点内容时，尽量少重渲

“渲染调度”解决的是：

- 一开始就选择最合适的渲染路径

两者相关，但不是一回事。

当前阶段更适合先做调度，原因是：

- 照片段缓存已经成型
- 视频 fitted / motion fitted 已经成型
- FFmpeg direct chunk 已经成型
- 现在缺的是统一判断层，而不是继续盲加新缓存桶

## 3. 调度分层

调度策略分两层：

### 3.1 compile 静态建议

写入 `render_plan.json` 的字段：

- `render_route`
- `render_route_reason`
- `render_route_tags`

它表达的是：

- 按蓝图、策略、素材类型、预计项目体量，系统建议这段更适合走哪条路线

这一层适合做：

- 预先可视化
- 调试 render_plan
- 后续做批量分析

### 3.2 runtime 实际路线

渲染器启动后再根据当前参数重判：

- `runtime_render_route`
- `runtime_render_route_reason`
- `runtime_render_route_tags`

它表达的是：

- 当前实际渲染参数下，这段最终会走哪条执行路径

这样做的原因是：

- 用户可能在 UI 里改了性能档位
- 改了预览模式 / 正式渲染模式
- 改了引擎或质量设置

静态建议不能替代实际执行路线。

## 4. 第一版段级路由规则

### 4.1 图片段

- `photo_prerender`
  - 适合中大项目
  - motion 在安全集合内
  - 优先进入 `photo_segments`
- `image_live_compose`
  - 项目不大，或段本身不适合预烘焙
  - 保留现有 MoviePy 即时拼装

### 4.2 视频段

- `direct_chunk_candidate`
  - 轻量视频段
  - 无 overlay
  - `cut / none`
  - `none / still_hold`
- `video_fit`
  - 可安全先做画幅适配、音轨标准化
  - 后续仍可交给时间线做转场或叠字
- `video_motion_fit`
  - 在 `video_fit` 基础上，再预烘焙简单视频 motion
  - 当前仅先覆盖 `gentle_push / slow_push`
- `moviepy_required`
  - 复杂叠字、复杂转场、复杂 motion，或其他高风险段

### 4.3 文字/章节卡

- 默认 `moviepy_required`

原因很明确：

- 这类段本身就属于时间线表达层
- 当前优先级不是先把它们纯 FFmpeg 化

## 5. 第一阶段已落地内容

本轮先完成三件事：

1. `compile` 输出静态路由建议
2. `Renderer` 在启动时输出 runtime 路由
3. 稳定模式 `build_report.json` 带上 `render_scheduler`

也就是说，现在系统已经不再只是“渲染时顺手判断”，而是开始有正式的调度骨架。

## 6. 当前新增的 chunk 级调度收口

在第一阶段基础上，chunk 写入链路也开始收口到调度层：

- `chunk group` 会带：
  - `runtime_chunk_route`
  - `runtime_chunk_route_reason`
  - `runtime_chunk_route_tags`
- 当前第一版 chunk 路由规则：
  - 全部段都是 `direct_chunk_candidate`
    - `ffmpeg_direct_chunk`
  - 只要包含图片段、时间线段、复杂视频段
    - `moviepy_chunk`

这意味着：

- `write_chunk` 不再临时自己再发明一套路径判断
- `FFmpeg direct chunk` 会优先消费 chunk 调度结果
- `build_report.json` 里会同时看到 `segment scheduler` 和 `chunk scheduler`

## 7. 当前可以收口的性能线

以下线路可以阶段性收口：

- 照片段专项缓存
- 音频基础性能链路
- 视频 fitted / motion fitted 基础能力
- 性能档位 UI

它们后面仍可增强，但已经不是当前第一优先。

## 8. 下一阶段优先级

### 第一优先

段级调度规则继续完善

- 让更多路径消费 `runtime_render_route`
- 把 direct chunk / fitted / motion fitted 的判断统一到调度层

### 第二优先

chunk 级调度

- 不只判断单段
- 还判断一组段是否可以整块直出

### 第三优先

预览 / 正式渲染分层

- 预览优先代理、低清、轻滤镜
- 正式渲染再走完整路径

### 第四优先

局部失效和段级复用深化

- 改一点配置，尽量只失效必要段
- 让缓存体系在调度稳定后变得更聪明

## 9. 当前结论

从整体方向看，下一阶段不是简单继续加某个缓存桶，而是：

- 先把渲染调度做成正式层
- 再让更多执行路径去消费调度结果
- 最后再回头深化局部失效和更细的段级复用

这意味着：

- 现在最该打的是“段级调度规则”
- 不是先做前端细碎展示
- 也不是马上进入更深的局部失效系统
