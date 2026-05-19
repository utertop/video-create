from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def _write_bytes(path: Path, size: int, mtime: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))


def _make_image(path: Path) -> None:
    Image.new("RGB", (960, 540), (42, 112, 82)).save(path, quality=92)


def test_bucket_cleanup_prunes_oldest_files_first() -> None:
    root = Path("tests/tmp_vcs_cache_cleanup_bucket")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    bucket = root / "render_cache"
    oldest = bucket / "oldest.bin"
    middle = bucket / "middle.bin"
    newest = bucket / "newest.bin"
    _write_bytes(oldest, 2048, 100)
    _write_bytes(middle, 2048, 200)
    _write_bytes(newest, 1024, 300)

    summary = engine._cleanup_cache_buckets(
        [("render_cache", bucket, 1)],
        {"cache_cleanup_limits_mb": {"render_cache": 0.003}},
    )
    render_summary = summary["buckets"]["render_cache"]

    assert not oldest.exists()
    assert middle.exists()
    assert newest.exists()
    assert render_summary["deleted_files"] == 1
    assert render_summary["bytes_after"] <= render_summary["limit_bytes"]


def test_render_report_includes_cache_cleanup_summary() -> None:
    root = Path("tests/tmp_vcs_cache_cleanup_report")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "source.jpg"
    _make_image(source)

    proxies_dir = root / ".video_create_project" / "proxies"
    stale_proxy = proxies_dir / "stale.bin"
    fresh_proxy = proxies_dir / "fresh.bin"
    _write_bytes(stale_proxy, 2048, 100)
    _write_bytes(fresh_proxy, 1024, 300)

    plan = {
        "render_settings": {"fps": 12, "aspect_ratio": "16:9"},
        "segments": [
            {
                "segment_id": "seg_cleanup_0001",
                "type": "image",
                "source_path": str(source),
                "duration": 0.8,
                "text": None,
                "subtitle": None,
                "start_time": 0.0,
                "end_time": 0.8,
                "transition": "cut",
                "transition_config": {"type": "cut", "duration": 0},
                "motion_config": {"type": "still_hold"},
                "rhythm_config": {"pace": "fast_review", "role": "visual"},
                "keep_audio": False,
            }
        ],
    }

    output = root / "cleanup.mp4"
    engine.Renderer(
        plan,
        str(output),
        {
            "fps": 12,
            "quality": "draft",
            "cache_cleanup_limits_mb": {"proxies": 0.0025},
        },
    ).render()

    report = engine.read_json(str(root / ".video_create_project" / "build_report.json"))
    cleanup = report["cache_cleanup"]

    assert cleanup["enabled"] is True
    assert cleanup["deleted_files"] >= 1
    assert not stale_proxy.exists()
    assert report["cache_cleanup"]["buckets"]["proxies"]["bytes_after"] <= report["cache_cleanup"]["buckets"]["proxies"]["limit_bytes"]


if __name__ == "__main__":
    test_bucket_cleanup_prunes_oldest_files_first()
    test_render_report_includes_cache_cleanup_summary()
    print("V5 cache cleanup smoke test passed")
