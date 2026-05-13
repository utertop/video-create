# Video Create Studio V5.3.2 稳定收口 Patch

这份 patch 的目标是把 V5.3 功能收口成一个更稳定、更容易排查的工程版本。

## 包含内容

```text
.github/workflows/build.yml      # CI 增加 Python 依赖安装与 scan/plan/compile 烟测
tests/smoke_v5.py                # 最小 V5 scan -> plan -> compile 测试
tools/apply_v5_3_2_patch.py      # 本地源码局部修补脚本
docs/V5_3_2_STABILITY_PATCH.md   # 使用说明
```

## 使用方式

在项目根目录覆盖/复制本 patch 的文件后，执行：

```powershell
python .\tools\apply_v5_3_2_patch.py
```

然后本地验证：

```powershell
python -m pip install -r .\requirements.txt
python -m py_compile .\video_engine_v5.py
python .\video_engine_v5.py --help
python .\tests\smoke_v5.py
npm run build
cargo check --manifest-path .\src-tauri\Cargo.toml
```

## 修改目标

- `SCHEMA_VERSION` 对齐到 `5.3`。
- `ENGINE_VERSION` 对齐到 `video-create-engine-v5.3.2`。
- 顶层 `--help` 不再依赖 numpy / pillow / moviepy。
- CI 在 Python smoke 前安装 `requirements.txt`。
- CI 新增 scan / plan / compile 最小烟测，不跑真实 render，避免耗时和不稳定。
- 修复可能存在的 Cascadia Mono CSS 字符串 warning。
- README 追加 V5.3.2 稳定收口说明。
