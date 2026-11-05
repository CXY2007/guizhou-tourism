"""生成主页非首屏背景：5 张实景淡化合拼 + 模糊（1600x900）。

用法：python scripts/make_home_bg.py
输出：app/static/images/hero/bg_soft.jpg（首屏以外的固定背景）
"""
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "app" / "static" / "images"
OUT = ROOT / "app" / "static" / "images" / "hero" / "bg_soft.jpg"
W, H = 1600, 900


def cover(path, size):
    img = Image.open(path).convert("RGB")
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))), Image.LANCZOS)
    left = (img.width - tw) // 2
    top = (img.height - th) // 2
    return img.crop((left, top, left + tw, top + th))


def feather_mask(size, left=0, right=0, top=0, bottom=0):
    w, h = size
    a = np.ones((h, w), dtype=np.float32)
    if left:
        a *= np.clip(np.arange(w) / left, 0, 1)[None, :]
    if right:
        a *= np.clip(np.arange(w)[::-1] / right, 0, 1)[None, :]
    if top:
        a *= np.clip(np.arange(h) / top, 0, 1)[:, None]
    if bottom:
        a *= np.clip(np.arange(h)[::-1] / bottom, 0, 1)[:, None]
    return Image.fromarray((a * 255).astype(np.uint8))


def scaled(mask, opacity):
    return mask.point(lambda v: int(v * opacity))


canvas = cover(IMG / "XJQHMZ2.jpg", (W, H))
canvas = ImageEnhance.Brightness(canvas).enhance(1.05)

# 左侧：黄果树夜景
panel = cover(IMG / "HGSPB1.jpg", (520, H))
canvas.paste(panel, (0, 0), scaled(feather_mask((520, H), right=200), 0.68))

# 右上：中国天眼
panel = cover(IMG / "ZGTY5.jpg", (1100, 520))
canvas.paste(panel, (500, 0), scaled(feather_mask((1100, 520), left=220, bottom=180), 0.62))

# 右下：西江夜景
panel = cover(IMG / "XJQHMZ1.jpg", (1100, 420))
canvas.paste(panel, (500, 480), scaled(feather_mask((1100, 420), left=220, top=160), 0.62))

# 中部：遵义群像，椭圆淡入
panel = cover(IMG / "ZYHY4.jpg", (900, 520))
yy, xx = np.mgrid[0:520, 0:900]
d = np.sqrt(((xx - 450) / 470) ** 2 + ((yy - 260) / 250) ** 2)
arr = (np.clip(1.1 - d * 1.1, 0, 1) ** 1.6 * 255).astype(np.uint8)
canvas.paste(panel, (330, 190), scaled(Image.fromarray(arr), 0.26))

# 统一色调：降饱和、偏冷、提亮（纸色遮罩之下要透得出来）
canvas = ImageEnhance.Color(canvas).enhance(0.8)
canvas = ImageEnhance.Brightness(canvas).enhance(1.14)
teal = Image.new("RGB", (W, H), (16, 54, 54))
canvas = Image.blend(canvas, teal, 0.06)
paper = Image.new("RGB", (W, H), (244, 239, 230))
canvas = Image.blend(canvas, paper, 0.08)

canvas = canvas.filter(ImageFilter.GaussianBlur(6))

OUT.parent.mkdir(parents=True, exist_ok=True)
canvas.save(OUT, "JPEG", quality=72, optimize=True, progressive=True)
print(OUT, OUT.stat().st_size // 1024, "KB")
