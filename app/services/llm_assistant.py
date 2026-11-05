"""DeepSeek 工具调用调度：导航、搜索、天气、景点事实、行程。

只读，不写数据。没有配置 AI_API_KEY 或调用失败时返回 None，由规则引擎兜底。
"""
import json
import re
from contextvars import ContextVar

import requests
from flask import current_app
from sqlalchemy import and_, or_

from ..extensions import db
from ..i18n import attr_field, city_label, current_lang, price_text, t
from ..models import Attraction, AttractionTranslation
from .assistant import _find_attraction, _published
from .itinerary import generate_itinerary
from .itinerary_analysis import build_budget, detect_conflicts
from .weather import build_advice, get_weather

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "navigate",
            "description": "Open a page in the site. Use only the allowed paths.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "e.g. /attractions, /itinerary, /attractions/huangguoshu"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_attractions",
            "description": "Search published attractions by keyword and/or category. Results are sorted by rating, highest first, and include each rating value.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "category": {"type": "string", "enum": ["自然", "人文", "红色", "科技", "季节", "nature", "culture", "red", "technology", "seasonal"]},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get current weather and 3-day forecast for an attraction.",
            "parameters": {
                "type": "object",
                "properties": {"attraction_id": {"type": "integer"}},
                "required": ["attraction_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_attraction_fact",
            "description": "Look up one fact about an attraction: ticket, hours, address, duration, months, rating, summary.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "field": {"type": "string", "enum": ["ticket", "hours", "address", "duration", "months", "rating", "summary"]},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_conflicts",
            "description": (
                "Review the itinerary the user is currently looking at and report conflicts "
                "(cross-city day, overlapping slots, over-packed day, missing return trip, over budget). "
                "Only works when an itinerary has already been generated on the page."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "estimate_budget",
            "description": (
                "Estimate the per-person budget of the itinerary the user is currently looking at "
                "(transport, tickets, lodging, meals, contingency) and compare it with their budget. "
                "Only works when an itinerary has already been generated on the page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "people": {"type": "integer", "description": "Number of travellers, 1-8"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "plan_itinerary",
            "description": "Build a day-by-day itinerary. Optionally pass attraction ids; otherwise pick top-rated ones.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "minimum": 1, "maximum": 5},
                    "attraction_ids": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["days"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are the Guizhou Tourism assistant. Use tools for facts and navigation; never invent prices, hours or locations. "
    "Only published attractions are available. If the user wants to go somewhere, call navigate with an allowed path. "
    "If they ask for the best or highest-rated attraction, call search_attractions (results are already sorted by rating) "
    "and navigate to that attraction's /attractions/<slug> path. "
    "If they ask for a plan, call plan_itinerary. After tool results, answer in 1-3 short sentences in the user's language. "
    "Only call the tools listed in the schema; never invent tool names or write tool-call syntax into your reply. "
    "If a tool returns ok:false, say you could not find it; never guess a value. "
    "Do not mention hotel counts or room rates unless the user explicitly asks; if asked, say lodging options are on the attraction page. "
    "Do not mention tool names or JSON. Allowed paths: /, /attractions, /attractions/<slug>, /itinerary, /profile, /orders, /booking/<id>."
)

TOOL_MARKUP = re.compile(r"<[|｜]{0,2}DSML[|｜]{0,2}")

MAX_TOOL_ROUNDS = 3

VALID_BASE = {"/", "/attractions", "/itinerary", "/profile", "/orders"}
CATEGORY_MAP = {
    "nature": "自然", "natural": "自然",
    "culture": "人文", "humanity": "人文",
    "red": "红色", "red-culture": "红色",
    "technology": "科技", "science": "科技",
    "seasonal": "季节", "season": "季节",
    "自然": "自然", "人文": "人文", "红色": "红色", "红色文化": "红色文化", "科技": "科技", "季节": "季节",
}
CATEGORY_VALUES = {"自然", "人文", "红色", "红色文化", "科技", "季节"}


def llm_available():
    return bool(current_app.config.get("AI_API_KEY")) and bool(current_app.config.get("AI_BASE_URL"))


def _valid_path(path):
    if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
        return False
    base = path.split("?", 1)[0]
    if base in VALID_BASE:
        return True
    if re.fullmatch(r"/attractions/[a-z0-9\-]+", base):
        return True
    return bool(re.fullmatch(r"/booking/\d+", base))


def _tool_navigate(args):
    path = str(args.get("path") or "").strip()
    if not _valid_path(path):
        return {"ok": False, "error": "path not allowed"}
    return {"ok": True, "url": path}


def _tool_search(args):
    query = Attraction.query.filter_by(status="published")
    text = str(args.get("query") or "").strip()
    category = args.get("category")
    category = CATEGORY_MAP.get(category, category)
    if category in CATEGORY_VALUES:
        query = query.filter(Attraction.category.startswith(category, autoescape=True))
    if text:
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        like = f"%{escaped}%"
        query = query.filter(or_(
            Attraction.name.ilike(like, escape="\\"),
            Attraction.summary.ilike(like, escape="\\"),
            Attraction.description.ilike(like, escape="\\"),
            Attraction.slug.ilike(like, escape="\\"),
            Attraction.translations.any(and_(
                AttractionTranslation.lang == "en",
                or_(
                    AttractionTranslation.name.ilike(like, escape="\\"),
                    AttractionTranslation.summary.ilike(like, escape="\\"),
                ),
            )),
        ))
    rows = query.order_by(Attraction.rating.desc()).limit(5).all()
    items = [
        {"id": row.id, "name": attr_field(row, "name"), "slug": row.slug,
         "city": city_label(row.city), "category": t(row.category), "price": price_text(row),
         "rating": float(row.rating or 0)}
        for row in rows
    ]
    return {"ok": True, "items": items, "count": len(items)}


def _tool_weather(args):
    attraction_id = args.get("attraction_id")
    if isinstance(attraction_id, bool) or not isinstance(attraction_id, int):
        return {"ok": False, "error": "invalid attraction_id"}
    attraction = db.session.get(Attraction, attraction_id)
    if attraction is None or attraction.status != "published":
        return {"ok": False, "error": "attraction not found"}
    weather = get_weather(attraction.city or "", attraction.weather_code)
    if not weather:
        return {"ok": False, "error": "weather unavailable"}
    live = weather.get("live") or {}
    return {
        "ok": True,
        "name": attr_field(attraction, "name"),
        "city": city_label(attraction.city),
        "live": {"weather": live.get("text", ""), "temp": live.get("temp", ""), "humidity": live.get("humidity", "")},
        "forecast": [
            {"date": day.get("fxDate", ""), "day": day.get("textDay", ""), "night": day.get("textNight", ""),
             "max": day.get("tempMax", ""), "min": day.get("tempMin", "")}
            for day in (weather.get("forecast") or [])[:3]
        ],
        "advice": build_advice(live),
    }


def _tool_fact(args):
    text = str(args.get("name") or "").strip()
    attraction = _find_attraction(text, _published()) if text else None
    if attraction is None:
        return {"ok": False, "error": "attraction not found"}
    field = args.get("field") or "summary"
    if field == "ticket":
        value = price_text(attraction)
    elif field == "hours":
        value = attr_field(attraction, "open_time")
    elif field == "address":
        value = attr_field(attraction, "address")
    elif field == "duration":
        value = f"{attraction.visit_duration / 60:.1f} {t('小时')}" if attraction.visit_duration else ""
    elif field == "months":
        value = attr_field(attraction, "best_months")
    elif field == "rating":
        value = f"{attraction.rating_label}/5 ({attraction.rating_count or 0})"
    else:
        value = attr_field(attraction, "summary")
    return {"ok": True, "name": attr_field(attraction, "name"), "field": field, "value": value}


def _tool_plan(args):
    days = args.get("days")
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 5:
        days = 3
    ids = args.get("attraction_ids") or []
    selections = []
    if isinstance(ids, list):
        for value in ids[:8]:
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            attraction = db.session.get(Attraction, value)
            if attraction is not None and attraction.status == "published":
                selections.append(attraction)
    if not selections:
        selections = Attraction.query.filter_by(status="published").order_by(Attraction.rating.desc()).limit(days * 2).all()
    if not selections:
        return {"ok": False, "error": "no attractions"}
    plan = generate_itinerary(selections, days)
    links, seen = [], set()
    for day in plan:
        for slot in ("morning", "afternoon"):
            item = day.get(slot)
            if item and item["slug"] not in seen:
                seen.add(item["slug"])
                links.append({"name": item["name"], "url": f"/attractions/{item['slug']}"})
    return {"ok": True, "days": plan, "links": links}


def _tool_conflicts(args):
    ctx = _CTX.get() or {}
    days = ctx.get("days") or []
    if not days:
        return {"ok": False, "error": "no itinerary on the page yet"}
    result = detect_conflicts(days, ctx.get("budget") or 0)
    store = _STRUCT.get()
    if store is not None:
        store["conflicts"] = result
    items = result.get("conflicts") or []
    return {
        "ok": True,
        "count": int(result.get("count") or 0),
        "high": sum(1 for item in items if item.get("severity") == "high"),
        "titles": [item.get("title") for item in items[:5]],
    }


def _tool_budget(args):
    ctx = _CTX.get() or {}
    days = ctx.get("days") or []
    if not days:
        return {"ok": False, "error": "no itinerary on the page yet"}
    # 页面上的出行人数是准的，优先用它；模型只能在没有上下文时自己给
    try:
        people = int(ctx.get("people") or args.get("people") or 2)
    except (TypeError, ValueError):
        people = 2
    people = max(1, min(people, 8))
    result = build_budget(
        days,
        people=people,
        budget=ctx.get("budget") or 0,
        start_date=ctx.get("start_date") or "",
        hotel_price=ctx.get("hotel_price") or 0,
    )
    store = _STRUCT.get()
    if store is not None:
        store["budget"] = result
    compare = result.get("compare") or {}
    return {
        "ok": True,
        "people": result.get("people") or people,
        "total_per_person": result.get("total_per_person"),
        "total_all": result.get("total_all"),
        "budget": compare.get("budget"),
        "delta": compare.get("delta"),
        "status": compare.get("status"),
        "items": [
            {"label": item.get("label"), "per_person": item.get("per_person")}
            for item in (result.get("items") or [])
        ],
    }


TOOL_HANDLERS = {
    "navigate": _tool_navigate,
    "search_attractions": _tool_search,
    "get_weather": _tool_weather,
    "get_attraction_fact": _tool_fact,
    "plan_itinerary": _tool_plan,
    "check_conflicts": _tool_conflicts,
    "estimate_budget": _tool_budget,
}


def run_tool(name, args):
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return {"ok": False, "error": "unknown tool"}
    try:
        return handler(args or {})
    except Exception:
        return {"ok": False, "error": "tool failed"}


def _chat(messages, tool_choice="auto"):
    base = (current_app.config.get("AI_BASE_URL") or "").rstrip("/")
    if not base or not current_app.config.get("AI_API_KEY"):
        return None
    payload = {
        "model": current_app.config.get("AI_MODEL", "deepseek-chat"),
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": tool_choice,
        "temperature": 0.2,
        "max_tokens": 600,
    }
    try:
        response = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {current_app.config['AI_API_KEY']}", "Content-Type": "application/json"},
            json=payload,
            timeout=int(current_app.config.get("AI_TIMEOUT", 15)),
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


_CTX = ContextVar("assistant_ctx", default=None)
_STRUCT = ContextVar("assistant_struct", default=None)


def _result(reply, action, links):
    return {"reply": reply, "intent": "llm", "action": action, "confidence": 0.9, "links": links}


def _content(data):
    try:
        message = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return None, ""
    return message, (message.get("content") or "").strip()


def _finalize(messages, msg, action, links):
    """收尾：模型偶尔会把工具调用语法写进正文，要求它用纯文本重答一次。"""
    reply = (msg.get("content") or "").strip()
    if not reply:
        return None
    if not TOOL_MARKUP.search(reply):
        return _result(reply, action, links)
    messages.append({"role": "assistant", "content": reply})
    messages.append({
        "role": "system",
        "content": "Do not output tool-call markup or invent tools. Reply to the user in plain text, 1-3 sentences.",
    })
    msg, reply = _content(_chat(messages, tool_choice="none"))
    reply = (reply or "").strip()
    if msg is None or not reply or TOOL_MARKUP.search(reply):
        return None
    return _result(reply, action, links)


def answer_with_llm(message, user=None, context=None):
    if not llm_available():
        return None
    if context is not None:
        _CTX.set(context)
        _STRUCT.set({})
        # 页面上已经有行程时明确告诉模型，否则它会反问「你有行程吗」，白白多一轮
        system_hint = (
            "\nThe user already has a generated itinerary open on the page (attached as context). "
            "When they ask about budget or conflicts, call estimate_budget or check_conflicts right away "
            "and do not ask whether an itinerary exists."
        )
    else:
        system_hint = ""
    system = (
        SYSTEM_PROMPT
        + system_hint
        + f"\nReply in {'English' if current_lang() == 'en' else 'Chinese'}."
    )
    messages = [{"role": "system", "content": system}, {"role": "user", "content": message}]
    action, links = None, []

    for _ in range(MAX_TOOL_ROUNDS):
        msg, _ = _content(_chat(messages))
        if msg is None:
            return None
        calls = msg.get("tool_calls") or []
        if not calls:
            payload = _finalize(messages, msg, action, links)
            if isinstance(payload, dict) and context is not None:
                payload["structured"] = _STRUCT.get() or {}
            return payload

        messages.append({"role": "assistant", "content": msg.get("content") or None, "tool_calls": calls})
        for call in calls:
            function = call.get("function") or {}
            name = function.get("name")
            raw = function.get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except json.JSONDecodeError:
                args = {}
            result = run_tool(name, args)
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id"),
                "content": json.dumps(result, ensure_ascii=False),
            })
            if name == "navigate" and result.get("ok"):
                action = {"type": "navigate", "url": result["url"]}
            elif name == "search_attractions" and result.get("items"):
                links = [{"name": item["name"], "url": f"/attractions/{item['slug']}"} for item in result["items"]]
            elif name == "plan_itinerary" and result.get("links"):
                links = result["links"]

    # 轮次用尽仍在调工具：强制一次纯文本收尾，避免整段结果被丢弃
    msg, _ = _content(_chat(messages, tool_choice="none"))
    if msg is None:
        return None
    return _finalize(messages, msg, action, links)
