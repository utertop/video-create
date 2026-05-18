# 标题模板与照片运动质感提升方案

## 目标

这轮升级主要解决两个直接影响观看体验的质量问题：

- 章节标题和叠加文字目前仍然像“工程参数组合”，缺少一个真正有设计感的标题包装系统。
- 照片段运动在长时间观看时偶尔会显得晃、飘或让人眩晕，影响成片舒适度。

产品目标是让自动生成的视频在观感上更像“被认真包装过的成片”，而不是单纯把素材拼起来。

## 问题一：标题文字质感不足

### 当前状态

- 蓝图编辑器目前把文字预设和动效拆成两个独立控制项。
- 现有预设虽然能用，但数量偏少，视觉上也不够适合当代旅行 / vlog 包装。
- 预览能力和文字动效实验区很有价值，应该保留。
- 开场标题、章节卡、叠加标题、结尾卡和封面生成，应该使用同一套标题模板语言。

### 新模型

把逐行的“风格 + 动效”控制替换成一个“标题模板”按钮。一个模板应该是完整设计包，包含：

- 字体方向
- 版式布局
- 纹理或装饰处理
- 最匹配的动效
- 兼容静态导出的模式，供封面和静态标题卡使用

实验区继续保留更强控制力：用户可以选择模板包、单独覆盖动效、即时预览、真实渲染低清预览、应用到当前章节 / 同类型章节 / 所有章节，并保存为默认值。

### 模板集合

| 预设 ID | 中文名称 | 匹配动效 ID | 适用场景 |
| --- | --- | --- | --- |
| `cinematic_bold` | 电影感粗体 | `cinematic_reveal` | 山景、城市大全景、戏剧化章节切分 |
| `travel_postcard` | 旅行明信片 | `postcard_drift` | 旅行、美食、老街、温暖 vlog |
| `playful_pop` | 活泼跳色 | `playful_bounce` | 宠物、日常、轻松片段 |
| `impact_flash` | 冲击闪现 | `impact_slam` | 运动、滑雪、高能场景 |
| `minimal_editorial` | 极简编辑感 | `editorial_fade` | 建筑、摄影、城市氛围 |
| `documentary_lower_third` | 纪录片下三分之一字幕条 | `lower_third_slide` | 地点、人名、时间说明 |
| `handwritten_note` | 手写贴纸便签 | `handwritten_draw` | vlog 笔记、海边、随性旅行 |
| `neon_night` | 霓虹夜景 | `neon_flicker` | 夜城市、赛博感、夜生活 |
| `film_subtitle` | 胶片字幕 | `film_burn` | 温暖回忆、黄金时刻、电影感字幕 |
| `route_marker` | 路线标记 | `route_trace` | 路书、行程、天数标记 |

另外保留 `static_hold` 动效，用于封面、结尾卡和静态图片导出。

### 实施规则

- 为兼容旧数据，JSON 字段仍保留 `title_style.preset` 和 `title_style.motion`。
- 模板按钮一次性写入预设和匹配动效。
- 实验区仍可单独覆盖动效，包括 `static_hold`。
- 如果遇到旧预设或旧动效，统一归一到最接近的新模板 / 新动效。
- 封面、标题、结尾等静态渲染统一走同一套 renderer，`static_hold` 负责关闭动画。

## 问题二：照片运动舒适度不足

### 当前状态

- 静态图片会被施加 Ken Burns、推进或 punch zoom 等运动。
- 这样确实避免了“完全静止”的死板感，但在某些项目里会造成明显晃动或眩晕感。
- 旅行类项目中如果照片很多，这个问题会更突出。

### 新运动策略

默认的照片运动应当是“稳定且有质感”的：

- 不要有明显抖动。
- 普通照片段不使用弹跳式运动。
- 只保留非常慢、非常小幅度的缩放和位移。
- 尽量让画面视觉中心稳定。
- 更强的动势应主要放在标题文字，而不是每一张照片上。

### 运动映射

| 运动类型 | 旧体感 | 新行为 |
| --- | --- | --- |
| `ken_burns` | 位移感明显 | 改为非常缓慢的 2.2% 缩放 |
| `gentle_push` | 推进感偏强 | 改为 1.8% 的缓慢推进 |
| `slow_push` | 持续推进 | 改为 1.5% 的慢推进 |
| `subtle_ken_burns` | 虽轻但仍可感知 | 改为 1.2% 的轻呼吸感 |
| `punch_zoom` | 冲击式照片击打 | 降到 3.5%，仅保留短促 ease |
| `micro_zoom` | 小幅击打感 | 降到 2.5%，仅保留短促 ease |
| `none` / `still_hold` | 稳定 | 保持不变 |

## 验证要求

完成标题 renderer 或照片运动相关改动后，应至少运行：

```powershell
npm.cmd run build
python tests\smoke_v5_edit_strategy_compile.py
python tests\smoke_v5_low_res_preview.py
python tests\smoke_v5_video_geometry.py
```

如果改动可能影响音频或长视频稳定性，还应继续验证：

```powershell
python tests\smoke_v5_bgm_mix.py
python tests\smoke_v5_6_long_video_stability.py
```
