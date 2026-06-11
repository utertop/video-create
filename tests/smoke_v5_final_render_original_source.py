import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def test_final_render_ignores_requested_proxy_media() -> None:
    root = Path("tests/tmp_vcs_final_original_source")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "image_01.jpg"
    engine.Image.new("RGB", (1280, 720), (96, 138, 188)).save(source, quality=92)
    plan = {"render_settings": {"fps": 12, "aspect_ratio": "16:9"}, "segments": []}
    renderer = engine.Renderer(
        plan,
        str(root / "output.mp4"),
        {"fps": 12, "quality": "draft", "proxy_media": True},
    )

    resolved = renderer._get_proxy_source(source, is_video=False)
    stats = renderer._proxy_media_summary()

    assert resolved == source
    assert stats["eligible"] == 0
    assert stats["created"] == 0
    assert stats["hit"] == 0
    assert stats["fallback"] == 0
    assert stats["final_proxy_blocked"] == 1
    assert renderer.cache_policy_summary["render_intent"] == "final"
    assert renderer.cache_policy_summary["allow_proxy"] is False
    assert renderer.cache_policy_summary["uses_original_source"] is True


def test_preview_render_can_use_proxy_media() -> None:
    root = Path("tests/tmp_vcs_preview_proxy_allowed")
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)

    source = root / "image_01.jpg"
    engine.Image.new("RGB", (1280, 720), (116, 150, 198)).save(source, quality=92)
    plan = {"render_settings": {"fps": 12, "aspect_ratio": "16:9"}, "segments": []}
    renderer = engine.Renderer(
        plan,
        str(root / "output.mp4"),
        {"preview": True, "preview_height": 360, "fps": 12, "quality": "draft", "proxy_media": True},
    )

    resolved = renderer._get_proxy_source(source, is_video=False)
    stats = renderer._proxy_media_summary()

    assert resolved != source
    assert resolved.is_file()
    assert resolved.parent == root / ".video_create_project" / "proxies"
    assert stats["eligible"] == 1
    assert stats["created"] == 1
    assert stats["final_proxy_blocked"] == 0
    assert renderer.cache_policy_summary["render_intent"] == "preview"
    assert renderer.cache_policy_summary["allow_proxy"] is True


if __name__ == "__main__":
    test_final_render_ignores_requested_proxy_media()
    test_preview_render_can_use_proxy_media()
    print("V5 final original source smoke test passed")
