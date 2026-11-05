"""用 DeepSeek 生成完整行程规划（出发点 / 是否住宿 / 天数 / 出发时间 / 预算 / 景点）。

会先查和风天气与小红书笔记，再把事实塞进提示词；没有 key、超时或返回不合法时返回 None，
由调用方回退到规则草案。只读调用，不写库。
"""
from __future__ import annotations

import json
import time

import requests
from flask import current_app, has_app_context

from ..i18n import attr_field, city_label, current_lang, price_text
from .weather import build_advice, get_weather
from .xhs import notes_for_attractions

SYSTEM_PROMPT = """你是资深贵州本地行程规划师。根据用户给的出发点、是否安排住宿、天数、出发时间、人均预算、
天气事实和候选景点，输出一份可直接落地的行程。要求：
1. 严格输出 JSON，不要任何解释文字、不要 markdown 代码块。
2. 只能从候选景点里选，不能编造不存在的景点；slug 必须原样使用候选里给的值。
3. 按地理位置和动线安排，同一天尽量在相近城市；每天 2-3 个景点，留出交通时间。
4. 雨天把户外景点往后排或给替代方案；天气事实只能引用给定数据，不要自己编。
5. 每个时间段的 detail 不超过 40 个字，写具体动作（几点出发、吃什么、怎么走）。
6. slug 只在该时段确实是「参观这个景点」时填写；吃饭、交通、休息、返程这类活动一律填空字符串 ""。
7. 住宿：只有用户明确说「不需要」才写「当日往返、不安排住宿」；只要用户选了「需要住宿」，
   哪怕只玩 1 天也要安排当晚住宿（住一晚、次日上午返程），lodging 必须写明城市/片区、价位档
   和大致房价，budget_plan 里必须有住宿一项，不能写「当日往返」。
8. 预算：交通 + 门票 + 住宿 + 餐饮 + 机动，各项合计要贴近用户给的人均预算，超了就说明取舍。
9. 用简体中文（若要求英文则用英文）。
JSON 结构：
{"summary":"一句话总览",
 "transport":"出发推荐方式（自驾/高铁/包车 + 大致耗时与理由）",
 "route":["途经城市或路段 1","途经城市或路段 2"],
 "weather":"行程期间的天气概况（引用给定事实）",
 "clothing":"穿衣与随身物品建议",
 "lodging":"住宿安排（需要住宿：城市/片区 + 价位档 + 大致房价；不需要：当日往返）",
 "budget_plan":[{"item":"交通","amount":"约 ￥300"},{"item":"门票","amount":"￥220"}],
 "days":[{"day":1,"theme":"当天主题","slots":[{"period":"上午","title":"景点或活动名","slug":"该景点的 slug","detail":"具体安排"}],"tips":"当天提醒"}],
 "notes":["整体提醒"]}
"""


def _config(name, default=None):
    if has_app_context():
        value = current_app.config.get(name)
        if value:
            return value
    return default


def _candidate_line(attraction) -> dict:
    return {
        "slug": attraction.slug,
        "name": attr_field(attraction, "name"),
        "city": city_label(attraction.city),
        "price": price_text(attraction),
        "open_time": attr_field(attraction, "open_time"),
        "hours": round((attraction.visit_duration or 0) / 60, 1),
        "rating": float(attraction.rating or 0),
        "summary": (attr_field(attraction, "summary") or "")[:60],
    }


def _weather_facts(attractions, limit: int = 3) -> list[dict]:
    """按候选景点所在城市去重查天气，最多 3 个城市，失败跳过。"""
    seen, facts = set(), []
    for attraction in attractions:
        key = (attraction.city or "") + "|" + (attraction.weather_code or "")
        if key in seen or len(facts) >= limit:
            continue
        seen.add(key)
        try:
            data = get_weather(attraction.city or "", attraction.weather_code)
        except Exception:
            data = None
        if not data or not data.get("live"):
            continue
        live = data["live"]
        forecast = [
            {
                "日期": item.get("fxDate"),
                "白天": item.get("textDay"),
                "夜间": item.get("textNight"),
                "气温": f"{item.get('tempMin')}~{item.get('tempMax')}℃",
            }
            for item in (data.get("forecast") or [])[:3]
        ]
        facts.append({
            "城市": data.get("city") or city_label(attraction.city),
            "实况": f"{live.get('text')} {live.get('temp')}℃ 湿度{live.get('humidity')}% 风{live.get('windDir')}{live.get('windScale')}级",
            "未来三天": forecast,
            "建议": build_advice(live),
        })
    return facts


def _build_messages(attractions, days, origin, need_stay, start_date, budget, xhs_notes=None, weather=None) -> list[dict]:
    language = "英文" if current_lang() == "en" else "简体中文"
    facts = {
        "语言": language,
        "出发点": origin or "未提供",
        "是否需要安排住宿": "需要" if need_stay else "不需要（当日往返或自行解决）",
        "天数": days,
        "出发时间": start_date or "未指定",
        "人均预算": f"{budget} 元" if budget else "未提供",
        "候选景点": [_candidate_line(item) for item in attractions],
    }
    if weather:
        facts["天气事实（和风实时，只能引用这些）"] = weather
    if xhs_notes:
        facts["小红书游客笔记（可引用其中的机位、避坑、时间经验，写进 detail 或 tips，不要整段照抄）"] = [
            {"景点": note.get("name", ""), "标题": note.get("title", ""), "内容": note.get("body", "")}
            for note in xhs_notes[:6]
        ]
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(facts, ensure_ascii=False)},
    ]


def _post(messages, max_tokens: int = 1600) -> dict | None:
    base = (_config("AI_BASE_URL") or "").rstrip("/")
    key = _config("AI_API_KEY")
    if not base or not key:
        return None
    payload = {
        "model": _config("AI_MODEL", "deepseek-chat"),
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        response = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=max(int(_config("AI_TIMEOUT", 15)), 45),
        )
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _normalize(data, attractions, days) -> dict | None:
    if not isinstance(data, dict):
        return None
    by_slug = {item.slug: item for item in attractions}
    names = {item.slug: attr_field(item, "name") for item in attractions}
    cities = {item.slug: city_label(item.city) for item in attractions}

    raw_days = data.get("days")
    if not isinstance(raw_days, list) or not raw_days:
        return None

    result = []
    for index, raw in enumerate(raw_days[:days], start=1):
        if not isinstance(raw, dict):
            continue
        slots = []
        for raw_slot in raw.get("slots") or []:
            if not isinstance(raw_slot, dict):
                continue
            slug = str(raw_slot.get("slug") or "").strip()
            title = str(raw_slot.get("title") or "").strip()[:40]
            if slug and slug in by_slug:
                # 只校验 slug 有效；标题保留模型写的动作描述，空了才回落到景点名
                title = title or names[slug]
            else:
                slug = ""
            if not title:
                continue
            slots.append({
                "period": str(raw_slot.get("period") or "").strip()[:6] or "自由安排",
                "title": title,
                "slug": slug,
                "city": cities.get(slug, ""),
                "detail": str(raw_slot.get("detail") or "").strip()[:80],
            })
        if not slots:
            continue
        result.append({
            "day": int(raw.get("day") or index),
            "theme": str(raw.get("theme") or "").strip()[:40],
            "slots": slots,
            "tips": str(raw.get("tips") or "").strip()[:120],
        })

    if not result:
        return None
    notes = [str(item).strip()[:120] for item in (data.get("notes") or []) if str(item).strip()][:4]
    route = [str(item).strip()[:60] for item in (data.get("route") or []) if str(item).strip()][:5]
    budget_plan = []
    for item in (data.get("budget_plan") or [])[:6]:
        if isinstance(item, dict) and item.get("item"):
            budget_plan.append({
                "item": str(item.get("item")).strip()[:20],
                "amount": str(item.get("amount") or "").strip()[:20],
            })
    return {
        "summary": str(data.get("summary") or "").strip()[:200],
        "transport": str(data.get("transport") or "").strip()[:160],
        "route": route,
        "weather": str(data.get("weather") or "").strip()[:160],
        "clothing": str(data.get("clothing") or "").strip()[:120],
        "lodging": str(data.get("lodging") or "").strip()[:160],
        "budget_plan": budget_plan,
        "days": result,
        "notes": notes,
    }


def _ask(attractions, days, origin, need_stay, start_date, budget, xhs_notes, weather):
    """调一次模型并解析；JSON 不合法/结构不对就返回 None。"""
    data = _post(_build_messages(attractions, days, origin, need_stay, start_date, budget,
                                 xhs_notes, weather))
    if not data:
        return None
    choices = data.get("choices") or []
    if not choices:
        return None
    content = ((choices[0].get("message") or {}).get("content") or "").strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    try:
        parsed = json.loads(content)
    except ValueError:
        return None
    return _normalize(parsed, attractions, days)


def plan_with_llm(attractions, days, origin="", need_stay=True, start_date="", budget=0):
    """返回 {"summary","transport","route","weather","clothing","lodging","budget_plan","days","notes","source":"ai","xhs":{...}} 或 None。

    模型偶尔会返回夹带文字的 JSON，解析失败时重试一次；仍失败交给调用方回退规则草案。
    """
    started = time.monotonic()
    xhs = notes_for_attractions(attractions, per_attraction=1, max_total=6)
    weather = _weather_facts(attractions)

    normalized = None
    for _ in range(2):
        normalized = _ask(attractions, days, origin, need_stay, start_date, budget,
                          xhs["notes"], weather)
        if normalized is not None:
            break
    if normalized is None:
        return None

    normalized["source"] = "ai"
    normalized["latency_ms"] = int((time.monotonic() - started) * 1000)
    normalized["xhs"] = {
        "source": xhs["source"],
        "status": xhs["status"],
        "count": len(xhs["notes"]),
        "titles": [note.get("title", "") for note in xhs["notes"][:3]],
    }
    normalized["weather_source"] = "qweather" if weather else "none"
    return normalized


# ---------------- 已保存行程的翻译 ----------------

TRANSLATE_PROMPT = """你是翻译助手。把用户给的行程 JSON 翻译成{target}。
规则：
1. 只翻译给人看的文本：summary / transport / weather / clothing / lodging / route / notes /
   budget_plan[].item / days[].theme / days[].tips / days[].slots[].period / days[].slots[].title / days[].slots[].detail /
   conflicts[].title / conflicts[].detail。
2. 绝不能改动：slug、days[].day 的数字、预算里的金额与货币符号、百分比、日期。
3. period 统一译成 {period}。
4. 结构必须与输入完全一致，严格输出 JSON，不要任何解释文字或代码块。"""


def _translate_strings(texts: list[str], target: str = "en") -> list[str] | None:
    """把一组短文本翻成目标语言。返回等长列表，失败返回 None。"""
    if not texts:
        return []
    is_en = target == "en"
    body = _post(
        [
            {
                "role": "system",
                "content": (
                    "你是翻译助手。把用户给的 JSON 字符串数组逐条翻译成"
                    + ("英文" if is_en else "简体中文")
                    + "，保持顺序与条数不变，不要合并、不要增删。"
                    "只输出 JSON 数组，不要任何解释。"
                ),
            },
            {"role": "user", "content": json.dumps(texts, ensure_ascii=False)},
        ],
        max_tokens=900,
    )
    if not body:
        return None
    try:
        content = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    except (AttributeError, IndexError, TypeError):
        return None
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    try:
        parsed = json.loads(content)
    except ValueError:
        return None
    if not isinstance(parsed, list) or len(parsed) != len(texts):
        return None
    return [str(item) for item in parsed]


def translate_conflicts(conflicts, target: str):
    """冲突文案单独翻一次：结构与 rules 引擎产出的一致，只动 title/detail/suggestion。"""
    if not isinstance(conflicts, dict):
        return conflicts
    items = conflicts.get("conflicts")
    if not isinstance(items, list) or not items:
        return conflicts

    texts = []
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("title", "detail", "suggestion"):
            value = str(item.get(key) or "").strip()
            if value:
                texts.append(value)
    if not texts:
        return conflicts

    translated = _translate_strings(texts, target)
    if translated is None:
        return conflicts

    out = []
    index = 0
    for item in items:
        if not isinstance(item, dict):
            out.append(item)
            continue
        copy = dict(item)
        for key in ("title", "detail", "suggestion"):
            if str(item.get(key) or "").strip():
                copy[key] = translated[index]
                index += 1
        out.append(copy)
    result = dict(conflicts)
    result["conflicts"] = out
    return result


def translate_plan(plan: dict, target: str = "en") -> dict | None:
    """把已保存的行程（brief + days）整体翻译。失败返回 None，调用方保留原文。"""
    if not isinstance(plan, dict):
        return None
    payload = {"brief": plan.get("brief") or {}, "days": plan.get("days") or []}
    if not payload["brief"] and not payload["days"]:
        return None

    is_en = target == "en"
    system = TRANSLATE_PROMPT.format(
        target="英文" if is_en else "简体中文",
        period="Morning / Afternoon / Evening" if is_en else "上午 / 下午 / 晚上",
    )
    body = _post(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        max_tokens=2600,
    )
    if not body:
        return None
    try:
        choices = body.get("choices") or []
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
    except (AttributeError, IndexError, TypeError):
        return None
    if not content:
        return None
    if content.startswith("```"):
        content = content.strip("`")
        if content.lower().startswith("json"):
            content = content[4:]
    try:
        parsed = json.loads(content)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    brief = parsed.get("brief") if isinstance(parsed.get("brief"), dict) else {}
    days = parsed.get("days") if isinstance(parsed.get("days"), list) else []

    # 模型经常整段丢掉 conflicts（结构嵌套），单独翻一次补上
    source_conflicts = ((plan.get("brief") or {}).get("conflicts"))
    if source_conflicts:
        brief["conflicts"] = translate_conflicts(source_conflicts, target)

    return {"brief": brief, "days": days}
