import os
import json
import shutil
from pathlib import Path
import video_engine_v5 as engine

def setup_mock_project(root: Path):
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    
    # Create folders with different keywords to test auto-recommendation
    (root / "我的猫咪").mkdir()
    (root / "我的猫咪" / "pic1.jpg").touch()
    
    (root / "雪山徒步").mkdir()
    (root / "雪山徒步" / "pic2.jpg").touch()
    
    (root / "极限滑雪").mkdir()
    (root / "极限滑雪" / "pic3.jpg").touch()
    
    (root / "古镇美食").mkdir()
    (root / "古镇美食" / "pic4.jpg").touch()
    
    (root / "普通章节").mkdir()
    (root / "普通章节" / "pic5.jpg").touch()

def test_v5_5_pipeline():
    test_root = Path("d:/Automatic/video_create/tests/mock_v5_5_project")
    setup_mock_project(test_root)
    
    print("--- Phase 1: Scan ---")
    scanner = engine.Scanner(str(test_root))
    lib = scanner.scan()
    
    # Verify recommendations
    nodes = {n["name"]: n for n in lib["directory_nodes"]}
    
    expected = {
        "我的猫咪": "playful_pop",
        "雪山徒步": "nature_documentary",
        "极限滑雪": "impact_flash",
        "古镇美食": "travel_postcard",
        "普通章节": "cinematic_bold"
    }
    
    for name, expected_preset in expected.items():
        style = nodes[name].get("title_style")
        preset = style["preset"] if style else "MISSING"
        print(f"Folder: {name} -> Recommended Preset: {preset}")
        assert preset == expected_preset, f"Expected {expected_preset} for {name}, got {preset}"

    print("\n--- Phase 2: Plan ---")
    planner = engine.Planner(lib)
    blueprint = planner.plan()
    
    # Check if style propagated to blueprint
    for section in blueprint["sections"]:
        style = section.get("title_style")
        print(f"Section: {section['title']} -> Style in Blueprint: {style['preset'] if style else 'MISSING'}")
        assert style is not None

    print("\n--- Phase 3: Compile ---")
    compiler = engine.Compiler(blueprint, lib)
    plan = compiler.compile()
    
    # Check if style is in render plan segments
    for seg in plan["segments"]:
        if seg["type"] == "chapter":
            style = seg.get("title_style")
            print(f"Segment: {seg['text']} -> Style in Render Plan: {style['preset'] if style else 'MISSING'}")
            assert style is not None

    print("\n--- V5.5 Smoke Test Passed! ---")

if __name__ == "__main__":
    try:
        test_v5_5_pipeline()
    except Exception as e:
        print(f"Test FAILED: {e}")
        import traceback
        traceback.print_exc()
