# -*- coding: utf-8 -*-
"""Local JSON-line worker for Video Create Studio V5.

This process is intentionally small: Tauri should pass file paths and JSON
settings, never video bytes. It can later be packaged with PyInstaller/Nuitka
and used instead of repeatedly spawning `python video_engine_v5.py`.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from argparse import Namespace
from typing import Any, Dict

import video_engine_v5 as engine


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def worker_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "engine_version": engine.ENGINE_VERSION,
        "hardware_encoders": engine.detect_ffmpeg_hardware_encoders(),
    }


def run_task(task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or task.get("command") or "").strip()
    task_id = str(task.get("id") or "")

    if task_type == "health":
        return {"type": "result", "id": task_id, **worker_health()}

    if task_type == "render":
        engine.render_with_v56_stability(
            str(task["plan_path"]),
            str(task["output_path"]),
            dict(task.get("params") or {}),
        )
        return {"type": "result", "id": task_id, "ok": True, "output_path": task["output_path"]}

    if task_type == "preview-render":
        args = Namespace(
            plan=str(task["plan_path"]),
            output=str(task["output_path"]),
            params=json.dumps(task.get("params") or {}, ensure_ascii=False),
            height=int(task.get("height") or 540),
            fps=int(task.get("fps") or 15),
            max_duration=float(task.get("max_duration") or 20.0),
            max_segments=int(task.get("max_segments") or 8),
        )
        engine.command_preview_render(args)
        return {"type": "result", "id": task_id, "ok": True, "output_path": task["output_path"]}

    if task_type in {"stop", "shutdown"}:
        return {"type": "result", "id": task_id, "ok": True, "stopping": True}

    raise ValueError(f"unsupported worker task type: {task_type}")


def serve_once(raw: str) -> int:
    try:
        result = run_task(json.loads(raw))
        emit(result)
        return 0 if result.get("ok") else 1
    except Exception as exc:
        emit({
            "type": "error",
            "ok": False,
            "message": str(exc),
            "traceback": traceback.format_exc(limit=8),
        })
        return 1


def serve_forever() -> int:
    emit({"type": "worker_ready", **worker_health()})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            result = run_task(json.loads(line))
            emit(result)
            if result.get("stopping"):
                return 0
        except Exception as exc:
            emit({
                "type": "error",
                "ok": False,
                "message": str(exc),
                "traceback": traceback.format_exc(limit=8),
            })
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Video Create Studio V5 local worker")
    parser.add_argument("--health", action="store_true", help="Print worker health JSON and exit")
    parser.add_argument("--once", action="store_true", help="Read one JSON task from stdin and exit")
    args = parser.parse_args()

    if args.health:
        emit(worker_health())
        return 0
    if args.once:
        return serve_once(sys.stdin.read())
    return serve_forever()


if __name__ == "__main__":
    raise SystemExit(main())
