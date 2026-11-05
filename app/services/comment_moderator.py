"""评论 AI 预审：明显没问题的直接放行，拿不准的交给后台人工审核。

无 key / 超时 / 返回不合法 → verdict = "unavailable"，同样走人工审核（保守策略）。
"""
from __future__ import annotations

import json

import requests
from flask import current_app, has_app_context

SYSTEM_PROMPT = """你是中文旅游网站的评论审核员。判断用户评论是否可以直接公开。
可以直接公开（pass）：真实体验、攻略细节、提问、温和的负面评价、闲聊式好评。
需要人工复核（flag）：广告/引流/联系方式、辱骂攻击、涉政涉黄涉暴、隐私信息、
                  明显复制粘贴的垃圾内容、与景点完全无关的内容。
宁可 flag 也不要放过可疑内容。只输出 JSON：
{"verdict":"pass","reason":"不超过 30 字的中文理由"}
"""


def _config(name, default=None):
    if has_app_context():
        value = current_app.config.get(name)
        if value:
            return value
    return default


def review(content: str, attraction_name: str = "") -> dict:
    """返回 {"verdict": "pass|flag|unavailable", "reason": "..."}。"""
    base = (_config("AI_BASE_URL") or "").rstrip("/")
    key = _config("AI_API_KEY")
    if not base or not key:
        return {"verdict": "unavailable", "reason": "未配置 AI key"}

    payload = {
        "model": _config("AI_MODEL", "deepseek-chat"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "景点": attraction_name or "未提供",
                "评论": content[:500],
            }, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": 120,
        "response_format": {"type": "json_object"},
    }
    try:
        response = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=12,
        )
    except requests.RequestException:
        return {"verdict": "unavailable", "reason": "AI 请求失败"}

    if response.status_code != 200:
        return {"verdict": "unavailable", "reason": f"AI 返回 {response.status_code}"}
    try:
        body = response.json()
        raw = ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
        parsed = json.loads(raw)
    except (ValueError, KeyError, IndexError):
        return {"verdict": "unavailable", "reason": "AI 返回格式异常"}

    verdict = str(parsed.get("verdict") or "").strip().lower()
    reason = str(parsed.get("reason") or "").strip()[:120]
    if verdict not in ("pass", "flag"):
        return {"verdict": "unavailable", "reason": reason or "AI 判定不明确"}
    return {"verdict": verdict, "reason": reason}
