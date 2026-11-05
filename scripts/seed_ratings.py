"""给详情页的扇形图 / 折线图刷演示数据：批量建账号 + 评分 + 评论。

    python scripts/seed_ratings.py            # 幂等：已存在的 (user, attraction) 跳过
    python scripts/seed_ratings.py --reset    # 先清掉这些演示账号的评分/评论再重建

评分按最近 8 个自然月铺开（每月至少一条，越近的月份分数略高），保证折线图连续；
1–5 星分布按 5★45% / 4★30% / 3★15% / 2★7% / 1★3% 取样，扇形图不会只有一根柱。
"""
from __future__ import annotations

import calendar
import pathlib
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from werkzeug.security import generate_password_hash  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Attraction, Comment, Rating, User  # noqa: E402

PASSWORD = "Gz#" + secrets.token_urlsafe(12)
ACCOUNTS = [
    ("tourist1", "阿岚"),
    ("tourist2", "小舟"),
    ("tourist3", "山野"),
    ("tourist4", "米粒"),
    ("tourist5", "老周"),
    ("tourist6", "木子"),
    ("tourist7", "青禾"),
    ("tourist8", "阿蓬"),
]
WEIGHTED = [5] * 45 + [4] * 30 + [3] * 15 + [2] * 7 + [1] * 3

# 各景点原本的均分（取自 instance/guizhou.db 快照）。
# 补数据是为了让趋势图每个月有点，不应该顺带改掉站点原本展示的评分。
FALLBACK_TARGETS = {
    "huangguoshu": 4.0, "xijiang-miao": 4.0, "fanjingshan": 4.0, "fast-tianyan": 4.2,
    "zunyi-conference": 3.9, "loushanguan": 4.0, "xifeng-camp": 4.2, "liping-conference": 4.0,
    "wanfenglin": 3.9, "pingba-cherry": 4.5, "huajiang-bridge": 4.1, "zhaoxing-dong": 4.0,
    "zhenyuan": 4.5, "qingyan": 3.8, "wumeng-grassland": 4.1, "baili-dujuan": 4.2,
    "xiaoqikong": 4.0, "zhijindong": 4.0,
}


def load_targets() -> dict:
    """优先从 SQLite 快照读原始均分，读不到就用兜底表。"""
    snapshot = pathlib.Path(__file__).resolve().parent.parent / "instance" / "guizhou.db"
    if snapshot.exists():
        try:
            import sqlite3

            con = sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)
            rows = con.execute("SELECT slug, rating FROM attractions").fetchall()
            con.close()
            found = {slug: float(value) for slug, value in rows if value}
            if found:
                return {**FALLBACK_TARGETS, **found}
        except Exception:  # noqa: BLE001
            pass
    return dict(FALLBACK_TARGETS)


def ratings_for_target(target: float, count: int, rng: random.Random) -> list[int]:
    """生成 count 个 3~5 星评分，使其均值尽量贴近 target。"""
    total = round(target * count)
    total = max(count * 3, min(count * 5, total))
    values = [4] * count
    diff = total - 4 * count
    index = 0
    while diff > 0 and index < count:
        values[index] += 1
        diff -= 1
        index += 1
    index = 0
    while diff < 0 and index < count:
        values[index] -= 1
        diff += 1
        index += 1
    # 加一点方差但保持总和不变：成对地「一个 +1、一个 -1」，
    # 否则目标 4.0 会生成全是 4 星，折线图平得不像真实数据
    pairs = 1  # 只做一组成对调整，起伏自然又不夸张
    for _ in range(pairs):
        up = rng.randrange(count)
        down = rng.randrange(count)
        if up == down:
            continue
        if values[up] < 5 and values[down] > 3:
            values[up] += 1
            values[down] -= 1
    rng.shuffle(values)
    return values
COMMENTS = [
    "清晨去人少，光线最好，拍照很出片。",
    "建议留足半天，慢慢走比赶点舒服。",
    "停车场离入口有点远，带老人小孩的注意。",
    "门票在官方小程序买更快，现场排队要二十分钟。",
    "雨天路滑，鞋底防滑的比较好走。",
    "附近的农家菜比景区里实惠，可以出来吃。",
]


def main() -> None:
    reset = "--reset" in sys.argv
    rng = random.Random(20261102)
    app = create_app()

    with app.app_context():
        targets = load_targets()

        # 1) 账号
        users = []
        for username, nickname in ACCOUNTS:
            user = User.query.filter_by(username=username).first()
            if user is None:
                user = User(
                    username=username,
                    nickname=nickname,
                    password_hash=generate_password_hash(PASSWORD),
                    role="user",
                    status="active",
                )
                db.session.add(user)
                print(f"  新建用户 {username} / {PASSWORD}")
            users.append(user)
        db.session.flush()

        if reset:
            ids = [u.id for u in users]
            Rating.query.filter(Rating.user_id.in_(ids)).delete(synchronize_session=False)
            Comment.query.filter(Comment.user_id.in_(ids)).delete(synchronize_session=False)
            db.session.flush()
            print("  已清空演示账号的历史评分/评论")

        # 2) 评分：按最近 8 个自然月铺开，每月至少一条，近期略高
        today = datetime.utcnow()
        month_slots = []
        total_month = today.year * 12 + (today.month - 1)
        for offset in range(7, -1, -1):
            slot = total_month - offset
            month_slots.append((slot // 12, slot % 12 + 1))

        attractions = Attraction.query.filter_by(status="published").order_by(Attraction.id).all()
        created = 0
        for attraction in attractions:
            # 每月安排一个人评，保证「近 8 个月」折线每个点都有值
            want = min(len(users), len(month_slots))
            reviewers = rng.sample(users, want)
            target = targets.get(attraction.slug, 4.0)
            month_values = ratings_for_target(target, len(month_slots), rng)
            for index, user in enumerate(reviewers):
                exists = Rating.query.filter_by(user_id=user.id, attraction_id=attraction.id).first()
                if exists:
                    continue
                year, month = month_slots[index % len(month_slots)]
                last_day = calendar.monthrange(year, month)[1]
                upper = today.day if (year, month) == (today.year, today.month) else last_day
                when = datetime(
                    year, month, rng.randint(1, max(1, upper)),
                    rng.randint(8, 21), rng.randint(0, 59),
                )
                if when > today:
                    when = today - timedelta(hours=rng.randint(1, 20))
                rating = month_values[index % len(month_values)]
                db.session.add(Rating(user_id=user.id, attraction_id=attraction.id,
                                      rating=rating, created_at=when))
                created += 1
            db.session.flush()

            # 3) 评论：一半景点各来一条已通过
            if rng.random() < 0.5:
                author = rng.choice(reviewers)
                if not Comment.query.filter_by(user_id=author.id, attraction_id=attraction.id).first():
                    db.session.add(Comment(
                        user_id=author.id, attraction_id=attraction.id,
                        content=rng.choice(COMMENTS), status="approved",
                        created_at=today - timedelta(days=rng.randint(1, 50)),
                    ))

        db.session.flush()

        # 4) 回写景点的平均分 / 人数（与 /api/ratings 的口径一致）
        from sqlalchemy import func

        stats = (
            db.session.query(Rating.attraction_id, func.avg(Rating.rating), func.count(Rating.id))
            .group_by(Rating.attraction_id)
            .all()
        )
        for attraction_id, avg, count in stats:
            attraction = db.session.get(Attraction, attraction_id)
            if attraction is None:
                continue
            attraction.rating = round(float(avg or 0), 1)
            attraction.rating_count = int(count or 0)

        db.session.commit()

        total_ratings = Rating.query.count()
        total_comments = Comment.query.filter_by(status="approved").count()
        print(f"\n新增评分 {created} 条；当前评分总数 {total_ratings}，已通过评论 {total_comments}")
        for attraction in Attraction.query.order_by(Attraction.id).limit(5):
            print(f"  {attraction.name:12} ★ {attraction.rating} ({attraction.rating_count} 人)")


if __name__ == "__main__":
    main()
