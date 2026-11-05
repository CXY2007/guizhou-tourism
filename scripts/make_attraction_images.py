"""把「新十大风景图」素材库里的 10 组景点照处理成站点图片。

    python scripts/make_attraction_images.py            # 写 app/static/images/<缩写><n>.jpg
    python scripts/make_attraction_images.py --preview  # 只拼一张对比图 docs/shots/bg/_lib_preview.jpg

素材库位置：`新十大风景图/十大风景图/<景点名>/<缩写><n>.jpg`（原图不进仓库，见 .gitignore）
输出规格：1200x800、JPEG q82、渐进式，命名沿用现有 18 个景点的 `<缩写><序号>.jpg`。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "app" / "static" / "images"
LIBRARY = ROOT / "新十大风景图" / "十大风景图"
PREVIEW = ROOT / "docs" / "shots" / "bg" / "_lib_preview.jpg"
TARGET = (1200, 800)

# slug -> (素材库目录, 站点缩写)
PLAN = {
    "wanfenglin": ("万峰林", "WFL"),
    "pingba-cherry": ("贵安平坝樱花", "GAPBYH"),
    "huajiang-bridge": ("花江峡谷大桥", "HJXGDQ"),
    "zhaoxing-dong": ("肇兴侗寨", "ZXDZ"),
    "zhenyuan": ("镇远古镇", "ZYGZ"),
    "qingyan": ("青岩古镇", "QYGZ"),
    "wumeng-grassland": ("乌蒙大草原", "WMDCY"),
    "baili-dujuan": ("百里杜鹃", "BLDJ"),
    "xiaoqikong": ("荔波小七孔", "LBXQK"),
    "zhijindong": ("织金洞", "ZJD"),
}

CREDITS: list[dict] = []


def natural_key(path: pathlib.Path):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", path.name)]


def center_crop(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    tw, th = size
    im = im.convert("RGB")
    scale = max(tw / im.width, th / im.height)
    im = im.resize((max(tw, round(im.width * scale)), max(th, round(im.height * scale))), Image.LANCZOS)
    left = (im.width - tw) // 2
    top = (im.height - th) // 2
    return im.crop((left, top, left + tw, top + th))


def main() -> None:
    preview = "--preview" in sys.argv
    if not LIBRARY.exists():
        raise SystemExit(f"素材库不存在：{LIBRARY}")
    if not preview:
        IMAGES.mkdir(parents=True, exist_ok=True)

    thumbs: list[pathlib.Path] = []
    for slug, (folder, abbr) in PLAN.items():
        src_dir = LIBRARY / folder
        files = sorted((p for p in src_dir.glob("*.jpg") if p.suffix.lower() == ".jpg"), key=natural_key)
        if not files:
            print(f"  !! {folder} 没有图片", file=sys.stderr)
            continue
        for idx, src in enumerate(files, start=1):
            name = f"{abbr}{idx}.jpg"
            CREDITS.append({
                "file": name, "subject": slug,
                "source": f"repo:新十大风景图/十大风景图/{folder}/{src.name}",
                "license": "项目自带素材", "author": "",
            })
            out = IMAGES / name
            if preview:
                tmp = ROOT / "docs" / "shots" / "bg" / "_tmp_lib" / name
                tmp.parent.mkdir(parents=True, exist_ok=True)
                center_crop(Image.open(src), (560, 374)).save(tmp, "JPEG", quality=85)
                thumbs.append(tmp)
                continue
            center_crop(Image.open(src), TARGET).save(
                out, "JPEG", quality=82, optimize=True, progressive=True)
            print(f"wrote {out.relative_to(ROOT)} {out.stat().st_size // 1024}KB")
        if not preview:
            print(f"{slug}: {len(files)} 张")

    if preview and thumbs:
        cols, cell_w, cell_h = 6, 280, 187
        rows = (len(thumbs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "#111")
        for i, path in enumerate(thumbs):
            sheet.paste(Image.open(path), ((i % cols) * cell_w, (i // cols) * cell_h))
        sheet.save(PREVIEW, "JPEG", quality=88)
        print(f"preview -> {PREVIEW.relative_to(ROOT)}")

    # 供 make_image_credits.py 使用
    (ROOT / "docs" / "shots" / "bg" / "_credits_preview.json").write_text(
        json.dumps(CREDITS, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
