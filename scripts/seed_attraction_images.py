"""把 make_attraction_images.py 产出的实景图写进数据库（幂等）。

    python scripts/make_attraction_images.py     # 先产出图片文件
    python scripts/seed_attraction_images.py     # 再写库：cover_image + attraction_images

每个景点按 PLAN 的顺序建立图集，第一张作为封面。
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app
from app.extensions import db
from app.models import Attraction, AttractionImage
from scripts.make_attraction_images import PLAN

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMAGES = ROOT / "app" / "static" / "images"


def main() -> None:
    app = create_app()
    with app.app_context():
        changed = 0
        for slug, (_folder, abbr) in PLAN.items():
            attraction = Attraction.query.filter_by(slug=slug).first()
            if attraction is None:
                print(f"  !! {slug} 不存在，先跑 seed_new_attractions.py", file=sys.stderr)
                continue

            urls = []
            idx = 1
            while (IMAGES / f"{abbr}{idx}.jpg").exists():
                urls.append(f"/static/images/{abbr}{idx}.jpg")
                idx += 1
            if not urls:
                print(f"  !! {slug} 没有图片文件（先跑 make_attraction_images.py）", file=sys.stderr)
                continue

            attraction.cover_image = urls[0]
            existing = {img.sort_order: img for img in attraction.images}
            keep = set()
            for order, url in enumerate(urls):
                row = existing.get(order)
                if row is None:
                    row = AttractionImage(attraction_id=attraction.id, sort_order=order)
                    db.session.add(row)
                row.image_url = url
                row.caption = f"{attraction.name} · {order + 1}"
                keep.add(order)
            for order, row in existing.items():
                if order not in keep:
                    db.session.delete(row)
            changed += 1
            print(f"{slug}: {len(urls)} 张 -> {urls[0]}")
        db.session.commit()
        print(f"updated {changed} attractions")


if __name__ == "__main__":
    main()
