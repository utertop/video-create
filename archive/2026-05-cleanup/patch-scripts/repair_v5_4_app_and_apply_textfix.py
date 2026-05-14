# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()
APP = ROOT / "src" / "App.tsx"
ENGINE_TS = ROOT / "src" / "lib" / "engine.ts"
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


def looks_like_valid_app(text: str) -> bool:
    return (
        "export function App" in text
        and "from \"react\"" in text
        and "return (" in text
    )


def restore_app_if_corrupted() -> None:
    if not APP.exists():
        raise FileNotFoundError(APP)

    current = read(APP)
    if looks_like_valid_app(current):
        print("[OK] src/App.tsx looks like a valid module.")
        return

    print("[WARN] src/App.tsx does not look like a valid module. Trying to restore from backup...")

    candidates = [
        APP.with_suffix(APP.suffix + ".v54_textfix_v2.bak"),
        APP.with_suffix(APP.suffix + ".v54_textfix.bak"),
        APP.with_suffix(APP.suffix + ".v54.bak"),
        APP.with_suffix(APP.suffix + ".bak"),
        APP.with_suffix(APP.suffix + ".v53.bak"),
    ]

    for candidate in candidates:
        if candidate.exists():
            text = read(candidate)
            if looks_like_valid_app(text):
                backup(APP, ".broken_before_repair.bak")
                write(APP, text)
                print(f"[OK] restored src/App.tsx from {candidate.name}")
                return
            print(f"[SKIP] backup {candidate.name} exists but does not look valid.")

    raise SystemExit(
        "Cannot repair src/App.tsx automatically: no valid backup found. "
        "Please restore src/App.tsx from git, then run this script again."
    )


def patch_app_text_flow() -> None:
    text = read(APP)
    backup(APP, ".safe_textfix.bak")
    changed = False

    if "片头副标题（可选，不填则不显示）" not in text:
        text = text.replace("片头副标题", "片头副标题（可选，不填则不显示）", 1)
        changed = True

    old = '''      const blueprint = await planV5(libPath, `${v5ProjectDir}\\\\story_blueprint.json`);
      state.patch({ v5Blueprint: blueprint, v5Stage: "BLUEPRINT" });'''
    new = '''      const blueprint = await planV5(libPath, `${v5ProjectDir}\\\\story_blueprint.json`);
      const blueprintWithGuiText = {
        ...blueprint,
        title: state.title,
        subtitle: state.titleSubtitle,
        end_text: state.endText,
        metadata: {
          ...(blueprint.metadata || {}),
          end_text: state.endText,
          gui_title_applied: true,
        },
      };
      state.patch({ v5Blueprint: blueprintWithGuiText, v5Stage: "BLUEPRINT" });'''

    if old in text and "const blueprintWithGuiText" not in text:
        text = text.replace(old, new, 1)
        changed = True
        print("[OK] patched planV5 result -> blueprintWithGuiText")
    elif "const blueprintWithGuiText" in text:
        print("[SKIP] blueprintWithGuiText already exists.")
    else:
        print("[WARN] did not find exact planV5 patch target. App.tsx may already be customized.")

    old = '''      const blueprintForCompile = withBlueprintMetadata(state.v5Blueprint, {
        chapter_background_mode: state.chapterBackgroundMode,
        scenic_spot_title_mode: "overlay",
      });'''
    new = '''      const blueprintForCompile = withBlueprintMetadata(
        {
          ...state.v5Blueprint,
          title: state.title,
          subtitle: state.titleSubtitle,
          end_text: state.endText,
        },
        {
          chapter_background_mode: state.chapterBackgroundMode,
          scenic_spot_title_mode: "overlay",
          end_text: state.endText,
        },
      );'''

    if old in text and "end_text: state.endText" not in text:
        text = text.replace(old, new, 1)
        changed = True
        print("[OK] patched blueprintForCompile with GUI text")
    elif "end_text: state.endText" in text:
        print("[SKIP] blueprintForCompile already contains end_text.")
    else:
        print("[WARN] did not find exact withBlueprintMetadata patch target. App.tsx may already be customized.")

    if not looks_like_valid_app(text):
        raise SystemExit(
            "Patch would make App.tsx invalid, aborting before write. "
            "Your original App.tsx is preserved."
        )

    if changed:
        write(APP, text)
        print("[OK] wrote src/App.tsx")
    else:
        print("[SKIP] src/App.tsx no changes needed")


def patch_engine_ts() -> None:
    if not ENGINE_TS.exists():
        return

    text = read(ENGINE_TS)
    backup(ENGINE_TS, ".safe_textfix.bak")
    changed = False

    if "end_text?: string | null;" not in text:
        needle = "  title_subtitle?: string;\n"
        if needle in text:
            text = text.replace(
                needle,
                needle + "  /** Optional ending text. Real render text is compiled from story_blueprint before render. */\n  end_text?: string | null;\n",
                1,
            )
            changed = True
            print("[OK] added RenderV5Params.end_text to engine.ts")
        else:
            print("[WARN] did not find title_subtitle?: string; in engine.ts")

    if changed:
        write(ENGINE_TS, text)
        print("[OK] wrote src/lib/engine.ts")
    else:
        print("[SKIP] src/lib/engine.ts no changes needed")


def patch_engine_py() -> None:
    if not ENGINE_PY.exists():
        raise FileNotFoundError(ENGINE_PY)

    text = read(ENGINE_PY)
    backup(ENGINE_PY, ".safe_textfix.bak")
    changed = False

    if '"subtitle": "Travel Video",' in text:
        text = text.replace('"subtitle": "Travel Video",', '"subtitle": "",')
        changed = True
        print('[OK] removed default subtitle "Travel Video" from video_engine_v5.py')
    else:
        print('[SKIP] no hard-coded subtitle "Travel Video" found.')

    old = '        self._add("end", duration=3.0, text="To be continued!")'
    new = '''        end_text = (
            self.blueprint.get("end_text")
            or self.blueprint_metadata.get("end_text")
            or "To be continued!"
        )
        self._add("end", duration=3.0, text=end_text)'''

    if old in text:
        text = text.replace(old, new, 1)
        changed = True
        print("[OK] patched end-card text to use blueprint.end_text")
    elif 'self.blueprint.get("end_text")' in text:
        print("[SKIP] end_text logic already exists.")
    else:
        print("[WARN] did not find hard-coded end-card text target.")

    if changed:
        write(ENGINE_PY, text)
        print("[OK] wrote video_engine_v5.py")
    else:
        print("[SKIP] video_engine_v5.py no changes needed")


def main() -> None:
    if not (ROOT / "package.json").exists():
        raise SystemExit("Please run from project root, for example: cd D:\\Automatic\\video_create")

    restore_app_if_corrupted()
    patch_app_text_flow()
    patch_engine_ts()
    patch_engine_py()

    print()
    print("Repair + V5.4 title/subtitle/end-text hotfix applied.")
    print()
    print("Now run:")
    print(r"  python -m py_compile .\video_engine_v5.py")
    print(r"  npm run build")
    print()
    print("If build passes, delete old output project cache before regenerating video:")
    print(r'  Remove-Item "C:\Users\pb\Desktop\AI Video_output\.video_create_project" -Recurse -Force')


if __name__ == "__main__":
    main()
