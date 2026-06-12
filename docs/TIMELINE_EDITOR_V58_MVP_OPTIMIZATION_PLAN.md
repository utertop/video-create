# Video-Create V5.8 Timeline Editor MVP 成熟优化规划方案

版本：V5.8  
定位：Timeline Editor MVP  
目标：把 V5.7 已落地的 Timeline Kernel 打磨成用户能自然使用的基础编辑器。

---

## 1. 当前基线

V5.7 阶段已经完成 Timeline Kernel 的主链路建设，当前项目具备继续进入编辑器体验打磨的基础。

已具备能力：

- `timeline.json` 可由 Python 生成器生成。
- 前端已接入 `v5Timeline` 状态。
- Timeline 可编译回 `render_plan.json`。
- Preview / Final / Cache 已有画质护栏与隔离策略。
- Build Report V2 已兼容 Timeline / Render Plan 信息。
- Recovery / Migration 已形成基础闭环。
- 主工作台、诊断中心、设置中心已经完成初步产品分区。
- 只读 Timeline UI 已替换旧 segments timeline 展示。
- Timeline 基础编辑已经有最小闭环，预览和导出前可自动应用 dirty timeline。

这意味着 V5.8 不需要重新设计 Timeline 架构，而应该集中打磨“用户能不能顺手编辑、看懂状态、放心预览和导出”。

---

## 2. V5.8 产品定位

V5.8 不是专业 NLE 完整版本，也不是 Premiere / DaVinci 级别编辑器。

V5.8 的正确定位是：

> 一个面向 AI 旅行视频生成场景的 Timeline Editor MVP，让用户可以理解生成结果、做基础修改、预览修改、导出修改后的成片。

核心判断：

- 用户不需要一开始就拥有复杂剪辑软件的全部能力。
- 用户首先需要“看懂这条视频是怎么组成的”。
- 用户其次需要“改几个明显不合适的地方”。
- 用户最后需要“确认修改真的进入预览和导出结果”。

因此，V5.8 的重点是自然、稳定、可信，而不是功能堆叠。

---

## 3. V5.8 核心目标

V5.8 完成后，用户应该可以完成以下闭环：

1. 生成视频方案后，自动看到完整 Timeline。
2. 选中一个片段后，能在右侧 Inspector 看懂它是什么。
3. 能修改基础字段，例如标题、字幕、启用状态、图片时长、BGM 音量等。
4. 能调整片段顺序。
5. 能清楚知道当前 Timeline 是否有未应用修改。
6. 点击预览或导出时，系统会自动应用修改。
7. 修改后的结果能进入 `render_plan.json`，并反映到预览和最终导出。
8. 如果修改失败，用户能看到明确原因，系统能保留可恢复状态。

一句话验收：

> 用户不需要懂 `timeline.json` 或 `render_plan.json`，也能完成一次基础视频编辑并成功导出。

---

## 4. 非目标

以下能力不建议放进 V5.8 MVP：

- 专业级精确 trim / split / ripple edit。
- 多轨自由拖拽混剪。
- 嵌套 Timeline。
- 完整字幕编辑器。
- 视频特效栈。
- LUT / 调色系统。
- 复杂转场编辑器。
- 多人协作。
- 云端项目同步。
- 账号体系、邮箱授权登录、远程上报后台闭环。

这些能力更适合放到后续版本：

- V5.9：Trim / Split / Ripple Edit 以及更强预览体验。
- V6：成熟专业编辑器架构、素材级编辑、复杂轨道系统、云端账号与商业化闭环。

---

## 5. 架构原则

V5.8 必须继续遵守 V5.7 已建立的 Timeline 架构边界。

### 5.1 Timeline 是编辑意图源

前端编辑应该修改 `v5Timeline` / `timeline.json`。

UI 不应该直接编辑 `render_plan.json`。

### 5.2 Render Plan 是编译产物

`render_plan.json` 应该由 Timeline 编译生成。

用户点击应用、预览、导出时，系统应通过统一编译链路生成 Render Plan。

### 5.3 Preview / Final 保持画质护栏

预览可以使用 preview cache。

最终导出必须使用 final path 与 final cache 策略，不能被 preview 缓存污染。

### 5.4 Fallback 只用于恢复和兼容

如果 Timeline 缺失或损坏，可以 fallback 到 segments / render plan 展示。

但正常项目路径下，UI 应该优先进入完整 Timeline 数据驱动状态。

### 5.5 用户只感知编辑器，不感知内部 JSON

所有内部状态都应该转成用户可理解的 UI 文案：

- 未应用修改
- 已应用到预览
- 已应用到导出
- Timeline 已恢复
- 当前片段不可编辑
- 当前修改需要重新编译

---

## 6. 阶段规划

## 阶段 0：V5.8 启动门禁

目标：确认 V5.7 基线稳定，避免在脏状态上继续堆功能。

任务：

- 确认新项目生成后有 `timeline.json`。
- 确认主工作台默认使用 Timeline 数据，而不是 segments fallback。
- 确认 `timeline_compile_v5` 能正常生成 `render_plan.json`。
- 确认预览和导出前的 dirty timeline 自动应用逻辑可用。
- 确认诊断中心与设置中心不再干扰主工作台编辑体验。

建议检查：

```powershell
npm run build:web
cargo check --manifest-path .\src-tauri\Cargo.toml
npm run check
```

验收：

- 当前主分支可构建。
- 当前 UI 能打开 Timeline。
- 当前预览和导出主链路没有被 V5.7 改动破坏。

---

## 阶段 1：Timeline 编辑体验打磨

目标：让用户知道自己选中了什么、改了什么、是否需要应用。

任务：

- 优化 Timeline 选中态。
- 优化片段 hover 态。
- 增加明确的 dirty state 提示。
- 增加“应用修改到视频方案”主按钮。
- 应用中、应用成功、应用失败都有清楚状态。
- 禁用不可编辑字段时显示原因。
- 片段为空、Timeline 缺失、fallback 状态都有明确文案。
- 中文文案统一，不暴露过多内部字段。

建议涉及文件：

- `src/features/timeline/TimelineEditor.tsx`
- `src/features/timeline/TimelineTrack.tsx`
- `src/features/timeline/TimelineClip.tsx`
- `src/features/timeline/TimelineInspector.tsx`
- `src/styles.css`

验收：

- 用户能一眼看出当前选中片段。
- 用户能一眼看出 Timeline 是否有未应用修改。
- 应用按钮不会和预览、导出按钮的职责混淆。
- fallback 状态不会被误认为正常编辑状态。

---

## 阶段 2：Inspector 基础编辑成熟化

目标：右侧 Inspector 成为基础编辑入口。

建议 V5.8 MVP 支持字段：

- 片段标题。
- 字幕或显示文本。
- 启用 / 禁用片段。
- 图片片段时长。
- BGM 音量。
- 是否需要重新编译。

任务：

- 为可编辑字段提供清晰输入控件。
- 为数字字段提供最小值、最大值、步进限制。
- 为文本字段提供空值校验。
- 为不可编辑字段只读展示，不提供假编辑入口。
- 修改字段后立即进入 dirty state。
- 保存失败时保留用户编辑状态。

建议涉及文件：

- `src/features/timeline/TimelineInspector.tsx`
- `src/features/timeline/timelineOps.ts`
- `src/lib/engine.ts`
- `src/App.tsx`

验收：

- 修改标题后，Timeline UI 即时更新。
- 修改图片时长后，编译后的 Render Plan 时长同步变化。
- 禁用片段后，预览和导出不再包含该片段。
- 错误输入会被 UI 拦截，而不是等到后端报错。

---

## 阶段 3：Timeline 交互增强

目标：让编辑器从“能改”提升到“顺手改”。

任务：

- 优化拖拽排序手感。
- 增加片段拖拽前后的视觉提示。
- 支持点击片段选中。
- 支持键盘方向键切换片段。
- 支持 `Delete` 或按钮删除 / 禁用片段。
- 支持 Timeline 横向滚动。
- 支持 fit-to-width。
- 支持基础 zoom in / zoom out。
- hover 时显示片段摘要 tooltip。

建议涉及文件：

- `src/features/timeline/TimelineEditor.tsx`
- `src/features/timeline/TimelineTrack.tsx`
- `src/features/timeline/TimelineClip.tsx`
- `src/features/timeline/timelineOps.ts`
- `src/styles.css`

验收：

- 8 到 20 个片段时仍然可读、可选、可拖动。
- 拖拽不会造成片段错位或状态丢失。
- 键盘选择不会触发浏览器默认滚动干扰。
- 缩放和滚动不会破坏布局。

---

## 阶段 4：应用、预览、导出信任闭环

目标：用户相信“我改的东西真的生效了”。

任务：

- 点击预览前，如果 Timeline dirty，自动保存并编译。
- 点击导出前，如果 Timeline dirty，自动保存并编译。
- 自动应用过程中锁定重复提交。
- 应用成功后刷新 Build Report V2 摘要。
- 应用失败后保留 dirty state，并显示失败原因。
- 成功预览后提示当前预览基于最新 Timeline。
- 成功导出后记录 Timeline revision / build report 信息。

建议涉及文件：

- `src/App.tsx`
- `src/lib/engine.ts`
- `src/features/timeline/TimelineEditor.tsx`
- `video_engine/timeline_compile.py`
- `video_engine/build_report.py`

验收：

- 用户修改 Timeline 后直接点预览，预览结果包含修改。
- 用户修改 Timeline 后直接点导出，最终成片包含修改。
- 编译失败不会覆盖可恢复 Timeline。
- Build Report 能说明本次输出来自 Timeline 编译链路。

---

## 阶段 5：最小 Undo / Redo

目标：降低用户编辑心理成本。

V5.8 只做 Timeline 层面的最小撤销重做，不做项目级历史。

任务：

- 为 Timeline 操作建立 snapshot stack。
- 支持撤销字段编辑。
- 支持撤销排序。
- 支持撤销启用 / 禁用。
- 限制历史长度，避免内存无限增长。
- dirty state 与 undo / redo 状态保持一致。

建议涉及文件：

- `src/features/timeline/useTimelineHistory.ts`
- `src/features/timeline/timelineOps.ts`
- `src/features/timeline/TimelineEditor.tsx`

验收：

- 连续编辑 5 次后可以逐步撤销。
- 撤销后可以重做。
- 应用成功后历史策略明确，不出现“撤销到已应用前但 UI 不知道”的混乱状态。

---

## 阶段 6：保存与恢复体验完善

目标：让基础编辑可以放心使用，不怕误操作或异常退出。

任务：

- Timeline 修改后写入项目本地状态。
- App 重启后能恢复上次 Timeline。
- 检测到坏 Timeline 时进入恢复提示。
- 保留 migration 记录给诊断中心。
- 用户可从诊断中心查看恢复来源。
- 主工作台只展示必要恢复提示，不展示研发细节。

建议涉及文件：

- `src/App.tsx`
- `src/lib/engine.ts`
- `src-tauri/src/lib.rs`
- `video_engine/timeline.py`
- `video_engine/timeline_compile.py`

验收：

- 编辑后关闭应用，再打开仍能看到修改后的 Timeline。
- 损坏 Timeline 不会导致白屏。
- 恢复状态对用户清楚，对研发可追踪。

---

## 阶段 7：MVP 验收与打包

目标：用一组真实用户路径确认 V5.8 可交付。

验收路径：

1. 新建一个旅行视频项目。
2. 生成 AI 视频方案。
3. 自动进入 Timeline 编辑状态。
4. 修改一个片段标题。
5. 调整一个图片片段时长。
6. 禁用一个不需要的片段。
7. 调整两个片段顺序。
8. 点击预览，确认结果包含修改。
9. 点击导出，确认最终视频包含修改。
10. 打开 Build Report，确认 Timeline / Render Plan 信息可追踪。
11. 重启应用，确认 Timeline 可恢复。

建议检查：

```powershell
npm run build:web
cargo check --manifest-path .\src-tauri\Cargo.toml
npm run check
npm run tauri build
```

验收：

- Web 构建通过。
- Rust 检查通过。
- 自动检查通过。
- Tauri release 可打包。
- `src-tauri\target\release\video-create-studio.exe` 可运行。

---

## 7. 文件改造清单

重点前端文件：

- `src/App.tsx`
- `src/lib/engine.ts`
- `src/features/timeline/TimelineEditor.tsx`
- `src/features/timeline/TimelineTrack.tsx`
- `src/features/timeline/TimelineClip.tsx`
- `src/features/timeline/TimelineInspector.tsx`
- `src/features/timeline/timelineOps.ts`
- `src/styles.css`

建议新增文件：

- `src/features/timeline/useTimelineHistory.ts`
- `src/features/timeline/timelineValidation.ts`
- `src/features/timeline/timelineEditorState.ts`

重点后端文件：

- `src-tauri/src/lib.rs`
- `video_engine/timeline.py`
- `video_engine/timeline_compile.py`
- `video_engine/build_report.py`

重点测试文件：

- `tests/`
- `video_engine/tests/`
- 前端现有检查脚本对应测试入口。

---

## 8. V5.8 MVP 验收清单

- [ ] 新项目生成后默认进入 Timeline 数据驱动状态。
- [ ] 正常项目不再显示 `segments fallback` 作为主编辑状态。
- [ ] 用户可以选中 Timeline 片段。
- [ ] 用户可以修改基础文本字段。
- [ ] 用户可以修改图片片段时长。
- [ ] 用户可以启用 / 禁用片段。
- [ ] 用户可以调整片段顺序。
- [ ] Timeline dirty state 清楚可见。
- [ ] 点击应用后可生成最新 Render Plan。
- [ ] 点击预览前会自动应用 dirty Timeline。
- [ ] 点击导出前会自动应用 dirty Timeline。
- [ ] 预览结果包含 Timeline 修改。
- [ ] 最终导出结果包含 Timeline 修改。
- [ ] Build Report V2 能追踪 Timeline 编译信息。
- [ ] Timeline 损坏时有恢复路径。
- [ ] 诊断中心可查看恢复和编译细节。
- [ ] 主工作台不暴露过多研发字段。
- [ ] 最小 Undo / Redo 可用于支持的编辑操作。
- [ ] `npm run build:web` 通过。
- [ ] `cargo check --manifest-path .\src-tauri\Cargo.toml` 通过。
- [ ] `npm run check` 通过。
- [ ] `npm run tauri build` 通过。

---

## 9. 风险与控制

### 风险 1：过早做专业剪辑能力

控制：

- V5.8 只做基础编辑。
- trim / split / ripple edit 放到 V5.9。
- 多轨自由剪辑放到 V6。

### 风险 2：UI 直接修改 Render Plan

控制：

- UI 只改 Timeline。
- Render Plan 只由 compile 生成。
- 所有 preview / export 入口统一走 apply timeline。

### 风险 3：Fallback 状态被当作正常编辑状态

控制：

- fallback UI 只用于恢复、兼容、诊断。
- 正常项目必须优先使用 `v5Timeline`。
- fallback badge 文案要明确。

### 风险 4：用户不知道修改是否生效

控制：

- dirty state 常驻可见。
- 应用成功后明确提示。
- 预览和导出自动应用。
- Build Report 记录 Timeline revision。

### 风险 5：编辑失败造成项目不可恢复

控制：

- 保存前保留旧 Timeline。
- 编译失败不覆盖可用 Render Plan。
- Recovery / Migration 写入诊断信息。

---

## 10. 版本建议

建议版本线：

- V5.7：Timeline Kernel 闭环。
- V5.8：Timeline Editor MVP。
- V5.9：Trim / Split / Ripple Edit 与预览体验增强。
- V6.0：成熟 Timeline Editor 架构与商业化产品闭环。

因此，当前下一阶段命名为：

> V5.8 Timeline Editor MVP

这是合理的，不建议直接跳到 V6。

V6 应该留给架构和产品形态都明显升级的版本，例如素材级编辑、多轨编辑、账号授权、远程诊断、商业化设置中心、云端同步等完整体系。

---

## 11. 推荐开干顺序

最建议的执行顺序：

1. 阶段 0：V5.8 启动门禁。
2. 阶段 1：Timeline 编辑体验打磨。
3. 阶段 2：Inspector 基础编辑成熟化。
4. 阶段 4：应用、预览、导出信任闭环。
5. 阶段 5：最小 Undo / Redo。
6. 阶段 3：Timeline 交互增强。
7. 阶段 6：保存与恢复体验完善。
8. 阶段 7：MVP 验收与打包。

原因：

- 先确认基线。
- 再把用户最容易感知的编辑体验打磨好。
- 再保证修改一定能进入预览和导出。
- 最后补齐撤销、交互增强、恢复、打包验收。

---

## 12. 最终交付定义

V5.8 完成时，Video-Create 应该从“AI 生成视频工具”向“AI 生成 + 基础可编辑视频工具”迈进一步。

最终交付不以功能数量为标准，而以用户闭环为标准：

> 用户生成视频后，可以自然地在 Timeline 上调整结果，预览确认，再导出最终视频。

只要这个闭环稳定、清楚、可信，V5.8 就达到了 MVP 目标。

---

## 13. 当前代码情况评估

基于当前项目代码状态，V5.8 可以开始，但建议按阶段推进，不建议一次性大改。

当前代码已经具备 V5.8 的关键前提：

- `src/App.tsx` 已经接入 `v5Timeline` 状态。
- `src/lib/engine.ts` 已经提供 `saveTimelineV5`、`timelineGenerateV5`、`timelineCompileV5`。
- `src-tauri/src/lib.rs` 已经提供 Timeline 保存、生成、编译命令。
- `src/features/timeline/TimelineEditor.tsx` 已经能优先展示 Timeline，缺失时 fallback 到 Render Plan。
- `src/features/timeline/TimelineInspector.tsx` 已经有基础编辑入口。
- `src/features/timeline/timelineOps.ts` 已经支持基础编辑操作，并能标记 dirty、写入 edit metadata、生成 invalidation hint。
- `video_engine/timeline.py` 和 `video_engine/timeline_compile.py` 已经形成 Timeline 生成与编译链路。
- `tests/` 下已有 Timeline schema、generate、edit ops、compile、invalidation、recovery、Build Report V2 相关 smoke test。

因此，V5.8 不是从零建设 Timeline Editor，也不是推翻 V5.7 架构。

更准确的判断是：

> 当前项目已经有 Timeline Editor 的骨架，V5.8 要做的是把它从“能用的工程闭环”打磨成“用户能自然使用的编辑器 MVP”。

## 14. 方案可行性与改动风险

V5.8 方案整体可行，且不会天然破坏原有结构。

原因：

- 方案继续遵守 Timeline 是编辑源、Render Plan 是编译产物的架构边界。
- 方案没有要求 UI 直接编辑 `render_plan.json`。
- 方案没有要求重写 Python 渲染链路。
- 方案没有要求推翻现有主工作台、诊断中心、设置中心分区。
- 方案的核心改动集中在 `src/features/timeline/` 和少量 `src/App.tsx` 编排逻辑。

推荐风险分级：

| 阶段 | 改动量 | 风险判断 |
| --- | --- | --- |
| 阶段 0：启动门禁 | 小 | 主要是检查，不应改动主结构 |
| 阶段 1：编辑体验打磨 | 小到中 | UI 状态、文案、选中态、dirty 提示为主 |
| 阶段 2：Inspector 成熟化 | 中 | 会影响基础编辑体验，但不应动渲染架构 |
| 阶段 3：Timeline 交互增强 | 中到偏大 | 拖拽、缩放、键盘操作需要谨慎 |
| 阶段 4：应用/预览/导出闭环 | 中 | 当前已有基础，主要补状态和失败处理 |
| 阶段 5：Undo / Redo | 中到偏大 | 必须限制在 Timeline 层，不能扩成项目级历史 |
| 阶段 6：保存与恢复 | 中 | 已有基础，重点是体验和边界补齐 |
| 阶段 7：验收打包 | 小到中 | 主要是验证和 release 构建 |

必须控制的风险：

- 不要继续把大量 Timeline 编辑逻辑堆进 `src/App.tsx`。
- 不要让 UI 直接修改 Render Plan。
- 不要把 fallback 状态当作正常编辑状态。
- 不要在 V5.8 就做完整专业剪辑器能力。
- 不要把 Undo / Redo 做成全项目历史。

推荐实现原则：

- 新增编辑体验优先放进 `src/features/timeline/`。
- `src/App.tsx` 只负责状态编排、保存、编译、预览、导出。
- Timeline UI 只表达编辑意图。
- Render Plan 继续由 compile 链路统一生成。

结论：

> V5.8 可以开始，改动不算小，但属于产品化增强，不属于架构级重构。只要按阶段推进，不会破坏原来整体结构。

## 15. V5.8 UI 形态建议

V5.8 的 UI 不应该把所有编辑控件塞进当前主工作台区域。

当前主工作台已经承载了素材、参数、引擎、AI 蓝图、预览、导出等流程。如果继续把完整 Timeline 编辑控件全部放在原页面里，会出现三个问题：

- 页面空间不足。
- 用户分不清“生成流程”和“编辑流程”。
- 后续做缩放、拖拽、撤销、片段详情时会越来越拥挤。

因此，V5.8 推荐采用三层 UI 形态。

### 15.1 主工作台 Timeline：轻量展示

主工作台里的 Timeline 主要承担总览和快速反馈。

适合保留：

- Timeline 概览。
- 当前片段选中态。
- dirty state。
- 应用 Timeline 编辑。
- 预览。
- 导出。
- fallback / recovery 的最小提示。

不适合放太多：

- 大量字段编辑。
- 复杂样式编辑。
- 长文本字幕编辑。
- 多轨精细操作。
- 高级撤销历史。

主工作台的目标是让用户知道：

> 当前视频结构是什么，是否有改动，能不能预览和导出。

### 15.2 片段编辑：优先使用右侧抽屉

V5.8 MVP 最推荐的编辑形态是右侧抽屉，而不是传统居中弹窗。

原因：

- 抽屉比弹窗更适合编辑器。
- 用户编辑片段时仍然能看到 Timeline 上下文。
- 不会打断主工作台流程。
- 改动量比新建完整编辑器页面更小。
- 后续可以自然升级成专用 Timeline Editor 页面。

右侧抽屉适合承载：

- 片段标题。
- 字幕或显示文本。
- 启用 / 禁用。
- 图片时长。
- BGM 音量。
- 标题样式。
- 片段来源信息。
- 重新编译提示。
- 保存 / 应用状态。
- 基础错误提示。

交互建议：

- 用户点击 Timeline 片段后，打开右侧编辑抽屉。
- 抽屉标题显示当前片段类型和名称。
- 抽屉顶部显示是否已修改。
- 抽屉底部提供应用、撤销、关闭操作。
- 关闭抽屉时，如果有未应用修改，需要保留 dirty state，而不是静默丢失。

### 15.3 完整 Timeline 编辑器页面：作为后续增强

如果后续需要更大编辑空间，可以增加“打开完整编辑器”入口。

完整编辑器页面更适合放到 V5.8 后半段或 V5.9。

适合承载：

- 大 Timeline。
- 多轨展示。
- 缩放。
- 横向滚动。
- 拖拽排序。
- 快捷键。
- Undo / Redo。
- 更完整 Inspector。
- 预览联动。

推荐页面结构：

- 顶部：编辑器工具栏。
- 中间：完整 Timeline。
- 右侧：Inspector。
- 底部或侧边：状态栏、应用状态、编译状态。

这个页面的目标是：

> 用户进入专注编辑模式，不再被主工作台的素材、参数、引擎配置打扰。

### 15.4 V5.8 推荐落地顺序

推荐 UI 落地顺序：

1. 保留主工作台 Timeline 轻量展示。
2. 将当前 Inspector 升级为右侧抽屉。
3. 抽屉内完成基础编辑控件成熟化。
4. 主工作台只保留关键状态和操作按钮。
5. 等基础闭环稳定后，再考虑完整 Timeline 编辑器页面。

不建议 V5.8 一开始就直接做完整新页面。

原因：

- 当前代码已有主工作台 Timeline 和 Inspector 骨架。
- 抽屉改造可以复用现有组件。
- 风险比新页面低。
- 更符合 MVP 的节奏。

最终 UI 原则：

> 主工作台负责生成和总览，右侧抽屉负责基础编辑，完整编辑器页面留给后续专业化增强。

---

## 16. 阶段 7 执行记录

执行日期：2026-06-12

阶段状态：自动验收与 release 打包已通过。

已完成检查：

- `npm run build:web`：通过。
- `cargo check --manifest-path .\src-tauri\Cargo.toml`：通过。
- `npm run check`：通过，核心套件 18/18。
- `npm run build:desktop`：通过。

已生成产物：

- `src-tauri\target\release\video-create-studio.exe`
- `src-tauri\target\release\bundle\nsis\Video Create Studio_5.6.2_x64-setup.exe`

本阶段结论：

- V5.8 Timeline Editor MVP 的核心工程验收通过。
- Web 前端、Tauri 后端、Python Timeline/Render Plan smoke tests、项目恢复 smoke tests 均未发现回归。
- release 桌面端 exe 与 NSIS 安装包已重新生成。

仍建议保留的人工验收：

- 使用真实素材新建项目，完整走一遍“生成方案 -> 编辑 Timeline -> 预览 -> 导出 -> 重启恢复”。
- 重点确认标题修改、图片时长调整、片段禁用、片段排序在预览和最终导出中都生效。
- 打开 Build Report，确认 Timeline / Render Plan 的追踪信息符合预期。
