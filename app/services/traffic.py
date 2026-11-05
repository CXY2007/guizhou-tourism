"""景点访问量统计：每次打开详情页记一次，按「景点 × 天」汇总。

- views：浏览量（同一会话重复刷新也计）
- visitors：访客数（同一会话当天同一景点只计一次）
游客和登录用户都计；不写用户身份，只累加计数。
"""
from __future__ import annotations

from datetime import date, timedelta

from flask import session
from sqlalchemy import func

from ..extensions import db
from ..models import Attraction, TrafficDaily

_SEEN_KEY = "traffic_seen"


def record_traffic(attraction_id: int) -> None:
    today = date.today()
    row = TrafficDaily.query.filter_by(attraction_id=attraction_id, day=today).first()
    if row is None:
        row = TrafficDaily(attraction_id=attraction_id, day=today, views=0, visitors=0)
        db.session.add(row)

    row.views = int(row.views or 0) + 1
    seen = session.get(_SEEN_KEY) or {}
    key = str(attraction_id)
    stamp = today.isoformat()
    if seen.get(key) != stamp:
        row.visitors = int(row.visitors or 0) + 1
        # 只保留今天的标记，避免 session 越滚越大
        seen = {item: value for item, value in seen.items() if value == stamp}
        seen[key] = stamp
        session[_SEEN_KEY] = seen
    db.session.commit()


def _sum_since(days: int) -> dict[int, int]:
    cutoff = date.today() - timedelta(days=days - 1)
    rows = (
        db.session.query(TrafficDaily.attraction_id, func.sum(TrafficDaily.views))
        .filter(TrafficDaily.day >= cutoff)
        .group_by(TrafficDaily.attraction_id)
        .all()
    )
    return {attraction_id: int(total or 0) for attraction_id, total in rows}


def summary(days: int = 30) -> dict:
    """后台流量页数据：总量、每个景点的今日/7天/30天、近 N 天趋势。"""
    today = date.today()
    cutoff = today - timedelta(days=days - 1)

    per_attraction = []
    attractions = Attraction.query.order_by(Attraction.id).all()
    today_rows = {
        attraction_id: (views, visitors)
        for attraction_id, views, visitors in db.session.query(
            TrafficDaily.attraction_id, TrafficDaily.views, TrafficDaily.visitors
        ).filter(TrafficDaily.day == today).all()
    }
    week = _sum_since(7)
    month = _sum_since(30)
    total_rows = (
        db.session.query(TrafficDaily.attraction_id, func.sum(TrafficDaily.views))
        .group_by(TrafficDaily.attraction_id)
        .all()
    )
    all_time = {attraction_id: int(total or 0) for attraction_id, total in total_rows}

    for attraction in attractions:
        views_today, visitors_today = today_rows.get(attraction.id, (0, 0))
        per_attraction.append({
            "id": attraction.id,
            "slug": attraction.slug,
            "name": attraction.name,
            "category": attraction.category,
            "today": int(views_today or 0),
            "visitors_today": int(visitors_today or 0),
            "week": week.get(attraction.id, 0),
            "month": month.get(attraction.id, 0),
            "total": all_time.get(attraction.id, 0),
        })
    per_attraction.sort(key=lambda item: (-item["month"], -item["total"]))

    daily_rows = (
        db.session.query(TrafficDaily.day, func.sum(TrafficDaily.views), func.sum(TrafficDaily.visitors))
        .filter(TrafficDaily.day >= cutoff)
        .group_by(TrafficDaily.day)
        .order_by(TrafficDaily.day)
        .all()
    )
    daily_map = {day.isoformat(): (int(views or 0), int(visitors or 0)) for day, views, visitors in daily_rows}
    series = []
    for offset in range(days):
        day = cutoff + timedelta(days=offset)
        key = day.isoformat()
        views, visitors = daily_map.get(key, (0, 0))
        series.append({"date": key, "views": views, "visitors": visitors})

    month_total = sum(item["month"] for item in per_attraction)
    today_total = sum(item["today"] for item in per_attraction)
    week_total = sum(item["week"] for item in per_attraction)
    all_total = sum(item["total"] for item in per_attraction)
    peak = max(per_attraction, key=lambda item: item["month"], default=None)

    return {
        "cards": {
            "today": today_total,
            "week": week_total,
            "month": month_total,
            "total": all_total,
            "peak": peak["name"] if peak and peak["month"] else "",
            "peak_views": peak["month"] if peak else 0,
        },
        "rows": per_attraction,
        "series": series,
        "days": days,
    }
