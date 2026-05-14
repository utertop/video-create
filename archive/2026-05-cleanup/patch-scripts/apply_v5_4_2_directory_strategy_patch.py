
# -*- coding: utf-8 -*-
from __future__ import annotations

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

def replace_between(text: str, start: str, end: str, replacement: str) -> tuple[str, bool]:
    s = text.find(start)
    if s < 0:
        return text, False
    e = text.find(end, s)
    if e < 0:
        return text, False
    return text[:s] + replacement + text[e:], True

DIRECTORY_CONSTANTS = """CITY_KEYWORDS = [
    "北京", "上海", "广州", "深圳", "杭州", "泉州", "厦门", "福州", "南京", "苏州",
    "成都", "重庆", "西安", "东京", "京都", "巴黎", "伦敦", "纽约",
]

# V5.4.2 directory recognition strategy:
# - Strong spot names can identify scenic spots when there is travel context.
# - Suffix keywords are useful under city/date/chapter parents, but should not override
#   first-level content categories by themselves.
# - Weak one-character keywords such as "山" or "桥" are only signals, not decisions.
SPOT_STRONG_KEYWORDS = [
    "开元寺", "西街", "鼓浪屿", "曾厝垵", "清源山", "武夷山", "黄山", "泰山",
    "外滩", "故宫", "天坛", "颐和园", "兵马俑", "环球影城", "迪士尼",
]

SPOT_SUFFIX_KEYWORDS = [
    "寺", "庙", "宫", "塔", "岛", "湖", "海", "湾", "街", "巷", "馆", "园",
    "古城", "古镇", "公园", "博物馆", "美术馆", "植物园", "动物园",
]

SPOT_WEAK_KEYWORDS = [
    "山", "桥", "路", "村", "城", "港", "江", "河",
]

THEME_KEYWORDS = [
    "猫", "猫咪", "狗", "宠物", "美食", "登山", "滑雪", "雪崩", "日常", "人物",
    "人像", "运动", "露营", "航拍", "街拍",
]

EVENT_KEYWORDS = [
    "婚礼", "生日", "聚会", "毕业", "演出", "旅行", "团建", "年会",
]

# Backward-compatible alias for old code/comments.
SPOT_KEYWORDS = SPOT_STRONG_KEYWORDS + SPOT_SUFFIX_KEYWORDS + SPOT_WEAK_KEYWORDS

"""

DETECT_FUNCTION = """def match_keywords(name: str, keywords: Iterable[str]) -> List[str]:
    return [kw for kw in keywords if kw and kw in name]


def detect_directory_type(
    name: str,
    depth: int,
    parent_type: str = "project_root",
    sibling_names: Optional[List[str]] = None,
) -> Tuple[str, float, str, Dict[str, Any], str]:
    \"\"\"
    V5.4.2 hierarchy-aware directory recognition.

    Return:
      detected_type, confidence, reason, signals, raw_detected_type

    Important rules:
      - First-level folders under project root default to chapter.
      - scenic_spot requires travel context such as city/date parent, or a strong spot name.
      - Weak single-character spot keywords never decide scenic_spot by themselves.
      - Sibling normalization runs later in Scanner._normalize_directory_nodes().
    \"\"\"
    normalized = name.strip()
    lower = normalized.lower()
    parent_type = parent_type or "project_root"

    matched_city = match_keywords(normalized, CITY_KEYWORDS)
    matched_spot_strong = match_keywords(normalized, SPOT_STRONG_KEYWORDS)
    matched_spot_suffix = match_keywords(normalized, SPOT_SUFFIX_KEYWORDS)
    matched_spot_weak = match_keywords(normalized, SPOT_WEAK_KEYWORDS)
    matched_theme = match_keywords(normalized, THEME_KEYWORDS)
    matched_event = match_keywords(normalized, EVENT_KEYWORDS)

    signals: Dict[str, Any] = {
        "parent_detected_type": parent_type,
        "depth": depth,
        "matched_city_keywords": matched_city,
        "matched_spot_strong_keywords": matched_spot_strong,
        "matched_spot_suffix_keywords": matched_spot_suffix,
        "matched_spot_weak_keywords": matched_spot_weak,
        "matched_theme_keywords": matched_theme,
        "matched_event_keywords": matched_event,
        "date_pattern_matched": False,
        "sibling_names": sibling_names or [],
    }

    if depth == 0:
        return "unknown", 0.35, "项目根目录，不作为叙事章节类型", signals, "project_root"

    for pattern in DATE_PATTERNS:
        if pattern.search(lower):
            signals["date_pattern_matched"] = True
            return "date", 0.96, "目录名匹配日期模式", signals, "date"

    if matched_city:
        return "city", 0.90, f"目录名匹配城市关键词: {matched_city[0]}", signals, "city"

    has_travel_parent = parent_type in {"city", "date"}
    has_story_parent = parent_type in {"chapter", "theme", "event"}
    strong_spot = bool(matched_spot_strong)
    suffix_spot = bool(matched_spot_suffix)
    weak_only_spot = bool(matched_spot_weak) and not strong_spot and not suffix_spot

    if has_travel_parent and (strong_spot or suffix_spot):
        kw = (matched_spot_strong or matched_spot_suffix)[0]
        return "scenic_spot", 0.88, f"父目录为 {parent_type}，且命中景点特征: {kw}", signals, "scenic_spot"

    if has_travel_parent and depth >= 2 and not (matched_theme or matched_event):
        return "scenic_spot", 0.64, "父目录为城市/日期，深层目录默认按景点候选处理", signals, "scenic_spot_candidate"

    if strong_spot and depth >= 2:
        kw = matched_spot_strong[0]
        return "scenic_spot", 0.78, f"深层目录命中强景点名: {kw}", signals, "scenic_spot"

    if depth == 1:
        if matched_theme:
            return "chapter", 0.74, f"一级目录默认作为内容章节；主题关键词: {matched_theme[0]}", signals, "theme"
        if matched_event:
            return "chapter", 0.74, f"一级目录默认作为内容章节；事件关键词: {matched_event[0]}", signals, "event"
        if weak_only_spot:
            return "chapter", 0.70, f"一级目录命中弱景点关键词 {matched_spot_weak[0]}，不足以判定为景点，按内容章节处理", signals, "scenic_spot_candidate"
        if suffix_spot and not has_travel_parent:
            return "chapter", 0.68, f"一级目录命中景点后缀 {matched_spot_suffix[0]}，但缺少城市/日期父级上下文，按章节处理", signals, "scenic_spot_candidate"
        return "chapter", 0.65, "一级目录默认识别为内容章节", signals, "chapter"

    if has_story_parent and (strong_spot or suffix_spot):
        kw = (matched_spot_strong or matched_spot_suffix)[0]
        return "scenic_spot", 0.72, f"章节下子目录命中景点特征: {kw}", signals, "scenic_spot"

    if matched_theme:
        return "chapter", 0.66, f"目录命中主题关键词: {matched_theme[0]}，按章节处理", signals, "theme"

    if weak_only_spot:
        return "chapter", 0.58, f"仅命中弱景点关键词 {matched_spot_weak[0]}，按章节处理", signals, "scenic_spot_candidate"

    if depth >= 2:
        return "chapter", 0.56, "深层目录未命中明确景点特征，按子章节处理", signals, "chapter"

    return "unknown", 0.35, "未知目录类型", signals, "unknown"


"""

SCANNER_METHODS = """    def _normalize_directory_nodes(self) -> None:
        \"\"\"Second-pass normalization for sibling consistency and weak keyword false positives.\"\"\"
        for parent in list(self.nodes.values()):
            children = [self.nodes[cid] for cid in parent.children if cid in self.nodes]
            if not children:
                continue

            counts: Dict[str, int] = {}
            for child in children:
                counts[child.detected_type] = counts.get(child.detected_type, 0) + 1
            majority_type = max(counts.items(), key=lambda item: item[1])[0] if counts else None
            parent_type = parent.detected_type or "project_root"
            parent_is_travel = parent_type in {"city", "date"}

            for child in children:
                if child.user_overridden:
                    continue

                signals = child.signals or {}
                signals["sibling_majority_type"] = majority_type
                signals["sibling_type_counts"] = counts
                signals["parent_detected_type"] = parent_type

                weak_only = bool(signals.get("matched_spot_weak_keywords")) and not signals.get("matched_spot_strong_keywords") and not signals.get("matched_spot_suffix_keywords")
                no_strong_spot = not signals.get("matched_spot_strong_keywords")
                first_level_under_root = parent.parent_id is None and child.depth == 1

                if (
                    child.detected_type == "scenic_spot"
                    and not parent_is_travel
                    and (first_level_under_root or majority_type == "chapter" or weak_only or no_strong_spot)
                ):
                    original = child.detected_type
                    child.raw_detected_type = child.raw_detected_type or original
                    child.detected_type = "chapter"
                    child.confidence = max(float(child.confidence or 0), 0.72)
                    child.reason = (
                        "同级目录一致性修正：父目录不是城市/日期，"
                        "弱景点关键词或单个景点候选不足以单独判定 scenic_spot，按章节处理"
                    )
                    signals["normalized_from"] = original
                    signals["normalization_rule"] = "sibling_context_consistency"

                if first_level_under_root and child.detected_type not in {"city", "date", "chapter"}:
                    original = child.detected_type
                    child.raw_detected_type = child.raw_detected_type or original
                    child.detected_type = "chapter"
                    child.confidence = max(float(child.confidence or 0), 0.70)
                    child.reason = "一级同级素材目录统一作为内容章节，避免目录类型混杂"
                    signals["normalized_from"] = original
                    signals["normalization_rule"] = "first_level_content_chapter"

                child.signals = signals

    def _context_for_node(self, node_id: str) -> Dict[str, Optional[str]]:
        city = None
        date = None
        scenic_spot = None
        current = self.nodes.get(node_id)

        while current:
            if current.detected_type == "city" and city is None:
                city = current.name
            elif current.detected_type == "date" and date is None:
                date = current.name
            elif current.detected_type == "scenic_spot" and scenic_spot is None:
                scenic_spot = current.name

            if not current.parent_id:
                break
            current = self.nodes.get(current.parent_id)

        return {"city": city, "date": date, "scenic_spot": scenic_spot}

    def _refresh_asset_classification_context(self) -> None:
        \"\"\"Refresh asset city/date/scenic_spot after directory normalization.\"\"\"
        for asset in self.assets:
            node_id = asset.classification.get("directory_node_id")
            if not node_id:
                continue
            context = self._context_for_node(node_id)
            asset.classification["city"] = context.get("city")
            asset.classification["date"] = context.get("date")
            asset.classification["scenic_spot"] = context.get("scenic_spot")

"""

def patch_engine_py() -> None:
    if not ENGINE_PY.exists():
        raise FileNotFoundError(ENGINE_PY)

    backup(ENGINE_PY, ".v542_directory_strategy.bak")
    text = read(ENGINE_PY)
    changed = False

    if 'ENGINE_VERSION = "video-create-engine-v5.4.2"' not in text:
        text = text.replace('ENGINE_VERSION = "video-create-engine-v5.3.2"', 'ENGINE_VERSION = "video-create-engine-v5.4.2"')
        text = text.replace("Video Create Studio V5.3.2 Engine", "Video Create Studio V5.4.2 Engine")
        changed = True
        print("[OK] updated engine version to V5.4.2")

    if "SPOT_STRONG_KEYWORDS" not in text:
        text, ok = replace_between(text, "CITY_KEYWORDS = [", "DATE_PATTERNS = [", DIRECTORY_CONSTANTS)
        if not ok:
            raise RuntimeError("Could not replace directory keyword constants in video_engine_v5.py")
        changed = True
        print("[OK] replaced directory keyword constants")

    if "def match_keywords(" not in text:
        text, ok = replace_between(text, "def detect_directory_type(name: str, depth: int) -> Tuple[str, float, str]:", "def get_exif_date", DETECT_FUNCTION + "\n")
        if not ok:
            raise RuntimeError("Could not replace detect_directory_type() in video_engine_v5.py")
        changed = True
        print("[OK] replaced detect_directory_type()")

    if "raw_detected_type:" not in text:
        old = "    display_title: str\n    asset_count: int = 0\n"
        new = (
            "    display_title: str\n"
            "    raw_detected_type: Optional[str] = None\n"
            "    signals: Dict[str, Any] = field(default_factory=dict)\n"
            "    user_override_fields: List[str] = field(default_factory=list)\n"
            "    asset_count: int = 0\n"
        )
        if old not in text:
            raise RuntimeError("Could not patch DirectoryNode dataclass")
        text = text.replace(old, new, 1)
        changed = True
        print("[OK] extended DirectoryNode dataclass")

    old = "        self._scan_dir(self.root, depth=0, parent_id=None, inherited={})\n        emit_event(\"phase\", phase=\"scan\", message=\"素材扫描完成\", percent=100)\n"
    new = (
        "        self._scan_dir(self.root, depth=0, parent_id=None, inherited={})\n"
        "        self._normalize_directory_nodes()\n"
        "        self._refresh_asset_classification_context()\n"
        "        emit_event(\"phase\", phase=\"scan\", message=\"素材扫描完成\", percent=100)\n"
    )
    if old in text and "self._normalize_directory_nodes()" not in text:
        text = text.replace(old, new, 1)
        changed = True
        print("[OK] added second-pass directory normalization in scan()")

    old = "        dtype, confidence, reason = detect_directory_type(current.name, depth)\n        node_id = \"dir_\" + safe_id(rel or current.name)\n"
    new = (
        "        parent_type = self.nodes[parent_id].detected_type if parent_id and parent_id in self.nodes else \"project_root\"\n"
        "        sibling_names: List[str] = []\n"
        "        try:\n"
        "            sibling_names = [p.name for p in current.parent.iterdir() if p.is_dir()] if current.parent else []\n"
        "        except Exception:\n"
        "            sibling_names = []\n"
        "        dtype, confidence, reason, signals, raw_type = detect_directory_type(current.name, depth, parent_type, sibling_names)\n"
        "        node_id = \"dir_\" + safe_id(rel or current.name)\n"
    )
    if old in text:
        text = text.replace(old, new, 1)
        changed = True
        print("[OK] patched _scan_dir() to use parent/sibling context")
    elif "dtype, confidence, reason, signals, raw_type = detect_directory_type" in text:
        print("[SKIP] _scan_dir() context detection already patched")
    else:
        print("[WARN] did not find _scan_dir() detect_directory_type call target")

    old = (
        "            reason=reason,\n"
        "            display_title=current.name,\n"
        "        )\n"
    )
    new = (
        "            reason=reason,\n"
        "            display_title=current.name,\n"
        "            raw_detected_type=raw_type,\n"
        "            signals=signals,\n"
        "        )\n"
    )
    if old in text and "raw_detected_type=raw_type" not in text:
        text = text.replace(old, new, 1)
        changed = True
        print("[OK] DirectoryNode constructor now stores raw_type/signals")

    if "def _normalize_directory_nodes(self)" not in text:
        marker = "    def _scan_asset(self, path: Path, node_id: str, context: Dict[str, Optional[str]]) -> Asset:\n"
        if marker not in text:
            raise RuntimeError("Could not find _scan_asset() insertion point")
        text = text.replace(marker, SCANNER_METHODS + "\n" + marker, 1)
        changed = True
        print("[OK] inserted Scanner normalization/context methods")

    if changed:
        write(ENGINE_PY, text)
        print("[OK] wrote video_engine_v5.py")
    else:
        print("[SKIP] video_engine_v5.py already contains V5.4.2 directory strategy")

def patch_engine_ts() -> None:
    if not ENGINE_TS.exists():
        return
    backup(ENGINE_TS, ".v542_directory_strategy.bak")
    text = read(ENGINE_TS)
    changed = False
    if 'export const V5_SCHEMA_VERSION = "5.4";' not in text:
        text = text.replace('export const V5_SCHEMA_VERSION = "5.3";', 'export const V5_SCHEMA_VERSION = "5.4";')
        changed = True
        print("[OK] engine.ts schema const updated to 5.4")
    if "raw_detected_type?: string | null;" not in text:
        old = "  display_title: string;\n  asset_count: number;\n"
        new = (
            "  display_title: string;\n"
            "  raw_detected_type?: string | null;\n"
            "  signals?: Record<string, unknown>;\n"
            "  user_override_fields?: string[];\n"
            "  asset_count: number;\n"
        )
        if old in text:
            text = text.replace(old, new, 1)
            changed = True
            print("[OK] engine.ts V5DirectoryNode metadata fields added")
        else:
            print("[WARN] engine.ts: V5DirectoryNode insertion target not found")
    if changed:
        write(ENGINE_TS, text)
        print("[OK] wrote src/lib/engine.ts")
    else:
        print("[SKIP] src/lib/engine.ts no changes needed")

def patch_workflow() -> None:
    if not WORKFLOW.exists():
        return
    backup(WORKFLOW, ".v542_directory_strategy.bak")
    text = read(WORKFLOW)
    if "smoke_v5_4_2_directory_strategy.py" in text:
        print("[SKIP] workflow already runs V5.4.2 directory smoke test")
        return
    lines = text.splitlines()
    out = []
    inserted = False
    for line in lines:
        out.append(line)
        if "python .\\tests\\smoke_v5_4.py" in line or "python .\\tests\\smoke_v5.py" in line:
            indent = line[: len(line) - len(line.lstrip())]
            out.append(indent + "python .\\tests\\smoke_v5_4_2_directory_strategy.py")
            inserted = True
    if not inserted:
        out.append("")
        out.append("      - name: Python V5.4.2 directory strategy smoke test")
        out.append("        run: python .\\tests\\smoke_v5_4_2_directory_strategy.py")
    write(WORKFLOW, "\n".join(out) + "\n")
    print("[OK] workflow updated with V5.4.2 directory smoke test")

def patch_readme() -> None:
    if not README.exists():
        return
    backup(README, ".v542_directory_strategy.bak")
    text = read(README)
    if "V5.4.2 目录识别策略增强" in text:
        print("[SKIP] README already has V5.4.2 section")
        return
    addition = """
## V5.4.2 目录识别策略增强

V5.4.2 将目录识别从简单关键词命中升级为“层级上下文 + 同级一致性 + 强/中/弱关键词 + 置信度解释”的策略。

核心规则：

- 根目录下一层素材目录默认作为 `chapter`，避免 `登山` 因单字 `山` 被误判为 `scenic_spot`。
- `scenic_spot` 更依赖父级上下文：父目录是城市或日期时，子目录才更容易识别为景点。
- 景点关键词分为强景点名、景点后缀、弱关键词；弱关键词不会单独决定类型。
- 扫描后执行同级目录一致性修正，避免同一级目录出现一个 `SCENIC_SPOT`、其他都是 `CHAPTER` 的割裂结果。
- `directory_nodes` 增加 `raw_detected_type` 与 `signals`，便于 GUI 展示识别依据，也方便用户覆盖自动识别结果。
"""
    write(README, text.rstrip() + "\n\n" + addition.strip() + "\n")
    print("[OK] README appended V5.4.2 directory strategy notes")

def main() -> None:
    if not (ROOT / "package.json").exists():
        raise SystemExit("请在项目根目录执行，例如：cd D:\\Automatic\\video_create")
    patch_engine_py()
    patch_engine_ts()
    patch_workflow()
    patch_readme()
    print()
    print("V5.4.2 directory recognition strategy patch applied.")
    print()
    print("建议验证：")
    print(r"  python -m py_compile .\video_engine_v5.py")
    print(r"  python .\tests\smoke_v5_4_2_directory_strategy.py")
    print(r"  npm run build")
    print(r"  cargo check --manifest-path .\src-tauri\Cargo.toml")
    print()
    print("重新测试 GUI 前，请删除旧输出目录里的 .video_create_project，避免读取旧蓝图：")
    print(r'  Remove-Item "C:\Users\pb\Desktop\AI Video_output\.video_create_project" -Recurse -Force')

if __name__ == "__main__":
    main()
