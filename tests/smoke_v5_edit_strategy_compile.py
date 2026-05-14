import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import video_engine_v5 as engine


def compile_with_strategy(strategy: str):
    library = {
        "assets": [
            {
                "asset_id": "asset_image_01",
                "type": "image",
                "status": "ok",
                "absolute_path": "D:/mock/image_01.jpg",
                "media": {"orientation": "landscape"},
            },
            {
                "asset_id": "asset_image_02",
                "type": "image",
                "status": "ok",
                "absolute_path": "D:/mock/image_02.jpg",
                "media": {"orientation": "landscape"},
            },
        ]
    }
    blueprint = {
        "title": "Creative Strategy Smoke",
        "subtitle": None,
        "metadata": {
            "edit_strategy": strategy,
            "transition_profile": strategy,
            "rhythm_profile": strategy,
        },
        "sections": [
            {
                "section_id": "section_travel",
                "section_type": "scenic_spot",
                "title": "Travel",
                "subtitle": None,
                "enabled": True,
                "asset_refs": [
                    {"asset_id": "asset_image_01", "enabled": True},
                    {"asset_id": "asset_image_02", "enabled": True},
                ],
                "children": [],
            }
        ],
    }

    return engine.Compiler(blueprint, library).compile()


def test_edit_strategy_compile_configs() -> None:
    travel_plan = compile_with_strategy("travel_soft")
    beat_plan = compile_with_strategy("beat_cut")

    travel_assets = [seg for seg in travel_plan["segments"] if seg["type"] in {"image", "video"}]
    beat_assets = [seg for seg in beat_plan["segments"] if seg["type"] in {"image", "video"}]

    assert travel_assets, "expected visual segments for travel strategy"
    assert beat_assets, "expected visual segments for beat strategy"

    travel_transition = travel_assets[0]["transition_config"]
    beat_transition = beat_assets[0]["transition_config"]

    assert travel_plan["render_settings"]["edit_strategy"] == "travel_soft"
    assert beat_plan["render_settings"]["edit_strategy"] == "beat_cut"
    assert travel_transition["strategy"] == "travel_soft"
    assert beat_transition["strategy"] == "beat_cut"
    assert travel_transition["type"] == "soft_crossfade"
    assert beat_transition["type"] == "quick_zoom"
    assert travel_assets[0]["motion_config"]["type"] == "gentle_push"
    assert beat_assets[0]["motion_config"]["type"] == "punch_zoom"
    assert travel_assets[0]["rhythm_config"]["pace"] == "medium_soft"
    assert beat_assets[0]["rhythm_config"]["pace"] == "fast_punchy"
    assert travel_assets[0]["cache_key"] != beat_assets[0]["cache_key"]


if __name__ == "__main__":
    test_edit_strategy_compile_configs()
    print("V5 edit strategy compile smoke test passed")
