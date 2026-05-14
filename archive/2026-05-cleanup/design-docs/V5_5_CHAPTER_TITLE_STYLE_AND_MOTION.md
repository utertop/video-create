# Video Create Studio V5.5 章节文字动效设计文档

## 1. 概述
V5.5 版本引入了基于模板的文字动效系统，旨在取代 V5.4 中简单的静态文字卡片。系统通过识别素材目录的关键词，自动为每个章节推荐最匹配的视觉风格（Preset）和动效（Motion）。

## 2. 视觉模板 (Presets)

| 模板 ID | 视觉特征 | 推荐场景 | 默认动效 |
| :--- | :--- | :--- | :--- |
| `cinematic_bold` | 白色粗体，暗色叠加层 | 壮丽风景、山脉、大片感 | `fade_slide_up` |
| `travel_postcard` | 米色背景，白框边框，复古感 | 小镇、美食、旅行记录 | `soft_zoom_in` |
| `playful_pop` | 圆角矩形底框，鲜艳配色 | 宠物、儿童、趣味日常 | `pop_bounce` |
| `impact_flash` | 高对比度，极速缩放 | 运动、滑雪、转场冲击 | `quick_zoom_punch` |
| `minimal_editorial` | 细体文字，极简排版 | Vlog、人像、摄影集 | `fade_only` |
| `nature_documentary` | 自然色系（如森林绿），优雅比例 | 森林、湖泊、自然纪录片 | `slow_fade_zoom` |

## 3. 动效类型 (Motions)

- **`fade_only`**: 简单的淡入淡出（0.5s 淡入, 0.4s 淡出）。
- **`fade_slide_up`**: 淡入的同时从下方 20px 处平滑升至中心。
- **`soft_zoom_in`**: 从 96% 缓慢放大至 100%，增加呼吸感。
- **`pop_bounce`**: 弹跳效果（0.8 -> 1.08 -> 1.0），富有活力。
- **`quick_zoom_punch`**: 极速缩放（1.15 -> 1.0），具有视觉冲击力。
- **`slow_fade_zoom`**: 慢速淡入并伴随轻微放大（100% -> 105%）。

## 4. 智能推荐系统 (标签权重)
V5.5 不再使用简单的关键词匹配，而是引入了**轻量级标签权重系统**：

- **多维度评分**：系统会为每个分类（如“萌宠”、“旅行”）计算总分。
- **权重区分**：核心词（如“猫咪”、“滑雪”）拥有更高的权重（2.0-2.5），而辅助词（如“日常”、“旅行”）权重较低（1.0）。
- **智能竞速**：如果一个文件夹同时包含多个场景关键词，系统将根据权重总分挑选最合适的风格，避免误判。

### 示例逻辑：
- 文件夹名 `猫咪滑雪.mp4` -> `猫咪`(2.2) vs `滑雪`(2.5) -> 最终选择 `impact_flash` (滑雪)。
- 文件夹名 `我的萌宠日常` -> `萌`(1.5) + `日常`(1.0) -> 最终选择 `playful_pop`。

## 5. 数据结构实现

### Story Blueprint (JSON)
```json
{
  "section_type": "chapter",
  "title": "雪山徒步",
  "title_style": {
    "preset": "nature_documentary",
    "motion": "slow_fade_zoom",
    "color_theme": "auto",
    "position": "center"
  }
}
```

### Render Plan (JSON)
```json
{
  "type": "chapter",
  "text": "雪山徒步",
  "title_style": {
    "preset": "nature_documentary",
    "motion": "slow_fade_zoom"
  }
}
```

## 6. 技术实现细节
- **渲染层**: 使用 Pillow (PIL) 生成带 Alpha 通道的透明 PNG 序列。
- **动画层**: 使用 MoviePy 的 `set_opacity`, `set_position`, `resize` 方法，通过 Lambda 表达式实现时间相关的动态属性计算。
- **性能**: 文字层单独渲染并与背景层复合，避免了重复渲染复杂背景，提高了编译速度。
