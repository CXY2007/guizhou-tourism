import json
import os
import time
from urllib.parse import urlencode

import requests
from flask import current_app, has_app_context

from ..i18n import current_lang, t


_CACHE_TTL_SECONDS = 10 * 60
_weather_cache = {}


def _setting(name, default=""):
    if has_app_context():
        value = current_app.config.get(name)
        if value:
            return value
    return os.getenv(name, default)


def _request_json(host, path, params):
    url = f"https://{host.rstrip('/')}{path}?{urlencode(params)}"
    try:
        response = requests.get(url, timeout=5)
    except requests.RequestException:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def get_weather(city: str, weather_code: str | None = None) -> dict | None:
    key = _setting("HEFENG_KEY")
    host = (_setting("HEFENG_HOST") or "devapi.qweather.com").strip()
    if not key or not host:
        return None
    if host.startswith("https://"):
        host = host[8:]
    elif host.startswith("http://"):
        host = host[7:]
    host = host.rstrip("/")

    try:
        if weather_code:
            location_id = str(weather_code)
            city_name = city
        else:
            if not city:
                return None
            lookup = _request_json(host, "/geo/v2/city/lookup", {"location": city, "key": key})
            locations = (lookup or {}).get("location") or []
            if (lookup or {}).get("code") != "200" or not locations:
                return None
            location_id = locations[0].get("id")
            city_name = locations[0].get("name") or city
            if not location_id:
                return None

        cached = _weather_cache.get(str(location_id))
        now = time.monotonic()
        if cached and now - cached[0] < _CACHE_TTL_SECONDS:
            return cached[1]

        params = {"location": location_id, "key": key}
        live_response = _request_json(host, "/v7/weather/now", params)
        forecast_response = _request_json(host, "/v7/weather/3d", params)
        if (live_response or {}).get("code") != "200" or (forecast_response or {}).get("code") != "200":
            return None
        live = (live_response.get("now") or {})
        forecast = (forecast_response.get("daily") or [])
        result = {"city": city_name, "live": live, "forecast": forecast}
        _weather_cache[str(location_id)] = (now, result)
        return result
    except Exception:
        return None


def build_advice(live: dict) -> str:
    advice = []
    try:
        temperature = float(live.get("temp"))
    except (TypeError, ValueError):
        temperature = None
    weather = str(live.get("text", ""))
    wind = str(live.get("windScale", ""))

    if temperature is not None:
        if temperature >= 30:
            advice.append("气温较高，注意防晒并及时补水")
        elif temperature <= 10:
            advice.append("气温偏低，建议添衣保暖")
        elif temperature <= 16:
            advice.append("早晚偏凉，建议带件外套")
    if any(word in weather for word in ("雨", "雪", "冰雹")):
        advice.append("天气有降水，出行请携带雨具并留意路面湿滑")
    elif any(word in weather for word in ("晴", "少云")) and not any(word in weather for word in ("雨", "雪")):
        advice.append("天气晴好，户外游览建议做好防晒")

    try:
        wind_scale = float(wind.replace("级", "").split("-")[0])
    except (TypeError, ValueError):
        wind_scale = 0
    if wind_scale >= 6:
        advice.append("风力较强，户外活动请注意防风")

    phrases = [t(item) for item in advice[:2]]
    if not phrases:
        return t("天气适宜，祝您游览愉快。")
    if current_lang() == "en":
        return " ".join(phrases) + "."
    return "。".join(phrases) + "。"
