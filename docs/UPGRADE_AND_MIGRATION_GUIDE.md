# 升级与项目迁移指南

## 目的

这份文档说明当前项目在版本升级时，如何处理已有 `.video_create_project` 内的项目文档，以及当迁移失败时应该怎么恢复。

---

## 一、当前迁移范围

当前自动迁移覆盖三类文档：

- `media_library.json`
- `story_blueprint.json`
- `render_plan.json`

恢复最近项目时，系统会优先尝试：

1. 读取项目目录中的这三份文档
2. 校验 `document_type`
3. 自动补齐当前版本需要的关键字段
4. 将 `schema_version` 统一迁到当前版本
5. 必要时写回迁移后的 JSON

---

## 二、当前会自动补齐的内容

### `media_library.json`

- `project.project_title`
- `directory_nodes`
- `assets`
- `summary`
- `thumbnail_path` / `thumbnail` 兼容字段
- 缺失的 `status`

### `story_blueprint.json`

- `subtitle`
- `sections`
- `metadata`
- `metadata.chapter_background_mode`
- section 层级中的 `children`
- section 层级中的 `asset_refs`

### `render_plan.json`

- `segments`
- `output_path`
- segment 层级中的 `render_route_tags`

---

## 三、升级时用户会看到什么

当最近项目恢复时，如果触发迁移，界面会显示：

- 一条恢复成功提示
- 一张“项目迁移”说明卡
- 本次迁移的字段补齐或 schema 升级项

这样用户能知道：

- 项目已被自动升级
- 系统改了哪些兼容字段
- 当前版本为什么还能继续打开旧项目

---

## 四、迁移失败时怎么办

如果迁移失败，最常见的情况有：

- 项目目录不存在
- 项目目录只读
- 项目 JSON 已损坏
- 项目 JSON 被错误替换

这时建议按下面顺序处理：

1. 先看错误码
2. 检查 `.video_create_project` 是否仍在原路径
3. 检查目录是否可写
4. 如 JSON 损坏，尝试保留仍可读取的文件
5. 必要时重新扫描素材并重新生成蓝图/渲染计划

---

## 五、发版建议

以后每次 schema 发生变化，建议同时做三件事：

1. 更新迁移逻辑
2. 在 changelog 中明确写出升级影响
3. 为迁移新增 smoke test 或 regression case

推荐把“版本升级不会破坏旧项目”当作正式发布前的基线要求，而不是上线后再靠人工补救。

---

## 六、支持建议

如果用户升级后反馈“项目打不开”，优先收集：

- 错误码
- 应用版本
- 是否通过“最近项目恢复”进入
- `.video_create_project` 是否仍存在
- 诊断包

如果用户能恢复路径但加载不到文档，通常说明：

- 路径还在
- 但项目 JSON 存在损坏、权限或类型错位问题

这类问题优先按迁移/文档层排查，而不是先怀疑渲染引擎。
