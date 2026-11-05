from urllib.parse import urlsplit

from flask import Blueprint, Response, abort, render_template, request
from flask_login import current_user, login_required

from ..extensions import db
from ..i18n import attr_field, current_lang
from ..models import Attraction, Booking, Comment, Favorite, Itinerary, Rating, User
from ..services.ai_itinerary import translate_conflicts, translate_plan
from ..services.history import recent_views

bp = Blueprint("user", __name__)


@bp.get("/avatar/<int:user_id>")
def avatar(user_id):
    """头像直接从数据库读出来返回（用户未上传时 404，模板回落到首字）。"""
    user = db.session.get(User, user_id)
    if user is None or not user.avatar_data:
        abort(404)
    response = Response(user.avatar_data, mimetype=user.avatar_mime or "image/jpeg")
    response.headers["Cache-Control"] = "public, max-age=300"
    response.set_etag(f"{user.id}-{user.avatar_version or 0}")
    return response.make_conditional(request)

_SLOT_LABELS = {"morning": "上午", "afternoon": "下午", "evening": "晚上"}


def _itinerary_days(items):
    """把库里存的行程项统一成 [{day, theme, slots:[{period,title,slug}]}]。

    兼容两种历史结构：老结构 {day, morning, afternoon, evening} 与
    新结构 {day, theme, slots:[...]}。
    """
    days = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        if isinstance(item.get("slots"), list):
            slots = [
                {
                    "period": str(slot.get("period") or ""),
                    "title": str(slot.get("title") or ""),
                    "slug": str(slot.get("slug") or ""),
                    "city": str(slot.get("city") or ""),
                    "detail": str(slot.get("detail") or ""),
                }
                for slot in item["slots"]
                if isinstance(slot, dict) and slot.get("title")
            ]
        else:
            slots = [
                {"period": label, "title": item[key].get("name", ""), "slug": item[key].get("slug", ""),
                 "city": item[key].get("city", ""), "detail": item[key].get("detail", "")}
                for key, label in _SLOT_LABELS.items()
                if isinstance(item.get(key), dict) and item[key].get("name")
            ]
        if slots:
            days.append({
                "day": item.get("day"),
                "theme": item.get("theme") or "",
                "slots": slots,
                "tips": str(item.get("tips") or ""),
            })
    return days


_BRIEF_KEYS = ("summary", "transport", "weather", "clothing", "lodging")


def _safe_link(url, hosts):
    """只留 https + 指定域名下的外链，避免把存档里的任意 URL 渲染成可点按钮。"""
    text = str(url or "").strip()
    if not text.startswith("https://"):
        return ""
    try:
        host = (urlsplit(text).hostname or "").lower()
    except ValueError:
        return ""
    if not host or not any(host == item or host.endswith("." + item) for item in hosts):
        return ""
    return text


def _saved_hotels(source):
    """清洗「住宿推荐」存档：最多 2 段、每段 3 家，只保留可展示的字段。"""
    if not isinstance(source, dict):
        return None
    stays = []
    for stay in (source.get("stays") or [])[:2]:
        if not isinstance(stay, dict):
            continue
        hotels = []
        for hotel in (stay.get("hotels") or [])[:3]:
            if not isinstance(hotel, dict):
                continue
            name = str(hotel.get("name") or "").strip()
            if not name:
                continue
            hotels.append({
                "name": name[:60],
                "star": hotel.get("star") if isinstance(hotel.get("star"), (int, float)) else 0,
                "price_text": str(hotel.get("price_text") or "").strip()[:20],
                "address": str(hotel.get("address") or "").strip()[:60],
                "image": _safe_link(hotel.get("image"), ("rollinggo.cn",)),
                "booking_url": _safe_link(hotel.get("booking_url"), ("rollinggo.cn",)),
            })
        if hotels:
            try:
                nights = int(stay.get("nights") or 0)
            except (TypeError, ValueError):
                nights = 0
            stays.append({
                "city": str(stay.get("city") or "").strip()[:20],
                "nights": nights,
                "place": str(stay.get("place") or "").strip()[:40],
                "hotels": hotels,
            })
    if not stays:
        return None
    return {"stays": stays, "note": str(source.get("note") or "").strip()[:60]}


def _finite(value, default=0.0):
    """把存档里的数字收敛成有限 float；脏数据一律归默认值。"""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if number != number or number in (float("inf"), float("-inf")):
        return default
    return number


def _saved_conflicts(source):
    """清洗冲突存档：最多 10 条，只留契约字段，等级非法归 low。

    两种形态都要吃下：规则引擎产出的是 {"count": N, "conflicts": [...]}，
    早期存档可能直接是数组。只认数组会让 brief.conflicts 恒为空，
    模板于是回退去读未清洗的原始数据——这里必须兼容，否则又是一处隐患。
    """
    if isinstance(source, dict):
        source = source.get("conflicts")
    if not isinstance(source, list):
        return None
    rows = []
    for item in source[:10]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        severity = str(item.get("severity") or "").strip().lower()
        if severity not in ("high", "medium", "low"):
            severity = "low"
        try:
            day = int(item.get("day") or 0)
        except (TypeError, ValueError):
            day = 0
        rows.append({
            "code": str(item.get("code") or "").strip()[:32],
            "severity": severity,
            "day": max(0, min(day, 5)),
            "title": title[:120],
            "detail": str(item.get("detail") or "").strip()[:200],
            "suggestion": str(item.get("suggestion") or "").strip()[:200],
        })
    return rows or None


def _saved_budget(source):
    """清洗预算沙盘存档：只留契约字段，数值做有限性校验。"""
    if not isinstance(source, dict):
        return None
    items = []
    for item in (source.get("items") or [])[:8]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        if not label:
            continue
        items.append({
            "key": str(item.get("key") or "").strip()[:20],
            "label": label[:24],
            "per_person": round(_finite(item.get("per_person")), 1),
            "detail": str(item.get("detail") or "").strip()[:100],
        })
    cuts = []
    for cut in (source.get("cuts") or [])[:6]:
        if not isinstance(cut, dict):
            continue
        label = str(cut.get("label") or "").strip()
        if not label:
            continue
        cuts.append({"label": label[:100], "saving": round(_finite(cut.get("saving")), 1)})
    compare = source.get("compare")
    if not isinstance(compare, dict):
        compare = {}
    status = str(compare.get("status") or "").strip().lower()
    if status not in ("under", "over", "even", "unknown"):
        status = "unknown"
    view = {
        "total_per_person": round(_finite(source.get("total_per_person")), 1),
        "total_all": round(_finite(source.get("total_all")), 1),
        "people": max(0, min(int(_finite(source.get("people"))), 20)),
        "items": items,
        "cuts": cuts,
        "compare": {
            "budget": round(_finite(compare.get("budget")), 1),
            "delta": round(_finite(compare.get("delta")), 1),
            "status": status,
        },
    }
    if not (view["total_per_person"] or view["total_all"] or items):
        return None
    return view


def _saved_plan(items):
    """拆出「概要 + 逐日」：新结构存 dict（含 brief），老结构存 list。"""
    brief = {}
    if isinstance(items, dict):
        source = items.get("brief") or {}
        if isinstance(source, dict):
            for key in _BRIEF_KEYS:
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    brief[key] = value.strip()
            route = [str(part).strip() for part in (source.get("route") or []) if str(part).strip()]
            if route:
                brief["route"] = route
            budget = [
                {"item": str(part.get("item") or "").strip(), "amount": str(part.get("amount") or "").strip()}
                for part in (source.get("budget_plan") or [])
                if isinstance(part, dict) and part.get("item")
            ]
            if budget:
                brief["budget_plan"] = budget
            notes = [str(part).strip() for part in (source.get("notes") or []) if str(part).strip()]
            if notes:
                brief["notes"] = notes
            xhs = source.get("xhs")
            if isinstance(xhs, dict) and xhs.get("count"):
                brief["xhs"] = {"count": int(xhs.get("count") or 0), "source": str(xhs.get("source") or "")}
            hotels = _saved_hotels(source.get("hotels"))
            if hotels:
                brief["hotels"] = hotels
            conflicts = _saved_conflicts(source.get("conflicts"))
            if conflicts:
                brief["conflicts"] = conflicts
            budget_view = _saved_budget(source.get("budget"))
            if budget_view:
                brief["budget"] = budget_view
        days_source = items.get("days")
    else:
        days_source = items
    return {"brief": brief, "days": _itinerary_days(days_source)}


@bp.get("/profile")
@login_required
def profile():
    favorites = (
        db.session.query(Favorite, Attraction)
        .join(Attraction, Favorite.attraction_id == Attraction.id)
        .filter(Favorite.user_id == current_user.id)
        .order_by(Favorite.created_at.desc())
        .all()
    )
    comments = (
        db.session.query(Comment, Attraction)
        .join(Attraction, Comment.attraction_id == Attraction.id)
        .filter(Comment.user_id == current_user.id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    ratings = (
        db.session.query(Rating, Attraction)
        .join(Attraction, Rating.attraction_id == Attraction.id)
        .filter(Rating.user_id == current_user.id)
        .order_by(Rating.created_at.desc())
        .all()
    )
    views = recent_views(current_user.id)
    itineraries = (
        Itinerary.query.filter_by(user_id=current_user.id)
        .order_by(Itinerary.created_at.desc(), Itinerary.id.desc())
        .limit(20)
        .all()
    )
    return render_template(
        "pages/profile.html",
        favorites=favorites,
        comments=comments,
        ratings=ratings,
        views=views,
        itineraries=[
            {
                "id": row.id,
                "title": row.title,
                "days": row.days,
                "created_at": row.created_at,
            }
            for row in itineraries
        ],
    )


@bp.get("/itinerary/<int:itinerary_id>")
@login_required
def itinerary_saved(itinerary_id):
    """点进「我的行程」里的某一条，看保存下来的完整 AI 规划。"""
    row = Itinerary.query.filter_by(id=itinerary_id, user_id=current_user.id).first()
    if row is None:
        abort(404)
    plan = _saved_plan(row.items)

    # 行程正文是生成时那一刻的语言存下来的。英文站看到中文原文时，
    # 首次访问翻译一次并缓存进 items["_en"]，之后直接复用。
    # 注意：_saved_plan() 的 brief 走白名单，conflicts / hotels 不在里面，
    # 但模板会从原始 items.brief 取，所以冲突文案要单独翻。
    if current_lang() == "en":
        raw_brief = row.items.get("brief") if isinstance(row.items, dict) else None
        raw_conflicts = (raw_brief or {}).get("conflicts") if isinstance(raw_brief, dict) else None

        cached = row.items.get("_en") or {} if isinstance(row.items, dict) else {}
        if cached.get("brief") or cached.get("days"):
            merged = dict(plan["brief"])
            merged.update(cached.get("brief") or {})
            if raw_conflicts and not merged.get("conflicts"):
                merged["conflicts"] = raw_conflicts
            plan = {"brief": merged, "days": cached.get("days") or plan["days"]}
        else:
            translated = translate_plan(plan, "en")
            if translated and (translated.get("brief") or translated.get("days")):
                # 模型只翻文本字段，hotels / budget / xhs 等结构字段必须保留原样
                merged_brief = dict(plan["brief"])
                merged_brief.update(translated.get("brief") or {})
                if raw_conflicts and not merged_brief.get("conflicts"):
                    merged_brief["conflicts"] = translate_conflicts(raw_conflicts, "en")
                translated_days = translated.get("days") or []
                stored = dict(row.items) if isinstance(row.items, dict) else {"brief": plan["brief"], "days": plan["days"]}
                cached_brief = dict(translated.get("brief") or {})
                if merged_brief.get("conflicts"):
                    cached_brief["conflicts"] = merged_brief["conflicts"]
                stored["_en"] = {"brief": cached_brief, "days": translated_days}
                row.items = stored
                db.session.commit()
                plan = {
                    "brief": merged_brief,
                    "days": translated_days if len(translated_days) == len(plan["days"]) else plan["days"],
                }
            elif raw_conflicts:
                # 整体翻译失败也要让冲突至少不报错
                plan = {"brief": dict(plan["brief"], conflicts=raw_conflicts), "days": plan["days"]}

    return render_template(
        "pages/itinerary_saved.html",
        itinerary=row,
        brief=plan["brief"],
        days=plan["days"],
    )


def _order_data(booking):
    attraction = db.session.get(Attraction, booking.attraction_id)
    return {"id": booking.id, "attraction": {"id": attraction.id, "name": attr_field(attraction, "name"), "slug": attraction.slug},
            "visit_date": booking.visit_date.isoformat(), "quantity": booking.quantity, "unit_price": float(booking.unit_price),
            "total": float(booking.total), "status": booking.status, "created_at": booking.created_at.isoformat() if booking.created_at else None}


@bp.get("/booking/<int:attraction_id>")
@login_required
def booking(attraction_id):
    attraction = Attraction.query.filter_by(id=attraction_id, status="published").first()
    if attraction is None:
        abort(404)
    return render_template("pages/booking.html", attraction=attraction)


@bp.get("/orders")
@login_required
def orders():
    rows = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc(), Booking.id.desc()).all()
    return render_template("pages/orders.html", orders=[_order_data(row) for row in rows])


@bp.get("/itinerary")
def itinerary():
    attractions = Attraction.query.filter_by(status="published").order_by(Attraction.city, Attraction.rating.desc()).all()
    return render_template("pages/itinerary.html", attractions=attractions)
