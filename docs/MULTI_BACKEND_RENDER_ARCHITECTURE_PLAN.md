# 多 Backend 渲染架构实施方案

## 相关文档

- [ROADMAP_INDEX.md](./ROADMAP_INDEX.md)
- [RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md](./RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md)
- [RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md](./RENDER_PERFORMANCE_LOW_RISK_ACCELERATION_PLAN.md)
- [PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md](./PRO_EDITOR_GAP_AND_MATURITY_ROADMAP.md)

## 目标

这份文档回答一个具体问题：

如果决定“增加引擎”，应该怎么做，才能在不推翻现有系统的前提下，把当前项目升级成多 backend 渲染架构。

这里的“增加引擎”，不是指：

- 再加一个用户手动选择的导出按钮
- 直接全量替换当前渲染系统
- 让 UI、worker、协议、渲染逻辑一起重写

这里真正要做的是：

- 保留当前 `scan -> plan -> compile -> worker -> render` 主链
- 把渲染执行层抽象成可插拔 backend
- 让系统内部按场景自动选择最合适的 backend
- 让新 backend 先只接管最安全、最能带来收益的长视频场景

---

## 一、结论先行

当前最合理的路线不是“换引擎”，而是“加 backend”。

也就是：

1. 保留上层数据结构不动。
2. 保留现有 worker 协议不动。
3. 保留现有 `render_plan` 基本格式不动。
4. 把底层执行层改成 backend abstraction。
5. 让现有路径和新路径先并存。
6. 让新 backend 第一阶段只接管一小类正式导出场景。

这是最重要的原则，因为现在项目已经有很多不能轻易丢掉的资产：

- worker 打包链路
- Tauri 集成
- cache / proxy / build report
- stable renderer
- FFmpeg 快路径
- CI smoke

如果直接推翻重来，风险很高，也会把当前已经跑通的工程基础一起打散。

---

## 二、为什么要做成多 backend，而不是继续堆一个大 Renderer

当前 `video_engine_v5.py` 里的渲染执行已经逐渐变成“混合后端系统”：

- `Renderer`
- `V56StableRenderer`
- `ffmpeg_direct_chunk`
- `ffmpeg_image_chunk`
- `ffmpeg_card_chunk`
- `ffmpeg_fitted_video_chunk`
- `MoviePy` 时间线兜底

这说明系统已经客观上走向了“多后端执行”，只是还没有被正式抽象出来。

如果继续把所有逻辑都堆在同一个大文件和同一组条件分支里，后续会越来越难维护：

- 哪个场景该走哪个 backend，会越来越难看懂
- 回退边界越来越难解释
- 新 backend 很难渐进接入
- worker 与诊断层也难以稳定输出更清晰的执行信息

所以，多 backend 架构的主要价值不是“看起来更高级”，而是：

- 把已经存在的混合执行现实，整理成正式结构
- 为新增后端提供可控接入点
- 让未来“继续补现有 backend”与“引入新 backend”都能共存

---

## 三、当前代码里最适合抽象的位置

现有主链里，最适合抽象成 backend 的位置，不在 `scan / plan / compile`，而在 `render` 执行层。

当前关键位置包括：

- [video_engine_v5.py](/d:/Automatic/video_create/video_engine_v5.py:3933) `Renderer`
- [video_engine_v5.py](/d:/Automatic/video_create/video_engine_v5.py:7386) `_v56_write_chunk_video`
- [video_engine_v5.py](/d:/Automatic/video_create/video_engine_v5.py:7501) `V56StableRenderer`
- [video_engine_v5.py](/d:/Automatic/video_create/video_engine_v5.py:7795) `command_preview_render`
- [video_engine_worker.py](/d:/Automatic/video_create/video_engine_worker.py:122) worker preview/render 入口
- [src-tauri/src/lib.rs](/d:/Automatic/video_create/src-tauri/src/lib.rs:918) `run_v5_worker_task`

这些位置说明：

- 上层协议已经相对稳定
- 真正需要解耦的是“渲染计划如何执行”
- 新 backend 不必碰前面三阶段

也就是说，抽象边界应放在：

- `compile` 之后
- `render_plan` 已生成之后
- `worker` 已拿到 task 之后

这是风险最低的切入点。

---

## 四、建议的多 backend 架构

建议把架构拆成四层。

### 1. 计划层

职责：

- `scan`
- `plan`
- `compile`
- 输出统一 `render_plan`

这一层保持现状，不先改。

### 2. 调度层

职责：

- 基于 `render_plan`
- 结合项目特征、模式、时长、复杂度
- 选择合适的 backend
- 生成 backend 执行决策

建议新增概念：

- `backend_family`
- `backend_route`
- `backend_fallback_chain`

例如：

- `backend_family = stable_long_video`
- `backend_route = ffmpeg_stable`
- `backend_fallback_chain = ["ffmpeg_stable", "moviepy_stable", "legacy_renderer"]`

### 3. backend 层

建议至少抽出这些 backend：

- `legacy_moviepy_backend`
- `ffmpeg_stable_backend`
- `preview_proxy_backend`
- `new_long_video_backend` 未来候选

其中：

- `legacy_moviepy_backend` 负责复杂兜底
- `ffmpeg_stable_backend` 负责当前主力快路径
- `preview_proxy_backend` 负责预览和代理素材路径
- `new_long_video_backend` 暂时先保留接口，不急着落实现

### 4. 结果与诊断层

职责：

- 收集 route / backend 命中信息
- 记录 fallback
- 输出 `build_report`
- 输出 worker 事件和日志

这一层后续要让“为什么走这个 backend”更可解释。

---

## 五、第一阶段不要做什么

在开始多 backend 化之前，有几件事现在不该做。

### 1. 不要先改 UI

第一阶段不要把重点放在：

- 前端增加“选择第 4 个引擎”
- 增加复杂可视化选项面板

因为当前最核心的工作是：

- 后端架构抽象
- 自动选择逻辑
- 回退链条

不是界面暴露更多开关。

### 2. 不要先改 worker 协议格式

第一阶段应尽量复用现有 worker task 结构，避免：

- Tauri 侧同步改很多协议
- 新后端接入本身还没验证，先引入协议复杂度

### 3. 不要先做全量切换

第一阶段不应该让新 backend 一上来就接全部项目。

必须先限定范围，只吃最安全场景。

### 4. 不要让新 backend 没有回退

任何新 backend 都必须支持：

- 命中失败回退
- 某段不支持回退
- 结果校验失败回退

否则会直接损伤可用性。

---

## 六、第一阶段推荐接管的场景

如果我们要增加一个“新引擎后端”，第一阶段最适合接管的是：

### 1. 长视频正式导出

原因：

- 这是当前最慢、最需要提速的主战场
- 也是最容易从 backend 更换中看到真实收益的场景

### 2. 纯图片项目

原因：

- 结构简单
- 对视觉一致性更容易控制
- 更适合验证新 backend 的时间线组织能力

### 3. 纯视频项目

原因：

- 相比混合项目边界更清晰
- 更容易对比现有 FFmpeg/stable 路径的真实收益

### 4. 简单转场与简单字幕

第一阶段只建议接：

- `cut`
- 轻量 `crossfade`
- 简单单层 overlay
- 无复杂动画字幕

不要第一阶段就碰：

- 多层字幕动画
- 复杂章节卡系统
- 特殊风格卡
- 重型转场

---

## 七、第一阶段模块拆分建议

建议先不做大搬家，而是先做“轻抽象 + 保留现实现”。

### Step 1：新增 backend 调度抽象

建议新增一个中心接口，例如：

- `resolve_render_backend(plan, params) -> backend decision`

输出内容建议包括：

- `backend_name`
- `backend_mode`
- `fallback_chain`
- `reason`
- `capability_flags`

### Step 2：把现有 stable 路径封成第一个正式 backend

也就是把当前 `V56StableRenderer` 和相关 chunk 写出逻辑，整理成：

- `ffmpeg_stable_backend`

注意：

- 这一步不是重写逻辑
- 只是给现有主力路径一个正式 backend 身份

### Step 3：把现有 `Renderer` 兜底路径封成 legacy backend

对应：

- `legacy_moviepy_backend`

职责就是：

- 继续承担复杂时间线兜底
- 保证当前兼容性不丢

### Step 4：render 入口改成“先选 backend，再执行 backend”

也就是：

- 不再让入口直接决定“调哪个大类函数”
- 而是统一先拿 backend decision

### Step 5：把 backend 命中信息写进 report

至少应记录：

- `selected_backend`
- `selected_backend_reason`
- `fallback_backend`
- `backend_route_counts`

这样以后讨论“新引擎值不值”，就不是靠感觉。

---

## 八、建议的文件级拆分方向

第一阶段不一定要一次拆很细，但建议至少形成这样的结构方向：

### 1. 保留

- `video_engine_v5.py`

继续承载：

- `scan`
- `plan`
- `compile`
- 总入口 glue code

### 2. 逐步抽出

建议未来拆出：

- `render_backends/base.py`
- `render_backends/legacy_moviepy.py`
- `render_backends/ffmpeg_stable.py`
- `render_backends/preview_proxy.py`
- `render_backends/backend_selector.py`

### 3. 暂时不急着拆

以下内容可先保留在旧文件里，通过函数调用接入：

- 现有缓存细节
- 卡片段预渲染
- 图片段预渲染
- 具体 FFmpeg filter graph 细节

先抽“结构边界”，再抽“实现细节”。

---

## 九、如果未来真的引入新后端，推荐接法

新 backend 第一阶段不应直接替代一切，而应按这种方式接入：

### 1. 名义上接成 long-video backend 候选

例如：

- `backend_name = new_long_video_backend`

### 2. 只在这些条件下尝试命中

- 正式导出
- 长视频
- 结构简单
- 白名单素材类型
- 白名单转场
- 白名单字幕样式

### 3. 某段不支持就整路回退

不要让第一阶段出现：

- 半段新 backend
- 半段复杂临时拼接
- 到处夹杂非正式分支

宁可保守回退，也不要先把系统变得难解释。

### 4. 先比较工程指标，不先比较理论能力

真正要比较的是：

- 真实项目总耗时
- 失败率
- 回退率
- 画质一致性
- Windows 分发复杂度
- CI 与 worker 接入成本

---

## 十、建议的三阶段实施顺序

### P0：做 backend abstraction，不引入新后端

目标：

- 先把“多 backend”结构搭出来

交付：

- backend selector
- legacy backend 封装
- ffmpeg stable backend 封装
- report 写出 backend 决策

### P1：让现有 FFmpeg/stable 正式成为主 backend

目标：

- 从“很多快路径拼起来”变成“一个有正式身份的主后端”

交付：

- `ffmpeg_stable_backend`
- 更清晰的 route / fallback 统计
- 更清晰的 worker 事件

### P2：引入新 backend 候选并做白名单试点

目标：

- 不推翻旧系统的前提下，验证新 backend 对真实长视频是否有明显收益

交付：

- 新 backend 仅接管长视频正式导出白名单场景
- 可回退
- 可统计
- 可对比

---

## 十一、验收标准

这件事做完后，不应该只是“多了个概念”，而应满足这些可见结果：

### 架构层

- render 入口能明确选出 backend
- backend 选择逻辑独立于具体渲染实现
- fallback 链清晰存在

### 工程层

- `build_report` 能说明实际走了哪个 backend
- worker 日志能说明 backend 命中和回退
- CI 至少覆盖 legacy backend 和 ffmpeg stable backend

### 产品层

- 用户即使不知道 backend 细节，也不会因为新增后端损伤可用性
- 新 backend 不支持时，结果仍然能稳定导出

---

## 十二、一句话结论

可以增加引擎，而且这是合理方向。  
但正确做法不是“推翻旧引擎”，而是：

- 把当前 render 层正式抽象成多 backend 架构
- 先让现有 `FFmpeg/stable` 成为正式主 backend
- 再让新 backend 以白名单方式接入长视频正式导出
- 始终保留旧路径兜底和自动回退

只有这样，新增引擎才会让项目更成熟，而不是更混乱。

