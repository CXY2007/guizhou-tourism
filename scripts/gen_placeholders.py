"""生成 10 个新增景点的占位图（抽象渐变，不烙景点名）。"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "app" / "static" / "images" / "placeholders"

ACCENTS = {
    "自然": "#1F4E5A",
    "人文": "#8A6A2F",
    "季节": "#8F4F63",
    "科技": "#2E5E8C",
    "红色": "#B83A2D",
}

ITEMS = [
    ("wanfenglin", "自然"),
    ("pingba-cherry", "季节"),
    ("huajiang-bridge", "科技"),
    ("zhaoxing-dong", "人文"),
    ("zhenyuan", "人文"),
    ("qingyan", "人文"),
    ("wumeng-grassland", "自然"),
    ("baili-dujuan", "季节"),
    ("xiaoqikong", "自然"),
    ("zhijindong", "自然"),
]

TEMPLATE = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800" viewBox="0 0 1200 800">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0E2A24"/>
      <stop offset="1" stop-color="{accent}"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="800" fill="url(#bg)"/>
  <circle cx="980" cy="180" r="220" fill="#F4EFE6" opacity="0.06"/>
  <circle cx="1080" cy="620" r="160" fill="#C9A227" opacity="0.08"/>
  <path d="M0 620 L220 470 L390 560 L560 430 L760 570 L940 450 L1200 600 L1200 800 L0 800 Z" fill="#06120F" opacity="0.35"/>
  <text x="80" y="700" fill="#C9A227" font-size="24" letter-spacing="6">图片待补 · IMAGE PENDING</text>
  <text x="80" y="750" fill="#8FA6A0" font-size="18" letter-spacing="6">GUIZHOU · CHINA</text>
</svg>
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for slug, category in ITEMS:
        svg = TEMPLATE.format(accent=ACCENTS.get(category, "#1F4E5A"))
        (OUT / f"{slug}.svg").write_text(svg, encoding="utf-8")
        print("wrote", slug)


if __name__ == "__main__":
    main()
