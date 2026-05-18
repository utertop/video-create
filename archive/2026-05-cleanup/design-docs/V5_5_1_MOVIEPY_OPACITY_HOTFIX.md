# V5.5.1 MoviePy 动态透明度热修说明

## 问题现象

点击最终渲染后，渲染流程失败：

```text
TypeError: unsupported operand type(s) for *: 'function' and 'float'
```

报错栈定位到：

```python
clip.set_opacity(lambda t: self._fade_curve(t, duration))
```

## 根因分析

MoviePy 1.0.3 不支持在 `VideoClip.set_opacity()` 中传入可调用对象。它只接受数值透明度。当传入函数时，MoviePy 后续会执行 `op * pic`，此时 `op` 实际上是函数对象，因此触发类型错误。

## 修复方案

V5.5.1 将可调用 `set_opacity(lambda ...)` 替换为基于 mask 的动态透明度实现：

```python
base_mask.fl(lambda gf, t: gf(t) * alpha(t))
```

## 使用方式

```powershell
cd D:\Automatic\video_create

python .\tools\apply_v5_5_1_moviepy_opacity_hotfix.py
python -m py_compile .\video_engine_v5.py
python .\tests\smoke_v5_5_1_moviepy_opacity.py
npm run build
```

如果 Tauri 仍然加载旧的复制资源，请重启 `npm run tauri dev`，或者删除：

```powershell
Remove-Item .\src-tauri\target\debug\video_engine_v5.py -Force
```
