# Video Create Studio V4 技术落地设计文档

**文档定位**：这是在《素材库与故事蓝图联动优化方案》之后的第二份工程落地文档。第一份文档回答“为什么这么设计、整体怎么联动”；本文档回答“具体怎么实现、接口怎么定义、页面怎么改、Python V4 如何拆分命令”。

**目标版本**：V4 作为从 V3 脚本工具升级为“桌面视频创作工作台”的关键版本。

**核心结论**：

```text
城市 - 日期 - 景点 = 素材组织层
Story Blueprint = 成片叙事层
Render Plan = 渲染执行层
GUI = 用户审核与调整层
Python V4 = scan / plan / render 三阶段引擎
```

---

## 1. V4 总体目标与边界

### 1.1 V4 目标

V4 的目标不是做一个复杂剪辑软件，而是做一个“创作者友好的旅行视频自动化生产工作台”。它要把用户从命令行和目录猜测中解放出来，让用户通过 GUI 完成素材导入、目录识别、缩略图浏览、故事蓝图确认、章节调整和一键渲染。

V4 必须解决四个核心问题：

1. **素材怎么识别**：从目录和文件中识别城市、日期、景点、媒体类型、方向、时长、封面候选等信息。
2. **故事怎么组织**：把素材组织成可编辑的 Story Blueprint，而不是直接拼接。
3. **界面怎么展示**：GUI 要让用户看见目录结构、缩略图、章节、时间线和渲染参数。
4. **脚本怎么执行**：Python V4 拆成 `scan / plan / render` 三阶段，便于 GUI 调用和后续扩展。

### 1.2 V4 明确不做的事情

V4 应该保持工程边界，不建议一次性做成复杂剪辑器。以下能力可以进入 V5 或 V6：

- AI 自动选片与审美评分。
- 自动配乐和节拍卡点。
- 多轨时间线编辑。
- 字幕识别、旁白生成、AI 文案生成。
- 云端素材库、多设备同步。
- 专业 LUT 调色、复杂转场库。

V4 的关键词是：**可识别、可预览、可调整、可渲染、可复用**。

---

## 2. 目录识别规则

### 2.1 设计原则

目录识别不能把“城市 - 日期 - 景点”写死成唯一结构。它应该作为默认推荐结构，同时允许用户显式选择组织模式。真实创作者素材目录往往不完全标准，因此识别逻辑必须具备容错能力。

推荐把目录识别分为两层：

```text
目录物理结构：用户磁盘上的文件夹层级
素材语义结构：系统识别出的 city / date / spot / chapter
```

GUI 展示时不直接展示“文件夹”，而是展示“系统识别后的素材库视图”。

### 2.2 推荐素材目录结构

#### 标准结构 A：城市 → 景点

```text
泉州-厦门/
├── 泉州/
│   ├── 西街/
│   ├── 开元寺/
│   └── 蟳埔村/
└── 厦门/
    ├── 鼓浪屿/
    ├── 曾厝垵/
    └── 环岛路/
```

适合旅行 Vlog、B站城市旅行视频。

#### 标准结构 B：日期 → 城市 → 景点

```text
泉州-厦门/
├── 2026-05-01/
│   ├── 泉州/
│   │   └── 西街/
│   └── 厦门/
└── 2026-05-02/
    └── 厦门/
        └── 鼓浪屿/
```

适合多日旅行、每日流水式记录。

#### 标准结构 C：城市 → 日期 → 景点

```text
泉州-厦门/
├── 泉州/
│   ├── 2026-05-01/
│   │   ├── 西街/
│   │   └── 开元寺/
└── 厦门/
    └── 2026-05-02/
        └── 鼓浪屿/
```

适合跨城市但每个城市内又按日期归档的情况。

#### 简化结构 D：章节目录

```text
泉州-厦门/
├── 01_泉州古城/
├── 02_开元寺/
├── 03_厦门海边/
└── 04_鼓浪屿日落/
```

这种结构虽然不严格区分城市/日期/景点，但非常适合创作者式叙事。

### 2.3 识别优先级

系统识别目录时，建议采用以下优先级：

| 优先级 | 规则 | 说明 | GUI 默认展示 |
|---|---|---|---|
| P0 | 用户显式选择组织方式 | 用户在 GUI 选择“按城市/日期/景点/章节”时，以用户选择为准 | 用户选择的视图 |
| P1 | 日期识别 | 目录名匹配 `YYYY-MM-DD`、`YYYYMMDD`、`Day1`、`D1` | 日期视图 |
| P2 | 城市识别 | 目录名匹配用户城市词典、项目标题、常见城市名 | 城市视图 |
| P3 | 景点识别 | 城市下二级目录、包含“寺/街/岛/山/湖/村/馆”等地点特征 | 景点视图 |
| P4 | 编号章节识别 | 目录名以 `01_`、`02-`、`第1章` 开头 | 章节视图 |
| P5 | 文件名自然排序 | 无法识别时按文件名排序 | 文件列表视图 |

### 2.4 日期识别规则

建议支持以下格式：

```text
2026-05-11
2026_05_11
20260511
2026.05.11
Day1
Day 1
D1
第1天
第一天
```

识别结果统一转换为：

```json
{
  "date": "2026-05-11",
  "date_label": "Day 1"
}
```

如果只有 `Day1`，但没有绝对日期，则 `date` 可以为空，`date_label` 保留。

### 2.5 城市识别规则

城市识别建议结合三种来源：

1. 用户项目标题，例如“福建-泉州-厦门”。
2. 用户自定义城市词典，例如 `泉州, 厦门`。
3. 目录名直接匹配。

示例：

```text
项目标题：福建-泉州-厦门
系统提取候选城市：泉州、厦门
目录名：泉州、厦门
识别结果：city = 泉州 / 厦门
```

对于“福州-平潭-泉州”这种多城市项目，也可以从标题中自动提取候选词，但 GUI 必须允许用户手动修正。

### 2.6 景点识别规则

景点识别不建议依赖外部地图 API，V4 先用目录结构和名称规则即可：

- 城市目录下的二级目录默认识别为景点。
- 日期目录下的城市子目录再往下一级默认识别为景点。
- 包含地点特征词的目录可提高置信度：寺、街、岛、山、湖、村、馆、桥、港、湾、路、公园、古城、码头、海滩。

示例：

```text
泉州/开元寺/P10001.JPG
→ city = 泉州
→ spot = 开元寺
```

### 2.7 冲突处理规则

真实目录会出现冲突，必须定义处理策略：

| 冲突场景 | 处理方式 |
|---|---|
| 目录名既像城市又像景点 | 如果上级目录已是城市，则当前目录优先识别为景点 |
| 日期和城市同级混合 | 按用户选择的组织方式优先；未选择时进入“混合结构” |
| 文件散落在根目录 | 归入 `未分组` 章节 |
| 同名文件 | 以相对路径作为唯一 ID，不以文件名作为唯一 ID |
| 目录无法识别 | 保留原目录名作为 `chapter_title` |
| 缺失 EXIF 日期 | 使用文件修改时间作为候选，不覆盖用户目录语义 |

### 2.8 扫描输出字段

扫描阶段应该生成 `media_library.json`。每个素材至少包含：

```json
{
  "id": "media_000001",
  "path": "泉州/开元寺/P100001.JPG",
  "abs_path": "E:/bilibili_create/泉州-厦门/泉州/开元寺/P100001.JPG",
  "type": "image",
  "city": "泉州",
  "date": null,
  "date_label": null,
  "spot": "开元寺",
  "chapter": "开元寺",
  "width": 5184,
  "height": 3888,
  "orientation": "landscape",
  "duration": null,
  "has_audio": false,
  "status": "ready",
  "thumbnail": ".cache_v4/thumbnails/media_000001.jpg",
  "tags": ["city:泉州", "spot:开元寺", "orientation:landscape"],
  "warnings": []
}
```

### 2.9 素材状态机

素材状态建议设计为：

| 状态 | 含义 |
|---|---|
| `new` | 已发现但未分析 |
| `analyzed` | 已读取尺寸、方向、时长等信息 |
| `ready` | 可进入故事蓝图 |
| `excluded` | 用户或规则排除 |
| `broken` | 损坏或无法读取 |
| `selected` | 已进入故事蓝图 |
| `rendered` | 已成功渲染为片段 |
| `failed` | 渲染失败 |

GUI 可按状态筛选素材。

---

## 3. Story Blueprint JSON Schema

### 3.1 Story Blueprint 的定位

Story Blueprint 是 V4 的核心中间层。它不是素材库，也不是最终视频文件，而是“这个视频怎么讲故事”的结构化描述。

它应该回答：

```text
这个视频叫什么？
按什么顺序讲？
有哪些章节？
每个章节使用哪些素材？
每个素材时长多久？
是否保留视频声音？
是否加章节卡、水印、封面？
最终用什么比例和画质渲染？
```

### 3.2 顶层结构

建议结构如下：

```json
{
  "schema_version": "4.0",
  "project": {},
  "source": {},
  "story": {},
  "render": {},
  "cover": {},
  "watermark": {},
  "sections": [],
  "assets": {},
  "metadata": {}
}
```

### 3.3 完整示例

```json
{
  "schema_version": "4.0",
  "project": {
    "title": "福建-泉州-厦门",
    "subtitle": "一段关于古城、海风与旅途记忆的影像",
    "author": "PangBo Travel",
    "project_id": "quanzhou_xiamen_202605"
  },
  "source": {
    "input_folder": "E:/bilibili_create/泉州-厦门",
    "recursive": true,
    "organization_mode": "auto",
    "detected_mode": "city_spot",
    "media_library": "project.media.json"
  },
  "story": {
    "style": "travel_documentary",
    "pacing": "standard",
    "chapter_strategy": "from_dirs",
    "default_image_duration": 3.2,
    "transition": "crossfade",
    "transition_duration": 0.5
  },
  "render": {
    "ratio": "16:9",
    "resolution": [1920, 1080],
    "fps": 30,
    "quality": "high",
    "engine": "auto",
    "keep_video_audio": true,
    "add_music": false,
    "output_dir": "E:/bilibili_create/泉州-厦门/output",
    "output_name": "quanzhou_xiamen"
  },
  "cover": {
    "enabled": true,
    "title": "福建-泉州-厦门",
    "subtitle": "Travel Video",
    "candidate_media_id": "media_000012",
    "output": "cover_quanzhou_xiamen.jpg"
  },
  "watermark": {
    "enabled": true,
    "text": "PangBo Travel",
    "position": "bottom_right",
    "opacity": 0.75
  },
  "sections": [
    {
      "id": "section_001",
      "type": "chapter",
      "title": "泉州",
      "subtitle": "古城、街巷与烟火气",
      "enabled": true,
      "chapter_card": true,
      "chapter_duration": 2.5,
      "items": [
        {
          "media_id": "media_000001",
          "role": "opening",
          "duration": 3.8,
          "fit_mode": "blur_contain",
          "keep_audio": false,
          "enabled": true
        },
        {
          "media_id": "media_000002",
          "role": "ambient_video",
          "duration": "source",
          "fit_mode": "blur_contain",
          "keep_audio": true,
          "enabled": true
        }
      ]
    },
    {
      "id": "section_002",
      "type": "chapter",
      "title": "厦门",
      "subtitle": "海风、岛屿与日落",
      "enabled": true,
      "chapter_card": true,
      "chapter_duration": 2.5,
      "items": []
    }
  ],
  "assets": {
    "media_000001": {
      "path": "泉州/开元寺/P100001.JPG",
      "type": "image",
      "city": "泉州",
      "spot": "开元寺",
      "orientation": "landscape",
      "thumbnail": ".cache_v4/thumbnails/media_000001.jpg"
    },
    "media_000002": {
      "path": "泉州/西街/P100002.MP4",
      "type": "video",
      "city": "泉州",
      "spot": "西街",
      "duration": 8.2,
      "has_audio": true,
      "thumbnail": ".cache_v4/thumbnails/media_000002.jpg"
    }
  },
  "metadata": {
    "created_at": "2026-05-11T10:00:00",
    "updated_at": "2026-05-11T10:10:00",
    "created_by": "Video Create Studio V4"
  }
}
```

### 3.4 字段说明

#### project

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `title` | string | 是 | 视频标题 |
| `subtitle` | string | 否 | 副标题或情绪描述 |
| `author` | string | 否 | 创作者名称 |
| `project_id` | string | 是 | 项目唯一 ID |

#### source

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `input_folder` | string | 是 | 素材根目录 |
| `recursive` | bool | 是 | 是否递归扫描 |
| `organization_mode` | string | 是 | 用户选择的组织模式 |
| `detected_mode` | string | 否 | 系统识别结果 |
| `media_library` | string | 是 | 素材库 JSON 路径 |

#### sections

`sections` 是故事蓝图的核心。每个 section 对应一个章节、日期、城市或景点。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | string | 章节 ID |
| `type` | string | `chapter` / `date` / `city` / `spot` / `custom` |
| `title` | string | 章节标题 |
| `subtitle` | string | 章节副标题 |
| `enabled` | bool | 是否参与渲染 |
| `chapter_card` | bool | 是否生成章节卡 |
| `items` | array | 当前章节素材列表 |

#### section.items

| 字段 | 类型 | 说明 |
|---|---|---|
| `media_id` | string | 对应素材库 ID |
| `role` | string | `opening` / `detail` / `ambient_video` / `ending` |
| `duration` | number/string | 图片秒数或视频 `source` |
| `fit_mode` | string | `blur_contain` / `contain_black` / `cover_crop` |
| `keep_audio` | bool | 是否保留视频原声 |
| `enabled` | bool | 是否参与渲染 |

### 3.5 校验规则

生成和渲染前必须校验：

1. `schema_version` 必须存在。
2. `project.title` 不能为空。
3. `render.ratio` 必须是 `16:9`、`9:16` 或 `1:1`。
4. 每个 `section.id` 唯一。
5. 每个 `items.media_id` 必须能在 `assets` 中找到。
6. 禁用的 section 和 item 不参与渲染。
7. 视频素材 `duration = source` 时使用原视频时长。
8. 图片素材必须有明确 duration。
9. 输出目录不存在时自动创建。
10. 所有路径统一使用 `/` 存储，执行时再转换为系统路径。

---

## 4. GUI 页面与组件设计

### 4.1 GUI 总体结构

V4 GUI 建议从单页命令面板升级为四个核心页面：

```text
项目导入页
素材库页
故事蓝图页
渲染任务页
```

导航结构：

```text
Video Create Studio
├── 1. 项目导入
├── 2. 素材库
├── 3. 故事蓝图
├── 4. 渲染输出
└── 5. 结果与报告
```

### 4.2 页面一：项目导入页

#### 目标

让用户选择素材根目录，并指定素材组织逻辑。

#### 核心控件

| 控件 | 说明 |
|---|---|
| 素材目录选择器 | 选择根目录 |
| 项目标题输入框 | 例如“福建-泉州-厦门” |
| 组织方式选择 | 自动识别 / 按城市 / 按日期 / 按景点 / 按章节 |
| 递归扫描开关 | 是否扫描子目录 |
| 城市词典输入 | 可选，例：泉州,厦门 |
| 开始扫描按钮 | 调用 Python `scan` |

#### 交互流程

```text
选择目录
→ 输入项目标题
→ 选择组织方式
→ 点击“扫描素材”
→ 生成 media_library.json
→ 自动进入素材库页
```

### 4.3 页面二：素材库页

#### 目标

让用户看到素材被系统如何识别，并允许用户修正识别结果。

#### 视图模式

| 视图 | 说明 |
|---|---|
| 城市视图 | 按城市聚合素材 |
| 日期视图 | 按日期聚合素材 |
| 景点视图 | 按景点聚合素材 |
| 文件夹视图 | 按真实目录展示 |
| 状态视图 | 按 ready / broken / excluded 分类 |

#### 组件设计

```text
素材库页
├── 左侧：分组树
│   ├── 泉州
│   ├── 厦门
│   └── 未分组
├── 中间：缩略图网格
│   ├── 图片缩略图
│   ├── 视频缩略图
│   └── 状态标记
└── 右侧：素材详情面板
    ├── 文件路径
    ├── 类型/方向/尺寸/时长
    ├── city/date/spot/chapter
    ├── 是否入选
    └── 错误/警告
```

#### 素材卡片信息

每张素材卡显示：

```text
缩略图
媒体类型：图片/视频
方向：横屏/竖屏/方形
时长：视频显示秒数，图片显示默认秒数
标签：城市、景点、日期
状态：ready / broken / excluded
```

#### 用户可编辑字段

| 字段 | 是否可编辑 | 说明 |
|---|---|---|
| city | 是 | 用户可修正城市识别 |
| date | 是 | 用户可修正日期 |
| spot | 是 | 用户可修正景点 |
| chapter | 是 | 用户可指定章节 |
| status | 是 | 可排除素材 |
| cover_candidate | 是 | 可设为封面候选 |

### 4.4 页面三：故事蓝图页

#### 目标

让用户看到系统自动生成的视频结构，并可以调整章节顺序、标题和素材入选情况。

#### 布局

```text
故事蓝图页
├── 左侧：章节大纲
│   ├── 片头
│   ├── 泉州
│   ├── 厦门
│   └── 片尾
├── 中间：Storyboard 横向卡片流
│   ├── 章节卡
│   ├── 图片片段
│   ├── 视频片段
│   └── 结尾卡
└── 右侧：章节/片段属性
    ├── 标题
    ├── 副标题
    ├── 时长
    ├── 转场
    ├── 是否保留原声
    └── fit_mode
```

#### 必须支持的操作

| 操作 | V4 是否支持 | 说明 |
|---|---|---|
| 章节启用/禁用 | 是 | 不删除，只是不渲染 |
| 章节标题编辑 | 是 | 修改 Story Blueprint |
| 章节顺序调整 | 建议支持 | V4 可先用上移/下移按钮 |
| 素材启用/禁用 | 是 | 控制 item.enabled |
| 选择封面素材 | 是 | 设置 cover.candidate_media_id |
| 修改章节卡时长 | 是 | chapter_duration |
| 修改图片时长 | 是 | item.duration |
| 拖拽时间线 | V5 | V4 可先不做复杂拖拽 |

### 4.5 页面四：渲染输出页

#### 目标

让用户配置输出参数，并调用 Python `render`。

#### 渲染参数

| 参数 | 默认值 | GUI 控件 |
|---|---|---|
| 比例 | 16:9 | 单选：横屏/竖屏/方形 |
| 画质 | high | normal/high/ultra |
| 引擎 | auto | auto/moviepy_crossfade/ffmpeg_concat |
| FPS | 30 | 下拉选择 |
| 输出目录 | input/output | 目录选择器 |
| 是否生成封面 | true | 开关 |
| 是否保留视频原声 | true | 开关 |
| 水印 | 可选 | 输入框 + 开关 |

#### 日志与进度

Python V4 应输出结构化日志，GUI 按行解析：

```json
{"event":"scan_progress","current":20,"total":100,"message":"正在分析 P100020.JPG"}
{"event":"render_segment","current":5,"total":80,"message":"生成片段 5/80"}
{"event":"render_done","output":"output/quanzhou_xiamen_16x9.mp4"}
```

### 4.6 页面五：结果与报告页

生成完成后展示：

```text
最终视频路径
封面图路径
构建报告路径
视频时长
素材数量
被跳过素材
错误列表
打开输出目录按钮
```

---

## 5. Python V4 scan / plan / render 命令设计

### 5.1 命令总览

V4 Python 引擎建议从一个大命令拆成三个子命令：

```bash
python make_bilibili_video_v4.py scan   --input_folder ...
python make_bilibili_video_v4.py plan   --media_json ...
python make_bilibili_video_v4.py render --blueprint ...
```

每个阶段都有明确输入和输出。

```text
scan  ：从磁盘扫描素材，生成 media_library.json
plan  ：从素材库生成 Story Blueprint
render：从 Story Blueprint 渲染最终视频
```

### 5.2 scan 命令

#### 作用

扫描素材目录，生成素材库 JSON、缩略图、基础分析信息。

#### 命令示例

```bash
python make_bilibili_video_v4.py scan \
  --input_folder "E:\bilibili_create\泉州-厦门" \
  --recursive \
  --project_title "福建-泉州-厦门" \
  --organization_mode auto \
  --city_hints "泉州,厦门" \
  --output "E:\bilibili_create\泉州-厦门\project.media.json"
```

#### 参数表

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--input_folder` | 是 | 无 | 素材根目录 |
| `--recursive` | 否 | false | 是否递归扫描 |
| `--project_title` | 否 | 空 | 项目标题，用于城市识别 |
| `--organization_mode` | 否 | auto | auto/city/date/spot/chapter/folder |
| `--city_hints` | 否 | 空 | 用户提供城市词典 |
| `--ignore_duplicates` | 否 | true | 是否过滤副本文件 |
| `--cache_dir` | 否 | `.cache_v4` | 缓存目录 |
| `--output` | 是 | 无 | 输出 media JSON |
| `--json_logs` | 否 | true | 是否输出 JSON 行日志 |

#### 输出文件

```text
project.media.json
.cache_v4/
├── thumbnails/
├── fixed_images/
├── video_frames/
└── scan_report.txt
```

### 5.3 plan 命令

#### 作用

根据素材库生成 Story Blueprint。这个阶段不渲染视频，只生成可编辑的故事结构。

#### 命令示例

```bash
python make_bilibili_video_v4.py plan \
  --media_json "E:\bilibili_create\泉州-厦门\project.media.json" \
  --strategy city_spot \
  --title "福建-泉州-厦门" \
  --subtitle "古城、海风与旅途记忆" \
  --watermark "PangBo Travel" \
  --cover \
  --output "E:\bilibili_create\泉州-厦门\story.blueprint.json"
```

#### strategy 可选值

| strategy | 说明 |
|---|---|
| `auto` | 根据 scan 识别结果自动选择 |
| `city` | 按城市生成章节 |
| `date` | 按日期生成章节 |
| `spot` | 按景点生成章节 |
| `city_spot` | 城市为一级章节，景点为子章节或素材组 |
| `date_city_spot` | 日期 → 城市 → 景点 |
| `folder` | 按目录结构生成章节 |
| `custom` | GUI 手动编辑后保存 |

#### 输出文件

```text
story.blueprint.json
story.preview.json
```

`story.preview.json` 可以给 GUI 快速展示，不包含过多素材底层字段。

### 5.4 render 命令

#### 作用

读取 Story Blueprint，渲染最终视频、封面和构建报告。

#### 命令示例

```bash
python make_bilibili_video_v4.py render \
  --blueprint "E:\bilibili_create\泉州-厦门\story.blueprint.json" \
  --output_dir "E:\bilibili_create\泉州-厦门\output" \
  --engine auto \
  --quality high
```

#### 参数表

| 参数 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `--blueprint` | 是 | 无 | Story Blueprint JSON |
| `--output_dir` | 否 | blueprint.render.output_dir | 输出目录 |
| `--engine` | 否 | auto | auto/moviepy_crossfade/ffmpeg_concat |
| `--quality` | 否 | high | normal/high/ultra |
| `--fps` | 否 | blueprint.render.fps | 输出帧率 |
| `--dry_run` | 否 | false | 只验证，不渲染 |
| `--json_logs` | 否 | true | 输出 JSON 行日志 |

#### 输出文件

```text
output/
├── quanzhou_xiamen_16x9.mp4
├── cover_quanzhou_xiamen.jpg
├── build_report_quanzhou_xiamen.txt
└── render_plan_quanzhou_xiamen.json
```

### 5.5 可选 validate 命令

虽然 V4 主流程是 scan / plan / render，但建议内部保留 validate 能力：

```bash
python make_bilibili_video_v4.py validate --blueprint story.blueprint.json
```

GUI 在点击“生成视频”前可以自动调用 validate，提前发现问题。

### 5.6 JSON 日志规范

所有命令建议输出 JSON Lines，便于 GUI 实时解析：

```json
{"level":"info","event":"scan_start","message":"开始扫描素材"}
{"level":"info","event":"scan_item","current":1,"total":120,"path":"泉州/P100001.JPG"}
{"level":"warning","event":"media_skipped","path":"副本.JPG","reason":"duplicate_copy"}
{"level":"info","event":"plan_section","title":"泉州","items":80}
{"level":"info","event":"render_progress","current":10,"total":100,"message":"生成片段 10/100"}
{"level":"info","event":"render_done","output":"output/quanzhou_xiamen_16x9.mp4"}
{"level":"error","event":"render_failed","message":"ffmpeg concat failed"}
```

建议 GUI 只依赖 `event` 字段，不依赖中文 message。

### 5.7 退出码规范

| 退出码 | 含义 |
|---|---|
| 0 | 成功 |
| 1 | 通用错误 |
| 2 | 参数错误 |
| 3 | 输入目录不存在 |
| 4 | 没有可用素材 |
| 5 | JSON schema 校验失败 |
| 6 | 渲染失败 |
| 7 | FFmpeg 不可用 |
| 8 | 权限或写入失败 |

---

## 6. GUI 与 Python V4 的联动流程

### 6.1 首次导入流程

```text
GUI：用户选择目录
→ 调用 scan
→ 生成 project.media.json
→ GUI 读取 media JSON
→ 展示素材库
```

### 6.2 生成故事蓝图流程

```text
GUI：用户选择组织方式
→ 调用 plan
→ 生成 story.blueprint.json
→ GUI 读取 blueprint
→ 展示故事蓝图页
```

### 6.3 用户编辑流程

```text
GUI：用户修改章节标题/启用状态/素材顺序/封面候选
→ 直接修改 story.blueprint.json
→ 保存为 story.blueprint.edited.json
```

### 6.4 渲染流程

```text
GUI：点击生成视频
→ 调用 render --blueprint story.blueprint.edited.json
→ 解析 JSON Lines 日志
→ 更新进度条和日志窗口
→ 渲染完成后展示结果卡片
```

### 6.5 文件建议布局

```text
项目目录/
├── project.media.json
├── story.blueprint.json
├── story.blueprint.edited.json
├── .cache_v4/
│   ├── thumbnails/
│   ├── fixed_images/
│   ├── blur_backgrounds/
│   ├── video_frames/
│   └── segments/
└── output/
    ├── final_video_16x9.mp4
    ├── cover_final_video.jpg
    └── build_report_final_video.txt
```

---

## 7. V4 Action Plan

### Phase 0：Schema 与命令框架

目标：先把数据结构和 Python CLI 框架定下来。

任务：

1. 定义 `media_library.schema.json`。
2. 定义 `story_blueprint.schema.json`。
3. 新建 `make_bilibili_video_v4.py`。
4. 实现 argparse 子命令：`scan / plan / render`。
5. 实现统一 JSON 日志输出。
6. 保持 V3 能力可复用，不推翻重写。

验收标准：

```text
python make_bilibili_video_v4.py --help 能显示三个子命令
scan 能生成 project.media.json
plan 能生成 story.blueprint.json
render 能读取 blueprint 并输出视频
```

### Phase 1：scan 与素材库页

目标：让 GUI 能展示素材库。

任务：

1. scan 支持递归目录。
2. scan 支持城市/日期/景点识别。
3. scan 生成缩略图。
4. GUI 新增素材库页。
5. 支持城市/日期/景点/文件夹视图切换。
6. 支持素材状态展示。

验收标准：

```text
选择 E:\bilibili_create\泉州-厦门
GUI 能显示泉州、厦门分组
能看到图片/视频缩略图
能看到素材数量和异常素材
```

### Phase 2：plan 与故事蓝图页

目标：让系统自动生成可编辑的视频结构。

任务：

1. plan 支持 `city / date / spot / city_spot / folder` 策略。
2. 生成章节卡。
3. 生成素材入选列表。
4. GUI 展示章节大纲。
5. GUI 展示 storyboard 卡片流。
6. 支持章节启用/禁用、标题编辑、封面候选选择。

验收标准：

```text
按目录生成“泉州”“厦门”章节
用户能关闭某个章节
用户能修改章节标题
用户能保存 story.blueprint.edited.json
```

### Phase 3：render 与渲染任务页

目标：让用户通过 GUI 完成最终视频生成。

任务：

1. render 读取 Story Blueprint。
2. 复用 V3 的 EXIF 转正、模糊背景、缓存、封面、报告能力。
3. render 输出 JSON Lines 日志。
4. GUI 解析进度日志。
5. GUI 显示最终视频、封面、报告路径。

验收标准：

```text
点击生成视频
进度条能更新
最终生成 mp4、cover、report
GUI 能打开输出目录
```

### Phase 4：稳定性与体验优化

目标：把 V4 从“能用”提升为“好用”。

任务：

1. 增加错误提示友好化。
2. 增加路径不存在、Python 不存在、FFmpeg 不存在的检测。
3. 增加缓存清理按钮。
4. 增加导出项目配置功能。
5. 增加最近项目列表。
6. 增加操作手册入口。

验收标准：

```text
非技术用户能按界面完成一次完整视频生成
失败时能看到明确原因和修复建议
```

---

## 8. 推荐实施顺序

不要直接改 GUI 的大页面，也不要一开始就做复杂拖拽。推荐顺序：

```text
1. 先定义 JSON schema
2. 再实现 Python scan
3. 再让 GUI 展示 media_library.json
4. 再实现 Python plan
5. 再让 GUI 展示 story_blueprint.json
6. 再把 GUI 的生成按钮改成 render blueprint
7. 最后再加封面、报告、章节编辑增强
```

原因很简单：**数据结构稳定后，GUI 和 Python 才不会互相拖后腿。**

---

## 9. 最小可行 V4 验收用例

### 用例 1：城市目录

目录：

```text
泉州-厦门/
├── 泉州/
│   ├── P100001.JPG
│   └── P100002.MP4
└── 厦门/
    ├── P100100.JPG
    └── P100101.MP4
```

期望：

```text
scan 识别出 city=泉州、city=厦门
plan 生成两个章节：泉州、厦门
render 输出 quanzhou_xiamen_16x9.mp4
```

### 用例 2：日期目录

```text
旅行/
├── 2026-05-01/
├── 2026-05-02/
└── 2026-05-03/
```

期望：

```text
scan 识别出 3 个日期
plan 生成 Day 1 / Day 2 / Day 3
```

### 用例 3：混合目录

```text
旅行/
├── Day1_泉州西街/
├── Day2_厦门鼓浪屿/
└── 一些散落照片.JPG
```

期望：

```text
系统生成章节：Day1_泉州西街、Day2_厦门鼓浪屿、未分组
```

---

## 10. 最终结论

V4 的核心不是“再加一个功能”，而是把 Video Create Studio 从脚本调用器升级为结构化创作工作台。

最终架构应为：

```text
素材目录
  ↓ scan
media_library.json
  ↓ plan
story_blueprint.json
  ↓ GUI 审核与编辑
story_blueprint.edited.json
  ↓ render
最终视频 + 封面 + 构建报告
```

这套方案可以让系统同时满足两类用户：

```text
普通用户：选择目录 → 自动生成视频
创作者用户：选择目录 → 调整故事蓝图 → 输出更有叙事的视频
```

因此，V4 的重点应该是先完成：

```text
目录识别规则
Story Blueprint JSON
GUI 素材库与故事蓝图页面
Python scan / plan / render 三阶段命令
```

这四件事情完成后，Video Create Studio 才真正具备向 V5 的 AI 配乐、模板匹配、时间线编辑继续演进的基础。
