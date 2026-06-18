from __future__ import annotations

import json
import shutil
import sys
import struct
import subprocess
import wave
from argparse import Namespace
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine
import video_engine_worker as worker
from video_engine.timeline import (
    build_timeline_from_blueprint,
    build_timeline_preview_manifest,
    update_preview_quality_profile,
)


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _touch(path: Path, content: bytes = b"vcs") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path.resolve())


def _make_image(path: Path) -> str:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (320, 180), (30, 90, 72))
    draw = ImageDraw.Draw(image)
    draw.rectangle((24, 24, 296, 156), outline=(180, 255, 218), width=4)
    draw.text((42, 78), "timeline", fill=(240, 253, 244))
    image.save(path, quality=90)
    return str(path.resolve())


def _make_wav(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    sample_rate = 8000
    frames = []
    for index in range(sample_rate):
        value = int(12000 * (index % 80) / 80)
        frames.append(struct.pack("<h", value))
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))
    return str(path.resolve())


def _make_audio_m4a(path: Path) -> str:
    import imageio_ffmpeg

    wav_path = path.with_suffix(".wav")
    _make_wav(wav_path)
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-i",
        str(wav_path),
        "-c:a",
        "aac",
        "-b:a",
        "64k",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(path.resolve())


def _make_video(path: Path, image_path: str) -> str:
    import imageio_ffmpeg

    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-loop",
        "1",
        "-i",
        image_path,
        "-t",
        "1.0",
        "-vf",
        "scale=320:180,fps=12",
        "-an",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return str(path.resolve())


def _library(root: Path) -> Dict[str, Any]:
    image_path = _make_image(root / "media" / "image_01.jpg")
    video_path = _make_video(root / "media" / "video_01.mp4", image_path)
    audio_path = _make_audio_m4a(root / "media" / "music.m4a")
    return {
        "schema_version": "5.5",
        "document_type": "media_library",
        "assets": [
            {
                "asset_id": "asset_image_01",
                "type": "image",
                "status": "ready",
                "absolute_path": image_path,
                "relative_path": "image_01.jpg",
                "media": {"orientation": "landscape"},
            },
            {
                "asset_id": "asset_video_01",
                "type": "video",
                "status": "ready",
                "absolute_path": video_path,
                "relative_path": "video_01.mp4",
                "media": {"orientation": "landscape", "duration_seconds": 2.5},
            },
            {
                "asset_id": "asset_audio_01",
                "type": "audio",
                "status": "ready",
                "absolute_path": audio_path,
                "relative_path": "music.m4a",
                "media": {"duration_seconds": 30.0},
            },
        ],
        "proxy_media_manifest": {"assets": [], "summary": {"ready": 0}},
    }


def _blueprint(library: Dict[str, Any]) -> Dict[str, Any]:
    audio_path = next(asset["absolute_path"] for asset in library["assets"] if asset["type"] == "audio")
    return {
        "schema_version": "5.5",
        "document_type": "story_blueprint",
        "title": "Timeline Preview Manifest Smoke",
        "subtitle": "Preview assets",
        "metadata": {
            "edit_strategy": "fast_assembly",
            "performance_mode": "stable",
            "audio": {
                "music_mode": "manual",
                "music_path": audio_path,
                "bgm_volume": 0.25,
                "source_audio_volume": 1.0,
                "keep_source_audio": True,
                "auto_ducking": True,
                "fade_in_seconds": 1.0,
                "fade_out_seconds": 2.0,
            },
            "audio_blueprint": {
                "version": 1,
                "mode": "apply",
                "section_cues": [{"section_id": "section_city", "phase": "intro", "energy": "medium"}],
            },
        },
        "sections": [
            {
                "section_id": "section_city",
                "section_type": "city",
                "title": "City",
                "subtitle": None,
                "enabled": True,
                "asset_refs": [
                    {"asset_id": "asset_image_01", "enabled": True, "keep_audio": False},
                    {"asset_id": "asset_video_01", "enabled": True, "keep_audio": True},
                ],
                "children": [],
            }
        ],
    }


def _assert_manifest(manifest: Dict[str, Any], *, generated: bool = False) -> None:
    assert manifest["document_type"] == "timeline_preview_manifest"
    assert manifest["manifest_version"] == "timeline_preview_manifest_v1"
    assert manifest["preview_policy"]["profile"] == "high"
    assert manifest["preview_policy"]["mode"] == "proxy"
    assert manifest["preview_policy"]["height"] == 1080
    assert manifest["preview_policy"]["fps"] == 30
    assert manifest["cache_namespaces"]["preview"] == "preview"
    assert manifest["cache_namespaces"]["thumbnail"] == "thumbnail"
    assert manifest["cache_namespaces"]["proxy"] == "proxy"

    clips = manifest["clips"]
    assert any(clip["kind"] == "image_asset" for clip in clips.values())
    assert any(clip["kind"] == "video_asset" for clip in clips.values())
    assert any(clip["kind"] in {"title_card", "chapter_card"} for clip in clips.values())
    assert any(clip["kind"] == "audio_bgm" for clip in clips.values())

    image_clip = next(clip for clip in clips.values() if clip["kind"] == "image_asset")
    assert image_clip["thumbnail"]["status"] == ("ready" if generated else "planned")
    assert image_clip["preview_segment"]["status"] == ("ready" if generated else "planned")
    if generated:
        assert Path(image_clip["thumbnail"]["path"]).is_file()
        assert Path(image_clip["preview_segment"]["path"]).is_file()

    video_clip = next(clip for clip in clips.values() if clip["kind"] == "video_asset")
    assert video_clip["proxy"]["status"] == ("ready" if generated else "planned")
    assert video_clip["preview_segment"]["profile"] == "high"
    if generated:
        assert Path(video_clip["proxy"]["path"]).is_file()
        assert Path(video_clip["preview_segment"]["path"]).is_file()

    audio_clip = next(clip for clip in clips.values() if clip["kind"] == "audio_bgm")
    assert audio_clip["waveform"]["status"] == ("ready" if generated else "planned")
    assert audio_clip["waveform"]["path"].endswith(".json")
    if generated:
        assert Path(audio_clip["waveform"]["path"]).is_file()

    summary = manifest["summary"]
    assert summary["visual_clips"] >= 3
    assert summary["audio_clips"] >= 1
    if generated:
        assert summary["proxy_ready"] >= 1
        assert summary["waveform_ready"] >= 1
        assert summary["preview_segment_ready"] >= 1
    else:
        assert summary["proxy_planned"] >= 1
        assert summary["waveform_planned"] >= 1


def test_timeline_preview_manifest_module_cli_and_worker() -> None:
    root = Path("tests/tmp_vcs_timeline_preview_manifest")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    library = _library(root)
    blueprint = _blueprint(library)
    render_plan = engine.Compiler(blueprint, library).compile()
    timeline = build_timeline_from_blueprint(
        blueprint,
        render_plan,
        media_library=library,
        project_dir=str(root / ".video_create_project"),
    )
    timeline = update_preview_quality_profile(timeline, "high")

    manifest = build_timeline_preview_manifest(
        timeline,
        media_library=library,
        project_dir=str(root / ".video_create_project"),
        timeline_path=str(root / "timeline.json"),
    )
    _assert_manifest(manifest)

    library_path = root / "media_library.json"
    timeline_path = root / "timeline.json"
    manifest_path = root / "timeline_preview_manifest.json"
    worker_manifest_path = root / "timeline_preview_manifest_worker.json"
    assets_manifest_path = root / "timeline_preview_assets.json"
    worker_assets_manifest_path = root / "timeline_preview_assets_worker.json"
    _write_json(library_path, library)
    _write_json(timeline_path, timeline)

    engine.command_timeline_preview_manifest(
        Namespace(
            timeline=str(timeline_path),
            output=str(manifest_path),
            library=str(library_path),
            proxy_manifest=None,
            project_dir=str(root / ".video_create_project"),
        )
    )
    _assert_manifest(json.loads(manifest_path.read_text(encoding="utf-8")))

    result = worker.run_task(
        {
            "type": "timeline-preview-manifest",
            "id": "timeline-preview-manifest-smoke",
            "timeline_path": str(timeline_path),
            "library_path": str(library_path),
            "output_path": str(worker_manifest_path),
            "project_dir": str(root / ".video_create_project"),
        }
    )
    assert result["ok"] is True
    assert result["output_path"] == str(worker_manifest_path)
    _assert_manifest(result["document"])

    engine.command_timeline_preview_assets(
        Namespace(
            timeline=str(timeline_path),
            output=str(assets_manifest_path),
            library=str(library_path),
            proxy_manifest=None,
            project_dir=str(root / ".video_create_project"),
        )
    )
    _assert_manifest(json.loads(assets_manifest_path.read_text(encoding="utf-8")), generated=True)

    result = worker.run_task(
        {
            "type": "timeline-preview-assets",
            "id": "timeline-preview-assets-smoke",
            "timeline_path": str(timeline_path),
            "library_path": str(library_path),
            "output_path": str(worker_assets_manifest_path),
            "project_dir": str(root / ".video_create_project"),
        }
    )
    assert result["ok"] is True
    assert result["output_path"] == str(worker_assets_manifest_path)
    _assert_manifest(result["document"], generated=True)


if __name__ == "__main__":
    test_timeline_preview_manifest_module_cli_and_worker()
    print("V5 timeline preview manifest smoke test passed")
