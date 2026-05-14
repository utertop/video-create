
# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path.cwd()
ENGINE_PY = ROOT / "video_engine_v5.py"
ENGINE_TS = ROOT / "src" / "lib" / "engine.ts"
WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"
README = ROOT / "README.md"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def backup(path: Path, suffix: str) -> None:
    if not path.exists():
        return
    bak = path.with_suffix(path.suffix + suffix)
    if not bak.exists():
        bak.write_text(read(path), encoding="utf-8")


V56_CODE = r"""
# =========================
# V5.6 long-video stability renderer
# =========================

def _v56_stable_json_hash(data: Any) -> str:
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def _v56_segment_cache_key(seg: Dict[str, Any], params: Dict[str, Any]) -> str:
    stable = {
        "engine_version": ENGINE_VERSION,
        "segment_id": seg.get("segment_id"),
        "type": seg.get("type"),
        "source_path": seg.get("source_path"),
        "asset_id": seg.get("asset_id"),
        "duration": seg.get("duration"),
        "text": seg.get("text"),
        "subtitle": seg.get("subtitle"),
        "background_mode": seg.get("background_mode"),
        "background_source_path": seg.get("background_source_path"),
        "background_source_path_2": seg.get("background_source_path_2"),
        "overlay_text": seg.get("overlay_text"),
        "title_style": seg.get("title_style"),
        "overlay_title_style": seg.get("overlay_title_style"),
        "aspect_ratio": params.get("aspect_ratio"),
        "fps": params.get("fps"),
        "quality": params.get("quality"),
    }
    return _v56_stable_json_hash(stable)


def _v56_build_chunk_groups(
    segments: List[Dict[str, Any]],
    chunk_seconds: float,
    params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    params = params or {}
    chunk_seconds = max(float(chunk_seconds or 240), 30.0)

    groups: List[Dict[str, Any]] = []
    current: List[Dict[str, Any]] = []
    current_duration = 0.0
    current_keys: List[str] = []

    for seg in segments:
        duration = float(seg.get("duration") or 0.0)
        if current and current_duration + duration > chunk_seconds:
            groups.append({
                "index": len(groups),
                "segments": current,
                "duration": round(current_duration, 3),
                "cache_key": _v56_stable_json_hash(current_keys),
            })
            current = []
            current_duration = 0.0
            current_keys = []

        current.append(seg)
        current_duration += duration
        current_keys.append(_v56_segment_cache_key(seg, params))

    if current:
        groups.append({
            "index": len(groups),
            "segments": current,
            "duration": round(current_duration, 3),
            "cache_key": _v56_stable_json_hash(current_keys),
        })

    return groups


def _v56_validate_video(path: Path, min_size: int = 1024) -> Tuple[bool, str, Optional[float]]:
    if not path.exists():
        return False, "文件不存在", None
    if path.stat().st_size < min_size:
        return False, f"文件过小: {path.stat().st_size} bytes", None

    if not HAS_MOVIEPY:
        return True, "MoviePy 不可用，仅完成大小校验", None

    clip = None
    try:
        clip = VideoFileClip(str(path))
        duration = float(clip.duration or 0.0)
        if duration <= 0:
            return False, "视频时长无效", duration
        return True, "校验通过", duration
    except Exception as exc:
        return False, f"视频读取校验失败: {exc}", None
    finally:
        if clip is not None:
            close_clip(clip)


def _v56_atomic_replace(tmp_path: Path, final_path: Path) -> None:
    ensure_parent(final_path)
    if final_path.exists():
        final_path.unlink()
    os.replace(str(tmp_path), str(final_path))


def _v56_write_build_report(report_path: Path, report: Dict[str, Any]) -> None:
    try:
        ensure_parent(report_path)
        with report_path.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        emit_event("log", message=f"写入 build_report.json 失败: {exc}")


def _v56_concat_chunks_ffmpeg(chunks: List[Path], tmp_output: Path, project_dir: Path) -> bool:
    if not chunks:
        raise RuntimeError("没有可拼接的 chunk 文件")

    concat_list = project_dir / "concat_list.txt"
    with concat_list.open("w", encoding="utf-8", newline="\n") as f:
        for chunk in chunks:
            escaped = chunk.resolve().as_posix().replace("'", r"'\''")
            f.write(f"file '{escaped}'\n")

    try:
        import subprocess
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg,
            "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            str(tmp_output),
        ]
        emit_event("phase", phase="concat", message="使用 FFmpeg 快速拼接分段视频", percent=96)
        completed = subprocess.run(cmd, cwd=str(project_dir), capture_output=True, text=True, encoding="utf-8", errors="replace")
        if completed.returncode == 0:
            return True
        emit_event("log", message=f"FFmpeg concat copy 失败，准备回退 MoviePy: {completed.stderr[-800:]}")
        return False
    except Exception as exc:
        emit_event("log", message=f"FFmpeg concat 不可用，准备回退 MoviePy: {exc}")
        return False


def _v56_concat_chunks_moviepy(chunks: List[Path], tmp_output: Path, fps: int, params: Dict[str, Any]) -> None:
    emit_event("phase", phase="concat", message="使用 MoviePy 回退拼接分段视频", percent=96)
    clips = []
    final = None
    try:
        for chunk in chunks:
            clips.append(VideoFileClip(str(chunk)))
        final = concatenate_videoclips(clips, method="compose")
        crf = quality_to_crf(params.get("quality") or params.get("python_quality") or "high")
        final.write_videofile(
            str(tmp_output),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            ffmpeg_params=["-crf", crf, "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=JsonMoviePyLogger(base_percent=96, span_percent=3),
        )
    finally:
        if final is not None:
            close_clip(final)
        for clip in clips:
            close_clip(clip)


def _v56_write_chunk_video(
    renderer: Any,
    chunk: Dict[str, Any],
    chunk_path: Path,
    fps: int,
    params: Dict[str, Any],
) -> None:
    clips = []
    combined = None
    tmp_chunk = chunk_path.with_suffix(".rendering.tmp.mp4")

    try:
        for seg in chunk["segments"]:
            emit_event(
                "phase",
                phase="render",
                message=f"渲染分段 {chunk['index'] + 1}: {seg.get('type')} {seg.get('text') or ''}",
                percent=min(94, 10 + chunk["index"]),
            )
            clip = renderer._segment(seg)
            clips.append(clip)

        if not clips:
            raise RuntimeError(f"chunk_{chunk['index']:03d} 没有可渲染 clip")

        combined = concatenate_videoclips(clips, method="compose")
        crf = quality_to_crf(params.get("quality") or params.get("python_quality") or "high")
        combined.write_videofile(
            str(tmp_chunk),
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            preset="veryfast",
            ffmpeg_params=["-crf", crf, "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
            logger=JsonMoviePyLogger(base_percent=20, span_percent=70),
        )

        ok, reason, _duration = _v56_validate_video(tmp_chunk)
        if not ok:
            raise RuntimeError(f"chunk 校验失败: {reason}")

        _v56_atomic_replace(tmp_chunk, chunk_path)
    finally:
        if combined is not None:
            close_clip(combined)
        for clip in clips:
            close_clip(clip)
        if tmp_chunk.exists():
            try:
                tmp_chunk.unlink()
            except Exception:
                pass
        try:
            gc.collect()
        except Exception:
            pass


def _v56_should_use_stable_renderer(plan: Dict[str, Any], params: Dict[str, Any]) -> bool:
    mode = str(params.get("render_mode") or params.get("long_video_mode") or "auto").lower()
    if mode in {"stable", "long", "long_stable", "true", "1", "yes"}:
        return True
    if mode in {"standard", "classic", "moviepy"}:
        return False

    total_duration = float(plan.get("total_duration") or 0.0)
    segments = plan.get("segments", [])
    return total_duration >= float(params.get("stable_threshold_seconds", 600)) or len(segments) >= int(params.get("stable_threshold_segments", 80))


class V56StableRenderer:
    def __init__(self, plan: Dict[str, Any], output: str, params: Dict[str, Any], plan_path: Optional[str] = None):
        self.plan = plan
        self.output = Path(output)
        self.params = params or {}
        self.plan_path = Path(plan_path).resolve() if plan_path else None

        if self.plan_path:
            self.project_dir = self.plan_path.parent
        else:
            self.project_dir = self.output.parent / ".video_create_project"

        self.chunk_dir = self.project_dir / "chunks" / self.output.stem
        self.chunk_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.chunk_dir / "chunk_manifest.json"
        self.report_path = self.project_dir / "build_report.json"

        self.fps = int(self.params.get("fps") or self.plan.get("render_settings", {}).get("fps") or 30)
        self.chunk_seconds = float(self.params.get("chunk_seconds") or self.params.get("stable_chunk_seconds") or 240)

    def _load_manifest(self) -> Dict[str, Any]:
        if self.manifest_path.exists():
            try:
                with self.manifest_path.open("r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"chunks": {}}
        return {"chunks": {}}

    def _save_manifest(self, manifest: Dict[str, Any]) -> None:
        ensure_parent(self.manifest_path)
        with self.manifest_path.open("w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

    def render(self) -> None:
        if not HAS_MOVIEPY:
            raise RuntimeError("MoviePy 不可用，无法渲染视频")

        started_at = datetime.now()
        tmp_output = self.output.with_suffix(".rendering.tmp.mp4")
        final_output = self.output

        if tmp_output.exists():
            try:
                tmp_output.unlink()
            except Exception:
                pass

        segments = self.plan.get("segments", [])
        groups = _v56_build_chunk_groups(segments, self.chunk_seconds, self.params)
        manifest = self._load_manifest()
        manifest.setdefault("engine_version", ENGINE_VERSION)
        manifest.setdefault("chunks", {})

        emit_event(
            "phase",
            phase="render",
            message=f"启用 V5.6 长视频稳定模式：{len(groups)} 个分段，每段约 {int(self.chunk_seconds)} 秒",
            percent=8,
        )

        renderer = Renderer(self.plan, str(self.output), self.params)
        rendered_chunks: List[Path] = []
        chunk_reports: List[Dict[str, Any]] = []

        for group in groups:
            idx = int(group["index"])
            chunk_name = f"chunk_{idx:03d}.mp4"
            chunk_path = self.chunk_dir / chunk_name
            key = str(group["cache_key"])
            existing = manifest.get("chunks", {}).get(chunk_name, {})

            ok, reason, duration = _v56_validate_video(chunk_path)
            if existing.get("cache_key") == key and existing.get("status") == "done" and ok:
                emit_event("phase", phase="render", message=f"复用已完成分段 {chunk_name}", percent=min(94, 10 + int((idx / max(len(groups), 1)) * 80)))
                rendered_chunks.append(chunk_path)
                chunk_reports.append({"name": chunk_name, "status": "cached", "duration": duration, "cache_key": key})
                continue

            try:
                _v56_write_chunk_video(renderer, group, chunk_path, self.fps, self.params)
                ok, reason, duration = _v56_validate_video(chunk_path)
                if not ok:
                    raise RuntimeError(reason)

                manifest["chunks"][chunk_name] = {
                    "status": "done",
                    "cache_key": key,
                    "path": str(chunk_path),
                    "duration": duration,
                    "updated_at": datetime.now().isoformat(),
                }
                self._save_manifest(manifest)
                rendered_chunks.append(chunk_path)
                chunk_reports.append({"name": chunk_name, "status": "rendered", "duration": duration, "cache_key": key})
            except Exception as exc:
                manifest["chunks"][chunk_name] = {
                    "status": "failed",
                    "cache_key": key,
                    "path": str(chunk_path),
                    "error": str(exc),
                    "updated_at": datetime.now().isoformat(),
                }
                self._save_manifest(manifest)
                _v56_write_build_report(self.report_path, {
                    "engine_version": ENGINE_VERSION,
                    "status": "failed",
                    "failed_chunk": chunk_name,
                    "error": str(exc),
                    "output_path": str(final_output),
                    "chunk_dir": str(self.chunk_dir),
                    "chunks": chunk_reports,
                    "created_at": datetime.now().isoformat(),
                })
                raise

        if not rendered_chunks:
            raise RuntimeError("没有成功渲染任何分段")

        concat_ok = _v56_concat_chunks_ffmpeg(rendered_chunks, tmp_output, self.project_dir)
        if not concat_ok:
            _v56_concat_chunks_moviepy(rendered_chunks, tmp_output, self.fps, self.params)

        ok, reason, final_duration = _v56_validate_video(tmp_output)
        if not ok:
            raise RuntimeError(f"最终视频校验失败，不覆盖旧文件: {reason}")

        _v56_atomic_replace(tmp_output, final_output)

        elapsed = (datetime.now() - started_at).total_seconds()
        report = {
            "engine_version": ENGINE_VERSION,
            "status": "done",
            "render_mode": "v5.6_long_video_stable",
            "output_path": str(final_output),
            "output_size_bytes": final_output.stat().st_size if final_output.exists() else None,
            "duration_seconds": final_duration,
            "elapsed_seconds": elapsed,
            "chunk_seconds": self.chunk_seconds,
            "chunk_count": len(rendered_chunks),
            "chunk_dir": str(self.chunk_dir),
            "chunks": chunk_reports,
            "created_at": datetime.now().isoformat(),
        }
        _v56_write_build_report(self.report_path, report)
        emit_event("phase", phase="done", message="长视频稳定渲染完成", percent=100)


def render_with_v56_stability(plan_path: str, output: str, params: Dict[str, Any]) -> None:
    plan = read_json(plan_path)
    if _v56_should_use_stable_renderer(plan, params):
        V56StableRenderer(plan, output, params, plan_path=plan_path).render()
    else:
        final_output = Path(output)
        tmp_output = final_output.with_suffix(".rendering.tmp.mp4")
        if tmp_output.exists():
            try:
                tmp_output.unlink()
            except Exception:
                pass

        Renderer(plan, str(tmp_output), params).render()
        ok, reason, _duration = _v56_validate_video(tmp_output)
        if not ok:
            raise RuntimeError(f"标准渲染结果校验失败，不覆盖旧文件: {reason}")
        _v56_atomic_replace(tmp_output, final_output)

"""


def patch_engine_py() -> None:
    if not ENGINE_PY.exists():
        raise FileNotFoundError(ENGINE_PY)

    backup(ENGINE_PY, ".v56_long_stability.bak")
    text = read(ENGINE_PY)
    changed = False

    if "import subprocess" not in text:
        text = text.replace("import sys\n", "import sys\nimport subprocess\n", 1)
        changed = True
    if "import gc" not in text:
        text = text.replace("import tempfile\n", "import tempfile\nimport gc\n", 1)
        changed = True

    text = text.replace("Video Create Studio V5.5.1 Engine", "Video Create Studio V5.6.0 Engine")
    text = text.replace("Video Create Studio V5.5.0 Engine", "Video Create Studio V5.6.0 Engine")
    text = text.replace('ENGINE_VERSION = "video-create-engine-v5.5.1"', 'ENGINE_VERSION = "video-create-engine-v5.6.0"')
    text = text.replace('ENGINE_VERSION = "video-create-engine-v5.5.0"', 'ENGINE_VERSION = "video-create-engine-v5.6.0"')

    if "class V56StableRenderer" not in text:
        marker = "\ndef command_render"
        if marker not in text:
            raise RuntimeError("Could not find command_render insertion point")
        text = text.replace(marker, "\n" + V56_CODE + "\n\ndef command_render", 1)
        changed = True

    pattern = re.compile(
        r"def command_render\(args: argparse\.Namespace\) -> None:\n(?P<body>.*?)(?=\ndef command_|\ndef build_parser|\nif __name__)",
        re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        raise RuntimeError("Could not find command_render() body")

    new_func = """def command_render(args: argparse.Namespace) -> None:
    params = json.loads(args.params) if getattr(args, "params", None) else {}
    render_with_v56_stability(args.plan, args.output, params)

"""
    old_func = match.group(0)
    if "render_with_v56_stability(args.plan, args.output, params)" not in old_func:
        text = text[: match.start()] + new_func + text[match.end():]
        changed = True

    if changed:
        write(ENGINE_PY, text)
        print("[OK] patched video_engine_v5.py with V5.6 long-video stable renderer")
    else:
        print("[SKIP] video_engine_v5.py already patched")


def patch_engine_ts() -> None:
    if not ENGINE_TS.exists():
        return
    backup(ENGINE_TS, ".v56_long_stability.bak")
    text = read(ENGINE_TS)
    changed = False

    if "render_mode?: string | null;" not in text:
        needle = "  chapter_background_mode?: V5ChapterBackgroundMode;\n"
        if needle in text:
            text = text.replace(
                needle,
                needle + "  /** auto | standard | long_stable. Auto uses V5.6 chunk rendering for long timelines. */\n  render_mode?: string | null;\n  /** Chunk size in seconds for V5.6 long-video stable renderer. */\n  chunk_seconds?: number | null;\n",
                1,
            )
            changed = True
        else:
            print("[WARN] engine.ts RenderV5Params insertion target not found")

    if changed:
        write(ENGINE_TS, text)
        print("[OK] patched src/lib/engine.ts with V5.6 render params")
    else:
        print("[SKIP] src/lib/engine.ts no changes needed")


def patch_workflow() -> None:
    if not WORKFLOW.exists():
        return
    backup(WORKFLOW, ".v56_long_stability.bak")
    text = read(WORKFLOW)
    if "smoke_v5_6_long_video_stability.py" in text:
        print("[SKIP] workflow already contains V5.6 smoke test")
        return

    lines = text.splitlines()
    out = []
    inserted = False
    for line in lines:
        out.append(line)
        if not inserted and ("python .\\tests\\smoke_v5_5_1_moviepy_opacity.py" in line or "python .\\tests\\smoke_v5_5_title_style.py" in line or "python .\\tests\\smoke_v5.py" in line):
            indent = line[: len(line) - len(line.lstrip())]
            out.append(indent + "python .\\tests\\smoke_v5_6_long_video_stability.py")
            inserted = True

    if not inserted:
        out.append("")
        out.append("      - name: Python V5.6 long-video stability smoke test")
        out.append("        run: python .\\tests\\smoke_v5_6_long_video_stability.py")

    write(WORKFLOW, "\n".join(out) + "\n")
    print("[OK] workflow patched with V5.6 smoke test")


def patch_readme() -> None:
    if not README.exists():
        return
    backup(README, ".v56_long_stability.bak")
    text = read(README)
    if "V5.6 长视频性能与稳定性优化" in text:
        print("[SKIP] README already contains V5.6 section")
        return

    addition = """

## V5.6 长视频性能与稳定性优化

V5.6 解决 20~30 分钟以上视频渲染时卡死、内存过高、最终 mp4 损坏的问题。

核心改进：

- **原子输出**：先写 `*.rendering.tmp.mp4`，校验通过后再替换最终 mp4，失败不会污染旧成品。
- **长视频自动分段渲染**：当总时长超过阈值或 segment 数较多时，自动按 3~5 分钟切 chunk。
- **可恢复 chunk manifest**：已完成 chunk 会复用，失败后下次只重跑失败分段。
- **FFmpeg 快速拼接**：优先使用 `imageio-ffmpeg` 的 ffmpeg concat；失败时回退 MoviePy 拼接。
- **资源释放**：每个 chunk 渲染后执行 `close()` 和 `gc.collect()`。
- **构建报告**：输出 `.video_create_project/build_report.json`，记录 chunk、时长、耗时和错误。

默认模式为 `auto`：短视频继续走标准渲染，长视频自动启用稳定模式。
"""
    write(README, text.rstrip() + addition + "\n")
    print("[OK] README appended V5.6 section")


def main() -> None:
    if not (ROOT / "package.json").exists():
        raise SystemExit("请在项目根目录执行，例如：cd D:\\Automatic\\video_create")

    patch_engine_py()
    patch_engine_ts()
    patch_workflow()
    patch_readme()

    print()
    print("V5.6 long-video stability patch applied.")
    print()
    print("验证命令：")
    print(r"  python -m py_compile .\video_engine_v5.py")
    print(r"  python .\tests\smoke_v5_6_long_video_stability.py")
    print(r"  npm run build")
    print(r"  cargo check --manifest-path .\src-tauri\Cargo.toml")
    print()
    print("如果 Tauri 仍使用旧引擎，删除复制文件后重启：")
    print(r"  Remove-Item .\src-tauri\target\debug\video_engine_v5.py -Force")


if __name__ == "__main__":
    main()
