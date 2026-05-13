# Video Create Studio V5.4.2 目录识别策略增强

## 背景

旧逻辑主要依赖关键词命中，例如目录名 `登山` 命中了单字 `山`，就可能被识别成 `scenic_spot`。这会导致同一级素材目录出现不一致：

```text
AI Video/
├── 登山/  -> SCENIC_SPOT
├── 猫咪/  -> CHAPTER
└── 雪崩/  -> CHAPTER
```

这既影响蓝图页理解，也影响渲染策略，因为 `scenic_spot` 默认更偏向标题叠加，而 `chapter` 默认更偏向完整章节卡。

## V5.4.2 新策略

### 1. 关键词分级

景点关键词拆分为三层：

```text
强景点名：开元寺、西街、鼓浪屿、曾厝垵、清源山、武夷山、黄山、泰山
景点后缀：寺、庙、宫、塔、岛、湖、海、湾、街、巷、馆、园
弱关键词：山、桥、路、村、城
```

弱关键词只作为信号，不单独决定目录类型。

### 2. 一级目录默认是 chapter

对于普通素材库：

```text
AI Video/
├── 登山/
├── 猫咪/
└── 雪崩/
```

结果统一为：

```text
CHAPTER 登山
CHAPTER 猫咪
CHAPTER 雪崩
```

### 3. scenic_spot 依赖父级上下文

对于旅行素材：

```text
泉州/
├── 开元寺/
└── 西街/
厦门/
└── 鼓浪屿/
```

父级 `泉州 / 厦门` 被识别为 city，子目录才更容易识别为 scenic_spot。

### 4. 同级目录一致性修正

扫描结束后会进行第二轮 normalization：

- 如果父目录不是 city/date；
- 同级目录大多数是 chapter；
- 某个目录只是弱命中或单个景点候选；

则修正为 chapter，并记录：

```json
{
  "raw_detected_type": "scenic_spot_candidate",
  "detected_type": "chapter",
  "signals": {
    "normalized_from": "scenic_spot",
    "normalization_rule": "sibling_context_consistency"
  }
}
```

### 5. 可解释字段

`directory_nodes` 新增：

```json
{
  "raw_detected_type": "theme",
  "signals": {
    "matched_theme_keywords": ["登山"],
    "matched_spot_weak_keywords": ["山"],
    "parent_detected_type": "unknown",
    "sibling_majority_type": "chapter"
  }
}
```

这为后续 GUI 展示“识别依据”和用户手动覆盖打基础。

## 验证

```powershell
python -m py_compile .\video_engine_v5.py
python .\tests\smoke_v5_4_2_directory_strategy.py
npm run build
```
