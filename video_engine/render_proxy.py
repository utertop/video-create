"""Proxy media and display-normalization helpers for the V5 renderer."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional


EmitEvent = Callable[..., None]
ReadJson = Callable[[str], Dict[str, Any]]


def _noop_emit_event(_event_type: str, **_payload: Any) -> None:
    return None


def _default_read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def video_needs_display_normalization(source: Path) -> bool:
    """Detect mp4 files whose encoded size differs from display geometry."""
    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        completed = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        probe_text = completed.stderr or ""
        lower = probe_text.lower()
        if "displaymatrix" in lower or "rotate" in lower or "rotation of" in lower:
            return True
        return bool(re.search(r"\bSAR\s+(?!1:1\b)\d+:\d+", probe_text))
    except Exception:
        return False


def normalize_proxy_manifest(source: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(source, dict):
        return {}
    assets = source.get("assets")
    if not isinstance(assets, dict):
        return {}
    normalized: Dict[str, Dict[str, Any]] = {}
    for key, entry in assets.items():
        if not isinstance(entry, dict):
            continue
        abs_path = str(entry.get("source_path") or key or "")
        if not abs_path:
            continue
        normalized[abs_path] = entry
    return normalized


def load_proxy_manifest_from_library_path(
    library_path: Optional[str],
    *,
    read_json_fn: ReadJson = _default_read_json,
) -> Dict[str, Dict[str, Any]]:
    if not library_path:
        return {}
    path = Path(str(library_path))
    if not path.is_file():
        return {}
    try:
        library = read_json_fn(str(path))
    except Exception:
        return {}
    return normalize_proxy_manifest(library.get("proxy_media_manifest"))


def proxy_media_summary(renderer: Any) -> Dict[str, int]:
    return dict(getattr(renderer, "proxy_media_stats", {}) or {})


def emit_proxy_media_summary(
    renderer: Any,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
) -> None:
    proxy_cache = proxy_media_summary(renderer)
    if int(proxy_cache.get("eligible") or 0) <= 0:
        return
    emit_event_fn(
        "log",
        message=(
            "Proxy media summary: "
            f"eligible={proxy_cache.get('eligible')}, "
            f"hit={proxy_cache.get('hit')}, "
            f"manifest_hit={proxy_cache.get('manifest_hit')}, "
            f"created={proxy_cache.get('created')}, "
            f"fallback={proxy_cache.get('fallback')}"
        ),
    )
    emit_event_fn("proxy_cache", **proxy_cache)


def get_proxy_source(
    renderer: Any,
    source: Path,
    is_video: bool,
    *,
    engine_version: str,
    scan_proxy_profile: Dict[str, Any],
    emit_event_fn: EmitEvent = _noop_emit_event,
    image_cls: Any = None,
    image_ops: Any = None,
) -> Path:
    use_proxy = bool(
        renderer.params.get("preview")
        or renderer.params.get("proxy_media")
        or renderer.params.get("use_proxy_media")
        or renderer.params.get("optimized_media") == "proxy"
    )
    if not use_proxy:
        return source

    proxy_dir = renderer.render_cache_dir.parent / "proxies"
    proxy_dir.mkdir(parents=True, exist_ok=True)

    tw, th = renderer.target_size
    renderer.proxy_media_stats["eligible"] += 1
    manifest_entry = renderer.proxy_media_manifest.get(str(source.resolve())) or renderer.proxy_media_manifest.get(str(source))
    if manifest_entry:
        profiles = manifest_entry.get("profiles") or {}
        profile = profiles.get(str(scan_proxy_profile["name"])) if isinstance(profiles, dict) else None
        proxy_path_value = profile.get("path") if isinstance(profile, dict) else None
        if proxy_path_value:
            manifest_proxy_path = Path(str(proxy_path_value))
            if manifest_proxy_path.is_file():
                renderer.proxy_media_stats["manifest_hit"] += 1
                renderer.proxy_media_stats["hit"] += 1
                return manifest_proxy_path

    proxy_key = f"{engine_version}|{source.resolve()}|{source.stat().st_mtime_ns}|{source.stat().st_size}|{tw}x{th}|video={is_video}"
    proxy_hash = hashlib.md5(proxy_key.encode()).hexdigest()

    ext = ".mp4" if is_video else ".jpg"
    proxy_path = proxy_dir / f"proxy_{proxy_hash}{ext}"

    if proxy_path.exists():
        renderer.proxy_media_stats["hit"] += 1
        return proxy_path

    emit_event_fn("log", message=f"Creating preview proxy: {source.name}")
    try:
        if is_video:
            import imageio_ffmpeg

            cmd = [
                imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(source),
                "-vf", f"scale='min({tw},iw)':'min({th},ih)':force_original_aspect_ratio=decrease",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
                "-c:a", "copy",
                str(proxy_path),
            ]
            subprocess.run(cmd, check=True, capture_output=True)
        else:
            if image_cls is None or image_ops is None:
                from PIL import Image, ImageOps

                image_cls = Image
                image_ops = ImageOps
            with image_cls.open(source) as img:
                img = image_ops.exif_transpose(img).convert("RGB")
                img.thumbnail((tw, th), image_cls.Resampling.LANCZOS)
                img.save(proxy_path, quality=85)
        renderer.proxy_media_stats["created"] += 1
        return proxy_path
    except Exception as exc:
        renderer.proxy_media_stats["fallback"] += 1
        emit_event_fn("log", message=f"Proxy media creation failed, using source: {exc}")
        return source


def normalize_video_display_geometry(
    renderer: Any,
    source: Path,
    *,
    emit_event_fn: EmitEvent = _noop_emit_event,
    needs_display_normalization_fn: Callable[[Path], bool] = video_needs_display_normalization,
) -> Path:
    if not needs_display_normalization_fn(source):
        return source

    normalized = renderer._cache_path("normalized_videos", source, ".mp4", "display_geometry_v1")
    if normalized.exists():
        return normalized

    try:
        import imageio_ffmpeg

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vf",
            "scale=trunc(iw*sar/2)*2:trunc(ih/2)*2,setsar=1",
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(normalized),
        ]
        emit_event_fn("log", message=f"Display normalization required; creating normalized proxy: {source.name}")
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode == 0 and normalized.exists() and normalized.stat().st_size > 1024:
            return normalized
        emit_event_fn("log", message=f"FFmpeg display normalization failed, falling back to source: {source.name}: {completed.stderr[-600:]}")
    except Exception as exc:
        emit_event_fn("log", message=f"FFmpeg display normalization raised, falling back to source: {source.name}: {exc}")

    return source
