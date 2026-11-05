"""行程冲突检测、预算沙盘与选点预检（纯本地算法，契约见 team task-2 / task-7）。

对外三个函数：

    detect_conflicts(days, budget=0) -> {"conflicts": [...], "count": int}
    build_budget(days, people=2, budget=0, start_date="", hotel_price=0)
        -> {"total_per_person", "total_all", "items", "cuts", "compare", "people"}
    precheck_selection(attractions, days, budget=0)
        -> {"cities": [...], "count": int, "conflicts": [...]}

硬约束：
- 纯本地：不调外部服务、不烧 token、不写库、不进程内缓存；
- 城市坐标取该城 published 景点坐标均值（一次聚合查询），拿不到就跳过
  依赖坐标的规则，绝不编造距离；
- 任何异常都收口成空结果，绝不把异常抛给调用方 / 500。
"""

from __future__ import annotations

import math
import re

from ..i18n import current_lang, t

EARTH_RADIUS_KM = 6371.0

# ---- 冲突规则阈值（契约固定，不许自创）----
CROSS_CITY_KM = 100.0       # cross_city：同日两城直线距离超过 100km 才报
DENSE_ATTRACTIONS = 3       # too_dense：单日带 slug 景点数「超过」3 才报
MAX_DAYS = 5                # 与现成 /api/itinerary/* 保持一致
MAX_PEOPLE = 50             # 人数上限（与 api.py 的 _coerce_people 对齐）

# ---- 选点预检阈值（契约固定；跨城复用 CROSS_CITY_KM）----
SELECTION_ATTRACTIONS_PER_DAY = 3   # too_dense：景点数 > days × 3 才报
SELECTION_TICKET_SHARE = 0.5        # tickets_heavy：门票合计 > budget × 0.5 且 budget > 0
SELECTION_MIN_PICKS = 2             # 预检的下限：单点没有「跨城/密度」可比，直接空结果
                                    # （生成本身 1 个就够，不受这里限制）
SELECTION_MAX_PICKS = 8             # 与 generate / ai-plan 的 1–8 个对齐


def _nights_text(nights):
    """「N 晚」在英文里要区分 night / nights，中文保持原样。"""
    if current_lang() == "en":
        return f"{nights} night" if nights == 1 else f"{nights} nights"
    return f"{nights} 晚"


def _join_list(items):
    """中文用顿号、英文用逗号；否则英文界面会冒出「Anshun、Qiandongnan」。"""
    parts = [str(item) for item in items if str(item)]
    return (", " if current_lang() == "en" else "、").join(parts)

# ---- 预算公式（契约固定）----
CITY_TRANSFER_RATE = 0.6        # 城际交通 ¥/公里
SAME_CITY_TRANSFER = 30.0       # 同城接驳上限（¥）
LOCAL_TRANSPORT_PER_DAY = 50.0  # 市内交通 ¥/人/天
MEAL_PER_DAY = 120.0            # 餐饮 ¥/人/天
DEFAULT_HOTEL_PRICE = 300.0     # 房价兜底 ¥/晚
OTHER_RATE = 0.08               # 其他 = 以上合计的 8%
MAX_HOTEL_PRICE = 100000.0

_RETURN_KEYWORDS = ("返程", "返回", "回程", "回家", "解散", "送站")
_NO_STAY_KEYWORDS = ("无需住宿", "不需要住宿", "当日往返", "当日返回", "day trip", "no overnight")
_MAX_TICKET_NAMES = 6


# ---------------------------------------------------------------- 基础工具
def _num(value, default=0.0) -> float:
    """宽容地把 JSON 里的数字/数字字符串转成 float；布尔与脏数据走 default。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip().replace(",", ""))
        except ValueError:
            return default
    try:
        return float(value)  # Decimal（SQLAlchemy Numeric 列）等数字类型
    except (TypeError, ValueError):
        return default


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _money(value) -> float | int:
    """展示用金额：整数就不带小数点，否则保留 1 位。"""
    number = _num(value, 0)
    if abs(number - round(number)) < 0.05:
        return int(round(number))
    return round(number, 1)


def _people_count(people) -> int:
    """人数：宽容取整并夹到 [0, MAX_PEOPLE]，非法值按 0（先看人均）。"""
    try:
        count = int(round(_num(people, 0)))
    except (TypeError, ValueError):
        return 0
    return max(0, min(count, MAX_PEOPLE))


def _haversine(lng1, lat1, lng2, lat2) -> float:
    """两点经纬度直线距离（公里）。"""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def _normalise_days(days) -> list[dict]:
    """把任意形状的 days 收敛成 [{day, slots, tips}]；脏数据跳过，不抛异常。"""
    if not isinstance(days, list):
        return []
    result = []
    for index, raw in enumerate(days[:MAX_DAYS]):
        if not isinstance(raw, dict):
            continue
        try:
            day_no = int(raw.get("day") or index + 1)
        except (TypeError, ValueError):
            day_no = index + 1
        slots = raw.get("slots")
        slots = [slot for slot in slots if isinstance(slot, dict)] if isinstance(slots, list) else []
        result.append({"day": day_no, "slots": slots, "tips": _text(raw.get("tips"))})
    return result


def _day_city(slots) -> str:
    for slot in slots:
        city = _text(slot.get("city")).strip()
        if city:
            return city
    return ""


def _last_city(slots) -> str:
    """当天最后一个有城市的 slot——判断「最后一天之后是否还在外地」要用它。"""
    for slot in reversed(slots):
        city = _text(slot.get("city")).strip()
        if city:
            return city
    return ""


def _city_coords() -> dict:
    """{城市: (经度均值, 纬度均值)}，只读 published 景点；失败/无上下文返回 {}。"""
    try:
        from flask import has_app_context

        if not has_app_context():
            return {}
        from sqlalchemy import func

        from ..extensions import db
        from ..models import Attraction

        rows = (
            db.session.query(
                Attraction.city,
                func.avg(Attraction.longitude),
                func.avg(Attraction.latitude),
            )
            .filter(
                Attraction.status == "published",
                Attraction.city.isnot(None),
                Attraction.longitude.isnot(None),
                Attraction.latitude.isnot(None),
            )
            .group_by(Attraction.city)
            .all()
        )
        coords = {}
        for city, longitude, latitude in rows:
            if city and longitude is not None and latitude is not None:
                coords[str(city)] = (float(longitude), float(latitude))
        return coords
    except Exception:
        return {}


def _city_aliases(coords) -> dict:
    """城市名 -> 坐标表的 key；兼容英文界面下返回的 "Anshun" 这类译名。"""
    aliases = {city: city for city in coords}
    try:
        from ..i18n import EN

        for zh, en in EN.items():
            if zh in coords and isinstance(en, str) and en:
                aliases.setdefault(en.lower(), zh)
    except Exception:
        pass
    return aliases


def _resolve_city(name, aliases) -> str:
    if not name:
        return ""
    if name in aliases:
        return aliases[name]
    return aliases.get(name.lower(), "")


def _attraction_prices(normalised) -> dict:
    """{slug: (名称, 门票价)}；只查 published，查不到就不算钱（不编造票价）。"""
    try:
        slugs = sorted({
            _text(slot.get("slug")).strip()
            for day in normalised
            for slot in day["slots"]
            if _text(slot.get("slug")).strip()
        })
        if not slugs:
            return {}
        from flask import has_app_context

        if not has_app_context():
            return {}
        from ..models import Attraction

        rows = (
            Attraction.query
            .filter(Attraction.slug.in_(slugs), Attraction.status == "published")
            .all()
        )
        return {
            row.slug: (row.name or row.slug, _num(row.price, 0))
            for row in rows
            if row.slug
        }
    except Exception:
        return {}


# ---------------------------------------------------------------- 冲突检测
def _cross_city_conflict(day, coords, aliases) -> list[dict]:
    cities, periods = [], {}
    for slot in day["slots"]:
        city = _text(slot.get("city")).strip()
        if not city or city in periods:
            continue
        periods[city] = t(_text(slot.get("period")).strip()) if _text(slot.get("period")).strip() else ""
        cities.append(city)
    if len(cities) < 2:
        return []

    best = None  # (距离, 城市 A, 城市 B)
    for index, first in enumerate(cities):
        for second in cities[index + 1:]:
            key_a = _resolve_city(first, aliases)
            key_b = _resolve_city(second, aliases)
            if not key_a or not key_b:
                continue  # 坐标缺一个就跳过这条规则，不猜
            distance = _haversine(*coords[key_a], *coords[key_b])
            if best is None or distance > best[0]:
                best = (distance, first, second)
    if best is None:
        return []
    distance, first, second = best
    if distance <= CROSS_CITY_KM:
        return []

    km = int(round(distance))
    return [{
        "code": "cross_city",
        "severity": "high",
        "day": day["day"],
        "title": t("第 {n} 天跨城 {km} 公里", n=day["day"], km=km),
        "detail": t(
            "{p1}在{a}、{p2}在{b}，单程约 {km} 公里",
            p1=periods.get(first) or t("上午"),
            p2=periods.get(second) or t("下午"),
            a=first,
            b=second,
            km=km,
        ),
        "suggestion": t("把{place}的行程挪到相邻的一天", place=second),
    }]


def _overlap_conflicts(day) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for slot in day["slots"]:
        period = _text(slot.get("period")).strip()
        if period:
            buckets.setdefault(period, []).append(slot)

    conflicts = []
    for period, slots in buckets.items():
        if len(slots) < 2:
            continue
        titles = [
            _text(slot.get("title")).strip() or t("未命名安排")
            for slot in slots[:3]
        ]
        conflicts.append({
            "code": "overlap",
            "severity": "high",
            "day": day["day"],
            "title": t("第 {n} 天{period}安排了 {count} 个行程",
                       n=day["day"], period=t(period), count=len(slots)),
            "detail": t("同一时段排了：{titles}", titles=_join_list(titles)),
            "suggestion": t("把其中一个挪到下午或晚上"),
        })
    return conflicts


def _too_dense_conflict(day) -> list[dict]:
    slotted = [slot for slot in day["slots"] if _text(slot.get("slug")).strip()]
    if len(slotted) <= DENSE_ATTRACTIONS:
        return []
    titles = _join_list(
        _text(slot.get("title")).strip() or t("未命名安排")
        for slot in slotted[:4]
    )
    detail = t("一天 {count} 个景点，路上会赶。", count=len(slotted))
    if titles:
        detail = f"{detail}（{titles}）"
    return [{
        "code": "too_dense",
        "severity": "low",
        "day": day["day"],
        "title": t("第 {n} 天安排了 {count} 个景点", n=day["day"], count=len(slotted)),
        "detail": detail,
        "suggestion": t("删掉 1 个，或拆到第二天"),
    }]


def _no_return_conflict(normalised) -> list[dict]:
    if len(normalised) < 2:
        return []
    day_cities = [_day_city(day["slots"]) for day in normalised]
    distinct = {city for city in day_cities if city}
    if len(distinct) < 2:
        return []  # 单城行程谈不上「仍在外地」
    first_city = next((city for city in day_cities if city), "")
    last_day = normalised[-1]
    last_city = _last_city(last_day["slots"])
    if not first_city or not last_city or last_city == first_city:
        return []

    haystack = last_day["tips"] + "".join(
        _text(slot.get("detail")) + _text(slot.get("title")) for slot in last_day["slots"]
    )
    if any(keyword in haystack for keyword in _RETURN_KEYWORDS):
        return []
    return [{
        "code": "no_return",
        "severity": "low",
        "day": last_day["day"],
        "title": t("最后一天仍在{city}，没写返程", city=last_city),
        "detail": t("行程最后停在{city}，最后一天没有返程安排。", city=last_city),
        "suggestion": t("在最后一天留出返程时间，或加一天机动"),
    }]


def _over_budget_conflict(normalised, budget, budget_result) -> list[dict]:
    budget_value = _num(budget, 0)
    if budget_value <= 0:
        return []
    total = _num(budget_result.get("total_per_person"), 0)
    if total <= budget_value:
        return []
    return [{
        "code": "over_budget",
        "severity": "medium",
        "day": 0,
        "title": t("人均预计 ¥{total}，超出预算 ¥{over}",
                   total=_money(total), over=_money(total - budget_value)),
        "detail": t("按当前行程人均约 ¥{total}，你设的预算是 ¥{budget}。",
                    total=_money(total), budget=_money(budget_value)),
        "suggestion": t("换更便宜的住宿，或舍掉一个收费景点"),
    }]


def detect_conflicts(days, budget=0) -> dict:
    """检测行程冲突。纯函数：不改入参、不写库、任何异常返回空结果。"""
    empty = {"conflicts": [], "count": 0}
    try:
        normalised = _normalise_days(days)
        if not normalised:
            return empty

        coords = _city_coords()
        aliases = _city_aliases(coords)
        prices = _attraction_prices(normalised)
        budget_result = _budget_core(
            normalised,
            people=2,
            budget=budget,
            start_date="",
            hotel_price=0,
            lodging="",
            coords=coords,
            prices=prices,
        )

        conflicts: list[dict] = []
        for day in normalised:
            conflicts.extend(_cross_city_conflict(day, coords, aliases))
            conflicts.extend(_overlap_conflicts(day))
            conflicts.extend(_too_dense_conflict(day))
        conflicts.extend(_no_return_conflict(normalised))
        conflicts.extend(_over_budget_conflict(normalised, budget, budget_result))

        weight = {"high": 0, "medium": 1, "low": 2}
        conflicts.sort(key=lambda item: (weight.get(item["severity"], 9), item["day"]))
        return {"conflicts": conflicts, "count": len(conflicts)}
    except Exception:
        return empty


# ---------------------------------------------------------------- 选点预检
def _attraction_rows(attractions) -> list[dict]:
    """把 Attraction 模型 / 同形字典收敛成 [{name, city, price}]；脏数据跳过、重复去掉。"""
    if not isinstance(attractions, (list, tuple)):
        return []
    rows, seen = [], set()
    for raw in attractions:
        try:
            if isinstance(raw, dict):
                key = raw.get("id") or raw.get("slug") or raw.get("name")
                name = _text(raw.get("name")).strip()
                city = _text(raw.get("city")).strip()
                price = _num(raw.get("price"), 0)
            else:
                key = getattr(raw, "id", None) or getattr(raw, "slug", None) or getattr(raw, "name", "")
                name = _text(getattr(raw, "name", "")).strip()
                city = _text(getattr(raw, "city", "")).strip()
                price = _num(getattr(raw, "price", 0), 0)
            if not name and not city:
                continue
            if key in seen:
                continue
            seen.add(key)
            # 负票价按免费处理，不拿脏数据算「超过预算」
            rows.append({"name": name or city, "city": city, "price": max(0.0, price)})
        except Exception:
            continue  # 单条脏数据不拖垮整次预检
    return rows


def _selection_cross_city(rows, cities, days, coords, aliases) -> list[dict]:
    """所选景点跨 ≥2 个城市，且最远两城直线 >100km。坐标缺一个就跳过，不猜。"""
    if len(cities) < 2:
        return []

    best = None  # (距离, 城市 A, 城市 B)
    for index, first in enumerate(cities):
        for second in cities[index + 1:]:
            key_a = _resolve_city(first, aliases)
            key_b = _resolve_city(second, aliases)
            if not key_a or not key_b:
                continue
            distance = _haversine(*coords[key_a], *coords[key_b])
            if best is None or distance > best[0]:
                best = (distance, first, second)
    if best is None or best[0] <= CROSS_CITY_KM:
        return []

    distance = best[0]  # 只有最远那一对的距离要展示，城市整组都写进 title
    km = int(round(distance))
    if days < MAX_DAYS:
        suggestion = t("去掉一个远端景点，或把天数加到 {n} 天", n=days + 1)
    else:
        suggestion = t("去掉一个远端景点，两城之间只留一城")
    return [{
        "code": "selection_cross_city",
        "severity": "high",
        "title": t(
            "你选的 {count} 个景点分布在 {n} 个城市（{cities}）",
            count=len(rows), n=len(cities), cities=_join_list(t(city) for city in cities),
        ),
        "detail": t("最远两城直线相距 {km} 公里，{days} 天要来回跑", km=km, days=days),
        "suggestion": suggestion,
    }]


def _selection_dense(rows, days) -> list[dict]:
    """景点数 > days×3：跑不完，报密集。"""
    limit = days * SELECTION_ATTRACTIONS_PER_DAY
    if len(rows) <= limit:
        return []
    extra = len(rows) - limit
    if days < MAX_DAYS:
        suggestion = t("删掉 {n} 个景点，或把天数加到 {days} 天", n=extra, days=days + 1)
    else:
        suggestion = t("删掉 {n} 个景点", n=extra)
    return [{
        "code": "selection_too_dense",
        "severity": "medium",
        "title": t("{days} 天要跑 {count} 个景点，平均每天 {rate} 个",
                   days=days, count=len(rows), rate=_money(len(rows) / days)),
        "detail": t("按每天 {per_day} 个的上限，{days} 天最多安排 {cap} 个。",
                    per_day=SELECTION_ATTRACTIONS_PER_DAY, days=days, cap=limit),
        "suggestion": suggestion,
    }]


def _selection_tickets(rows, budget) -> list[dict]:
    """门票合计 > 预算的一半（且预算 > 0）：还没算吃住就已经吃掉一半预算。"""
    budget_value = _num(budget, 0)
    if budget_value <= 0:
        return []
    tickets = sum(row["price"] for row in rows)
    if tickets <= budget_value * SELECTION_TICKET_SHARE:
        return []
    return [{
        "code": "selection_tickets_heavy",
        "severity": "medium",
        "title": t("门票合计 ¥{total}，超过预算 ¥{budget} 的一半",
                   total=_money(tickets), budget=_money(budget_value)),
        "detail": t("预算 ¥{budget}，门票已占 ¥{total}，剩下还要覆盖交通、住宿和餐饮。",
                    budget=_money(budget_value), total=_money(tickets)),
        "suggestion": t("留 1–2 个收费景点，其余换成免费的"),
    }]


def _empty_precheck() -> dict:
    return {"cities": [], "count": 0, "conflicts": []}


def precheck_selection(attractions, days, budget=0) -> dict:
    """选择阶段预检：城市跨度 / 景点密度 / 门票占比。

    attractions 是端点已经查好的 Attraction 列表（也接受同形字典，便于测试）；
    纯本地、不写库、不调外部服务，任何异常都返回空结果，绝不 500。
    """
    empty = _empty_precheck()
    try:
        if isinstance(days, bool):
            return empty
        try:
            day_count = int(days)
        except (TypeError, ValueError):
            return empty
        if not 1 <= day_count <= MAX_DAYS:
            return empty

        rows = _attraction_rows(attractions)
        if len(rows) < SELECTION_MIN_PICKS:
            return empty

        cities = list(dict.fromkeys(row["city"] for row in rows if row["city"]))
        coords = _city_coords()
        aliases = _city_aliases(coords)

        conflicts: list[dict] = []
        conflicts.extend(_selection_cross_city(rows, cities, day_count, coords, aliases))
        conflicts.extend(_selection_dense(rows, day_count))
        conflicts.extend(_selection_tickets(rows, budget))
        return {"cities": cities, "count": len(conflicts), "conflicts": conflicts}
    except Exception:
        return empty


# ---------------------------------------------------------------- 预算沙盘
def _hotel_rate(hotel_price, lodging) -> float:
    """hotel_price 优先；否则取 lodging 文本里第一个 ¥/元 数字；都没有按 300 兜底。"""
    price = _num(hotel_price, 0)
    if price > 0:
        return min(price, MAX_HOTEL_PRICE)
    match = re.search(r"[¥￥]\s*([\d,]+(?:\.\d+)?)|([\d,]+(?:\.\d+)?)\s*元", _text(lodging))
    if match:
        value = _num((match.group(1) or match.group(2) or "").replace(",", ""), 0)
        if value > 0:
            return min(value, MAX_HOTEL_PRICE)
    return DEFAULT_HOTEL_PRICE


def _empty_budget(people=2, budget=0) -> dict:
    budget_value = int(round(_num(budget, 0)))
    return {
        "people": _people_count(people),
        "total_per_person": 0,
        "total_all": 0,
        "items": [],
        "cuts": [],
        "compare": {
            "budget": budget_value,
            "delta": 0,
            "status": "unknown" if budget_value <= 0 else "under",
        },
    }


def _budget_core(normalised, people, budget, start_date, hotel_price, lodging, coords, prices) -> dict:
    """预算主体。start_date 按契约收下，当前算法不需要它，保留占位。"""
    del start_date
    days_count = len(normalised)

    # 门票：同一天同景点去重；跨天重复入园照算（确实要再买一次）
    ticket_total = 0.0
    ticket_parts: list[tuple[str, float]] = []
    for day in normalised:
        seen = set()
        for slot in day["slots"]:
            slug = _text(slot.get("slug")).strip()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            info = prices.get(slug)
            if info is None:
                continue
            name, price = info
            ticket_total += price
            ticket_parts.append((name, price))

    # 住宿
    nightly = _hotel_rate(hotel_price, lodging)
    nights = max(0, days_count - 1)
    if _text(lodging) and any(keyword in _text(lodging).lower() for keyword in _NO_STAY_KEYWORDS):
        nights = 0
    lodging_cost = nightly * nights

    # 交通：城际 + 市内
    aliases = _city_aliases(coords)
    day_cities = [_day_city(day["slots"]) for day in normalised]
    intercity = 0.0
    intercity_km = 0.0
    for previous, current in zip(day_cities, day_cities[1:]):
        if not previous or not current:
            continue
        if previous == current:
            intercity += SAME_CITY_TRANSFER
            continue
        key_a = _resolve_city(previous, aliases)
        key_b = _resolve_city(current, aliases)
        if not key_a or not key_b:
            continue  # 查不到坐标就不算这一段，不编造
        distance = _haversine(*coords[key_a], *coords[key_b])
        intercity_km += distance
        intercity += distance * CITY_TRANSFER_RATE
    local_transport = LOCAL_TRANSPORT_PER_DAY * days_count
    transport_total = intercity + local_transport

    # 餐饮
    meal_total = MEAL_PER_DAY * days_count

    subtotal = ticket_total + lodging_cost + transport_total + meal_total
    other_total = subtotal * OTHER_RATE

    # 分项取整后合计，保证 items 之和 == total_per_person（前端可放心累加）
    ticket_value = int(round(ticket_total))
    lodging_value = int(round(lodging_cost))
    transport_value = int(round(transport_total))
    meal_value = int(round(meal_total))
    other_value = int(round(other_total))
    total_per_person = ticket_value + lodging_value + transport_value + meal_value + other_value

    people_count = _people_count(people)
    total_all = total_per_person * people_count

    # ---- items ----
    paid_parts = [(name, price) for name, price in ticket_parts if price > 0]
    if paid_parts:
        names = [f"{name} {int(round(price))}" for name, price in paid_parts[:_MAX_TICKET_NAMES]]
        ticket_detail = " + ".join(names)
        if len(paid_parts) > _MAX_TICKET_NAMES:
            ticket_detail = f"{ticket_detail} {t('等 {n} 个景点', n=len(paid_parts) - _MAX_TICKET_NAMES)}"
    else:
        ticket_detail = t("本次行程无收费景点")

    if intercity_km > 0:
        transport_detail = t(
            "城际 ¥{intercity}（约 {km} 公里）+ 市内 ¥{local}/人",
            intercity=_money(intercity), km=int(round(intercity_km)), local=_money(local_transport),
        )
    else:
        transport_detail = t(
            "城际 ¥{intercity} + 市内 ¥{local}/人",
            intercity=_money(intercity), local=_money(local_transport),
        )

    items = [
        {"key": "ticket", "label": t("门票"), "per_person": ticket_value, "detail": ticket_detail},
        {"key": "hotel", "label": t("住宿"), "per_person": lodging_value,
         "detail": t("{nights_text} × ¥{price}/晚", nights_text=_nights_text(nights), price=_money(nightly))},
        {"key": "transport", "label": t("交通"), "per_person": transport_value, "detail": transport_detail},
        {"key": "meal", "label": t("餐饮"), "per_person": meal_value,
         "detail": t("{days} 天 × ¥{rate}/人/天", days=days_count, rate=_money(MEAL_PER_DAY))},
        {"key": "other", "label": t("其他"), "per_person": other_value, "detail": t("以上合计的 8%")},
    ]

    # ---- cuts：至少 2 条可执行削减建议，数字全部由本行程算出 ----
    cuts: list[dict] = []
    paid = [(name, price) for name, price in ticket_parts if price > 0]
    if paid:
        name, price = max(paid, key=lambda item: item[1])
        cuts.append({
            "label": t("舍掉「{name}」门票，省 ¥{money}", name=name, money=_money(price)),
            "saving": int(round(price)),
        })
    if lodging_value > 0 and nights > 0:
        step = 100
        saving = min(step * nights, lodging_value)
        cuts.append({
            "label": t("换每晚便宜 ¥{step} 的住处，{nights_text}共省 ¥{saving}",
                       step=step, nights_text=_nights_text(nights), saving=_money(saving)),
            "saving": int(round(saving)),
        })
    if meal_value > 0:
        per_day = 30
        cuts.append({
            "label": t("午餐改简餐，每天省 ¥{per_day}", per_day=per_day),
            "saving": int(round(per_day * days_count)),
        })
    if transport_value > 0:
        per_day = 20
        cuts.append({
            "label": t("少打车、多坐公交，每天省 ¥{per_day}", per_day=per_day),
            "saving": int(round(per_day * days_count)),
        })

    # ---- compare ----
    budget_value = int(round(_num(budget, 0)))
    if budget_value > 0:
        delta = total_per_person - budget_value
        status = "under" if delta < 0 else ("over" if delta > 0 else "even")
    else:
        delta = 0
        status = "unknown"  # 没填预算就不下结论，前端据此隐藏对比条

    return {
        "people": people_count,
        "total_per_person": total_per_person,
        "total_all": total_all,
        "items": items,
        "cuts": cuts,
        "compare": {"budget": budget_value, "delta": delta, "status": status},
    }


def build_budget(days, people=2, budget=0, start_date="", hotel_price=0, lodging="") -> dict:
    """行程预算沙盘。纯函数：不改入参、不写库、任何异常返回空结果。"""
    empty = _empty_budget(people, budget)
    try:
        normalised = _normalise_days(days)
        if not normalised:
            return empty
        return _budget_core(
            normalised,
            people=people,
            budget=budget,
            start_date=start_date,
            hotel_price=hotel_price,
            lodging=lodging,
            coords=_city_coords(),
            prices=_attraction_prices(normalised),
        )
    except Exception:
        return empty
