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
from pathlib import Path
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


def _ensure_parent(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _read_output_json(path: str) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_task(task: Dict[str, Any]) -> Dict[str, Any]:
    task_type = str(task.get("type") or task.get("command") or "").strip()
    task_id = str(task.get("id") or "")

    if task_type == "health":
        return {"type": "result", "id": task_id, **worker_health()}

    if task_type == "scan":
        output_path = str(task["output_path"])
        _ensure_parent(output_path)
        engine.command_scan(
            Namespace(
                input_folder=str(task["input_folder"]),
                output=output_path,
                recursive=bool(task.get("recursive", True)),
            )
        )
        return {
            "type": "result",
            "id": task_id,
            "ok": True,
            "output_path": output_path,
            "document": _read_output_json(output_path),
        }

    if task_type == "plan":
        output_path = str(task["output_path"])
        _ensure_parent(output_path)
        engine.command_plan(
            Namespace(
                library=str(task["library_path"]),
                output=output_path,
                strategy=str(task.get("strategy") or "city_date_spot"),
                template=str(task.get("template") or "auto"),
                music_blueprint=str(task.get("music_blueprint") or "recommend"),
            )
        )
        return {
            "type": "result",
            "id": task_id,
            "ok": True,
            "output_path": output_path,
            "document": _read_output_json(output_path),
        }

    if task_type == "compile":
        output_path = str(task["output_path"])
        _ensure_parent(output_path)
        engine.command_compile(
            Namespace(
                blueprint=str(task["blueprint_path"]),
                library=str(task["library_path"]),
                output=output_path,
            )
        )
        return {
            "type": "result",
            "id": task_id,
            "ok": True,
            "output_path": output_path,
            "document": _read_output_json(output_path),
        }

    if task_type == "timeline-generate":
        output_path = str(task["output_path"])
        _ensure_parent(output_path)
        engine.command_timeline_generate(
            Namespace(
                render_plan=str(task["render_plan_path"]),
                output=output_path,
                blueprint=str(task["blueprint_path"]) if task.get("blueprint_path") else None,
                library=str(task["library_path"]) if task.get("library_path") else None,
                existing_timeline=str(task["existing_timeline_path"]) if task.get("existing_timeline_path") else None,
                project_dir=str(task["project_dir"]) if task.get("project_dir") else None,
            )
        )
        return {
            "type": "result",
            "id": task_id,
            "ok": True,
            "output_path": output_path,
            "document": _read_output_json(output_path),
        }

    if task_type == "timeline-compile":
        output_path = str(task["output_path"])
        _ensure_parent(output_path)
        engine.command_timeline_compile(
            Namespace(
                timeline=str(task["timeline_path"]),
                base_render_plan=str(task["base_render_plan_path"]),
                output=output_path,
            )
        )
        return {
            "type": "result",
            "id": task_id,
            "ok": True,
            "output_path": output_path,
            "document": _read_output_json(output_path),
        }

    if task_type == "timeline-preview-manifest":
        output_path = str(task["output_path"])
        _ensure_parent(output_path)
        engine.command_timeline_preview_manifest(
            Namespace(
                timeline=str(task["timeline_path"]),
                output=output_path,
                library=str(task["library_path"]) if task.get("library_path") else None,
                proxy_manifest=str(task["proxy_manifest_path"]) if task.get("proxy_manifest_path") else None,
                project_dir=str(task["project_dir"]) if task.get("project_dir") else None,
                batch_size=int(task.get("batch_size") or 8),
            )
        )
        return {
            "type": "result",
            "id": task_id,
            "ok": True,
            "output_path": output_path,
            "document": _read_output_json(output_path),
        }

    if task_type == "timeline-preview-assets":
        output_path = str(task["output_path"])
        _ensure_parent(output_path)
        engine.command_timeline_preview_assets(
            Namespace(
                timeline=str(task["timeline_path"]),
                output=output_path,
                library=str(task["library_path"]) if task.get("library_path") else None,
                proxy_manifest=str(task["proxy_manifest_path"]) if task.get("proxy_manifest_path") else None,
                project_dir=str(task["project_dir"]) if task.get("project_dir") else None,
            )
        )
        return {
            "type": "result",
            "id": task_id,
            "ok": True,
            "output_path": output_path,
            "document": _read_output_json(output_path),
        }

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

    if task_type == "preview-title":
        output_path = str(task["output_path"])
        _ensure_parent(output_path)
        args = Namespace(
            title=str(task.get("title") or ""),
            subtitle=str(task.get("subtitle") or ""),
            style_json=json.dumps(task.get("style") or {}, ensure_ascii=False),
            output=output_path,
            aspect_ratio=str(task.get("aspect_ratio") or "16:9"),
            background=str(task.get("background") or "travel"),
            duration=str(task.get("duration") or "3.0"),
        )
        engine.command_preview_title(args)
        return {
            "type": "result",
            "id": task_id,
            "ok": True,
            "output_path": output_path,
        }

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
