from __future__ import annotations

import json
import math
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from .cache import file_hash_light, safe_id

AUDIO_PREFERRED_EXT_SCORE = {
    ".wav": 6,
    ".m4a": 5,
    ".mp3": 4,
    ".flac": 4,
    ".aac": 3,
    ".ogg": 2,
}

AUDIO_MUSIC_HINTS = ("bgm", "music", "soundtrack", "instrumental", "score", "theme", "配乐", "音乐", "伴奏", "纯音乐", "背景音乐")
AUDIO_EFFECT_HINTS = ("effect", "sfx", "音效", "提示音", "转场音")

_emit_event: Callable[..., None] = lambda _event_type, **_payload: None


def set_audio_event_emitter(callback: Callable[..., None]) -> None:
    global _emit_event
    _emit_event = callback


def close_clip(clip: Any) -> None:
    if clip is None:
        return
    try:
        clip.close()
    except Exception:
        pass


def _moviepy_audio_deps() -> Tuple[Any, Any, Any]:
    try:
        from moviepy.editor import AudioFileClip, concatenate_audioclips
        try:
            from moviepy.audio.fx.all import audio_loop as moviepy_audio_loop
        except Exception:
            moviepy_audio_loop = None
        return AudioFileClip, concatenate_audioclips, moviepy_audio_loop
    except Exception as exc:
        raise RuntimeError("MoviePy is required for music bed generation") from exc


def probe_audio_file(source: Path) -> Dict[str, Any]:
    """Probe audio metadata using FFmpeg stderr, without requiring ffprobe."""
    media = {
        "width": None,
        "height": None,
        "orientation": None,
        "shooting_date": None,
        "duration_seconds": None,
        "sample_rate": None,
        "channels": None,
        "audio_codec": None,
    }
    try:
        import imageio_ffmpeg

        completed = subprocess.run(
            [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        probe_text = completed.stderr or ""

        duration_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", probe_text)
        if duration_match:
            hours = int(duration_match.group(1))
            minutes = int(duration_match.group(2))
            seconds = float(duration_match.group(3))
            media["duration_seconds"] = round(hours * 3600 + minutes * 60 + seconds, 3)

        audio_line = None
        for line in probe_text.splitlines():
            if "Audio:" in line:
                audio_line = line
                break

        if audio_line:
            codec_match = re.search(r"Audio:\s*([^,]+)", audio_line)
            if codec_match:
                media["audio_codec"] = codec_match.group(1).strip().lower()

            sample_rate_match = re.search(r"(\d+)\s*Hz", audio_line)
            if sample_rate_match:
                media["sample_rate"] = int(sample_rate_match.group(1))

            if "stereo" in audio_line.lower():
                media["channels"] = 2
            elif "mono" in audio_line.lower():
                media["channels"] = 1
            else:
                channels_match = re.search(r"(\d+(?:\.\d+)?)\s*channels?", audio_line.lower())
                if channels_match:
                    media["channels"] = int(float(channels_match.group(1)))
    except Exception:
        pass

    return media


def prepare_cached_audio_for_mix(
    source: Path,
    cache_root: Path,
    normalize_audio: bool = False,
    target_lufs: float = -16.0,
) -> Path:
    """Normalize audio once and reuse it across renders."""
    if not source.exists():
        raise FileNotFoundError(f"Audio source not found: {source}")

    bucket = cache_root / "normalized"
    bucket.mkdir(parents=True, exist_ok=True)
    try:
        target_lufs = float(target_lufs)
    except Exception:
        target_lufs = -16.0
    if not math.isfinite(target_lufs):
        target_lufs = -16.0
    target_lufs = max(-30.0, min(-8.0, target_lufs))
    cache_extra = f"audio_mix_aac_48k_stereo_v2|loudnorm={bool(normalize_audio)}|target_lufs={target_lufs:.1f}"
    cache_path = bucket / f"{file_hash_light(source, cache_extra)}.m4a"
    if cache_path.exists() and cache_path.stat().st_size > 1024:
        _emit_event("log", message=f"Audio cache hit: {cache_path.name}")
        return cache_path

    tmp_path = cache_path.with_suffix(".tmp.m4a")
    try:
        import imageio_ffmpeg

        cmd = [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "2",
            "-ar",
            "48000",
        ]
        if normalize_audio:
            cmd.extend([
                "-af",
                f"loudnorm=I={target_lufs:.1f}:TP=-1.5:LRA=11.0",
            ])
        cmd.extend([
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(tmp_path),
        ])
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode != 0:
            raise RuntimeError((completed.stderr or completed.stdout or "unknown ffmpeg error")[-800:])
        if not tmp_path.exists() or tmp_path.stat().st_size <= 1024:
            raise RuntimeError("normalized audio cache output is empty")
        os.replace(str(tmp_path), str(cache_path))
        _emit_event("log", message=f"Audio cache created: {cache_path.name}")
        return cache_path
    finally:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def audio_asset_duration_seconds(asset: Dict[str, Any]) -> float:
    media = asset.get("media", {}) if isinstance(asset, dict) else {}
    return float(media.get("duration_seconds") or media.get("duration") or 0.0)


def auto_music_score(asset: Dict[str, Any]) -> float:
    if asset.get("type") != "audio":
        return 0.0

    duration = audio_asset_duration_seconds(asset)
    if duration < 15:
        return 0.0

    file_info = asset.get("file", {}) if isinstance(asset, dict) else {}
    name = str(file_info.get("name") or "")
    rel_path = str(asset.get("relative_path") or "")
    haystack_lower = f"{name} {rel_path}".lower()
    haystack = f"{name} {rel_path}"
    ext = str(file_info.get("extension") or "").lower()

    score = 12.0 if duration >= 45 else 6.0
    if any(hint in haystack_lower for hint in AUDIO_MUSIC_HINTS[:6]) or any(hint in haystack for hint in AUDIO_MUSIC_HINTS[6:]):
        score += 40.0
    if any(hint in haystack_lower for hint in AUDIO_EFFECT_HINTS[:2]) or any(hint in haystack for hint in AUDIO_EFFECT_HINTS[2:]):
        score -= 25.0

    if duration >= 90:
        score += 18.0
    elif duration >= 45:
        score += 10.0
    elif duration >= 25:
        score += 4.0

    score += float(AUDIO_PREFERRED_EXT_SCORE.get(ext, 0))
    return score


def select_auto_music_asset(assets: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    ranked = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        status = asset.get("status")
        if status == "error" or (isinstance(status, dict) and status.get("state") == "error"):
            continue
        score = auto_music_score(asset)
        if score <= 0:
            continue
        ranked.append((score, audio_asset_duration_seconds(asset), str(asset.get("relative_path") or ""), asset))

    if not ranked:
        return None

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    return ranked[0][3]


def select_auto_music_assets(assets: Iterable[Dict[str, Any]], target_duration: float = 0.0) -> List[Dict[str, Any]]:
    ranked: List[Tuple[float, float, str, Dict[str, Any]]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        status = asset.get("status")
        if status == "error" or (isinstance(status, dict) and status.get("state") == "error"):
            continue
        score = auto_music_score(asset)
        if score <= 0:
            continue
        ranked.append((score, audio_asset_duration_seconds(asset), str(asset.get("relative_path") or ""), asset))

    if not ranked:
        return []

    ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
    ordered = [item[3] for item in ranked]
    if target_duration <= 0:
        return ordered[:1]
    if target_duration < 600:
        return ordered[:1]

    selected: List[Dict[str, Any]] = []
    total_duration = 0.0
    for asset in ordered:
        selected.append(asset)
        total_duration += audio_asset_duration_seconds(asset)
        if len(selected) >= 4 or total_duration >= target_duration * 0.72:
            break
    return selected or ordered[:1]


def build_music_bed_for_duration(
    prepared_tracks: List[Path],
    duration: float,
    cache_root: Path,
    fit_strategy: str = "auto",
    fade_in: float = 0.0,
    fade_out: float = 0.0,
) -> Optional[Path]:
    if not prepared_tracks:
        return None

    AudioFileClip, concatenate_audioclips, moviepy_audio_loop = _moviepy_audio_deps()
    duration = max(0.1, float(duration or 0.0))
    fit_strategy = str(fit_strategy or "auto").lower()
    if fit_strategy not in {"auto", "loop", "trim", "intro_loop_outro", "once"}:
        fit_strategy = "auto"

    bucket = cache_root / "beds"
    bucket.mkdir(parents=True, exist_ok=True)
    key = json.dumps(
        {
            "tracks": [str(path.resolve()) for path in prepared_tracks if path.exists()],
            "duration": round(duration, 3),
            "fit_strategy": fit_strategy,
            "fade_in": round(float(fade_in or 0.0), 3),
            "fade_out": round(float(fade_out or 0.0), 3),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    cache_path = bucket / f"{safe_id(key)}.m4a"
    if cache_path.exists() and cache_path.stat().st_size > 1024:
        _emit_event("log", message=f"Music bed cache hit: {cache_path.name}")
        return cache_path

    tmp_path = cache_path.with_suffix(".tmp.m4a")
    clips: List[Any] = []
    try:
        source_clips = [AudioFileClip(str(path)) for path in prepared_tracks if path.exists()]
        clips.extend(source_clips)
        if not source_clips:
            return None

        if len(source_clips) > 1:
            assembled: List[Any] = []
            remaining = duration
            index = 0
            while remaining > 0 and source_clips:
                source = source_clips[index % len(source_clips)]
                source_duration = float(getattr(source, "duration", 0.0) or 0.0)
                take = min(max(source_duration, 0.1), remaining)
                assembled.append(source.subclip(0, take))
                remaining -= take
                index += 1
            music_clip = concatenate_audioclips(assembled).set_duration(duration)
        else:
            source = source_clips[0]
            source_duration = float(getattr(source, "duration", 0.0) or 0.0)
            effective_strategy = fit_strategy
            if effective_strategy == "auto":
                if source_duration <= 0:
                    effective_strategy = "once"
                elif duration <= source_duration * 1.2:
                    effective_strategy = "trim"
                elif duration <= source_duration * 3.0:
                    effective_strategy = "intro_loop_outro"
                else:
                    effective_strategy = "loop"

            if source_duration <= 0:
                music_clip = source.set_duration(duration)
            elif effective_strategy in {"once", "trim"}:
                music_clip = source.subclip(0, min(duration, source_duration)).set_duration(min(duration, source_duration))
            elif effective_strategy == "intro_loop_outro" and source_duration > 18 and duration > source_duration:
                intro = min(max(6.0, source_duration * 0.18), 18.0)
                outro = min(max(8.0, source_duration * 0.18), 20.0)
                middle_start = min(intro, max(0.0, source_duration - 10.0))
                middle_end = max(middle_start + 4.0, source_duration - outro)
                if middle_end <= middle_start + 1.0:
                    music_clip = moviepy_audio_loop(source, duration=duration) if moviepy_audio_loop is not None else concatenate_audioclips([source] * int(math.ceil(duration / source_duration))).subclip(0, duration)
                else:
                    intro_clip = source.subclip(0, min(intro, duration))
                    outro_len = min(outro, max(0.0, duration - float(getattr(intro_clip, "duration", 0.0) or 0.0)))
                    body_target = max(0.0, duration - float(getattr(intro_clip, "duration", 0.0) or 0.0) - outro_len)
                    middle_clip = source.subclip(middle_start, middle_end)
                    if body_target > 0 and moviepy_audio_loop is not None:
                        body_clip = moviepy_audio_loop(middle_clip, duration=body_target)
                    elif body_target > 0:
                        body_segments: List[Any] = []
                        remaining = body_target
                        middle_duration = float(getattr(middle_clip, "duration", 0.0) or 0.0)
                        while remaining > 0 and middle_duration > 0:
                            take = min(middle_duration, remaining)
                            body_segments.append(middle_clip.subclip(0, take))
                            remaining -= take
                        body_clip = concatenate_audioclips(body_segments).set_duration(body_target) if body_segments else None
                    else:
                        body_clip = None
                    outro_clip = source.subclip(max(0.0, source_duration - outro_len), source_duration) if outro_len > 0 else None
                    parts = [clip for clip in [intro_clip, body_clip, outro_clip] if clip is not None]
                    music_clip = concatenate_audioclips(parts).set_duration(duration)
            else:
                if moviepy_audio_loop is not None:
                    music_clip = moviepy_audio_loop(source, duration=duration)
                else:
                    loops = max(1, int(math.ceil(duration / source_duration)))
                    music_clip = concatenate_audioclips([source] * loops).subclip(0, duration)

        actual_duration = min(duration, float(getattr(music_clip, "duration", duration) or duration))
        if fade_in > 0:
            music_clip = music_clip.audio_fadein(min(float(fade_in), actual_duration / 2.0))
        if fade_out > 0:
            music_clip = music_clip.audio_fadeout(min(float(fade_out), actual_duration / 2.0))

        music_clip.write_audiofile(
            str(tmp_path),
            fps=48000,
            codec="aac",
            bitrate="160k",
            ffmpeg_params=["-movflags", "+faststart"],
            verbose=False,
            logger=None,
        )
        if not tmp_path.exists() or tmp_path.stat().st_size <= 1024:
            raise RuntimeError("music bed output is empty")
        os.replace(str(tmp_path), str(cache_path))
        _emit_event("log", message=f"Music bed cache created: {cache_path.name}")
        return cache_path
    finally:
        for clip in clips:
            close_clip(clip)
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass


def build_chapter_restart_music_bed(
    prepared_tracks: List[Path],
    chapter_cues: List[Dict[str, Any]],
    duration: float,
    cache_root: Path,
    playlist_mode: str = "chapter_restart",
    fit_strategy: str = "auto",
    fade_in: float = 0.0,
    fade_out: float = 0.0,
) -> Optional[Path]:
    if not prepared_tracks or not chapter_cues:
        return None

    duration = max(0.1, float(duration or 0.0))
    normalized_cues: List[Dict[str, Any]] = []
    total_covered = 0.0
    for cue in chapter_cues:
        if not isinstance(cue, dict):
            continue
        cue_duration = float(cue.get("duration") or 0.0)
        if cue_duration <= 0:
            start_time = float(cue.get("start_time") or 0.0)
            end_time = float(cue.get("end_time") or 0.0)
            cue_duration = max(0.0, end_time - start_time)
        if cue_duration <= 0.05:
            continue
        remaining = max(0.0, duration - total_covered)
        if remaining <= 0.05:
            break
        cue_duration = min(cue_duration, remaining)
        normalized_cues.append({
            "duration": cue_duration,
            "title": cue.get("title"),
            "phase": cue.get("phase"),
        })
        total_covered += cue_duration

    if not normalized_cues:
        return None
    if total_covered < duration - 0.05:
        normalized_cues.append({"duration": duration - total_covered, "title": "tail_fill", "phase": "outro"})

    bucket = cache_root / "beds"
    bucket.mkdir(parents=True, exist_ok=True)
    key = json.dumps(
        {
            "tracks": [str(path.resolve()) for path in prepared_tracks if path.exists()],
            "duration": round(duration, 3),
            "playlist_mode": playlist_mode,
            "fit_strategy": fit_strategy,
            "fade_in": round(float(fade_in or 0.0), 3),
            "fade_out": round(float(fade_out or 0.0), 3),
            "chapter_cues": [{"duration": round(float(cue["duration"]), 3), "title": cue.get("title"), "phase": cue.get("phase")} for cue in normalized_cues],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    cache_path = bucket / f"{safe_id(key)}.m4a"
    if cache_path.exists() and cache_path.stat().st_size > 1024:
        _emit_event("log", message=f"Chapter restart music bed cache hit: {cache_path.name}")
        return cache_path

    segment_paths: List[Path] = []
    tmp_path = cache_path.with_suffix(".tmp.m4a")
    clips: List[Any] = []
    try:
        for index, cue in enumerate(normalized_cues):
            cue_duration = max(0.1, float(cue["duration"]))
            track = prepared_tracks[index % len(prepared_tracks)] if len(prepared_tracks) > 1 else prepared_tracks[0]
            segment_fade_in = min(float(fade_in or 0.0), cue_duration / 3.0)
            segment_fade_out = min(float(fade_out or 0.0), cue_duration / 3.0)
            if index > 0:
                segment_fade_in = min(segment_fade_in, 0.4)
            if index < len(normalized_cues) - 1:
                segment_fade_out = min(segment_fade_out, 0.6)
            segment_path = build_music_bed_for_duration(
                [track],
                cue_duration,
                cache_root,
                fit_strategy=fit_strategy,
                fade_in=segment_fade_in,
                fade_out=segment_fade_out,
            )
            if segment_path and segment_path.exists():
                segment_paths.append(segment_path)

        if not segment_paths:
            return None

        AudioFileClip, concatenate_audioclips, _moviepy_audio_loop = _moviepy_audio_deps()
        audio_clips = [AudioFileClip(str(path)) for path in segment_paths]
        clips.extend(audio_clips)
        final_clip = concatenate_audioclips(audio_clips).set_duration(duration)
        clips.append(final_clip)
        final_clip.write_audiofile(
            str(tmp_path),
            fps=48000,
            codec="aac",
            bitrate="160k",
            ffmpeg_params=["-movflags", "+faststart"],
            verbose=False,
            logger=None,
        )
        if not tmp_path.exists() or tmp_path.stat().st_size <= 1024:
            raise RuntimeError("chapter restart music bed output is empty")
        os.replace(str(tmp_path), str(cache_path))
        _emit_event("log", message=f"Chapter restart music bed cache created: {cache_path.name}")
        return cache_path
    finally:
        for clip in clips:
            close_clip(clip)
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        except Exception:
            pass
