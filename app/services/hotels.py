"""住宿推荐：经 RollingGo 公共 MCP 代理查真实在售房价。

设计原则（与 weather.py / xhs.py 一致）：
- 只做「加分项」：任何异常都返回 None，绝不让行程生成失败；
- 代理是第三方公共服务，随时可能挂掉或限流，所以必须有超时 + 缓存 + 降级；
- 只透出能验证的字段（名字/星级/价格/地址/图片/预订链接），不做二次包装或夸大。

数据获取方式就是一次 JSON-RPC POST（tools/call → searchHotels），
不需要 mcp SDK，也不需要任何 API Key。
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import requests
from flask import current_app, has_app_context

from ..i18n import EN, current_lang, t


DEFAULT_PROXY = "https://rollinggo-proxy-oekjonytob.cn-hangzhou.fcapp.run"

# 房价变动以小时计，缓存 3 小时内复用即可
CACHE_TTL_SECONDS = 3 * 60 * 60
FAIL_TTL_SECONDS = 60
# 查不到（代理超时/限流/无房源）只压 60 秒：
# 否则一次网络抖动会让这个城市连续 3 小时都拿不到酒店
CACHE_FILE = "hotel_cache.json"

# 只允许展示这些域下的外部链接/图片，避免把第三方返回的任意 URL 直接渲染出去
_ALLOWED_LINK_HOSTS = ("rollinggo.cn",)
_ALLOWED_IMAGE_HOSTS = ("image-cdn.rollinggo.cn",)

_memory_cache = {}
_loaded = False


# ---------------------------------------------------------------- 基础工具


def _setting(name, default=None):
    if has_app_context():
        value = current_app.config.get(name)
        if value:
            return value
    return os.getenv(name, default)


def _proxy_url():
    url = (_setting("HOTEL_PROXY_URL", DEFAULT_PROXY) or "").strip().rstrip("/")
    if not url.startswith("https://"):
        return ""
    return url


def _timeout():
    try:
        return max(3.0, float(_setting("HOTEL_TIMEOUT", 8) or 8))
    except (TypeError, ValueError):
        return 8.0


def _cache_path():
    if not has_app_context():
        return None
    try:
        root = Path(current_app.root_path).parent / "instance"
        root.mkdir(parents=True, exist_ok=True)
        return root / CACHE_FILE
    except OSError:
        return None


def _load_cache():
    global _loaded
    if _loaded:
        return
    _loaded = True
    path = _cache_path()
    if not path or not path.exists():
        return
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(raw, dict):
        now = time.time()
        for key, value in raw.items():
            if isinstance(value, dict) and now - float(value.get("ts") or 0) < CACHE_TTL_SECONDS:
                _memory_cache[key] = value


def _save_cache():
    path = _cache_path()
    if not path:
        return
    now = time.time()
    fresh = {key: value for key, value in _memory_cache.items()
             if isinstance(value, dict) and now - float(value.get("ts") or 0) < CACHE_TTL_SECONDS}
    try:
        path.write_text(json.dumps(fresh, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def _host_allowed(url, hosts):
    if not isinstance(url, str) or not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    return any(host == item or host.endswith("." + item) for item in hosts)


# ---------------------------------------------------------------- 代理调用


def _rpc(tool_name, arguments):
    """调用代理上的一个 MCP 工具，返回解析后的业务字典；失败一律 None。"""
    url = _proxy_url()
    if not url:
        return None
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    try:
        response = requests.post(url, json=body, timeout=_timeout())
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    result = (payload or {}).get("result") or {}
    contents = result.get("content") or []
    if not isinstance(contents, list):
        return None
    for item in contents:
        if isinstance(item, dict) and item.get("type") == "text":
            try:
                data = json.loads(item.get("text") or "")
            except (TypeError, ValueError):
                continue
            if isinstance(data, dict):
                return data
    return None


# ---------------------------------------------------------------- 结果归一化


def _price_of(price):
    if not isinstance(price, dict):
        return None
    if price.get("hasPrice") is False:
        return None
    value = price.get("lowestPrice")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        return None
    return round(float(value), 1)


def _price_text(value, lang):
    """线程池里没有请求上下文，所以按传入的 lang 直接取词条，不走 t()。"""
    if not value:
        return ""
    template = "¥{price}/晚"
    if lang == "en":
        template = EN.get(template, template)
    return template.format(price=int(value))


def _normalize_hotel(raw, lang="zh"):
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or "").strip()
    if not name:
        return None
    value = _price_of(raw.get("price"))
    star = raw.get("starRating")
    try:
        star = float(star) if star is not None else 0.0
    except (TypeError, ValueError):
        star = 0.0
    image = raw.get("imageUrl")
    link = raw.get("bookingUrl")
    tags = [str(tag).strip()[:12] for tag in (raw.get("tags") or []) if str(tag).strip()][:3]
    return {
        "id": raw.get("hotelId"),
        "name": name[:60],
        "star": round(star, 1),
        "price": value,
        "price_text": _price_text(value, lang),
        "address": str(raw.get("address") or "").strip()[:60],
        "image": image if _host_allowed(image, _ALLOWED_IMAGE_HOSTS) else "",
        "booking_url": link if _host_allowed(link, _ALLOWED_LINK_HOSTS) else "",
        "tags": tags,
    }


def _normalize_list(data, limit=3, lang="zh"):
    if not isinstance(data, dict):
        return []
    raw_list = data.get("hotelInformationList")
    if not isinstance(raw_list, list):
        return []
    hotels = []
    for item in raw_list:
        hotel = _normalize_hotel(item, lang)
        if hotel:
            hotels.append(hotel)
        if len(hotels) >= limit:
            break
    return hotels


# ---------------------------------------------------------------- 对外接口


def _search_once(place, place_type, check_in, nights, adults, max_price, size):
    arguments = {
        "originQuery": f"{place} 住 {nights} 晚，成人 {adults} 位",
        "place": place,
        "placeType": place_type,
        "size": size,
        "checkInParam": {"stayNights": nights, "adultCount": adults},
    }
    if check_in:
        arguments["checkInParam"]["checkInDate"] = check_in
    if max_price:
        arguments["hotelTags"] = {"maxPricePerNight": max_price}
    return _rpc("searchHotels", arguments)


def search_stay(city, attraction="", check_in="", nights=1, adults=2, max_price=0, size=3, lang=None):
    """查一个落点的酒店。

    先按景点 POI 查（结果最贴近实际位置），没有再退回城市；
    带限价查不到时去掉限价再试一次。全程失败返回 None。
    """
    city = str(city or "").strip()[:20]
    if not city:
        return None
    nights = max(1, min(int(nights or 1), 28))
    adults = max(1, min(int(adults or 2), 8))
    size = max(1, min(int(size or 3), 10))
    attraction = str(attraction or "").strip()[:30]

    # price_text / note 是本地化后的字符串，缓存必须按语言分开存，
    # 否则先落地的中文结果会被英文请求直接命中
    lang = lang or current_lang()
    key = "|".join([lang, city, attraction, check_in or "", str(nights),
                    str(adults), str(max_price), str(size)])
    _load_cache()
    cached = _memory_cache.get(key)
    if cached:
        ttl = CACHE_TTL_SECONDS if cached.get("data") else FAIL_TTL_SECONDS
        if time.time() - float(cached.get("ts") or 0) < ttl:
            return cached.get("data")

    attempts = []
    if attraction:
        attempts.append((f"{attraction} {city}", "景点", max_price))
    attempts.append((f"{city} 中国", "城市", max_price))
    if max_price:
        attempts.append((f"{city} 中国", "城市", 0))

    data = None
    for place, place_type, price_cap in attempts:
        hotels = _normalize_list(
            _search_once(place, place_type, check_in, nights, adults, price_cap, size),
            limit=size, lang=lang,
        )
        if hotels:
            data = {
                "city": city,
                "place": place,
                "place_type": place_type,
                "check_in": check_in,
                "nights": nights,
                "price_cap": price_cap or 0,
                "hotels": hotels,
            }
            break

    _memory_cache[key] = {"ts": time.time(), "data": data}
    _save_cache()
    return data


def _group_stays(day_cities):
    """把「每天落点」压成连续住宿段：同城连续几天算一段。

    晚数 = 该城连续天数，最后一段减 1（行程结束当天返程，不住）；
    减到 0 就整段去掉 —— 不能凭空多算一晚。
    """
    stays = []
    for city in day_cities:
        if not city:
            continue
        if stays and stays[-1]["city"] == city:
            stays[-1]["days"] += 1
        else:
            stays.append({"city": city, "days": 1})
    if not stays:
        return []
    for stay in stays:
        stay["nights"] = stay["days"]
    stays[-1]["nights"] = max(0, stays[-1]["nights"] - 1)
    # 末段 0 晚说明最后一天在返程，不安排住宿
    return [stay for stay in stays if stay["nights"] > 0]


def recommend_hotels(day_cities, focus_map=None, start_date="", budget=0, size=3, max_stays=2,
                     need_stay=True):
    """按行程落点给出住宿段 + 每段 3 家真实酒店。

    focus_map: {城市: 该城最值得住的景点名}，用来先按 POI 找更贴近的酒店。
    need_stay: 用户选了「需要安排住宿」。为真时至少给一段 ——
               只玩 1 天的行程末段晚数会被算成 0（按「当天返程」处理），
               但选了要住宿就是住一晚、第二天再回，不能整块没有。
    返回 {"source": "live"|"none", "stays": [...], "note": "..."}；永远不抛异常。
    """
    lang = current_lang()
    focus_map = focus_map if isinstance(focus_map, dict) else {}
    cities = [str(item or "").strip()[:20] for item in (day_cities or [])][:6]
    if not cities or not any(cities):
        return {"source": "none", "stays": [], "note": ""}

    total_days = len([item for item in cities if item])
    stays = _group_stays(cities)
    if not stays and need_stay:
        # 单天行程：住一晚再返程（末段落点就是最后一天所在地）
        city = next((item for item in reversed(cities) if item), "")
        if city:
            stays = [{"city": city, "days": 1, "nights": 1}]
    stays = stays[:max_stays]

    # 人均预算按天摊，再拿 1.2 倍作为单间夜房价上限；算是克制的经验值，避免整段超支
    cap = 0
    if isinstance(budget, int) and budget > 0 and total_days > 0:
        cap = int(budget / total_days * 1.2)

    filled = []
    try:
        with ThreadPoolExecutor(max_workers=max(1, min(len(stays), 2))) as pool:
            futures = [
                pool.submit(search_stay, stay["city"], focus_map.get(stay["city"], ""),
                            start_date, stay["nights"], 2, cap, size, lang)
                for stay in stays
            ]
            for stay, future in zip(stays, futures):
                try:
                    data = future.result(timeout=_timeout() + 5)
                except Exception:  # 线程内的异常不能影响整段行程
                    data = None
                if not data:
                    continue
                entry = dict(stay)
                entry["check_in"] = data.get("check_in") or start_date
                entry["place"] = data.get("place") or ""
                entry["hotels"] = data.get("hotels") or []
                entry["price_cap"] = data.get("price_cap") or 0
                if entry["hotels"]:
                    filled.append(entry)
    except Exception:
        return {"source": "none", "stays": [], "note": ""}

    if not filled:
        # 有住宿段却一条都没查到：多半是上游抖动，给个可见提示，避免用户以为功能坏了
        note = t("住宿查询暂时不可用，稍后会自动重试。") if stays else ""
        return {"source": "none", "stays": [], "note": note}
    return {
        "source": "live",
        "stays": filled,
        "note": t("房价为实时查询结果，以预订页显示为准。"),
    }
