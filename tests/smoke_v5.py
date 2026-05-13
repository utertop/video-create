# -*- coding: utf-8 -*-
"""
Minimal smoke test for Video Create Studio V5.x.

This test intentionally does not run final video rendering. It only verifies that
scan -> plan -> compile can complete with a tiny generated image. That keeps CI
fast and avoids FFmpeg/MoviePy rendering flakiness in hosted runners.

V5.3.2 unicode fix:
- GitHub Actions Windows PowerShell may expose stdout/stderr as cp1252.
- The smoke test uses Chinese folder names to verify Windows/Chinese-path behavior.
- Therefore we force UTF-8 for this test process and child Python processes.
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
    """Make prints safe on Windows CI where console encoding may be cp1252."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def format_cmd_for_log(args: list[str]) -> str:
    """Return a readable command line without raising UnicodeEncodeError."""
    return " ".join(str(x) for x in args)


def run_cmd(args: list[str]) -> None:
    print("RUN:", format_cmd_for_log(args))

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


def assert_document(path: Path, expected_type: str) -> dict:
    if not path.exists():
        raise AssertionError(f"expected output file does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    actual = data.get("document_type")
    if actual != expected_type:
        raise AssertionError(f"{path.name}: expected document_type={expected_type}, got {actual}")
    if not data.get("schema_version"):
        raise AssertionError(f"{path.name}: missing schema_version")
    return data


def main() -> None:
    configure_stdio()

    if not ENGINE.exists():
        raise SystemExit(f"missing engine file: {ENGINE}")

    with tempfile.TemporaryDirectory(prefix="video_create_v5_smoke_") as tmp:
        base = Path(tmp)

        # Keep Chinese names intentionally: this project targets Chinese Windows users,
        # and this smoke test should catch path/encoding regressions early.
        input_dir = base / "素材" / "泉州" / "开元寺"
        project_dir = base / "output" / ".video_create_project"
        input_dir.mkdir(parents=True, exist_ok=True)
        project_dir.mkdir(parents=True, exist_ok=True)

        image_path = input_dir / "P1000001.jpg"
        img = Image.new("RGB", (640, 360), (28, 90, 60))
        draw = ImageDraw.Draw(img)
        draw.rectangle((30, 30, 610, 330), outline=(230, 245, 230), width=6)
        draw.text((70, 150), "Video Create V5 Smoke", fill=(255, 255, 255))
        img.save(image_path, quality=92)

        media_library = project_dir / "media_library.json"
        story_blueprint = project_dir / "story_blueprint.json"
        render_plan = project_dir / "render_plan.json"

        run_cmd([
            sys.executable,
            str(ENGINE),
            "scan",
            "--input_folder",
            str(base / "素材"),
            "--output",
            str(media_library),
            "--recursive",
        ])
        assert_document(media_library, "media_library")

        run_cmd([
            sys.executable,
            str(ENGINE),
            "plan",
            "--library",
            str(media_library),
            "--output",
            str(story_blueprint),
        ])
        assert_document(story_blueprint, "story_blueprint")

        run_cmd([
            sys.executable,
            str(ENGINE),
            "compile",
            "--blueprint",
            str(story_blueprint),
            "--library",
            str(media_library),
            "--output",
            str(render_plan),
        ])
        plan = assert_document(render_plan, "render_plan")
        if not plan.get("segments"):
            raise AssertionError("render_plan.json contains no segments")

    print("V5 scan/plan/compile smoke test passed.")


if __name__ == "__main__":
    main()
