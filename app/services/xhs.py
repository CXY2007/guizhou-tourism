"""小红书笔记参考（供 AI 行程规划引用）。

策略：
1. 配了 `XHS_COOKIE` → 调小红书搜索接口抓实时笔记（结果缓存 6 小时到 instance/xhs_cache.json）；
2. cookie 缺失/过期/被风控 → 用 `content/xhs-notes.json` 里的本地笔记兜底；
3. 都拿不到 → 返回空，行程照常生成。

接口失败不抛异常，只返回状态，页面不报错。
"""
from __future__ import annotations

import json
import pathlib
import time

import requests
from flask import current_app, has_app_context

ROOT = pathlib.Path(__file__).resolve().parents[2]  # app/services/xhs.py -> 项目根
CURATED = ROOT / "content" / "xhs-notes.json"
CACHE = ROOT / "instance" / "xhs_cache.json"
TTL = 6 * 3600

API = "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://www.xiaohongshu.com",
    "Referer": "https://www.xiaohongshu.com/",
}


def _setting(name, default=""):
    if has_app_context():
        value = current_app.config.get(name)
        if value:
            return value
    return default


def _cookie() -> str:
    return (_setting("XHS_COOKIE") or "").strip()


def _cookie_dict(raw: str) -> dict:
    jar = {}
    for part in raw.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            jar[key.strip()] = value.strip()
    return jar


def _read_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_cache(data: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def search(keyword: str, limit: int = 5) -> tuple[list[dict] | None, str]:
    """返回 (notes, status)。status: ok / no_cookie / expired / http_error / empty。"""
    cookie = _cookie()
    if not cookie:
        return None, "no_cookie"

    cache = _read_cache()
    hit = cache.get(keyword)
    if hit and time.time() - hit.get("ts", 0) < TTL:
        return hit.get("notes") or [], "cache"

    payload = {
        "keyword": keyword,
        "page": 1,
        "page_size": 12,
        "search_id": f"xhs{int(time.time())}",
        "sort": "general",
        "note_type": 0,
    }
    try:
        response = requests.post(
            API, headers=HEADERS, cookies=_cookie_dict(cookie), json=payload, timeout=10
        )
    except requests.RequestException:
        return None, "http_error"

    if response.status_code != 200:
        return None, "http_error"
    try:
        body = response.json()
    except ValueError:
        return None, "http_error"
    if body.get("code") == -101:
        return None, "expired"
    if body.get("code") != 0:
        return None, "expired" if body.get("code") in (-100, 461) else "http_error"

    items = ((body.get("data") or {}).get("items") or [])
    notes = []
    for item in items[:limit]:
        card = item.get("note_card") or {}
        title = (card.get("display_title") or "").strip()
        desc = (card.get("desc") or "").strip()
        if not title and not desc:
            continue
        notes.append({
            "title": title[:60],
            "body": desc[:160],
            "likes": (card.get("interact_info") or {}).get("liked_count", ""),
            "note_id": item.get("id", ""),
        })
    if not notes:
        return [], "empty"

    cache[keyword] = {"ts": time.time(), "notes": notes}
    _write_cache(cache)
    return notes, "ok"


def curated_for(slug: str, limit: int = 2) -> list[dict]:
    try:
        data = json.loads(CURATED.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return (data.get(slug) or [])[:limit]


def notes_for_attractions(attractions, per_attraction: int = 1, max_total: int = 6) -> dict:
    """给一组景点找笔记：先试实时，再回落本地。返回 {notes, source, status}。"""
    notes: list[dict] = []
    statuses: list[str] = []
    live_used = False

    for attraction in attractions:
        if len(notes) >= max_total:
            break
        found, status = search(f"{attraction.name} 攻略", limit=per_attraction)
        statuses.append(status)
        if found:
            live_used = True
            for note in found[:per_attraction]:
                notes.append({**note, "attraction": attraction.slug, "name": attraction.name})
        else:
            for note in curated_for(attraction.slug, limit=per_attraction):
                if len(notes) >= max_total:
                    break
                notes.append({**note, "attraction": attraction.slug, "name": attraction.name})

    if live_used:
        source = "live"
    elif notes:
        source = "curated"
    else:
        source = "none"

    unique = {status for status in statuses}
    status = "no_cookie" if unique == {"no_cookie"} else ("ok" if live_used else "curated")

    return {"notes": notes[:max_total], "source": source, "status": status}
