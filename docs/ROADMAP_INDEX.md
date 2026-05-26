# 路线图总索引

## 目的

这份索引用来把项目当前最重要的几类路线图串起来，避免后续推进时在 `docs/` 目录里分散查找。

建议把路线理解成三层：

1. 先解决当前最直接的性能与工程瓶颈
2. 再把渲染内核做成稳定、可预期、可持续扩展的产品基础
3. 最后才考虑是否向更完整的专业剪辑器形态演进

---

## 一、当前最重要的主文档

### 1. 性能优化主线

- [RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md](./RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md)
- [NEXT_SYSTEM_OPTIMIZATION_AREAS.md](./NEXT_SYSTEM_OPTIMIZATION_AREAS.md)

适合在以下问题下优先查看：

- 为什么真实项目导出这么慢
- `10-15` 分钟视频如何从小时级往下压
- 哪些性能优化副作用最小
- `stable / FFmpeg / hardware encoding / MoviePy fallback` 应该如何排序推进
- 除了继续提速，接下来系统层还该优化什么

这组文档回答的是：

- 如何在不明显伤画质和一致性的前提下提速
- 先做哪几刀，收益最大
- 什么条件下才值得认真考虑新渲染后端
- 下一阶段该把项目往“更快、更稳、更能解释、更像成熟产品”的哪些方向推进

### 2. 产品成熟度与渲染后端主线

- [PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md](./PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md)
- [COMMERCIAL_PRODUCT_MATURITY_PLAN.md](./COMMERCIAL_PRODUCT_MATURITY_PLAN.md)
- [RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md](./RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md)
- [MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md](./MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md)

适合在以下问题下优先查看：

- 当前项目和 `Final Cut Pro / DaVinci Resolve / Premiere Pro` 的差距在哪里
- 这个项目到底应该先做成什么类型的产品
- 为什么现在不应该过早追完整专业剪辑器 UI
- 当前渲染引擎的问题是结构性问题，还是还可以继续优化
- 到什么条件下才值得认真考虑替换长视频渲染后端
- 如果决定增加引擎，应该如何做成多 backend 架构

这组文档回答的是：

- 当前项目的真实定位
- 当前距离成熟商业产品还有多远
- 与专业剪辑器的关键差距
- 三阶段成熟路线
- 现有底层渲染引擎的结构性短板
- 是否需要换后端的决策门槛
- 如何以低风险方式接入新的渲染 backend

### 3. 工程闭环与执行主线

- [PYTHON_WORKER_PACKAGING.md](./PYTHON_WORKER_PACKAGING.md)
- [ERROR_CODE_INDEX.md](./ERROR_CODE_INDEX.md)
- [UPGRADE_AND_MIGRATION_GUIDE.md](./UPGRADE_AND_MIGRATION_GUIDE.md)
- [RENDER_SCHEDULER_STRATEGY.md](./RENDER_SCHEDULER_STRATEGY.md)
- [PHOTO_SEGMENT_CACHE_IMPLEMENTATION.md](./PHOTO_SEGMENT_CACHE_IMPLEMENTATION.md)
- [VIDEO_SEGMENT_CACHE_AND_FFMPEG_EXPANSION.md](./VIDEO_SEGMENT_CACHE_AND_FFMPEG_EXPANSION.md)
- [TEMPLATE_MATCHING_BGM_AND_TIMELINE_EXECUTION_PLAN.md](./TEMPLATE_MATCHING_BGM_AND_TIMELINE_EXECUTION_PLAN.md)

适合在以下问题下优先查看：

- worker 打包与桌面分发是否稳定
- 错误码该如何解释、归类和支持排障
- 旧项目升级到新版本时会发生什么
- 调度器、segment/chunk/cache 快路径怎么设计
- 模板匹配、AI 配乐蓝图、轻量时间线微调该如何推进
- 当前工程闭环还有哪些地方不完整

---

## 二、推荐阅读顺序

### 场景 A：当前最关心“慢”

推荐顺序：

1. [RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md](./RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md)
2. [NEXT_OPTIMIZATION_PRIORITIES.md](./NEXT_OPTIMIZATION_PRIORITIES.md)
3. [RENDER_SCHEDULER_STRATEGY.md](./RENDER_SCHEDULER_STRATEGY.md)
4. [VIDEO_SEGMENT_CACHE_AND_FFMPEG_EXPANSION.md](./VIDEO_SEGMENT_CACHE_AND_FFMPEG_EXPANSION.md)
5. [NEXT_SYSTEM_OPTIMIZATION_AREAS.md](./NEXT_SYSTEM_OPTIMIZATION_AREAS.md)

这条线的目标是先把这些事情做强：

- 长视频导出速度
- stable 渲染命中率
- FFmpeg 快路径覆盖率
- 缓存与代理素材链路
- 后续系统性优化方向

### 场景 B：当前最关心“产品往哪走”

推荐顺序：

1. [PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md](./PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md)
2. [COMMERCIAL_PRODUCT_MATURITY_PLAN.md](./COMMERCIAL_PRODUCT_MATURITY_PLAN.md)
3. [RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md](./RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md)
4. [MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md](./MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md)
5. [RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md](./RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md)
6. [PYTHON_WORKER_PACKAGING.md](./PYTHON_WORKER_PACKAGING.md)
7. [TEMPLATE_MATCHING_BGM_AND_TIMELINE_EXECUTION_PLAN.md](./TEMPLATE_MATCHING_BGM_AND_TIMELINE_EXECUTION_PLAN.md)

这条线的目标是先回答：

- 这个项目先做成什么最有胜算
- 要达到成熟商业产品还差哪些关键能力
- 现有引擎还值不值得继续深挖
- 什么时候该从“补强现引擎”切到“评估新后端”
- 如果决定增加引擎，新 backend 应该怎么接
- 先补渲染引擎，还是先补更重的编辑器 UI

### 场景 C：当前最关心“工程闭环是否完整”

推荐顺序：

1. [PYTHON_WORKER_PACKAGING.md](./PYTHON_WORKER_PACKAGING.md)
2. [ERROR_CODE_INDEX.md](./ERROR_CODE_INDEX.md)
3. [UPGRADE_AND_MIGRATION_GUIDE.md](./UPGRADE_AND_MIGRATION_GUIDE.md)
4. [RENDER_SCHEDULER_STRATEGY.md](./RENDER_SCHEDULER_STRATEGY.md)
5. [PHOTO_SEGMENT_CACHE_IMPLEMENTATION.md](./PHOTO_SEGMENT_CACHE_IMPLEMENTATION.md)
6. [VIDEO_SEGMENT_CACHE_AND_FFMPEG_EXPANSION.md](./VIDEO_SEGMENT_CACHE_AND_FFMPEG_EXPANSION.md)
7. [NEXT_SYSTEM_OPTIMIZATION_AREAS.md](./NEXT_SYSTEM_OPTIMIZATION_AREAS.md)

这条线主要看：

- worker 打包与分发
- 错误码体系与支持闭环
- 项目升级与 schema migration
- 渲染调度与快路径归类
- segment / chunk / visual base 缓存
- FFmpeg 扩张路线
- 失败恢复、可观测性、fallback、素材体系等系统优化方向

---

## 三、当前阶段的主判断

当前阶段最重要的结论是：

- 项目应优先做成“成熟的自动化长视频生产工具”
- 不应过早追求“完整专业剪辑器 UI”
- 性能优化与产品成熟度路线不是两条线，而是一前一后的同一条主线

也就是说：

1. 先把 `stable + FFmpeg + hardware encoding + cache + worker` 做稳
2. 再把可观测性、可恢复性、分发能力做成熟
3. 最后再决定是否向更强交互型编辑器演进

---

## 四、当前优先级总览

### P0：性能和快路径覆盖率

目标：

- 明显压缩真实长视频导出时间
- 收缩 `MoviePy` 使用范围

主文档：

- [RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md](./RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md)

### P1：工程稳定性与产品基础

目标：

- worker 可分发
- 渲染行为可诊断
- 缓存与代理策略可控
- 进度、错误、日志、状态对用户更可信

主文档：

- [PYTHON_WORKER_PACKAGING.md](./PYTHON_WORKER_PACKAGING.md)
- [ERROR_CODE_INDEX.md](./ERROR_CODE_INDEX.md)
- [UPGRADE_AND_MIGRATION_GUIDE.md](./UPGRADE_AND_MIGRATION_GUIDE.md)
- [RENDER_SCHEDULER_STRATEGY.md](./RENDER_SCHEDULER_STRATEGY.md)
- [NEXT_SYSTEM_OPTIMIZATION_AREAS.md](./NEXT_SYSTEM_OPTIMIZATION_AREAS.md)

### P2：产品成熟度与后端决策

目标：

- 明确与专业剪辑器的差距
- 决定未来是“自动化生产工具优先”还是“向专业编辑器演进”
- 为“是否替换长视频后端”建立决策标准
- 为“如何增加新引擎”建立可执行的 backend 接入方案

主文档：

- [PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md](./PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md)
- [COMMERCIAL_PRODUCT_MATURITY_PLAN.md](./COMMERCIAL_PRODUCT_MATURITY_PLAN.md)
- [RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md](./RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md)
- [MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md](./MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md)
- [TEMPLATE_MATCHING_BGM_AND_TIMELINE_EXECUTION_PLAN.md](./TEMPLATE_MATCHING_BGM_AND_TIMELINE_EXECUTION_PLAN.md)

---

## 五、后续维护建议

后续如果再新增路线图文档，建议按下面方式归类：

- 性能类：渲染速度、快路径、缓存、FFmpeg、编码器
- 工程类：worker、CI、打包、协议、可恢复性、fallback、可观测性
- 产品类：定位、成熟度、UI/UX、编辑器能力、backend 架构

并把新增主文档挂到这份索引里，保持总入口稳定。
