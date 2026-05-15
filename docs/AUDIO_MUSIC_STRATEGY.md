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

## 12. V2 专业音频能力规划

V2 不是推翻 V1，而是在 V1 稳定后增加专业能力。V1 负责“稳定、可控、能用”，V2 负责“更聪明、更专业、更有创作灵感”。

核心原则：

- V2 必须兼容 V1 的 `audio` 配置。
- V2 只能新增字段，不能改变 V1 字段含义。
- V2 能力必须可以关闭，不能影响 V1 的稳定渲染。
- V2 的高级分析结果要进入缓存，不能每次渲染重复分析。
- 长视频仍然坚持 chunk 级音频处理，不允许回到整条 MoviePy 音频 timeline。

### 12.1 V1 到 V2 的兼容关系

V1 字段继续有效：

```json
{
  "audio": {
    "music_mode": "manual",
    "music_path": "D:/music/travel.mp3",
    "bgm_volume": 0.28,
    "source_audio_volume": 1.0,
    "keep_source_audio": true,
    "auto_ducking": true,
    "fade_in_seconds": 1.5,
    "fade_out_seconds": 3.0
  }
}
```

V2 只增加可选扩展：

```json
{
  "audio": {
    "analysis": {
      "enabled": true,
      "beat_detection": true,
      "voice_detection": true,
      "loudness_normalization": true
    },
    "beat_sync": {
      "enabled": false,
      "strength": "soft",
      "snap_transitions": true,
      "snap_image_durations": false
    },
    "mixing": {
      "target_lufs": -16,
      "limiter": true,
      "noise_reduction": false,
      "eq_preset": "none"
    },
    "multi_music": {
      "enabled": false,
      "mode": "per_chapter",
      "tracks": []
    },
    "rights": {
      "show_copyright_warning": true,
      "source": "user_local"
    }
  }
}
```

如果没有这些 V2 字段，系统必须按 V1 逻辑正常工作。

### 12.2 V2 能力清单

#### A. 音频波形预览

目标：

- 在 UI 中显示 BGM 波形。
- 在时间线上看到音量起伏。
- 帮助创作者知道哪里适合转场、卡点、章节切换。

实现建议：

- Python/FFmpeg 生成轻量波形 JSON 或 PNG。
- 前端只读取小体积波形数据。
- 不通过 IPC 传音频二进制。

缓存路径：

```text
.video_create_project/audio_cache/waveforms/
```

#### B. 节拍检测与卡点建议

目标：

- 检测 BGM 的 beat 点。
- 给出“适合切换画面”的时间点。
- 支持转场贴近节拍，但不强制改变创作者选择。

第一阶段建议：

- 只做 beat 标记和 UI 提示。
- 不自动重排视频。

第二阶段再考虑：

- 图片段时长轻微吸附到节拍。
- beat_cut 策略下转场靠近 beat。
- 快节奏短视频自动生成卡点建议。

风险：

- 自动卡点会改变视频节奏，必须可关闭。
- 长视频 beat 分析要缓存，不能每次重复跑。

#### C. 更精准的人声 ducking

V1 ducking 基于 segment 规则。

V2 ducking 可以基于音频分析：

- 使用 FFmpeg `volumedetect` 或 RMS 分析判断源音频强度。
- 有人声/环境声时降低 BGM。
- 无明显原声时恢复 BGM。
- 音量变化必须平滑，避免抽吸感。

推荐参数：

```json
{
  "ducking": {
    "mode": "smart",
    "duck_volume": 0.14,
    "attack_ms": 300,
    "release_ms": 900
  }
}
```

#### D. LUFS 响度标准化

目标：

- 避免最终视频音量忽大忽小。
- 更接近平台发布标准。

推荐：

- 短视频：目标 `-14 LUFS` 到 `-16 LUFS`。
- 长视频/纪录类：目标 `-16 LUFS` 到 `-18 LUFS`。
- 峰值限制：`-1 dBTP`。

实现方式：

- FFmpeg `loudnorm` 两遍分析更准，但更慢。
- 第一版可做单遍 `loudnorm` 或输出前 limiter。
- 稳定优先模式下默认不开重分析，只做安全 limiter。

#### E. 多首 BGM 按章节切换

目标：

- 旅行视频、长 vlog、纪录片可以每个章节不同情绪。
- 避免 30 分钟视频一首歌循环太单调。

模式：

- `single_track`: 全片一首。
- `per_chapter`: 每章一首或每章重启。
- `mood_sections`: 按情绪段落切换。

规则：

- 每次切歌必须淡入淡出。
- 章节切换点可以结合转场。
- 不允许突然硬切音乐。

#### F. 音乐情绪与素材情绪匹配

目标：

- 根据视频内容给出 BGM 风格建议。

可用信息：

- 剪辑策略：`travel_soft / beat_cut / documentary / long_stable`
- 章节标题关键词。
- 素材类型：城市、自然、生活、夜景、运动。
- 视频长度和节奏。

输出：

```json
{
  "music_recommendation": {
    "profile": "travel_light",
    "tempo": "medium",
    "energy": "warm",
    "reason": "旅行/风景素材较多，建议轻快但不抢画面的音乐。"
  }
}
```

#### G. 版权与来源提示

目标：

- 不内置未知版权音乐。
- 提醒用户本地音乐可能有版权风险。
- 后续可接入免版权音乐库，但不作为 V1/V2 初期依赖。

UI 提示：

```text
请确认您拥有该音乐的使用权，或该音乐允许用于公开视频发布。
```

### 12.3 V2 分阶段路线

#### V2-P1：波形与音频分析缓存

先做：

- BGM 波形生成。
- 音频基础分析 JSON。
- duration / peak / RMS / simple loudness。
- UI 显示波形预览。

不做：

- 自动改视频时长。
- 多首音乐切换。

#### V2-P2：智能 ducking 与响度安全

先做：

- 基于 RMS 的源音频检测。
- 更平滑的 BGM ducking。
- limiter。
- 可选 LUFS 标准化。

不做：

- AI 人声分离。
- 复杂降噪。

#### V2-P3：节拍点与卡点建议

先做：

- beat 点检测。
- UI 标记节拍。
- 给出“建议切换点”。

再做：

- beat_cut 策略下轻微吸附转场。
- 图片段自动微调时长。

#### V2-P4：多 BGM 与章节音乐

先做：

- 每章可选不同 BGM。
- 自动淡入淡出。
- 章节级音乐预览。

再做：

- 情绪段落自动推荐音乐。

### 12.4 暂时不做的能力

为了保护 V1 稳定性，以下能力不进入 V1，也不建议 V2 初期做：

- AI 生成音乐。
- 在线音乐商店或在线版权库。
- 专业 DAW 级多轨编辑。
- 实时音频插件链。
- 人声分离、伴奏分离。
- 自动降噪、混响、母带处理一整套。

这些能力复杂度很高，容易把项目从“视频自动编排工具”拖成“专业音频工作站”。后续如果确实需要，可以独立成 Audio Lab。

### 12.5 V2 成熟度标准

V2 是否值得启动，应看 V1 是否达到这些条件：

- P1/P2/P3 全部完成。
- 手动 BGM、自动 BGM、长视频 BGM 都稳定。
- 低清预览能准确听到最终音频效果。
- 30 分钟以上视频不会因为 BGM 混音导致内存疯涨。
- 用户已经开始需要“卡点、波形、响度、章节音乐”等专业能力。

满足这些条件后，再进入 V2，才不会过早复杂化。
