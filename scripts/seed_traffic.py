"""刷后台「浏览流量」演示数据：近 N 天 × 18 个景点的浏览量 / 访客数。

    python scripts/seed_traffic.py             # 默认 30 天
    python scripts/seed_traffic.py 90          # 90 天
    python scripts/seed_traffic.py --reset     # 先清空再重建

数值带工作日/周末差异和热点景点权重，趋势图不会是一条直线。
"""
from __future__ import annotations

import pathlib
import random
import sys
from datetime import date, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Attraction, TrafficDaily  # noqa: E402

HOT = {  # 知名度带来的基础热度权重
    "huangguoshu": 3.2,
    "xijiang-miao": 2.8,
    "fanjingshan": 2.4,
    "xiaoqikong": 2.2,
    "zhenyuan": 1.8,
    "qingyan": 1.7,
    "wanfenglin": 1.6,
    "zhaoxing-dong": 1.5,
}


def main() -> None:
    args = [item for item in sys.argv[1:] if not item.startswith("--")]
    days = int(args[0]) if args else 30
    reset = "--reset" in sys.argv
    rng = random.Random(20261102)

    app = create_app()
    with app.app_context():
        if reset:
            TrafficDaily.query.delete()
            db.session.commit()
            print("已清空 traffic_daily")

        attractions = Attraction.query.order_by(Attraction.id).all()
        today = date.today()
        created = 0

        for offset in range(days - 1, -1, -1):
            day = today - timedelta(days=offset)
            weekend = day.weekday() >= 5
            # 整体趋势：越近越多，周末上浮
            trend = 1 + (days - offset) / days * 0.9
            day_factor = trend * (1.45 if weekend else 1.0)
            for attraction in attractions:
                weight = HOT.get(attraction.slug, 0.7)
                base = 18 * weight * day_factor
                views = max(0, int(rng.gauss(base, base * 0.28)))
                if views == 0:
                    continue
                visitors = max(1, int(views * rng.uniform(0.55, 0.82)))
                exists = TrafficDaily.query.filter_by(attraction_id=attraction.id, day=day).first()
                if exists:
                    exists.views = views
                    exists.visitors = visitors
                else:
                    db.session.add(TrafficDaily(
                        attraction_id=attraction.id, day=day, views=views, visitors=visitors,
                    ))
                created += 1
        db.session.commit()
        print(f"写入 {created} 行；当前 traffic_daily 共 {TrafficDaily.query.count()} 行")


if __name__ == "__main__":
    main()
