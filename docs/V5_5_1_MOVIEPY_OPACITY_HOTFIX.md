# V5.5.1 MoviePy Dynamic Opacity Hotfix

## Problem

Rendering fails after clicking final render:

```text
TypeError: unsupported operand type(s) for *: 'function' and 'float'
```

The traceback points to:

```python
clip.set_opacity(lambda t: self._fade_curve(t, duration))
```

## Root cause

MoviePy 1.0.3 does not support callable opacity in `VideoClip.set_opacity()`. It expects a numeric value. When a function is passed, MoviePy later tries to do `op * pic`, where `op` is the function object.

## Fix

V5.5.1 replaces callable `set_opacity(lambda...)` with mask-based dynamic opacity:

```python
base_mask.fl(lambda gf, t: gf(t) * alpha(t))
```

## Usage

```powershell
cd D:\Automatic\video_create

python .\tools\apply_v5_5_1_moviepy_opacity_hotfix.py
python -m py_compile .\video_engine_v5.py
python .\tests\smoke_v5_5_1_moviepy_opacity.py
npm run build
```

If Tauri still uses the old copied resource, restart `npm run tauri dev` or delete:

```powershell
Remove-Item .\src-tauri\target\debug\video_engine_v5.py -Force
```
