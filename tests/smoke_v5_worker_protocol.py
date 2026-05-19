from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image


ROOT = Path("tests/tmp_vcs_worker_protocol")


def make_image(path: Path, color: tuple[int, int, int]) -> None:
    image = Image.new("RGB", (960, 540), color)
    image.save(path, quality=92)


def worker_command() -> list[str]:
    worker_exe = os.environ.get("VCS_WORKER_EXE", "").strip()
    if worker_exe:
        return [worker_exe]
    return [sys.executable, "video_engine_worker.py"]


def run_worker_once(task: dict) -> dict:
    command = worker_command() + ["--once"]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        command,
        input=json.dumps(task, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        check=False,
        env=env,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode != 0:
        raise RuntimeError(f"worker task failed: {stderr or stdout}")

    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    assert lines, "expected worker output"
    payload = json.loads(lines[-1])
    assert payload.get("ok") is True, payload
    return payload


def prepare_fixture() -> tuple[Path, Path, Path]:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    input_dir = ROOT / "input"
    project_dir = ROOT / ".video_create_project"
    input_dir.mkdir(parents=True)
    project_dir.mkdir(parents=True)
    make_image(input_dir / "first.jpg", (42, 112, 82))
    make_image(input_dir / "second.jpg", (160, 92, 64))
    return input_dir, project_dir, ROOT


def test_worker_protocol_flow() -> None:
    input_dir, project_dir, root = prepare_fixture()

    health = run_worker_once({"type": "health", "id": "health"})
    assert health["engine_version"]

    library_path = project_dir / "media_library.json"
    scan = run_worker_once(
        {
            "type": "scan",
            "id": "scan",
            "input_folder": str(input_dir),
            "output_path": str(library_path),
            "recursive": True,
        }
    )
    assert library_path.is_file()
    assert scan["document"]["document_type"] == "media_library"
    assert (scan["document"].get("proxy_media_manifest", {}).get("summary") or {}).get("ready", 0) >= 2

    blueprint_path = project_dir / "story_blueprint.json"
    plan = run_worker_once(
        {
            "type": "plan",
            "id": "plan",
            "library_path": str(library_path),
            "output_path": str(blueprint_path),
        }
    )
    assert blueprint_path.is_file()
    assert plan["document"]["document_type"] == "story_blueprint"

    render_plan_path = project_dir / "render_plan.json"
    compile_result = run_worker_once(
        {
            "type": "compile",
            "id": "compile",
            "blueprint_path": str(blueprint_path),
            "library_path": str(library_path),
            "output_path": str(render_plan_path),
        }
    )
    assert render_plan_path.is_file()
    assert compile_result["document"]["document_type"] == "render_plan"

    preview_path = root / "preview.mp4"
    preview = run_worker_once(
        {
            "type": "preview-render",
            "id": "preview-render",
            "plan_path": str(render_plan_path),
            "output_path": str(preview_path),
            "params": {"aspect_ratio": "16:9"},
            "height": 360,
            "fps": 12,
            "max_duration": 3.0,
            "max_segments": 1,
        }
    )
    assert preview_path.is_file()
    assert preview["output_path"] == str(preview_path)

    title_preview_path = root / "title_preview.mp4"
    title_preview = run_worker_once(
        {
            "type": "preview-title",
            "id": "preview-title",
            "title": "旅行样片",
            "subtitle": "Worker Preview",
            "style": {"preset": "travel_postcard", "motion": "postcard_drift"},
            "output_path": str(title_preview_path),
            "aspect_ratio": "16:9",
            "background": "travel",
            "duration": 3.0,
        }
    )
    assert title_preview_path.is_file()
    assert title_preview["output_path"] == str(title_preview_path)


if __name__ == "__main__":
    test_worker_protocol_flow()
    print("V5 worker protocol smoke test passed")
