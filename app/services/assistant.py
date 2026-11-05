"""AI 小球 v1：规则意图路由（不依赖 LLM）。

支持：导航（景点/页面）、分类搜索、关键词搜索、景点事实问答、
简单行程草案、待上线景点提示、帮助兜底。
"""
import re
from urllib.parse import quote

from ..models import Attraction
from .weather import build_advice, get_weather

PENDING = {}

ALIASES = {
    "黄果树": "黄果树瀑布",
    "huangguoshu": "黄果树瀑布",
    "西江": "西江千户苗寨",
    "千户苗寨": "西江千户苗寨",
    "xijiang": "西江千户苗寨",
    "梵净山": "梵净山",
    "fanjingshan": "梵净山",
    "天眼": "中国天眼 (FAST)",
    "fast": "中国天眼 (FAST)",
    "大射电": "中国天眼 (FAST)",
    "遵义会议": "遵义会议会址",
    "遵义": "遵义会议会址",
    "娄山": "娄山关",
    "娄山关": "娄山关",
    "息烽": "息烽集中营旧址",
    "黎平": "黎平会议会址",
    "小七孔": "荔波小七孔",
    "万峰林": "万峰林",
    "平坝樱花": "贵安平坝樱花",
    "花江": "花江峡谷大桥",
    "花江大桥": "花江峡谷大桥",
    "肇兴": "肇兴侗寨",
    "侗寨": "肇兴侗寨",
    "镇远": "镇远古镇",
    "青岩": "青岩古镇",
    "乌蒙": "乌蒙大草原",
    "草原": "乌蒙大草原",
    "百里杜鹃": "毕节百里杜鹃",
    "织金洞": "织金洞",
}

CATEGORY_ALIASES = {
    "自然": "自然",
    "山水": "自然",
    "瀑布": "自然",
    "人文": "人文",
    "村寨": "人文",
    "古镇": "人文",
    "红色": "红色",
    "科技": "科技",
    "科学": "科技",
    "季节": "季节",
    "花海": "季节",
}

HELP_REPLY = (
    "我可以：带你去某个景点、按分类找景点、回答门票/时长/最佳月份/地址，"
    "还能排一个简单行程。试试“带我去黄果树”“找红色景点”“黄果树门票多少”。"
)


def _resp(reply, intent, action=None, confidence=0.5, links=None):
    return {
        "reply": reply,
        "intent": intent,
        "action": action,
        "confidence": confidence,
        "links": links or [],
    }


def _published():
    return Attraction.query.filter_by(status="published").all()


def _alias_map(attractions):
    mapping = {}
    for attraction in attractions:
        mapping[attraction.name.lower()] = attraction
        mapping[attraction.slug.lower()] = attraction
        mapping[attraction.slug.replace("-", " ").lower()] = attraction
        for translation in getattr(attraction, "translations", None) or []:
            if translation.lang == "en" and translation.name:
                mapping[translation.name.lower()] = attraction
    for alias, name in ALIASES.items():
        for attraction in attractions:
            if attraction.name == name:
                mapping[alias.lower()] = attraction
                break
    return mapping


def _find_attraction(text, attractions):
    lower = text.lower()
    for key, attraction in sorted(_alias_map(attractions).items(), key=lambda item: len(item[0]), reverse=True):
        if key and key in lower:
            return attraction
    return None


def _days(text):
    match = re.search(r"(\d+)\s*(天|日)", text)
    if match:
        return max(1, min(5, int(match.group(1))))
    return 3


def _itinerary(attractions, days):
    picks = sorted(attractions, key=lambda a: float(a.rating or 0), reverse=True)[: days * 2]
    lines, links = [], []
    for day in range(days):
        group = picks[day * 2:(day + 1) * 2]
        if not group:
            break
        lines.append(f"Day {day + 1}：" + "、".join(a.name for a in group))
        links.extend({"name": a.name, "url": f"/attractions/{a.slug}"} for a in group)
    if not lines:
        return "现在还没有可推荐的景点。", []
    reply = f"先给你一个 {days} 天草案（按评分挑的，之后可以在行程页细调）：\n" + "\n".join(lines)
    return reply, links


def _fact_reply(text, attraction):
    if any(k in text for k in ("门票", "多少钱", "票价", "价格", "贵不贵")):
        note = f"（{attraction.ticket_note}）" if attraction.ticket_note else ""
        return f"{attraction.name}门票 {attraction.price_label}{note}。"
    if any(k in text for k in ("玩多久", "时长", "几个小时", "多久")):
        if attraction.visit_duration:
            return f"{attraction.name}建议游玩 {attraction.visit_duration / 60:.1f} 小时。"
    if any(k in text for k in ("最佳", "月份", "什么时候", "几月")):
        if attraction.best_months:
            return f"{attraction.name}最佳月份：{attraction.best_months}。"
    if any(k in text for k in ("地址", "在哪", "位置")):
        if attraction.address:
            return f"{attraction.name}地址：{attraction.address}。"
    if any(k in text for k in ("开放", "几点", "时间")):
        if attraction.open_time:
            return f"{attraction.name}开放时间：{attraction.open_time}。"
    if any(k in text for k in ("评分", "几分", "好评")):
        return f"{attraction.name}评分 {attraction.rating_label}/5（{attraction.rating_count or 0} 人）。"
    return None


def answer(message, user=None):
    text = (message or "").strip()
    if not text:
        return _resp(HELP_REPLY, "help", None, 0.3)

    attractions = _published()
    found = _find_attraction(text, attractions)

    if any(k in text for k in ("你能做什么", "帮助", "怎么用", "功能", "help")):
        return _resp(HELP_REPLY, "help", None, 0.9)

    if any(k in text for k in ("我的收藏", "收藏夹", "个人中心", "我的主页", "我的足迹")):
        if user is not None and getattr(user, "is_authenticated", False):
            return _resp("正在打开你的个人中心。", "navigate", {"type": "navigate", "url": "/profile"}, 0.85)
        return _resp("登录后就能看到收藏和足迹，先带你去登录。", "navigate",
                     {"type": "navigate", "url": "/auth/login?next=/profile"}, 0.8)

    if any(k in text for k in ("后台", "审核")):
        if user is not None and getattr(user, "is_admin", False):
            return _resp("正在打开评论审核。", "navigate", {"type": "navigate", "url": "/admin/comments"}, 0.8)
        return _resp("评论审核只有管理员能进。", "help", None, 0.7)

    if any(k in text for k in ("登录", "登陆")):
        return _resp("正在打开登录页。", "navigate", {"type": "navigate", "url": "/auth/login"}, 0.8)

    if any(k in text for k in ("景点列表", "全部景点", "所有景点", "探索景点")):
        return _resp("正在打开景点列表。", "navigate", {"type": "navigate", "url": "/attractions"}, 0.8)

    if any(k in text for k in ("首页", "主页", "回到首页")):
        return _resp("回到首页。", "navigate", {"type": "navigate", "url": "/"}, 0.8)

    if any(k in text for k in ("行程", "规划", "安排", "几天", "几日")):
        days = _days(text)
        plan, links = _itinerary(attractions, days)
        return _resp(plan, "itinerary", None, 0.8, links)

    if any(k in text for k in ("买票", "订票", "预订", "购票", "怎么买", "预约")):
        if found:
            return _resp(
                f"{found.name}门票 {found.price_label}。预订功能 D3-D 上线，先带你去详情页。",
                "booking",
                {"type": "navigate", "url": f"/attractions/{found.slug}"},
                0.8,
            )
        return _resp("想订哪个景点？告诉我名字，比如“黄果树怎么买票”。", "booking", None, 0.5)

    if any(k in text for k in ("天气", "下雨", "气温", "冷不冷", "热不热")):
        if found:
            weather = get_weather(found.city or "", found.weather_code)
            if weather and weather.get("live"):
                live = weather["live"]
                advice = build_advice(live)
                reply = (
                    f"{found.city or found.name}现在{live.get('text', '')} "
                    f"{live.get('temp', '')}℃，{advice}"
                )
                return _resp(reply, "weather",
                             {"type": "navigate", "url": f"/attractions/{found.slug}"}, 0.85)
            return _resp("天气服务暂时不可用，先带你去详情页看其他信息。", "weather",
                         {"type": "navigate", "url": f"/attractions/{found.slug}"}, 0.6)
        return _resp("想看哪个景点的天气？比如“黄果树天气”。", "weather", None, 0.5)

    if found:
        fact = _fact_reply(text, found)
        if fact:
            return _resp(fact, "qa", {"type": "navigate", "url": f"/attractions/{found.slug}"}, 0.9)
        return _resp(f"带你去{found.name}。", "navigate",
                     {"type": "navigate", "url": f"/attractions/{found.slug}"}, 0.9)

    category = next((value for key, value in CATEGORY_ALIASES.items() if key in text), None)
    if category:
        return _resp(f"正在找{category}类景点。", "search",
                     {"type": "navigate", "url": f"/attractions?category={quote(category)}"}, 0.85)

    match = re.search(r"(?:找|搜|查|有没有|推荐)(?:一下)?\s*(.+)", text)
    if match:
        keyword = match.group(1).strip(" 的？?。！!")
        if keyword:
            return _resp(f"正在搜索“{keyword}”。", "search",
                         {"type": "navigate", "url": f"/attractions?q={quote(keyword)}"}, 0.7)

    return _resp(
        "我还没听懂。可以试试：“带我去黄果树”“找红色景点”“黄果树门票多少”“帮我排 3 天行程”。",
        "help",
        None,
        0.4,
    )
