# Video Create Studio：素材库目录逻辑与“故事蓝图”联动优化方案

## 1. 总体结论

建议不要把“城市 - 日期 - 景点”设计成唯一的视频生成逻辑，而应把它定义为“素材组织层”的默认规则。真正决定成片观感的，应是“故事蓝图”。

```text
素材组织层：城市 / 日期 / 景点 / 类型 / 时间 / 横竖屏 / 质量
故事蓝图层：开场 / 章节 / 高光 / 情绪 / 节奏 / 转场 / 片尾
生成执行层：画幅 / 质量 / 水印 / 封面 / 缓存 / 日志 / 输出
GUI 展示层：素材库视图 / 蓝图视图 / 时间线预览 / 任务控制台
```

## 2. 核心方案

Video Create Studio 应升级为：素材库 + 故事蓝图 + 时间线 + 渲染引擎。

- “城市 - 日期 - 景点”作为默认素材结构。
- “故事蓝图”决定视频如何讲故事。
- Python V4 引擎拆成 scan / plan / render。
- GUI 增加素材库视图、故事蓝图视图、时间线预览。

## 3. 推荐目录

```text
泉州-厦门/
├── 01_泉州/
│   ├── 2026-05-01_开元寺/
│   ├── 2026-05-01_西街/
│   └── 2026-05-01_钟楼/
└── 02_厦门/
    ├── 2026-05-02_鼓浪屿/
    ├── 2026-05-02_沙坡尾/
    └── 2026-05-02_环岛路/
```

## 4. V4 命令设计

```bash
python make_bilibili_video_v4.py scan --input_folder "E:\bilibili_create\泉州-厦门" --recursive --organize_mode auto
python make_bilibili_video_v4.py plan --manifest manifest.json --template travel_classic --title "福建-泉州-厦门"
python make_bilibili_video_v4.py render --blueprint story_blueprint.json --quality high --cover --watermark "utertop Travel"
```

## 5. Action Plan

| 阶段 | 目标 | 主要任务 | 验收标准 |
|---|---|---|---|
| Phase 1 | 素材库扫描 MVP | scan、manifest、缩略图、目录识别 | GUI 能按城市/日期/景点展示缩略图 |
| Phase 2 | 故事蓝图 MVP | plan、模板、章节、开场/片尾 | GUI 能展示可审核蓝图 |
| Phase 3 | V4 渲染联动 | render 接收 blueprint | 同一素材可按不同蓝图生成视频 |
| Phase 4 | 交互式素材选择 | 跳过、封面、高光、章节调整 | 用户可修正自动识别结果 |
| Phase 5 | 风格模板增强 | 电影感、城市漫游、一日行程 | 成片不再只有目录拼接风格 |
| Phase 6 | 内容创作增强 | 标题、简介、封面、音乐蓝图 | 从素材到发布闭环 |
```

详细版请查看 DOCX。
