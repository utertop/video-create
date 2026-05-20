# 下一阶段系统优化方向

本文档用于整理当前项目在“继续提升性能、稳定性、成熟度”上的下一阶段主线，不替代已有的渲染性能文档，而是作为更高层的系统优化索引。

相关文档：

- [RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md](./RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md)
- [MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md](./MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md)
- [RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md](./RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md)
- [PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md](./PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md)

---

## 当前判断

当前项目已经完成了一批高价值基础建设：

- 更早切入 `stable` 长视频路径
- `ffmpeg_image_chunk / ffmpeg_card_chunk / ffmpeg_fitted_video_chunk`
- `BackendDecision / BackendExecutionResult`
- packaged worker 与 CI 基础链路
- 进度条、错误展示、章节素材视图的第一轮修复

所以下一阶段的优化重点，不应该只盯着“再快一点”，而应该同时推进四个目标：

1. 更快
2. 更稳
3. 更能解释
4. 更像成熟产品

---

## 优先级总览

建议的下一阶段优先级：

1. 渲染可观测性
2. 失败恢复能力
3. 剩余视频段快路径覆盖率
4. 音频链路
5. 素材与缩略图体系
6. 多 backend 真正 fallback 执行
7. 产品层体验持续打磨

---

## 1. 渲染可观测性

### 为什么优先

这是后续所有优化的判断基础。没有足够清晰的 report 和诊断信息，后面很容易继续“凭感觉优化”，但实际没有打在真实瓶颈上。

### 当前仍然缺什么

- 每个 `segment` 最终走了哪条 route
- 每个 `chunk` 最终走了哪条 route
- 为什么没有命中快路径
- backend 是否发生 fallback
- 最终实际执行的是哪个 backend
- 编码耗时
- 音频混流耗时
- 片段缓存命中与失效原因

### 建议补充

- 在 `build_report.json` 中增加更细粒度 diagnostics
- 给 chunk / segment 加上“路由原因字段”
- 给 fallback 写明：
  - `selected_backend`
  - `actual_backend_name`
  - `fallback_used`
  - `fallback_reason`
- 将编码、拼接、音频混流拆分计时

### 价值

- 明确真实瓶颈
- 降低误判
- 支撑后续性能优化与新 backend 决策

---

## 2. 失败恢复能力

### 为什么重要

长视频任务一旦跑到数小时级别，失败恢复能力就不再是“加分项”，而是必需能力。

### 建议方向

- chunk 级断点续跑
- 更明确的失败分类
- 中途失败后尽量保留已完成 chunk
- worker 中断后的恢复策略
- 更稳定的取消与重试行为

### 建议重点

- 不要让单个 chunk 失败直接废掉整次任务
- 重试时优先复用已完成 chunk
- 日志和 report 中明确失败发生在：
  - 预处理
  - chunk 写出
  - concat
  - 音频混流
  - 最终封装

### 价值

- 提升长视频任务可用性
- 降低失败成本
- 更接近成熟产品体验

---

## 3. 剩余视频段快路径覆盖率

### 为什么仍然关键

当前图片段相关快路径已经做了不少，下一阶段最可能继续明显压缩导出时间的，是视频段里剩余仍然回退到 `MoviePy` 的场景。

### 建议方向

- 安全视频段 + 轻 overlay
- 安全视频段 + 轻转场
- 安全视频段的更多 motion 白名单
- 能走 fitted/cache 的尽量别回到重时间线

### 建议策略

- 继续坚持白名单渐进扩张
- 不要一次性把复杂视频段全部切到新路径
- 优先支持“副作用小、收益明确”的场景

### 价值

- 对真实长视频导出耗时最直接
- 继续降低 `MoviePy` 覆盖面

---

## 4. 音频链路

### 当前现状

`audio_blueprint`、章节重启、自动参数落地已经有基础，但音频链路还没有完全成熟。

### 建议方向

- 更稳定的多首 BGM 接力
- 章节切换时的音乐衔接优化
- `source audio / bgm` 边界更清晰
- 长视频音频缓存命中策略更细
- 音频混流失败时的回退与诊断

### 不建议现在优先做的

- 过度复杂的章节级音量曲线自动化
- 太多不可解释的音量/ducking 自动规则

### 价值

- 提升成片质感
- 提升自动出片稳定度

---

## 5. 素材与缩略图体系

### 为什么这条线值得做

素材多的时候，用户对“这个项目稳不稳”的第一感知往往不是渲染器，而是素材浏览体验。

### 当前典型问题

- 章节视图素材过多时过载
- 背景选择器容易展示过量素材
- 缩略图失败回退不够统一
- 素材很多时滚动与加载体验容易变差

### 建议方向

- 缩略图失败回退统一化
- 大素材组默认限流 + 手动展开
- 章节背景选择优先本章节素材
- 大列表按需展开或虚拟化
- 更清楚的章节/类型/时间筛选

### 价值

- 改善大项目操作体验
- 减少“看起来像 bug”的感知

---

## 6. 多 backend 真正 fallback 执行

### 当前现状

结构层已经有：

- `BackendDecision`
- `BackendExecutionResult`
- backend selector
- backend modules

但现在 fallback 语义还主要停留在结构与 report 层，并没有真正进入“新 backend 失败后自动回退”的执行阶段。

### 建议方向

- 在 dispatcher 中接入真实 fallback
- 明确 fallback 链
- 将 fallback 状态透传到 report
- UI 侧明确展示：
  - 当前选中的 backend
  - 实际执行的 backend
  - 是否发生 fallback

### 执行原则

- fallback 必须可解释
- fallback 不能让用户误解成“卡住”
- fallback 后的结果要写清楚

### 价值

- 为未来接入第三个 backend 做准备
- 降低新 backend 试点风险

---

## 7. 产品层体验持续打磨

### 为什么不能忽略

即使引擎很强，如果用户感知到的是：

- 不知道当前在干什么
- 不知道失败了没有
- 不知道为什么慢
- 不知道为什么这次和上次不一样

那仍然不算成熟产品。

### 建议方向

- 进度条更可信
- 错误提示更明确
- 队列与历史记录更清楚
- 成功/失败/取消状态更稳定
- 输出结果、缓存状态、当前 backend 更易理解

### 价值

- 明显提升“成熟感”
- 减少误解与焦虑

---

## 建议推进顺序

### 第一阶段

- 渲染可观测性
- 失败恢复能力

目标：

- 先让系统变得更可判断、更能解释

### 第二阶段

- 剩余视频段快路径覆盖率
- 音频链路

目标：

- 继续压缩导出时间，同时提升成片稳定性

### 第三阶段

- 素材与缩略图体系
- 多 backend 真 fallback 执行
- 产品层体验持续打磨

目标：

- 把系统从“强原型”继续推向“成熟产品”

---

## 一句话结论

下一阶段不只是要继续“提速”，而是要把项目往下面四个方向一起推：

- 更快
- 更稳
- 更能解释
- 更像成熟产品

如果只选一个最值得立刻做的主线，优先建议是：

**渲染可观测性**

因为它会直接决定后面每一刀优化到底砍得准不准。
