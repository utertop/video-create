# -*- coding: utf-8 -*-
"""
Apply Video Create Studio V5.3.2 stability patch.

Run from repository root:
    python tools/apply_v5_3_2_patch.py

This script performs localized, idempotent updates:
  - align V5 schema/engine version numbers
  - make top-level --help independent from heavy Python media dependencies
  - fix malformed Cascadia Mono CSS font-family snippets if present
  - append a README V5.3.2 engineering note if not already present
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def backup(path: Path) -> None:
    if path.exists():
        bak = path.with_suffix(path.suffix + ".v5_3_2.bak")
        if not bak.exists():
            shutil.copy2(path, bak)


def patch_engine_ts() -> None:
    path = ROOT / "src" / "lib" / "engine.ts"
    if not path.exists():
        print(f"skip missing {path}")
        return
    backup(path)
    text = read(path)
    text = re.sub(r'export const V5_SCHEMA_VERSION = "[^"]+";', 'export const V5_SCHEMA_VERSION = "5.3";', text)
    write(path, text)
    print("patched src/lib/engine.ts")


def patch_video_engine() -> None:
    path = ROOT / "video_engine_v5.py"
    if not path.exists():
        print(f"skip missing {path}")
        return
    backup(path)
    text = read(path)

    text = re.sub(r'SCHEMA_VERSION\s*=\s*"[^"]+"', 'SCHEMA_VERSION = "5.3"', text)
    text = re.sub(r'ENGINE_VERSION\s*=\s*"[^"]+"', 'ENGINE_VERSION = "video-create-engine-v5.3.2"', text)

    marker = "# V5.3.2 early help guard"
    if marker not in text:
        guard = r'''
# V5.3.2 early help guard
# Keep `python video_engine_v5.py --help` available even before optional media
# dependencies such as numpy/moviepy/pillow are installed. Real scan/render work
# still validates dependencies when the command continues past this point.
def _print_early_help_without_optional_deps() -> None:
    print("""Video Create Studio V5.3.2 Engine

usage:
  python video_engine_v5.py scan    --input_folder <folder> --output <media_library.json> [--recursive]
  python video_engine_v5.py plan    --library <media_library.json> --output <story_blueprint.json>
  python video_engine_v5.py compile --blueprint <story_blueprint.json> --library <media_library.json> --output <render_plan.json>
  python video_engine_v5.py render  --plan <render_plan.json> --output <video.mp4> [--params <json>]

Pipeline:
  scan -> media_library.json -> plan -> story_blueprint.json -> compile -> render_plan.json -> render -> final mp4

Notes:
  - --help intentionally does not import heavy media dependencies.
  - scan/render require dependencies from requirements.txt.
""")


if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
    _print_early_help_without_optional_deps()
    raise SystemExit(0)

'''
        needle = "try:\n    from proglog import ProgressBarLogger"
        if needle in text:
            text = text.replace(needle, guard + needle, 1)
        else:
            # Fallback: insert after the last top-level stdlib import block we know exists.
            fallback = "from typing import Any, Dict, Iterable, List, Optional, Tuple\n"
            text = text.replace(fallback, fallback + guard, 1)

    write(path, text)
    print("patched video_engine_v5.py")


def patch_styles() -> None:
    path = ROOT / "src" / "styles.css"
    if not path.exists():
        print(f"skip missing {path}")
        return
    backup(path)
    text = read(path)
    # Fix malformed snippets seen in esbuild warnings, while preserving valid declarations.
    text = text.replace('font-family: " Cascadia Mono\\, Consolas, monospace;', 'font-family: "Cascadia Mono", Consolas, monospace;')
    text = text.replace('font-family: " Cascadia Mono\\, Consolas, monospace', 'font-family: "Cascadia Mono", Consolas, monospace')
    text = re.sub(
        r'font-family:\s*"\s*Cascadia Mono\\,\s*Consolas,\s*monospace;?',
        'font-family: "Cascadia Mono", Consolas, monospace;',
        text,
    )
    write(path, text)
    print("patched src/styles.css")


def patch_readme() -> None:
    path = ROOT / "README.md"
    if not path.exists():
        print(f"skip missing {path}")
        return
    backup(path)
    text = read(path)
    marker = "## V5.3.2 稳定收口"
    if marker in text:
        print("README.md already contains V5.3.2 note")
        return
    note = """

## V5.3.2 稳定收口

V5.3.2 的目标不是继续堆叠新剪辑能力，而是把 V5.3 已经具备的能力收口成可验证、可排查、可维护的工程版本。

当前主流程：

```text
scan -> media_library.json -> plan -> story_blueprint.json -> compile -> render_plan.json -> render -> final mp4
```

关键能力：

- 片头 / 片尾默认使用首帧 / 尾帧虚化背景。
- 片头 / 片尾支持用户手动选择背景图片。
- 投稿封面默认复用片头卡的虚化背景与标题布局。
- 章节卡支持智能过渡背景、章节首图背景、纯色背景、自定义背景。
- 景点章节默认使用标题叠加，减少完整章节卡造成的视频割裂感。
- CI 增加 Python 依赖安装与 scan / plan / compile 最小烟测。

V3 `make_bilibili_video_v3.py` 仅作为 Legacy 兼容路径保留；V5 主流程以 `video_engine_v5.py` 为准。
"""
    write(path, text.rstrip() + note + "\n")
    print("patched README.md")


def main() -> None:
    patch_engine_ts()
    patch_video_engine()
    patch_styles()
    patch_readme()
    print("V5.3.2 stability patch applied.")


if __name__ == "__main__":
    main()
