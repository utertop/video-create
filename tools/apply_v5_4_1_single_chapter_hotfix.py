# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path


ROOT = Path.cwd()
APP = ROOT / "src" / "App.tsx"
ENGINE_PY = ROOT / "video_engine_v5.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def backup(path: Path, suffix: str) -> None:
    bak = path.with_suffix(path.suffix + suffix)
    if path.exists() and not bak.exists():
        bak.write_text(read(path), encoding="utf-8")


def patch_app_labels() -> None:
    if not APP.exists():
        raise FileNotFoundError(APP)

    backup(APP, ".v541_single_chapter.bak")
    text = read(APP)
    changed = False

    replacements = [
        ("片头主标题", "视频片头标题（非封面）"),
        ("片头副标题（可选，不填则不显示）", "视频片头副标题（可选，不填则不显示）"),
        ("片头副标题", "视频片头副标题（可选，不填则不显示）"),
        ("选择片头背景", "选择片头卡背景"),
        ("默认：首个素材首帧虚化", "默认：首个素材首帧虚化；封面默认复用片头卡"),
    ]

    for old, new in replacements:
        if old in text and new not in text:
            text = text.replace(old, new, 1)
            changed = True
            print(f"[OK] App.tsx label: {old} -> {new}")

    if changed:
        write(APP, text)
        print("[OK] wrote src/App.tsx")
    else:
        print("[SKIP] src/App.tsx labels already look updated or targets not found")


def patch_engine_single_chapter_rule() -> None:
    if not ENGINE_PY.exists():
        raise FileNotFoundError(ENGINE_PY)

    backup(ENGINE_PY, ".v541_single_chapter.bak")
    text = read(ENGINE_PY)
    changed = False

    marker = '''        self.time = 0.0
        self.segments: List[RenderSegment] = []
        self.last_visual_source_path: Optional[str] = None
'''
    replacement = '''        self.time = 0.0
        self.segments: List[RenderSegment] = []
        self.last_visual_source_path: Optional[str] = None
        self.single_auto_section_id: Optional[str] = None
'''

    if marker in text and "self.single_auto_section_id" not in text:
        text = text.replace(marker, replacement, 1)
        changed = True
        print("[OK] video_engine_v5.py: added single_auto_section_id state")
    elif "self.single_auto_section_id" in text:
        print("[SKIP] video_engine_v5.py: single_auto_section_id already exists")
    else:
        print("[WARN] video_engine_v5.py: did not find Compiler.__init__ marker")

    marker = '''        self._add(
            "title",
            duration=4.0,
            text=self.blueprint.get("title"),
            subtitle=self.blueprint.get("subtitle"),
        )

        for section in self.blueprint.get("sections", []):
            self._section(section)
'''
    replacement = '''        self._add(
            "title",
            duration=4.0,
            text=self.blueprint.get("title"),
            subtitle=self.blueprint.get("subtitle"),
        )

        enabled_top_sections = [
            section for section in self.blueprint.get("sections", [])
            if section.get("enabled", True)
        ]
        if len(enabled_top_sections) == 1:
            only_section = enabled_top_sections[0]
            if (
                only_section.get("auto_detected", True)
                and not only_section.get("user_overridden", False)
                and self.blueprint_metadata.get("single_section_chapter_card", "auto") == "auto"
            ):
                # Single automatic folder chapters, such as a one-off folder named "haha",
                # are usually just containers. Suppress the extra chapter card to avoid
                # confusing it with the opening title card.
                self.single_auto_section_id = only_section.get("section_id")

        for section in self.blueprint.get("sections", []):
            self._section(section)
'''

    if marker in text and "enabled_top_sections = [" not in text:
        text = text.replace(marker, replacement, 1)
        changed = True
        print("[OK] video_engine_v5.py: added single top-level section detection")
    elif "enabled_top_sections = [" in text:
        print("[SKIP] video_engine_v5.py: single top-level section detection already exists")
    else:
        print("[WARN] video_engine_v5.py: did not find compile() title/section loop marker")

    marker = '''        has_custom_background = bool(background.get("user_overridden") and background.get("custom_path"))
        use_overlay_title = stype == "scenic_spot" and not has_custom_background and self.scenic_spot_title_mode == "overlay"

        pending_overlay_text = None
        pending_overlay_subtitle = None

        if stype in {"city", "date", "chapter"} or (stype == "scenic_spot" and not use_overlay_title):
'''
    replacement = '''        has_custom_background = bool(background.get("user_overridden") and background.get("custom_path"))
        use_overlay_title = stype == "scenic_spot" and not has_custom_background and self.scenic_spot_title_mode == "overlay"
        suppress_section_title = section.get("section_id") == self.single_auto_section_id

        pending_overlay_text = None
        pending_overlay_subtitle = None

        if suppress_section_title:
            # Only one automatic top-level section exists. Do not insert a chapter card
            # and do not overlay the folder name. The opening title already introduces the video.
            pass
        elif stype in {"city", "date", "chapter"} or (stype == "scenic_spot" and not use_overlay_title):
'''

    if marker in text and 'suppress_section_title = section.get("section_id") == self.single_auto_section_id' not in text:
        text = text.replace(marker, replacement, 1)
        changed = True
        print("[OK] video_engine_v5.py: suppress single automatic chapter card")
    elif 'suppress_section_title = section.get("section_id") == self.single_auto_section_id' in text:
        print("[SKIP] video_engine_v5.py: suppress_section_title logic already exists")
    else:
        print("[WARN] video_engine_v5.py: did not find _section() title-card marker")

    if changed:
        write(ENGINE_PY, text)
        print("[OK] wrote video_engine_v5.py")
    else:
        print("[SKIP] video_engine_v5.py no changes needed")


def main() -> None:
    if not (ROOT / "package.json").exists():
        raise SystemExit("请在项目根目录执行，例如：cd D:\\Automatic\\video_create")

    patch_app_labels()
    patch_engine_single_chapter_rule()

    print()
    print("V5.4.1 single auto-chapter hotfix applied.")
    print()
    print("请执行验证：")
    print(r"  python -m py_compile .\video_engine_v5.py")
    print(r"  npm run build")
    print()
    print("重要：删除旧输出目录里的 .video_create_project 后重新生成，否则旧 render_plan 仍会保留 haha 章节卡：")
    print(r'  Remove-Item "C:\Users\pb\Desktop\AI Video_output\.video_create_project" -Recurse -Force')


if __name__ == "__main__":
    main()
