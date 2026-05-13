# V5.3.2 Stability Patch Change List

## P0

1. CI 安装 Python 依赖
   - 避免 `python video_engine_v5.py --help` 报 `No module named numpy`。

2. CI 增加最小 V5 烟测
   - 自动生成一张测试图。
   - 执行 `scan -> plan -> compile`。
   - 校验三个 JSON 文档都存在且 `document_type` 正确。

3. Python CLI 顶层帮助懒加载
   - `--help` 不再依赖 numpy / pillow / moviepy。
   - 真正执行 scan/render 时仍然依赖 `requirements.txt`。

4. 版本号收口
   - `SCHEMA_VERSION = "5.3"`
   - `ENGINE_VERSION = "video-create-engine-v5.3.2"`
   - `V5_SCHEMA_VERSION = "5.3"`

## P1

1. CSS warning 修复
   - 修复可能存在的 `font-family: " Cascadia Mono\, ...` 字符串错误。

2. README 追加 V5.3.2 稳定收口说明
   - 明确 V5 主流程与 V3 Legacy 关系。
