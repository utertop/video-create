# Video Create Studio V5 音乐与音频策略方案

## 1. 目标

音乐系统要解决三个核心问题：

- 让创作者更快找到合适的 BGM，而不是导出后才发现氛围不对。
- 让视频原声、BGM、章节节奏、转场情绪能稳定共存。
- 让 30 分钟以上长视频也能安全混音，不因为一次性加载超长音频导致内存暴涨或成片损坏。

参考成熟视频剪辑软件的通用做法：Premiere / DaVinci Resolve / Final Cut Pro 偏向轨道与混音控制，CapCut / 剪映偏向模板化、自动配乐、节拍点与一键降噪。Video Create Studio V5 应该取中间路线：给创作者足够控制权，但默认策略要聪明、稳定、少打扰。

## 2. 产品原则

### 2.1 创作选择权优先

系统可以推荐音乐、音量和节奏，但不应该替用户强制替换音乐。

必须支持：

- 无 BGM。
- 自动从素材目录选择音乐。
- 手动选择本地音乐文件。
- 保留视频原声。
- 静音视频原声。
- BGM 与视频原声自动混音。

### 2.2 默认结果要安全

默认策略不能把人声、环境声、采访声盖掉。

推荐默认值：

- BGM 音量：`0.28`
- 视频原声音量：`1.0`
- 有明显原声的视频段：BGM 自动 duck 到 `0.12 - 0.18`
- 无原声图片段：BGM 使用正常音量
- 开头淡入：`1.0s - 2.0s`
- 结尾淡出：`2.0s - 4.0s`

### 2.3 长视频优先稳定

长视频不允许一次性把整条 BGM 和整条视频 timeline 全部塞进 MoviePy 内存。

长视频必须使用：

- chunk 级音频处理。
- FFmpeg 优先混音。
- 临时音频文件。
- 音频标准化缓存。
- concat 前统一音频规格。

## 3. UI 设计

建议在“剪辑策略 / 合成引擎 / 性能档位”附近增加一个「音乐与原声」区域。

### 3.1 一级选项

```text
音乐
[无音乐] [自动选择] [手动选择]
```

字段：

- `music_mode`: `off | auto | manual`
- `music_path`: 本地音乐路径，可为空
- `music_source`: `none | library | manual`

### 3.2 音量选项

```text
BGM 音量       [ 28%  slider ]
视频原声音量   [100%  slider]
```

字段：

- `bgm_volume`: `0.0 - 1.0`
- `source_audio_volume`: `0.0 - 1.0`

推荐 UI 显示为百分比，但渲染参数使用浮点数。

### 3.3 智能混音选项

```text
[x] 保留视频原声
[x] 自动压低 BGM，避免盖住人声/环境声
[x] 开头淡入 / 结尾淡出
```

字段：

- `keep_source_audio`: `boolean`
- `auto_ducking`: `boolean`
- `fade_in_seconds`: `number`
- `fade_out_seconds`: `number`

### 3.4 创作者高级选项

高级区默认折叠。

```text
音乐循环方式
[自动] [循环铺满] [只播一次] [按章节重启]

音乐情绪
[自动] [轻松旅行] [安静记录] [节奏卡点] [史诗氛围] [温暖生活]
```

字段：

- `music_loop_mode`: `auto | loop | once | per_chapter`
- `music_profile`: `auto | travel_light | calm_documentary | beat | cinematic | lifestyle`

## 4. 素材扫描策略

### 4.1 自动识别音乐文件

`scan` 阶段应识别：

- `.mp3`
- `.wav`
- `.m4a`
- `.aac`
- `.flac`
- `.ogg`

建议写入 media library：

```json
{
  "asset_id": "audio_00001",
  "type": "audio",
  "file_path": "D:/素材/music/bgm.mp3",
  "duration": 184.2,
  "audio_codec": "mp3",
  "sample_rate": 44100,
  "channels": 2,
  "title": "bgm",
  "tags": ["music_candidate"]
}
```

### 4.2 自动选择优先级

`music_mode=auto` 时：

1. 优先选择素材目录中明确命名为 `bgm / music / soundtrack / 配乐 / 音乐` 的文件。
2. 其次选择最长且不是很短音效的音频文件。
3. 小于 `15s` 的音频默认视为音效，不作为 BGM。
4. 多个候选时，优先 `.wav / .m4a / .mp3`。

## 5. Render Plan 数据结构

建议在 `render_settings` 增加：

```json
{
  "audio": {
    "music_mode": "manual",
    "music_path": "D:/music/travel.mp3",
    "music_source": "manual",
    "music_profile": "travel_light",
    "music_loop_mode": "auto",
    "bgm_volume": 0.28,
    "source_audio_volume": 1.0,
    "keep_source_audio": true,
    "auto_ducking": true,
    "fade_in_seconds": 1.5,
    "fade_out_seconds": 3.0,
    "normalize_audio": true,
    "target_lufs": -16
  }
}
```

每个 segment 可保留现有：

```json
{
  "keep_audio": true
}
```

后续可扩展：

```json
{
  "audio_role": "dialogue | ambience | music | silent",
  "source_audio_volume": 1.0,
  "duck_bgm": true
}
```

## 6. 渲染规则

### 6.1 MoviePy 路径

适用场景：

- 短视频。
- 复杂章节文字动效。
- 复杂转场。
- 小样预览。

规则：

- 视频原声通过 `clip.audio.volumex(source_audio_volume)` 控制。
- BGM 使用 `AudioFileClip`，但只在短视频或低清预览中直接加载。
- BGM 需要 `audio_loop` 或分段 subclip。
- 最终用 `CompositeAudioClip` 混音。
- 输出仍使用 `audio_codec="aac"`。

风险：

- 长视频直接使用 MoviePy 混整条 BGM 会明显增加内存。
- 30 分钟以上不建议走整条 MoviePy audio timeline。

### 6.2 FFmpeg 路径

适用场景：

- 长视频。
- 稳定优先。
- FFmpeg chunk 直出。
- 简单转场/直切场景。

规则：

- 所有源音频先统一为 AAC / 48kHz / stereo。
- 没有源音频的 segment 补静音轨。
- chunk 内混音优先用 FFmpeg `filter_complex`。
- BGM 按 chunk 时间范围裁剪或循环，不整条加载。
- chunk 输出规格保持一致，便于最终 concat copy。

推荐 filter 思路：

```text
[source_audio] volume=source_audio_volume,aresample=48000 [src]
[bgm] volume=bgm_volume,afade=t=in,afade=t=out,aresample=48000 [music]
[src][music] amix=inputs=2:duration=first:dropout_transition=0 [mix]
```

### 6.3 自动 ducking

第一版不做复杂人声识别，先做基于 segment 规则的 ducking：

- `keep_audio=true` 且 segment 是视频：BGM 降低到 `duck_volume`。
- 图片段或静音视频：BGM 使用正常音量。
- 转场前后 `0.3s - 0.8s` 平滑恢复，避免音量突变。

后续高级版可做：

- FFmpeg `volumedetect` 判断源音频是否明显有声。
- 简单 RMS 分析判断人声/环境声强度。
- 节拍检测与画面节奏对齐。

## 7. 长视频内存安全规则

### 7.1 禁止

- 禁止把整条 30 分钟以上 BGM 作为一个 MoviePy `AudioFileClip` 长时间挂在 final timeline 上。
- 禁止通过 Tauri IPC 传音频二进制或 base64。
- 禁止把 BGM 解码后的 PCM 整体读入内存。

### 7.2 必须

- 只传音频文件路径。
- BGM 统一预处理到 `.video_create_project/audio_cache/`。
- chunk 级裁剪、循环、混音。
- 每个 chunk 完成后释放音频 reader。
- 音频缓存 key 必须包含：
  - 源文件路径
  - 文件大小
  - mtime
  - 音量参数
  - 采样率
  - loop mode
  - engine version

### 7.3 推荐目录

```text
.video_create_project/
  audio_cache/
    normalized/
    bgm_chunks/
    mix_chunks/
```

## 8. 与现有性能策略的关系

音乐策略不能破坏已经做好的性能优化。

必须保持：

- FFmpeg chunk 直出仍可用。
- 带源音频 chunk 已经统一 AAC / 48kHz / stereo，这个能力要继续复用。
- BGM 混音不能让简单 chunk 退回 MoviePy，除非用户选择复杂音频效果。
- 稳定优先模式下，复杂音乐效果自动降级为安全混音。

性能档位影响：

```text
稳定优先：
  FFmpeg chunk 混音，简单 ducking，禁用复杂节拍重排。

平衡推荐：
  FFmpeg chunk 混音 + 简单淡入淡出 + segment ducking。

画质优先：
  允许更细的转场/章节音乐处理，但长视频仍不允许整条 MoviePy 混音。
```

## 9. P1 / P2 / P3 实现路线

### P1：基础 BGM 接入

目标：

- UI 增加音乐区。
- Render params 支持 `audio` 配置。
- 手动选择本地 BGM。
- 最终视频支持 BGM 音量、原声音量、开头淡入、结尾淡出。

范围：

- `src/lib/engine.ts`
- `src/store/studio.ts`
- `src/App.tsx`
- `video_engine_v5.py`
- smoke test：短视频 BGM 混音。

验收：

- 无 BGM 时行为不变。
- 手动 BGM 能进入最终视频。
- 保留原声时 BGM 不盖住原声。
- 低清预览也能听到同样的音乐策略。

### P2：自动选择与音频缓存

目标：

- scan 阶段识别音频素材。
- 自动从素材目录选择 BGM。
- BGM 预处理到 `audio_cache`。
- 统一音频规格，避免重复转码。

范围：

- `Scanner`
- media library schema
- compiler render settings
- audio cache helper
- smoke test：目录里放多首音频时自动选择合理 BGM。

验收：

- `music_mode=auto` 可自动选择候选 BGM。
- 短音效不会被误选为 BGM。
- 同一首 BGM 重复渲染能复用缓存。

### P3：长视频安全混音与 ducking

目标：

- V56 chunk renderer 支持 BGM chunk 混音。
- FFmpeg 直出 chunk 支持 BGM + 源音频混音。
- segment 级 ducking。
- 30 分钟以上视频不走整条 MoviePy 音频 timeline。

范围：

- `_v56_write_chunk_video`
- `_v56_try_write_ffmpeg_direct_chunk`
- `_ffmpeg_fit_video_segment`
- 新增 audio chunk helpers
- smoke test：带源音频视频 + BGM + 静音段 + chunk concat。

验收：

- 长视频模式下内存不随总时长线性疯涨。
- 每个 chunk 音频规格一致。
- 最终 concat 不丢音频。
- 人声/环境声段 BGM 自动降低。

## 10. 后续高级能力

后续可以做，但不建议第一阶段就上：

- 节拍检测。
- 音乐卡点自动调整图片时长。
- 多首 BGM 按章节切换。
- 情绪识别匹配 BGM。
- 音乐库管理。
- 版权风险提示。
- 自动响度标准化到平台规范，如 `-16 LUFS`。

## 11. 推荐下一步

先做 P1。

理由：

- 对用户价值最直接。
- 改动范围可控。
- 不会立刻碰长视频最复杂的 chunk 混音。
- P1 做完后，低清预览就能提前听到 BGM 效果，创作者试错成本会明显下降。

