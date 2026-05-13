# -*- coding: utf-8 -*-
"""
V5.4.2 directory recognition strategy smoke test.

Covers:
1. Sibling folders under project root stay consistent as chapter:
   登山 / 猫咪 / 雪崩 -> all chapter.
2. Travel hierarchy keeps scenic spots under city:
   泉州/开元寺, 泉州/西街, 厦门/鼓浪屿 -> city + scenic_spot.
3. directory_nodes expose raw_detected_type and signals for explainability.
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


def make_image(path: Path, label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (640, 360), (30, 90, 60))
    draw = ImageDraw.Draw(img)
    draw.text((40, 160), label, fill=(255, 255, 255))
    img.save(path, quality=90)


def run_scan(input_dir: Path, output_path: Path) -> dict:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    cmd = [
        sys.executable,
        str(ENGINE),
        "scan",
        "--input_folder",
        str(input_dir),
        "--output",
        str(output_path),
        "--recursive",
    ]
    completed = subprocess.run(
        cmd,
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
    return json.loads(output_path.read_text(encoding="utf-8"))


def nodes_by_name(data: dict) -> dict:
    return {node["name"]: node for node in data.get("directory_nodes", [])}


def assert_node_type(nodes: dict, name: str, expected: str) -> None:
    node = nodes.get(name)
    if not node:
        raise AssertionError(f"missing directory node: {name}")
    actual = node.get("detected_type")
    if actual != expected:
        raise AssertionError(f"{name}: expected {expected}, got {actual}. reason={node.get('reason')}")
    if "signals" not in node:
        raise AssertionError(f"{name}: missing signals for explainability")
    if "raw_detected_type" not in node:
        raise AssertionError(f"{name}: missing raw_detected_type")


def main() -> None:
    configure_stdio()

    with tempfile.TemporaryDirectory(prefix="video_create_v542_dir_") as tmp:
        base = Path(tmp)

        generic = base / "AI Video"
        make_image(generic / "登山" / "a.jpg", "mountain activity")
        make_image(generic / "猫咪" / "b.jpg", "cat")
        make_image(generic / "雪崩" / "c.jpg", "avalanche")

        generic_out = base / "generic_media_library.json"
        generic_data = run_scan(generic, generic_out)
        generic_nodes = nodes_by_name(generic_data)

        assert_node_type(generic_nodes, "登山", "chapter")
        assert_node_type(generic_nodes, "猫咪", "chapter")
        assert_node_type(generic_nodes, "雪崩", "chapter")

        travel = base / "旅行素材"
        make_image(travel / "泉州" / "开元寺" / "a.jpg", "kaiyuan temple")
        make_image(travel / "泉州" / "西街" / "b.jpg", "west street")
        make_image(travel / "厦门" / "鼓浪屿" / "c.jpg", "gulangyu")

        travel_out = base / "travel_media_library.json"
        travel_data = run_scan(travel, travel_out)
        travel_nodes = nodes_by_name(travel_data)

        assert_node_type(travel_nodes, "泉州", "city")
        assert_node_type(travel_nodes, "厦门", "city")
        assert_node_type(travel_nodes, "开元寺", "scenic_spot")
        assert_node_type(travel_nodes, "西街", "scenic_spot")
        assert_node_type(travel_nodes, "鼓浪屿", "scenic_spot")

    print("V5.4.2 directory recognition strategy smoke test passed.")


if __name__ == "__main__":
    main()
