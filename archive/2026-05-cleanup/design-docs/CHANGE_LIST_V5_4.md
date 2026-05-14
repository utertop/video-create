# V5.4 Patch Change List

## Added

- V5.4 故事蓝图审核页增强设计文档
- `tests/smoke_v5_4.py`
- 蓝图审核页章节信息增强
- 章节 title_mode：完整章节卡 / 标题叠加
- 章节 background 快捷切换：智能过渡 / 章节首图 / 纯色 / 自定义
- 素材启用 / 禁用
- 设为章节开场素材
- 设为章节背景素材
- `user_overridden` / `user_override_fields` 写入逻辑
- CI 增加 V5.4 smoke test

## Fixed

- `tests/smoke_v5.py` 在 Windows GitHub Actions 中打印中文路径导致 `UnicodeEncodeError`

## Updated

- README 追加 V5.4 说明
- `video_engine_v5.py` 版本元数据升级到 V5.4
- `src/lib/engine.ts` 追加 V5.4 用户覆盖辅助类型和函数
- `src/v5-background.css` 追加 V5.4 蓝图审核样式
