# MLT Backend 接入方案

## 相关文档

- [COMMERCIAL_PRODUCT_MATURITY_PLAN.md](./COMMERCIAL_PRODUCT_MATURITY_PLAN.md)
- [RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md](./RENDER_ENGINE_STRUCTURAL_ISSUES_AND_BACKEND_DECISION.md)
- [MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md](./MULTI_BACKEND_RENDER_ARCHITECTURE_PLAN.md)
- [VIDEO_SEGMENT_CACHE_AND_FFMPEG_EXPANSION.md](./VIDEO_SEGMENT_CACHE_AND_FFMPEG_EXPANSION.md)

## 目标

这份方案不是讨论“要不要做 MLT”，而是回答一个更具体的问题：

如何在当前仓库里，以最低风险把 `mlt_backend` 接入现有多 backend 架构，并且保持：

- `scan -> plan -> compile -> worker -> render` 主链不推翻
- 现有 `ffmpeg_stable_backend` 与 `legacy_moviepy_backend` 继续可用
- 新 backend 先白名单接管，失败时自动回退
- `build_report.json`、日志、诊断包能解释 MLT 是否命中、为什么回退

一句话结论：

推荐把 MLT 作为第三个正式 backend 接进当前 `render_backends/` 层，而不是作为新的“平行渲染系统”另起炉灶。

---

## 当前切入点

当前仓库已经有适合接入 MLT 的 backend 抽象边界：

- 选择器：[`render_backends/backend_selector.py`](d:/Automatic/video_create/render_backends/backend_selector.py)
- backend 基础类型：[`render_backends/base.py`](d:/Automatic/video_create/render_backends/base.py)
- 现有 backend 导出：[`render_backends/__init__.py`](d:/Automatic/video_create/render_backends/__init__.py)
- render 分发入口：[`video_engine_v5.py`](d:/Automatic/video_create/video_engine_v5.py:8318)
- backend 决策入口：[`video_engine_v5.py`](d:/Automatic/video_create/video_engine_v5.py:7865)

这意味着：

- 不需要先改前端协议
- 不需要先改 worker 任务结构
- 不需要先改 `render_plan.json` 基本 schema
- 可以先把 MLT 接成“render 执行层候选 backend”

---

## 总体策略

推荐采用下面这条顺序：

1. 先新增 `mlt_backend`，但默认不命中
2. 先做环境探测、能力白名单、自动回退
3. 先只接正式导出，不接 preview
4. 先只吃简单时间线场景，不碰复杂章节卡和重动画
5. 先保证“稳定导出 + 可解释”，再追求“覆盖更多效果”

### 第一阶段支持范围

建议 MLT 首批只支持这些场景：

- 图片与视频混编
- 单轨主画面时间线
- 简单 cut
- 轻量 crossfade
- 单层标题/字幕 overlay
- 常规 BGM 混音
- 长视频正式导出

第一阶段不要支持：

- 复杂章节卡拼装
- 多层字幕动画
- 复杂 motion preset
- 高度依赖当前 MoviePy 路径的特殊转场
- preview 实时预览链路

---

## 建议的文件级拆分

下面按当前仓库结构给出推荐拆分。

### 1. `render_backends/base.py`

目标：继续作为统一 backend 结果模型，不大改方向，只补 MLT 所需字段。

建议新增：

- `capability_flags` 继续保留，并为 MLT 补充约定值
  - `mlt`
  - `timeline`
  - `xml_project`
  - `ffmpeg_consumer`
  - `fallback_moviepy`
- `backend_mode` 继续沿用 `preview` / `final_render`
- `reason` 细化为可落到 report 的稳定字符串
  - `mlt_backend_selected`
  - `mlt_not_installed`
  - `mlt_unsupported_segment_type`
  - `mlt_unsupported_transition`
  - `mlt_validation_failed`

建议新增 helper：

- `merge_backend_reason_tags(...)`
  - 统一拼接命中原因、回退原因、白名单拒绝原因

### 2. `render_backends/backend_selector.py`

目标：在这里决定 MLT 是否命中，而不是把判断散进 `video_engine_v5.py`。

建议新增：

- `should_use_mlt_backend(plan, params, probe)`
- `collect_mlt_rejection_reasons(plan, params, probe)`

建议修改 `resolve_render_backend(...)`：

- `preview=true` 仍直接走 `legacy_moviepy_backend`
- 正式导出时，优先顺序改为：
  1. `mlt_backend`
  2. `ffmpeg_stable_backend`
  3. `legacy_moviepy_backend`

首批命中条件建议：

- `preview != true`
- `render_mode != long_stable` 时也可尝试，但优先针对正式导出
- plan 内 segment 类型只包含白名单
- transition 只包含 `cut` / `crossfade`
- overlay 数量、title 类型、motion 类型在白名单内
- 本机已探测到 MLT 可用

### 3. `render_backends/mlt_backend.py`

这是新的正式 backend 文件。

职责建议只做三件事：

1. 接收统一输入
2. 调用 MLT project builder 生成 `.mlt` 或等价中间文件
3. 启动 MLT consumer 导出并做结果校验

建议接口与现有 backend 保持一致：

```python
def run_render(
    engine: Any,
    decision: BackendDecision,
    plan: Dict[str, Any],
    output: str,
    params: Dict[str, Any],
    plan_path: Optional[str] = None,
) -> BackendExecutionResult:
    ...
```

建议内部步骤：

1. `probe_mlt_runtime()`
2. `validate_plan_for_mlt(...)`
3. `build_mlt_project(...)`
4. `run_mlt_consumer(...)`
5. `engine._v56_validate_video(...)`
6. 失败时抛出带稳定 reason 的异常，由上层触发 fallback

建议输出中间产物到：

- `.video_create_project/mlt/project.mlt`
- `.video_create_project/mlt/assets_manifest.json`
- `.video_create_project/mlt/render.log`

### 4. `render_backends/mlt_project_builder.py`

建议新建，专门负责从现有 `render_plan` 生成 MLT 时间线描述。

职责：

- 把 `render_plan.segments` 映射为 MLT producer / playlist / tractor
- 处理基础转场
- 处理简单 overlay
- 输出稳定的中间项目文件

这里是后续 MLT 能力扩张的主战场，不要把 XML/时间线组装塞进 `mlt_backend.py`。

建议拆成几个函数：

- `build_mlt_project(plan, params, output_path, working_dir) -> MltProjectBuildResult`
- `map_segment_to_mlt_entry(segment, ...)`
- `map_transition_to_mlt_mix(...)`
- `map_text_overlay_to_mlt_filter(...)`

建议新建数据结构：

- `MltProjectBuildResult`
  - `project_path`
  - `asset_manifest_path`
  - `supported`
  - `rejection_reasons`
  - `route_counts`

### 5. `render_backends/mlt_probe.py`

建议新建，专门探测 MLT 安装和能力。

职责：

- 探测 `melt` 或项目打包内的 MLT runtime 是否存在
- 探测 consumer / filter / transition 可用性
- 缓存探测结果，避免每次 render 都冷启动

建议输出：

- `MltProbeResult`
  - `available`
  - `binary_path`
  - `version`
  - `consumers`
  - `transitions`
  - `filters`
  - `reason`

首批只需要够用，不需要一次探测所有插件。

### 6. `render_backends/__init__.py`

建议新增导出：

- `run_mlt_backend`

如果新增 probe/result 类型，也可一并导出，但保持克制，避免把 builder 内部对象都暴露出来。

### 7. `video_engine_v5.py`

这是最关键的接入点，但不建议大改。

建议修改的地方：

#### a. backend 调用分发

在 [`video_engine_v5.py`](d:/Automatic/video_create/video_engine_v5.py:8324) 附近增加：

- `if backend_name == "mlt_backend": return run_mlt_backend(...)`

#### b. backend 决策输入

在 [`video_engine_v5.py`](d:/Automatic/video_create/video_engine_v5.py:7865) 附近，把 MLT probe 结果作为 selector 的输入之一。

建议方式：

- `backend_selector_resolve_render_backend(plan, params, _v56_should_use_stable_renderer, probe_mlt_runtime)`

如果不想立刻改函数签名，也可以先让 `backend_selector.py` 内部自己 import probe。

#### c. build_report 扩展

建议在现有 backend report payload 上补：

- `selected_backend = "mlt_backend"`
- `actual_backend_name`
- `backend_reason`
- `backend_rejection_reasons`
- `mlt_project_path`
- `mlt_probe_version`
- `mlt_route_counts`

#### d. fallback 执行策略

建议不要让 `mlt_backend.py` 自己直接调用 `legacy_moviepy_backend`。

更稳的做法是：

- `mlt_backend.py` 只负责抛出结构化失败
- `video_engine_v5.py` 统一接住异常
- 按 `decision.fallback_chain` 执行下一个 backend

也就是说，真正的 fallback orchestration 最终应收口在 `video_engine_v5.py`，不要散在每个 backend 里各自实现。

### 8. `video_engine_worker.py`

第一阶段不建议改协议。

只建议补两类事件：

- `backend_selected`
- `backend_fallback`

事件内容建议包含：

- `selected_backend`
- `actual_backend_name`
- `reason`
- `fallback_used`
- `fallback_reason`

这样前端和诊断包可以直接消费。

### 9. `src-tauri/src/lib.rs`

第一阶段不建议改 invoke 参数结构。

建议只做两件事：

- startup self-check 增加一个可选项：MLT runtime 是否存在
- diagnostic bundle 导出时，如果 report 中有 MLT 字段，照常带出

不要在第一阶段就做：

- GUI 上增加“手选 MLT backend”开关
- 单独的 MLT 安装向导

### 10. `src/lib/engine.ts`

建议只补类型，不改交互。

建议补充：

- `RenderRecoverySummary` 或 build report 相关类型中，为 MLT 预留字段
- 前端日志/诊断解析里接受新的 `backend_selected`、`backend_fallback`

### 11. `tests/`

建议新增三类测试。

#### a. selector 测试

建议新建：

- `tests/smoke_v5_mlt_selector.py`

覆盖：

- MLT 不可用时不命中
- preview 不命中
- 白名单 segment 命中
- 非白名单 transition 自动回退

#### b. project builder 测试

建议新建：

- `tests/smoke_v5_mlt_project_builder.py`

覆盖：

- render_plan 到 MLT project 文件生成
- 中文路径
- 图片、视频、音频混编
- 简单 crossfade

#### c. backend 集成测试

建议新建：

- `tests/smoke_v5_mlt_backend.py`

覆盖：

- 正常导出
- MLT 缺失自动回退
- 导出结果校验失败回退
- `build_report.json` 中 MLT 字段存在

### 12. `scripts/`

建议新增：

- `scripts/verify-mlt-runtime.mjs`
  - 检查打包产物内是否有 `melt` 或 MLT runtime

如后续需要 Windows 打包集成，可再增加：

- `scripts/package-mlt-runtime.ps1`

---

## 推荐的新文件清单

建议第一版新增这些文件：

- [render_backends/mlt_backend.py](d:/Automatic/video_create/render_backends/mlt_backend.py)
- [render_backends/mlt_project_builder.py](d:/Automatic/video_create/render_backends/mlt_project_builder.py)
- [render_backends/mlt_probe.py](d:/Automatic/video_create/render_backends/mlt_probe.py)
- [tests/smoke_v5_mlt_selector.py](d:/Automatic/video_create/tests/smoke_v5_mlt_selector.py)
- [tests/smoke_v5_mlt_project_builder.py](d:/Automatic/video_create/tests/smoke_v5_mlt_project_builder.py)
- [tests/smoke_v5_mlt_backend.py](d:/Automatic/video_create/tests/smoke_v5_mlt_backend.py)
- [scripts/verify-mlt-runtime.mjs](d:/Automatic/video_create/scripts/verify-mlt-runtime.mjs)

建议修改这些文件：

- [render_backends/base.py](d:/Automatic/video_create/render_backends/base.py)
- [render_backends/backend_selector.py](d:/Automatic/video_create/render_backends/backend_selector.py)
- [render_backends/__init__.py](d:/Automatic/video_create/render_backends/__init__.py)
- [video_engine_v5.py](d:/Automatic/video_create/video_engine_v5.py)
- [video_engine_worker.py](d:/Automatic/video_create/video_engine_worker.py)
- [src-tauri/src/lib.rs](d:/Automatic/video_create/src-tauri/src/lib.rs)
- [src/lib/engine.ts](d:/Automatic/video_create/src/lib/engine.ts)

---

## render_plan 到 MLT 的首批映射策略

### 建议直接复用的字段

从当前 `render_plan` 里，第一版优先使用：

- `segments[].type`
- `segments[].source_path`
- `segments[].duration`
- `segments[].start_time`
- `segments[].end_time`
- `segments[].text`
- `segments[].subtitle`
- `segments[].transition`
- `segments[].overlay_text`
- `segments[].overlay_subtitle`
- `render_settings.aspect_ratio`
- `render_settings.fps`
- `render_settings.audio`

### 建议第一版忽略或拒绝的字段

如果遇到这些，第一版直接拒绝并回退更稳：

- 复杂 `motion_config`
- 复杂 `transition_config`
- 多层 overlay
- 章节背景桥接的高级逻辑
- 当前依赖 MoviePy 精细排版的标题样式

### 白名单 rejection reason 建议

建议统一使用稳定字符串，方便写测试和诊断：

- `mlt_segment_type_not_supported`
- `mlt_transition_not_supported`
- `mlt_motion_config_not_supported`
- `mlt_title_style_not_supported`
- `mlt_multiple_overlay_layers_not_supported`
- `mlt_runtime_not_available`

---

## fallback 策略

建议明确成两层 fallback。

### 层 1：选择器级 fallback

在执行前就判定：

- MLT 不可用
- plan 不满足白名单

直接选：

- `ffmpeg_stable_backend`
- 或 `legacy_moviepy_backend`

### 层 2：执行级 fallback

在 MLT 已命中后执行失败：

- MLT 进程失败
- project 文件生成失败
- consumer 导出失败
- 输出校验失败

统一回退到：

1. `ffmpeg_stable_backend`
2. `legacy_moviepy_backend`

建议不要让 MLT 失败后直接“放弃导出”。

---

## build_report 增强建议

建议在现有 `build_report.json` 里新增一个稳定小节：

```json
{
  "backend": {
    "selected_backend": "mlt_backend",
    "actual_backend_name": "mlt_backend",
    "backend_family": "standard_timeline_gpu_candidate",
    "backend_mode": "final_render",
    "reason": "mlt_backend_selected",
    "fallback_chain": [
      "mlt_backend",
      "ffmpeg_stable_backend",
      "legacy_moviepy_backend"
    ],
    "fallback_used": null,
    "fallback_reason": null,
    "mlt_project_path": ".../.video_create_project/mlt/project.mlt",
    "mlt_probe_version": "..."
  }
}
```

如果回退，建议保留：

- 原始 `selected_backend = mlt_backend`
- `actual_backend_name = ffmpeg_stable_backend`
- `fallback_used = ffmpeg_stable_backend`
- `fallback_reason = mlt_validation_failed`

这样诊断时才看得出“试过 MLT，但最后没走成”。

---

## 分阶段实施顺序

### P0：接入骨架，不默认命中

交付目标：

- 文件结构到位
- probe 到位
- selector 能识别 MLT
- `video_engine_v5.py` 能分发到 MLT backend
- 但默认条件下仍以现有 backend 为主

## P0 可施工清单

下面把 P0 收敛成按提交粒度推进的 7 个小任务。

原则：

- 每个任务只解决一个层次的问题
- 每个任务完成后都应保持主流程可运行
- 前 4 个任务不要求真的导出成功，只要求骨架、探测、分发、诊断链路完整
- 第 5-7 个任务才开始让 MLT 真正参与受控白名单导出

### Task 1：补 backend 类型与导出骨架

建议提交标题：

- `render_backends: add mlt backend stubs and shared backend metadata`

修改文件：

- [render_backends/base.py](d:/Automatic/video_create/render_backends/base.py)
- [render_backends/__init__.py](d:/Automatic/video_create/render_backends/__init__.py)
- [render_backends/mlt_backend.py](d:/Automatic/video_create/render_backends/mlt_backend.py)
- [render_backends/mlt_probe.py](d:/Automatic/video_create/render_backends/mlt_probe.py)

交付内容：

- 新增 `run_mlt_backend(...)` 空实现或最小占位实现
- 新增 `probe_mlt_runtime()` 与 `MltProbeResult`
- 在 `base.py` 中补 MLT 专用 `reason` / `capability_flags` 约定
- 在 `__init__.py` 中导出 `run_mlt_backend`

验收标准：

- Python import 不报错
- 现有 backend 不受影响
- 还不改 selector，不让 MLT 命中

### Task 2：接入 runtime 探测与自检

建议提交标题：

- `mlt: add runtime probe and surface availability in diagnostics`

修改文件：

- [render_backends/mlt_probe.py](d:/Automatic/video_create/render_backends/mlt_probe.py)
- [src-tauri/src/lib.rs](d:/Automatic/video_create/src-tauri/src/lib.rs)
- 如有需要：[`scripts/verify-mlt-runtime.mjs`](d:/Automatic/video_create/scripts/verify-mlt-runtime.mjs)

交付内容：

- 探测 `melt` 或打包内 MLT runtime 是否存在
- 自检中增加一项可选检查：`mlt_runtime`
- 如果仓库已有 packaging check，则加一个 MLT runtime verify 脚本占位

验收标准：

- startup/self-check 能看见 MLT 是否可用
- MLT 缺失时给出稳定 code/reason
- 仍不影响现有 render 主流程

### Task 3：把 MLT backend 接进 render dispatch，但默认不命中

建议提交标题：

- `video_engine_v5: wire mlt backend into backend dispatch`

修改文件：

- [video_engine_v5.py](d:/Automatic/video_create/video_engine_v5.py)
- [render_backends/__init__.py](d:/Automatic/video_create/render_backends/__init__.py)

交付内容：

- 在 backend dispatch 中加上 `mlt_backend`
- 支持把 `_backend_decision`、`_backend_execution` 透传给 MLT backend
- 先不改 selector 逻辑，让 `resolve_render_backend()` 默认仍只选现有 backend

验收标准：

- 代码路径已能分发到 MLT backend
- 但没有白名单条件时，现有测试结果不变

### Task 4：补 selector 白名单与 rejection reason，但先只做“可解释”，不默认放量

建议提交标题：

- `backend_selector: add mlt whitelist evaluation and rejection reasons`

修改文件：

- [render_backends/backend_selector.py](d:/Automatic/video_create/render_backends/backend_selector.py)
- [render_backends/mlt_probe.py](d:/Automatic/video_create/render_backends/mlt_probe.py)

交付内容：

- 新增 `should_use_mlt_backend(...)`
- 新增 `collect_mlt_rejection_reasons(...)`
- 把 MLT 的命中条件和拒绝原因做成稳定字符串
- 可先加一个显式 gate，例如 `params["engine"] == "mlt_experimental"` 或内部实验 flag，避免默认命中

验收标准：

- selector 能解释“为什么没选 MLT”
- rejection reason 可写入 report / 日志
- 默认项目仍主要走现有 backend

### Task 5：实现 MLT project builder 的最小白名单映射

建议提交标题：

- `mlt: add minimal render_plan to mlt project builder`

修改文件：

- [render_backends/mlt_project_builder.py](d:/Automatic/video_create/render_backends/mlt_project_builder.py)
- [render_backends/mlt_backend.py](d:/Automatic/video_create/render_backends/mlt_backend.py)

交付内容：

- 新增 `build_mlt_project(...)`
- 首批只支持：
  - image/video segments
  - `cut`
  - 简单 `crossfade`
  - 单层 text overlay
- 输出 `.video_create_project/mlt/project.mlt`
- 不支持的内容返回结构化 rejection，而不是 silent fallback

验收标准：

- 给定简单 render plan 可以产出 MLT project 文件
- 中文路径和基础素材路径不炸
- builder 失败能稳定返回 rejection reason

### Task 6：让 MLT backend 真正执行最小导出，并统一回退

建议提交标题：

- `mlt: enable guarded final render execution with fallback`

修改文件：

- [render_backends/mlt_backend.py](d:/Automatic/video_create/render_backends/mlt_backend.py)
- [video_engine_v5.py](d:/Automatic/video_create/video_engine_v5.py)

交付内容：

- `mlt_backend.py` 调用 builder 和 `melt`/consumer 真正执行导出
- 输出后复用现有 `_v56_validate_video(...)`
- 失败时抛结构化错误
- 在 `video_engine_v5.py` 统一按 `fallback_chain` 回退到：
  1. `ffmpeg_stable_backend`
  2. `legacy_moviepy_backend`

验收标准：

- 白名单简单项目可导出
- MLT 执行失败时不会直接中断整单导出
- fallback 路径在日志里可见

### Task 7：补 report、worker 事件和测试闭环

建议提交标题：

- `mlt: add backend reporting events and smoke coverage`

修改文件：

- [video_engine_worker.py](d:/Automatic/video_create/video_engine_worker.py)
- [video_engine_v5.py](d:/Automatic/video_create/video_engine_v5.py)
- [src/lib/engine.ts](d:/Automatic/video_create/src/lib/engine.ts)
- [tests/smoke_v5_mlt_selector.py](d:/Automatic/video_create/tests/smoke_v5_mlt_selector.py)
- [tests/smoke_v5_mlt_project_builder.py](d:/Automatic/video_create/tests/smoke_v5_mlt_project_builder.py)
- [tests/smoke_v5_mlt_backend.py](d:/Automatic/video_create/tests/smoke_v5_mlt_backend.py)

交付内容：

- worker 事件补：
  - `backend_selected`
  - `backend_fallback`
- `build_report.json` 补：
  - `selected_backend`
  - `actual_backend_name`
  - `fallback_used`
  - `fallback_reason`
  - `mlt_project_path`
- 补 selector、builder、backend 三类 smoke test

验收标准：

- 诊断包和 build report 能解释 MLT 命中/回退
- 白名单项目、MLT 缺失、MLT 执行失败三种情况都有测试覆盖

## 推荐实施顺序

如果要最稳，我建议按下面节奏推进：

1. Task 1
2. Task 2
3. Task 3
4. Task 4
5. Task 5
6. Task 6
7. Task 7

不要把 Task 5-7 合成一个大提交。P0 最怕的是一口气把 builder、执行、fallback、report 全缠在一起，出了问题很难定位。

### P1：白名单正式导出

交付目标：

- 纯图片 / 纯视频 / 简单混编可稳定命中 MLT
- 自动回退稳定
- build report 可解释
- 新测试进入主线

### P2：扩大覆盖面

交付目标：

- 支持更多轻量 overlay
- 支持更多转场
- 提高长视频正式导出的 MLT 命中率

### P3：再决定是否把 MLT 提升为主 backend

这一步必须看真实数据，不要先拍脑袋：

- 实际耗时
- 失败率
- 输出一致性
- Windows 打包复杂度
- 后续维护成本

---

## 不建议现在做的事

- 不建议先改前端 UI 加“MLT 开关”
- 不建议先改 worker 协议大版本
- 不建议先让 preview 走 MLT
- 不建议先支持所有 title / motion / chapter card
- 不建议把 fallback 写散到各 backend 内部
- 不建议把 MLT 做成完全独立于现有 report/diagnostics 的平行系统

---

## 最终建议

这件事最稳的落地方式不是“引入一个很强的新引擎然后替换一切”，而是：

1. 让 `mlt_backend` 成为当前 `render_backends/` 里的第三个正式 backend
2. 先把它接进现有 selector、report、fallback、worker 事件体系
3. 先只吃简单正式导出白名单场景
4. 用真实项目数据决定它是否值得继续扩大覆盖面

如果照这个方案推进，MLT 会成为当前仓库里一个低风险、可验证、可回退的 backend 增强点，而不是新的结构性负担。
