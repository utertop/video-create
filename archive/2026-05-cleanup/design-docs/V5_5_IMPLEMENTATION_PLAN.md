# Video Create Studio V5.5 文字动效系统实施计划

本文档描述如何把当前静态文字渲染系统升级为基于模板的动态标题卡与叠加标题系统。

## 1. 数据模型更新

### 1.1 更新 `StorySection`

在 `video_engine_v5.py` 中为 `StorySection` 增加 `title_style` 字段。

```python
@dataclass
class TitleStyle:
    preset: str = "cinematic_bold"
    motion: str = "fade_slide_up"
    color_theme: str = "auto"
    position: str = "center"
    user_overridden: bool = False

@dataclass
class StorySection:
    ...
    title_style: Optional[TitleStyle] = None
```

### 1.2 更新 `RenderSegment`

为 `RenderSegment` 增加 `title_style` 字段。

## 2. 引擎逻辑：`TitleStyleRenderer`

在 `video_engine_v5.py` 中实现新的辅助类 `TitleStyleRenderer`，专门负责标题模板的视觉生成。

### 2.1 预设实现方案（基于 PIL）

- `cinematic_bold`：白色粗体字，搭配 20% 黑色遮罩。
- `travel_postcard`：奶油色底、边框效果、手写感字体。
- `playful_pop`：高饱和亮色、圆角矩形底板。
- `impact_flash`：高对比度、冲击感强的粗体设计。
- `minimal_editorial`：居中布局、细字体、编辑感排版。
- `nature_documentary`：低调绿色或大地色系。

### 2.2 动画实现方案（基于 MoviePy）

通过 lambda 函数对属性做时间驱动动画。

- `fade_only`：`set_opacity(lambda t: fade_in_out(t))`
- `fade_slide_up`：`set_position(lambda t: ("center", y0 - velocity*t))`
- `soft_zoom_in`：`resize(lambda t: 0.96 + 0.04 * (t/duration))`
- `pop_bounce`：多阶段缩放动画。

## 3. 自动推荐能力（扫描器）

更新 `Scanner`，根据目录关键词推荐标题风格：

- `PETS`、`CATS` -> `playful_pop`
- `MOUNTAIN`、`SNOW`、`FOREST` -> `nature_documentary`
- `SKI`、`ACTION` -> `impact_flash`
- `FOOD`、`TOWN` -> `travel_postcard`
- 默认 -> `cinematic_bold`

## 4. 执行步骤

1. **第一阶段：基础能力**
   - 修改 `video_engine_v5.py`，加入 `TitleStyle`，并更新 `StorySection` / `RenderSegment`。
   - 实现 `TitleStyleRenderer.render_text_layer`，生成透明 PNG 文字层。
2. **第二阶段：动效引擎**
   - 实现 `TitleStyleRenderer.animate_clip`，为文字层应用 MoviePy 效果。
   - 更新引擎中的 `_chapter_card` 与 `_apply_overlay_title`。
3. **第三阶段：智能推荐**
   - 更新 `Scanner` 的自动推荐逻辑。
   - 更新 `Planner` 与 `Compiler`，把风格配置传递到后续阶段。
4. **第四阶段：验证**
   - 新建 `tests/smoke_v5_5_title_style.py`。
   - 在 9:16、16:9 等不同画幅下验证效果。

## 5. 涉及文件

- `video_engine_v5.py`：主逻辑更新。
- `docs/V5_5_CHAPTER_TITLE_STYLE_AND_MOTION.md`：新增文档。
- `tests/smoke_v5_5_title_style.py`：新增测试脚本。
