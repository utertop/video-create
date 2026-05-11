# B站横屏旅行视频生成脚本 V3 操作手册

## 推荐安装

```bash
python -m pip install moviepy==1.0.3 pillow numpy imageio-ffmpeg
```

## 推荐命令

```bash
python make_bilibili_video_v3.py --input_folder "E:\Lumix\泉州-厦门" --recursive --chapters_from_dirs --title "福建-泉州-厦门" --end "To be continued!" --watermark "PangBo Travel" --cover --quality high --output_name "quanzhou_xiamen"
```

## 先预检

```bash
python make_bilibili_video_v3.py --input_folder "E:\Lumix\泉州-厦门" --recursive --chapters_from_dirs --dry_run
```

## 核心逻辑

1. 扫描素材，支持递归目录。
2. 自动过滤隐藏文件、临时文件、副本.JPG。
3. 自动插入片头、章节卡、片尾。
4. 照片按 EXIF 自动转正。
5. 照片完整显示，不裁剪、不拉伸。
6. 生成同图模糊背景，避免竖图黑边。
7. 视频完整显示，默认保留原声音。
8. 生成标准化片段并缓存。
9. 使用 moviepy_crossfade 或 ffmpeg_concat 进行最终合成。
10. 生成封面图和构建报告。

## 常用参数

| 参数 | 说明 |
|---|---|
| `--recursive` | 递归读取子目录 |
| `--chapters_from_dirs` | 按子目录生成章节卡 |
| `--quality high` | 推荐 B站旅行视频画质 |
| `--engine moviepy_crossfade` | 转场效果更好 |
| `--engine ffmpeg_concat` | 速度更快 |
| `--watermark` | 添加右下角水印 |
| `--cover` | 生成 B站封面图 |
| `--mute` | 静音原视频 |
| `--rebuild_cache` | 强制重建缓存 |
| `--dry_run` | 只预检不生成 |

## 输出文件

- `*_16x9.mp4`：最终视频
- `cover_*.jpg`：封面图
- `build_report_*.txt`：构建报告
- `.cache_bilibili_video/`：缓存目录
