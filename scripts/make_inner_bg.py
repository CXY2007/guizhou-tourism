"""由「内层背景图.jpg」生成页面底纹 inner-bg-soft.jpg（降低模糊、保留山形与色块）。

用法：
    python scripts/make_inner_bg.py            # 默认 blur=12（当前使用）
    python scripts/make_inner_bg.py 18         # 更模糊一档
"""
import sys
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "app" / "static" / "images" / "inner-bg.jpg"
DST = ROOT / "app" / "static" / "images" / "inner-bg-soft.jpg"
WIDTH = 1600


def main() -> None:
    radius = float(sys.argv[1]) if len(sys.argv) > 1 else 12.0
    im = Image.open(SRC).convert("RGB")
    ratio = WIDTH / im.width
    im = im.resize((WIDTH, round(im.height * ratio)), Image.LANCZOS)
    im = im.filter(ImageFilter.GaussianBlur(radius))
    im = ImageEnhance.Color(im).enhance(1.06)
    im = ImageEnhance.Contrast(im).enhance(1.04)
    im.save(DST, "JPEG", quality=82, optimize=True, progressive=True)
    size_kb = DST.stat().st_size / 1024
    print(f"wrote {DST.relative_to(ROOT)} {im.size[0]}x{im.size[1]} blur={radius} {size_kb:.0f}KB")


if __name__ == "__main__":
    main()
