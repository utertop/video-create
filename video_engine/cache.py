from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import CACHE_CLEANUP_DEFAULTS_MB, ENGINE_VERSION


def safe_id(text: str) -> str:
    normalized = text.replace("\\", "/")
    return hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()[:12]


def file_hash_light(path: Path, extra: str = "") -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}|{ENGINE_VERSION}|{extra}"
    return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()


def _cache_cleanup_limit_bytes(config: Dict[str, Any], bucket_name: str, default_mb: int) -> int:
    raw_limits = config.get("cache_cleanup_limits_mb")
    if isinstance(raw_limits, dict) and bucket_name in raw_limits:
        raw_value = raw_limits.get(bucket_name)
    else:
        raw_value = config.get(f"{bucket_name}_cache_max_mb")
    try:
        return max(0, int(float(raw_value if raw_value is not None else default_mb) * 1024 * 1024))
    except Exception:
        return max(0, int(default_mb * 1024 * 1024))


def _iter_cache_files(root: Path) -> List[Path]:
    if not root.exists():
        return []
    files: List[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.endswith((".tmp", ".part")) or ".rendering.tmp." in path.name:
            continue
        files.append(path)
    return files


def _cleanup_cache_bucket(root: Path, limit_bytes: int, bucket_name: str) -> Dict[str, Any]:
    files = _iter_cache_files(root)
    entries: List[Tuple[int, int, Path]] = []
    bytes_before = 0
    for path in files:
        try:
            stat = path.stat()
        except Exception:
            continue
        size = int(stat.st_size)
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
        entries.append((mtime_ns, size, path))
        bytes_before += size

    deleted_files = 0
    deleted_bytes = 0
    for _mtime_ns, size, path in sorted(entries, key=lambda item: item[0]):
        if bytes_before - deleted_bytes <= limit_bytes:
            break
        try:
            path.unlink()
            deleted_files += 1
            deleted_bytes += size
        except Exception:
            continue

    for directory in sorted((path for path in root.rglob("*") if path.is_dir()), key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except Exception:
            pass

    bytes_after = max(0, bytes_before - deleted_bytes)
    return {
        "bucket": bucket_name,
        "path": str(root),
        "limit_bytes": int(limit_bytes),
        "bytes_before": int(bytes_before),
        "bytes_after": int(bytes_after),
        "deleted_bytes": int(deleted_bytes),
        "deleted_files": int(deleted_files),
        "kept_files": max(0, len(entries) - deleted_files),
    }


def _cleanup_cache_buckets(
    specs: List[Tuple[str, Path, int]],
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    config = config or {}
    if config.get("cache_cleanup_enabled", True) is False:
        return {"enabled": False, "buckets": {}, "deleted_files": 0, "deleted_bytes": 0}

    buckets: Dict[str, Any] = {}
    deleted_files = 0
    deleted_bytes = 0
    for bucket_name, root, default_mb in specs:
        limit_bytes = _cache_cleanup_limit_bytes(config, bucket_name, default_mb)
        summary = _cleanup_cache_bucket(root, limit_bytes, bucket_name)
        buckets[bucket_name] = summary
        deleted_files += int(summary.get("deleted_files") or 0)
        deleted_bytes += int(summary.get("deleted_bytes") or 0)

    return {
        "enabled": True,
        "buckets": buckets,
        "deleted_files": int(deleted_files),
        "deleted_bytes": int(deleted_bytes),
    }
