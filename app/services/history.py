"""浏览记录与个性化每日推荐。

规则（按用户确认）：
- 记录登录用户对景点的浏览，同一景点同一天只记一次；
- 取最近 30 天浏览记录中出现最多的分类；
- 优先推荐该分类下、最近 7 天没看过的景点，按评分取前三，按日期轮换；
- 无记录（游客/新用户）回退到“今日精选”。
"""
from datetime import date, datetime, timedelta

from sqlalchemy import func

from ..extensions import db
from ..i18n import t
from ..models import Attraction, ViewLog

CATEGORY_LABELS = {
    "自然": "自然山水",
    "人文": "人文村寨",
    "红色": "红色记忆",
    "科技": "科技奇观",
    "季节": "艳季花海",
}


def record_view(user_id: int, attraction_id: int) -> None:
    today = date.today()
    existing = ViewLog.query.filter_by(
        user_id=user_id, attraction_id=attraction_id, view_date=today
    ).first()
    if existing:
        existing.viewed_at = datetime.utcnow()
    else:
        db.session.add(ViewLog(user_id=user_id, attraction_id=attraction_id, view_date=today))
    db.session.commit()


def _top_category(user_id: int, days: int = 30):
    cutoff = date.today() - timedelta(days=days)
    row = (
        db.session.query(Attraction.category, func.count(ViewLog.id).label("cnt"))
        .join(ViewLog, ViewLog.attraction_id == Attraction.id)
        .filter(ViewLog.user_id == user_id, ViewLog.view_date >= cutoff)
        .group_by(Attraction.category)
        .order_by(func.count(ViewLog.id).desc())
        .first()
    )
    return row[0] if row else None


def daily_recommendation(user=None):
    today = date.today()
    base = Attraction.query.filter_by(status="published")

    if user is not None and getattr(user, "is_authenticated", False):
        top = _top_category(user.id)
        if top:
            cutoff = today - timedelta(days=7)
            seen = {
                row[0]
                for row in db.session.query(ViewLog.attraction_id)
                .filter(ViewLog.user_id == user.id, ViewLog.view_date >= cutoff)
                .all()
            }
            query = base.filter(Attraction.category == top)
            if seen:
                query = query.filter(~Attraction.id.in_(seen))
            candidates = query.order_by(Attraction.rating.desc()).limit(3).all()
            if candidates:
                pick = candidates[today.toordinal() % len(candidates)]
                return {
                    "attraction": pick,
                    "reason": t("你最近常看{cat}", cat=t(CATEGORY_LABELS.get(top, top))),
                }
            # 该分类都看过了：回退到任意没看过的
            fallback = base
            if seen:
                fallback = fallback.filter(~Attraction.id.in_(seen))
            candidates = fallback.order_by(Attraction.rating.desc()).limit(3).all()
            if candidates:
                pick = candidates[today.toordinal() % len(candidates)]
                return {"attraction": pick, "reason": t("根据你的浏览记录推荐")}

    candidates = base.order_by(Attraction.rating.desc()).limit(5).all()
    if not candidates:
        return None
    pick = candidates[today.toordinal() % len(candidates)]
    return {"attraction": pick, "reason": t("今日精选 · 贵州必去")}


def recent_views(user_id: int, limit: int = 12):
    rows = (
        db.session.query(Attraction, func.max(ViewLog.viewed_at).label("last_viewed"))
        .join(ViewLog, ViewLog.attraction_id == Attraction.id)
        .filter(ViewLog.user_id == user_id)
        .group_by(Attraction.id)
        .order_by(func.max(ViewLog.viewed_at).desc())
        .limit(limit)
        .all()
    )
    return [{"attraction": attraction, "viewed_at": last} for attraction, last in rows]
