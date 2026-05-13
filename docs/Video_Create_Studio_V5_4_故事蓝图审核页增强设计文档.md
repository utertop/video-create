# Video Create Studio V5.4 故事蓝图审核页增强设计文档

## 1. 版本定位

V5.4 的目标不是继续增加更多视频特效，而是把 V5 的核心工作台能力落地：

```text
Media Library  管素材事实
Story Blueprint 管叙事意图与用户覆盖
Render Plan     管机器可执行时间线
GUI Workbench   管用户审核与调整
```

V5.4 聚焦：

```text
故事蓝图审核页增强
用户覆盖机制落地
素材启用 / 禁用
完整章节卡 / 标题叠加切换
只重新编译 Render Plan
```

---

## 2. V5.4-1：章节卡信息展示增强

每个章节卡展示：

- 章节类型：城市 / 日期 / 景点 / 普通章节
- 标题模式：完整章节卡 / 首素材标题叠加
- 背景模式：智能过渡 / 章节首图 / 自定义 / 纯色
- 素材统计：图片数 / 视频数 / 启用数 / 总数
- 预计时长：该章节预估时长
- 用户覆盖状态：是否已经手动修改

---

## 3. V5.4-2：章节快速操作按钮

每个章节卡提供轻量操作：

```text
[完整章节卡] [标题叠加]
[智能背景] [首图背景] [纯色] [选择背景]
[启用/禁用章节]
```

操作后立即写入 Story Blueprint，并设置：

```json
{
  "user_overridden": true,
  "user_override_fields": ["title_mode", "background", "enabled"]
}
```

---

## 4. V5.4-3：素材启用 / 禁用

章节下素材缩略图支持：

- 启用 / 禁用素材
- 设为章节开场图
- 设为章节背景
- 保留用户选择，不被重新 plan 覆盖

素材级别建议字段：

```json
{
  "asset_id": "asset_xxx",
  "enabled": false,
  "role": "opening",
  "user_overridden": true
}
```

---

## 5. V5.4-4：用户覆盖字段落地

用户在 GUI 中的任何编辑都要写入：

```json
{
  "user_overridden": true,
  "user_override_fields": ["title", "background", "title_mode"]
}
```

覆盖合并策略：

| 用户动作 | 写入字段 |
|---|---|
| 改章节标题 | title |
| 改章节背景 | background |
| 切换完整卡 / 标题叠加 | title_mode |
| 禁用章节 | enabled |
| 禁用素材 | asset_refs.enabled |
| 设为开场图 | asset_refs.role |

---

## 6. V5.4-5：只重新编译 Render Plan

素材没有变化时，不应该重新 scan。推荐流程：

```text
修改 story_blueprint.json
  ↓
saveBlueprintV5
  ↓
compileV5
  ↓
renderV5
```

GUI 上文案建议从“确认并进入渲染”升级为：

```text
保存修改并重新编译渲染计划
```

---

## 7. 本次 patch 修改范围

```text
P0：修复 smoke_v5.py Windows UTF-8 输出
P1：新增 V5.4 设计补充文档
P2：增强 App.tsx 蓝图审核页、engine.ts 类型、video_engine_v5.py 版本元数据、v5-background.css 样式、README
P3：新增 tests/smoke_v5_4.py，验证用户覆盖、章节背景模式、景点标题叠加模式
```
