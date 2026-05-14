# -*- coding: utf-8 -*-
"""
Apply Video Create Studio V5.4 patch.

Run from repository root:

    python .\tools\apply_v5_4_patch.py

This script is designed for the current main-branch V5.3.x codebase. It:
- backs up modified files
- writes V5.4 docs/tests
- patches README / workflow / engine metadata / CSS
- replaces the BlueprintEditor component with an enhanced V5.4 editor
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH_ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def backup(path: Path) -> None:
    if path.exists():
        bak = path.with_suffix(path.suffix + ".v54.bak")
        if not bak.exists():
            shutil.copy2(path, bak)


def copy_patch_file(relative: str) -> None:
    src = PATCH_ROOT / relative
    dst = ROOT / relative
    if src.exists():
        backup(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def append_once(path: Path, marker: str, content: str) -> None:
    backup(path)
    text = read(path) if path.exists() else ""
    if marker not in text:
        text = text.rstrip() + "\n\n" + content.strip() + "\n"
        write(path, text)


def patch_workflow() -> None:
    path = ROOT / ".github" / "workflows" / "build.yml"
    if not path.exists():
        return

    backup(path)
    text = read(path)
    if "smoke_v5_4.py" in text:
        return

    needle = "python .\\tests\\smoke_v5.py"
    if needle in text:
        text = text.replace(
            needle,
            needle + "\n\n      - name: Python V5.4 blueprint override smoke test\n        run: python .\\tests\\smoke_v5_4.py",
            1,
        )
    else:
        text += """

      - name: Python V5.4 blueprint override smoke test
        run: python .\tests\smoke_v5_4.py
"""
    write(path, text)


def patch_readme() -> None:
    path = ROOT / "README.md"
    marker = "## V5.4 故事蓝图审核页增强"
    content = f"""
{marker}

V5.4 的目标是把 V5 从“自动生成视频”继续推进到“创作者可控的故事蓝图工作台”。

新增重点：

- 章节卡展示章节类型、标题模式、背景模式、素材统计、预计时长、用户覆盖状态。
- 章节可快速切换：完整章节卡 / 首素材标题叠加。
- 章节可快速切换背景：智能过渡 / 章节首图 / 纯色 / 自定义背景。
- 章节素材支持启用 / 禁用、设为开场素材、设为章节背景。
- GUI 编辑会写入 `user_overridden` 与 `user_override_fields`。
- 素材未变化时，支持只保存 Story Blueprint 并重新 `compile` Render Plan，不必重新 `scan`。
- CI 增加 `tests/smoke_v5_4.py`，验证用户覆盖、章节背景模式和景点标题叠加语义。

V5.4 之后的推荐流程：

```text
scan -> plan -> GUI 审核/覆盖 -> saveBlueprint -> compile -> render
```
"""
    append_once(path, marker, content)


def patch_css() -> None:
    path = ROOT / "src" / "v5-background.css"
    marker = "/* V5.4 Blueprint Review Enhancements */"
    content = r"""
/* V5.4 Blueprint Review Enhancements */

.v54-blueprint-review {
  display: grid;
  gap: 16px;
}

.v54-blueprint-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(120px, 1fr));
  gap: 12px;
  margin-bottom: 14px;
}

.v54-summary-card {
  border: 1px solid rgba(18, 112, 78, 0.16);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.72);
  box-shadow: 0 8px 20px rgba(10, 40, 28, 0.05);
}

.v54-summary-card span {
  display: block;
  color: rgba(13, 56, 42, 0.58);
  font-size: 12px;
  margin-bottom: 4px;
}

.v54-summary-card strong {
  color: #0d3a2c;
  font-size: 18px;
}

.v54-section-card {
  border: 1px solid rgba(15, 111, 78, 0.15);
  border-radius: 18px;
  padding: 14px;
  background: linear-gradient(180deg, rgba(255,255,255,0.92), rgba(247,252,248,0.88));
  box-shadow: 0 12px 28px rgba(9, 40, 28, 0.06);
}

.v54-section-card.disabled {
  opacity: 0.55;
}

.v54-section-header {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.v54-section-title-area {
  min-width: 0;
  flex: 1;
}

.v54-section-title-line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.v54-section-title-input {
  border: 1px solid rgba(14, 96, 68, 0.16);
  border-radius: 12px;
  background: rgba(255,255,255,0.8);
  padding: 8px 10px;
  min-width: 220px;
  font-weight: 700;
  color: #0c2f25;
}

.v54-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 11px;
  color: rgba(8, 55, 38, 0.78);
  background: rgba(24, 161, 113, 0.10);
  border: 1px solid rgba(24, 161, 113, 0.12);
}

.v54-pill.warn {
  color: #936100;
  background: rgba(255, 183, 0, 0.14);
  border-color: rgba(255, 183, 0, 0.22);
}

.v54-section-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
  color: rgba(11, 55, 40, 0.66);
  font-size: 12px;
}

.v54-section-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.v54-action-btn {
  border: 1px solid rgba(16, 112, 80, 0.16);
  background: rgba(255,255,255,0.75);
  color: #0b3a2a;
  border-radius: 999px;
  padding: 7px 10px;
  font-size: 12px;
  cursor: pointer;
}

.v54-action-btn:hover,
.v54-action-btn.active {
  background: #15845f;
  color: white;
  border-color: #15845f;
}

.v54-action-btn.danger.active,
.v54-action-btn.danger:hover {
  background: #b63f3f;
  border-color: #b63f3f;
  color: white;
}

.v54-assets-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 14px;
}

.v54-asset-card {
  position: relative;
  width: 92px;
  border-radius: 14px;
  border: 1px solid rgba(10, 84, 58, 0.14);
  background: rgba(255,255,255,0.72);
  padding: 6px;
}

.v54-asset-card.disabled {
  filter: grayscale(1);
  opacity: 0.48;
}

.v54-asset-thumb {
  width: 80px;
  height: 52px;
  border-radius: 10px;
  object-fit: cover;
  background: rgba(10, 40, 28, 0.08);
  display: grid;
  place-items: center;
  color: rgba(10, 70, 48, 0.6);
  font-size: 11px;
}

.v54-asset-name {
  margin-top: 5px;
  font-size: 10px;
  color: rgba(8, 45, 32, 0.75);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.v54-asset-actions {
  display: flex;
  gap: 4px;
  margin-top: 5px;
}

.v54-mini-btn {
  border: 0;
  border-radius: 8px;
  padding: 3px 5px;
  font-size: 10px;
  color: #0c3d2c;
  background: rgba(24, 161, 113, 0.12);
  cursor: pointer;
}

.v54-mini-btn:hover {
  color: white;
  background: #15845f;
}

.v54-empty {
  padding: 18px;
  border-radius: 14px;
  background: rgba(13, 54, 39, 0.04);
  color: rgba(13, 54, 39, 0.56);
}
"""
    append_once(path, marker, content)


def patch_engine_ts() -> None:
    path = ROOT / "src" / "lib" / "engine.ts"
    if not path.exists():
        return
    marker = "// V5.4 user override helpers"
    content = r"""
// V5.4 user override helpers
export type V54SectionTitleMode = "full_card" | "overlay";
export type V54OverrideField =
  | "title"
  | "subtitle"
  | "title_mode"
  | "background"
  | "enabled"
  | "asset_refs"
  | "sort_index"
  | "section_type";

export interface V54OverrideAware {
  user_overridden?: boolean;
  user_override_fields?: string[];
}

export function mergeV54OverrideFields<T extends V54OverrideAware>(
  target: T,
  fields: V54OverrideField[],
): T {
  const existing = Array.isArray(target.user_override_fields)
    ? target.user_override_fields
    : [];

  const merged = [...existing];
  for (const field of fields) {
    if (!merged.includes(field)) merged.push(field);
  }

  return {
    ...target,
    user_overridden: true,
    user_override_fields: merged,
  };
}
"""
    append_once(path, marker, content)


def patch_video_engine() -> None:
    path = ROOT / "video_engine_v5.py"
    if not path.exists():
        return

    backup(path)
    text = read(path)

    text = re.sub(
        r'SCHEMA_VERSION\s*=\s*["\'][^"\']+["\']',
        'SCHEMA_VERSION = "5.4"',
        text,
        count=1,
    )
    text = re.sub(
        r'ENGINE_VERSION\s*=\s*["\'][^"\']+["\']',
        'ENGINE_VERSION = "video-create-engine-v5.4.0"',
        text,
        count=1,
    )

    marker = "V5.4 user override compatibility marker"
    if marker not in text:
        text += f