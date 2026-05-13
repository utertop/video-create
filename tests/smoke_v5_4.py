# -*- coding: utf-8 -*-
"""
V5.4 smoke test: Story Blueprint review and user override semantics.

This test verifies the V5.4 contract without running final video rendering:
1. scan -> plan generates a blueprint.
2. The blueprint can be edited like the GUI would edit it.
3. user_overridden / user_override_fields survive as explicit user intent.
4. chapter background mode and scenic-spot overlay mode can be represented.
5. compile accepts the modified blueprint and produces a render_plan.

It intentionally uses Chinese paths because the target users often work on
Chinese Windows directory names.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "video_engine_v5.py"


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def run_cmd(args: list[str]) -> None:
    print("RUN:", " ".join(str(x) for x in args))
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    completed = subprocess.run(
        args,
        cwd=str(ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    if completed.stdout:
        print(completed.stdout)
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_override(section: dict, *fields: str) -> None:
    section["user_overridden"] = True
    existing = list(section.get("user_override_fields") or [])
    for field in fields:
        if field not in existing:
            existing.append(field)
    section["user_override_fields"] = existing


def create_test_image(path: Path, text: str, color: tuple[int, int, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (640, 360), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle((28, 28, 612, 332), outline=(238, 247, 238), width=6)
    draw.text((70, 150), text, fill=(255, 255, 255))
    img.save(path, quality=92)


def main() -> None:
    configure_stdio()

    if not ENGINE.exists():
        raise SystemExit(f"missing engine file: {ENGINE}")

    with tempfile.TemporaryDirectory(prefix="video_create_v54_smoke_") as tmp:
        base = Path(tmp)
        source = base / "素材"
        project_dir = base / "output" / ".video_create_project"
        project_dir.mkdir(parents=True, exist_ok=True)

        create_test_image(source / "泉州" / "开元寺" / "P1000001.jpg", "Quanzhou Kaiyuan", (28, 90, 60))
        create_test_image(source / "泉州" / "西街" / "P1000002.jpg", "Quanzhou West Street", (90, 58, 28))
        create_test_image(source / "厦门" / "鼓浪屿" / "P1000003.jpg", "Xiamen Gulangyu", (28, 68, 110))

        media_library = project_dir / "media_library.json"
        story_blueprint = project_dir / "story_blueprint.json"
        render_plan = project_dir / "render_plan.json"

        run_cmd([
            sys.executable, str(ENGINE), "scan",
            "--input_folder", str(source),
            "--output", str(media_library),
            "--recursive",
        ])

        run_cmd([
            sys.executable, str(ENGINE), "plan",
            "--library", str(media_library),
            "--output", str(story_blueprint),
        ])

        blueprint = read_json(story_blueprint)
        sections = blueprint.get("sections") or []
        if not sections:
            raise AssertionError("story_blueprint.json contains no sections")

        first = sections[0]
        first["title"] = f"{first.get('title', '章节')} · 已人工调整"
        first["title_mode"] = "full_card"
        first["background"] = {
            "mode": "auto_first_asset",
            "custom_asset_id": None,
            "custom_path": None,
            "user_overridden": True,
        }
        add_override(first, "title", "title_mode", "background")

        scenic = next((s for s in sections if s.get("section_type") == "scenic_spot"), sections[-1])
        scenic["title_mode"] = "overlay"
        scenic.setdefault("background", {
            "mode": "auto_bridge",
            "custom_asset_id": None,
            "custom_path": None,
            "user_overridden": False,
        })
        add_override(scenic, "title_mode")

        refs = first.get("asset_refs") or []
        if refs:
            refs[0]["enabled"] = True
            refs[0]["role"] = "opening"
            refs[0]["user_overridden"] = True

        blueprint.setdefault("global_overrides", {})
        blueprint["global_overrides"]["chapter_background_mode"] = "auto_bridge"
        blueprint["global_overrides"]["scenic_spot_title_mode"] = "overlay"
        write_json(story_blueprint, blueprint)

        reloaded = read_json(story_blueprint)
        first_reloaded = reloaded["sections"][0]
        if not first_reloaded.get("user_overridden"):
            raise AssertionError("section user_overridden was not written")
        for required in ("title", "title_mode", "background"):
            if required not in first_reloaded.get("user_override_fields", []):
                raise AssertionError(f"missing user_override_fields entry: {required}")
        if first_reloaded.get("background", {}).get("mode") != "auto_first_asset":
            raise AssertionError("chapter background mode was not written")
        if not any((s.get("title_mode") == "overlay") for s in reloaded["sections"]):
            raise AssertionError("no section uses scenic overlay title mode")

        run_cmd([
            sys.executable, str(ENGINE), "compile",
            "--blueprint", str(story_blueprint),
            "--library", str(media_library),
            "--output", str(render_plan),
        ])

        plan = read_json(render_plan)
        if plan.get("document_type") != "render_plan":
            raise AssertionError(f"expected render_plan document, got {plan.get('document_type')}")
        if not plan.get("segments"):
            raise AssertionError("render_plan.json contains no segments")

    print("V5.4 blueprint override smoke test passed.")


if __name__ == "__main__":
    main()
