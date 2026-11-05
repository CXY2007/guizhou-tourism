from collections import defaultdict, deque
from datetime import date, datetime, timedelta
from functools import wraps
import io
import os
import time
import uuid

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user
from PIL import Image
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db
from ..i18n import attr_field, category_label, city_label, current_lang, t
from ..models import AssistantLog, Attraction, Booking, Comment, Favorite, Itinerary, Rating, User
from ..services.assistant import answer as assistant_answer
from ..services.history import recent_views
from ..services.comment_moderator import review as review_comment
from ..services.uploads import remove_file_if_unused
from ..services.itinerary import generate_itinerary
from ..services.itinerary_analysis import MAX_DAYS as ANALYSIS_MAX_DAYS
from ..services.itinerary_analysis import build_budget, detect_conflicts, precheck_selection
from ..services.ai_itinerary import plan_with_llm, translate_conflicts, translate_plan
from ..services.hotels import recommend_hotels
from ..services.llm_assistant import answer_with_llm, llm_available
from ..services.weather import build_advice, get_weather

bp = Blueprint("api", __name__, url_prefix="/api")


def ok(data=None):
    return jsonify({"ok": True, "data": data, "error": None})


def fail(code, message, status=400):
    return jsonify({"ok": False, "data": None, "error": {"code": code, "message": message}}), status


def login_required_api(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return fail("login_required", t("请先登录"), 401)
        return fn(*args, **kwargs)

    return wrapper


def admin_required_api(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return fail("login_required", t("请先登录"), 401)
        if not current_user.is_admin:
            return fail("forbidden", t("需要管理员权限"), 403)
        return fn(*args, **kwargs)

    return wrapper


def serialise_attraction(a: Attraction):
    return {
        "id": a.id,
        "slug": a.slug,
        "name": attr_field(a, "name"),
        "city": city_label(a.city),
        "category": category_label(a.category),
        "price": float(a.price or 0),
        "rating": float(a.rating or 0),
        "cover": a.card_image,
    }


def _get_attraction(aid):
    if isinstance(aid, bool) or not isinstance(aid, int) or aid <= 0:
        return None
    return db.session.get(Attraction, aid)


# ---------------- 景点：评分最高 ----------------
@bp.get("/attractions/top")
def attractions_top():
    """评分最高的已发布景点。小球快捷入口直连用，不经过大模型。"""
    row = (
        Attraction.query.filter_by(status="published")
        .order_by(Attraction.rating.desc(), Attraction.id.asc())
        .first()
    )
    if not row:
        return fail("not_found", "暂无可跳转的景点", 404)
    data = serialise_attraction(row)
    data["url"] = "/attractions/" + row.slug
    return ok(data)


# ---------------- 收藏 ----------------
@bp.get("/favorites")
@login_required_api
def favorites_list():
    rows = (
        db.session.query(Favorite, Attraction)
        .join(Attraction, Favorite.attraction_id == Attraction.id)
        .filter(Favorite.user_id == current_user.id)
        .order_by(Favorite.created_at.desc())
        .all()
    )
    return ok([serialise_attraction(a) for _, a in rows])


@bp.post("/favorites/<int:attraction_id>")
@login_required_api
def favorites_toggle(attraction_id):
    attraction = _get_attraction(attraction_id)
    if attraction is None:
        return fail("not_found", t("景点不存在"), 404)
    favorite = Favorite.query.filter_by(user_id=current_user.id, attraction_id=attraction_id).first()
    if favorite:
        db.session.delete(favorite)
        db.session.commit()
        return ok({"favorited": False})
    db.session.add(Favorite(user_id=current_user.id, attraction_id=attraction_id))
    db.session.commit()
    return ok({"favorited": True})


@bp.get("/favorites/<int:attraction_id>/status")
@login_required_api
def favorites_status(attraction_id):
    if _get_attraction(attraction_id) is None:
        return fail("not_found", t("景点不存在"), 404)
    exists = Favorite.query.filter_by(user_id=current_user.id, attraction_id=attraction_id).first()
    return ok({"favorited": bool(exists)})


# ---------------- 评论 ----------------
@bp.get("/comments")
def comments_list():
    attraction_id = request.args.get("attraction_id", type=int)
    if not attraction_id:
        return fail("invalid_params", t("缺少 attraction_id"))
    rows = (
        db.session.query(Comment, User)
        .join(User, Comment.user_id == User.id)
        .filter(Comment.attraction_id == attraction_id, Comment.status == "approved")
        .order_by(Comment.created_at.desc())
        .limit(80)
        .all()
    )

    def payload(comment, user):
        return {
            "id": comment.id,
            "content": comment.content,
            "image_url": comment.image_url or "",
            "created_at": comment.created_at.strftime("%Y-%m-%d %H:%M") if comment.created_at else "",
            "user": user.display_name,
            "user_id": user.id,
            "avatar_url": user.avatar_url,
            "parent_id": comment.parent_id,
        }

    tops = {}
    for comment, user in rows:
        if comment.parent_id is None:
            item = payload(comment, user)
            item["replies"] = []
            tops[comment.id] = item

    for comment, user in rows:
        if comment.parent_id is not None and comment.parent_id in tops:
            tops[comment.parent_id]["replies"].append(payload(comment, user))

    # 回复按时间正序（先说的在上面），顶层保持倒序
    for item in tops.values():
        item["replies"].sort(key=lambda row: row["created_at"])

    return ok(list(tops.values()))


COMMENT_UPLOAD_DIR = "uploads/comments"


@bp.post("/comments/upload")
@login_required_api
def comments_upload_image():
    """评论区配图上传：校验 → 限宽 1400 → 存 static/uploads/comments/。"""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return fail("invalid_params", t("请选择一张图片"))

    raw = upload.read()
    if not raw:
        return fail("invalid_params", t("请选择一张图片"))
    if len(raw) > 4 * 1024 * 1024:
        return fail("invalid_params", t("图片不能超过 4MB"), 413)

    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
    except Exception:
        return fail("invalid_params", t("请上传 jpg / png / webp 图片"))

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    if image.width > 1400:
        image = image.resize((1400, round(image.height * 1400 / image.width)), Image.LANCZOS)

    folder = os.path.join(current_app.static_folder, COMMENT_UPLOAD_DIR.replace("/", os.sep))
    os.makedirs(folder, exist_ok=True)
    filename = f"{current_user.id}-{uuid.uuid4().hex[:12]}.jpg"
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=84, optimize=True)
    with open(os.path.join(folder, filename), "wb") as handle:
        handle.write(buffer.getvalue())

    url = f"/static/{COMMENT_UPLOAD_DIR}/{filename}"
    return ok({"url": url, "bytes": len(buffer.getvalue())})


def _valid_comment_image(value) -> str:
    """只允许本站上传目录下的图片，防止塞外链或路径穿越。"""
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        return ""
    value = value.strip()
    prefix = f"/static/{COMMENT_UPLOAD_DIR}/"
    if not value.startswith(prefix) or len(value) > 255:
        return ""
    name = value[len(prefix):]
    if "/" in name or "\\" in name or name.startswith("."):
        return ""
    return value


@bp.post("/comments")
@login_required_api
def comments_create():
    data = request.get_json(silent=True) or {}
    attraction_id = data.get("attraction_id")
    content = data.get("content")
    if isinstance(attraction_id, bool) or not isinstance(attraction_id, int) or attraction_id <= 0:
        return fail("invalid_params", t("缺少 attraction_id"))
    if not isinstance(content, str):
        return fail("invalid_params", t("评论需为 1–500 字"))
    content = content.strip()
    if len(content) > 500:
        return fail("invalid_params", t("评论需为 1–500 字"))
    parent_id = data.get("parent_id")
    if parent_id is not None:
        if isinstance(parent_id, bool) or not isinstance(parent_id, int) or parent_id <= 0:
            return fail("invalid_params", t("回复目标不合法"))
        parent = db.session.get(Comment, parent_id)
        if parent is None or parent.attraction_id != attraction_id:
            return fail("not_found", t("回复的评论不存在"), 404)
        if parent.parent_id is not None:
            return fail("invalid_params", t("只能回复主评论"))
        if parent.status != "approved":
            return fail("invalid_params", t("该评论暂不可回复"))
    image_url = _valid_comment_image(data.get("image_url"))
    requested_image = bool(data.get("image_url"))
    if not content and not image_url:
        return fail("invalid_params", t("评论需为 1–500 字"))
    if requested_image and not image_url:
        return fail("invalid_params", t("图片地址不合法"))
    if _get_attraction(attraction_id) is None:
        return fail("not_found", t("景点不存在"), 404)

    attraction = _get_attraction(attraction_id)
    verdict = review_comment(content, attr_field(attraction, "name"))
    auto_pass = verdict["verdict"] == "pass"

    comment = Comment(
        user_id=current_user.id,
        attraction_id=attraction_id,
        content=content,
        image_url=image_url or None,
        parent_id=parent_id,
        status="approved" if auto_pass else "pending",
        review_by="ai" if auto_pass else "pending",
        ai_reason=(verdict.get("reason") or "")[:255],
    )
    db.session.add(comment)
    db.session.commit()
    return ok({
        "id": comment.id,
        "status": comment.status,
        "review_by": comment.review_by,
        "auto_passed": auto_pass,
        "ai_reason": comment.ai_reason or "",
        "image_url": image_url,
        "parent_id": parent_id,
    })


@bp.delete("/comments/<int:comment_id>")
@login_required_api
def comments_delete(comment_id):
    comment = db.session.get(Comment, comment_id)
    if comment is None:
        return fail("not_found", t("评论不存在"), 404)
    if comment.user_id != current_user.id and not current_user.is_admin:
        return fail("forbidden", t("只能删除自己的评论"), 403)
    image_url = comment.image_url or ""
    replies = Comment.query.filter_by(parent_id=comment.id).all()
    reply_images = [row.image_url for row in replies if row.image_url]
    for row in replies:
        db.session.delete(row)
    db.session.delete(comment)
    db.session.commit()

    removed = 0
    for url in [image_url] + reply_images:
        if url and remove_file_if_unused(url):
            removed += 1
    return ok({"deleted": True, "file_removed": removed > 0, "replies_deleted": len(replies)})


# ---------------- 评分 ----------------
@bp.get("/ratings/<int:attraction_id>")
def ratings_get(attraction_id):
    attraction = _get_attraction(attraction_id)
    if attraction is None:
        return fail("not_found", t("景点不存在"), 404)
    user_rating = None
    if current_user.is_authenticated:
        row = Rating.query.filter_by(user_id=current_user.id, attraction_id=attraction_id).first()
        user_rating = row.rating if row else None
    return ok({
        "user_rating": user_rating,
        "avg_rating": float(attraction.rating or 0),
        "rating_count": attraction.rating_count or 0,
    })


@bp.post("/ratings")
@login_required_api
def ratings_create():
    data = request.get_json(silent=True) or {}
    attraction_id = data.get("attraction_id")
    rating = data.get("rating")
    if (isinstance(attraction_id, bool) or not isinstance(attraction_id, int)
            or isinstance(rating, bool) or not isinstance(rating, int)
            or rating not in range(1, 6)):
        return fail("invalid_params", t("评分须为 1–5"))
    attraction = _get_attraction(attraction_id)
    if attraction is None:
        return fail("not_found", t("景点不存在"), 404)

    row = Rating.query.filter_by(user_id=current_user.id, attraction_id=attraction_id).first()
    if row:
        row.rating = rating
    else:
        db.session.add(Rating(user_id=current_user.id, attraction_id=attraction_id, rating=rating))
    db.session.flush()

    stats = (
        db.session.query(func.avg(Rating.rating), func.count(Rating.id))
        .filter(Rating.attraction_id == attraction_id)
        .one()
    )
    attraction.rating = round(float(stats[0] or 0), 1)
    attraction.rating_count = int(stats[1] or 0)
    db.session.commit()
    return ok({
        "user_rating": rating,
        "avg_rating": float(attraction.rating),
        "rating_count": attraction.rating_count,
    })


# ---------------- 个人资料 ----------------
@bp.get("/profile")
@login_required_api
def profile_get():
    return ok({
        "username": current_user.username,
        "nickname": current_user.nickname or "",
        "role": current_user.role,
        "created_at": current_user.created_at.strftime("%Y-%m-%d") if current_user.created_at else "",
    })


@bp.post("/profile/avatar")
@login_required_api
def profile_avatar_upload():
    """上传头像：校验图片 → 居中裁成 256×256 JPEG → 存进 users.avatar_data。"""
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return fail("invalid_params", t("请选择一张图片"))

    raw = upload.read()
    if not raw:
        return fail("invalid_params", t("请选择一张图片"))
    if len(raw) > 3 * 1024 * 1024:
        return fail("invalid_params", t("图片不能超过 3MB"), 413)

    try:
        image = Image.open(io.BytesIO(raw))
        image.verify()
        image = Image.open(io.BytesIO(raw))
    except Exception:
        return fail("invalid_params", t("请上传 jpg / png / webp 图片"))

    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")

    side = min(image.size)
    left = (image.width - side) // 2
    top = (image.height - side) // 2
    image = image.crop((left, top, left + side, top + side)).resize((256, 256), Image.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=86, optimize=True)

    current_user.avatar_data = buffer.getvalue()
    current_user.avatar_mime = "image/jpeg"
    current_user.avatar_version = int(current_user.avatar_version or 0) + 1
    db.session.commit()
    return ok({"avatar_url": current_user.avatar_url, "bytes": len(current_user.avatar_data)})


@bp.delete("/profile/avatar")
@login_required_api
def profile_avatar_delete():
    current_user.avatar_data = None
    current_user.avatar_mime = None
    current_user.avatar_version = int(current_user.avatar_version or 0) + 1
    db.session.commit()
    return ok({"avatar_url": ""})


@bp.put("/profile")
@login_required_api
def profile_update():
    data = request.get_json(silent=True) or {}
    nickname = data.get("nickname")
    if not isinstance(nickname, str):
        return fail("invalid_params", t("昵称需为 1–30 个字符"))
    nickname = nickname.strip()
    if not (1 <= len(nickname) <= 30):
        return fail("invalid_params", t("显示名需为 1–30 个字符"))
    # 显示名允许重复：不同账号可以叫同一个名字，靠 UID 区分
    current_user.nickname = nickname
    db.session.commit()
    return ok({"nickname": nickname, "display_name": current_user.display_name, "uid": current_user.id})


@bp.post("/profile/password")
@login_required_api
def profile_password():
    data = request.get_json(silent=True) or {}
    old_password = data.get("old_password")
    new_password = data.get("new_password")
    if not isinstance(old_password, str) or not isinstance(new_password, str):
        return fail("invalid_params", t("原密码错误"))
    if not current_user.check_password(old_password):
        return fail("invalid_params", t("原密码错误"))
    if len(new_password) < 6:
        return fail("invalid_params", t("新密码至少 6 位"))
    current_user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    return ok({"changed": True})


# ---------------- 管理端 ----------------
@bp.get("/admin/comments")
@admin_required_api
def admin_comments():
    status = request.args.get("status", "pending")
    query = (
        db.session.query(Comment, User, Attraction)
        .join(User, Comment.user_id == User.id)
        .join(Attraction, Comment.attraction_id == Attraction.id)
    )
    if status in ("pending", "approved", "rejected"):
        query = query.filter(Comment.status == status)
    rows = query.order_by(Comment.created_at.desc()).limit(100).all()
    return ok([
        {
            "id": comment.id,
            "content": comment.content,
            "image_url": comment.image_url or "",
            "status": comment.status,
            "review_by": comment.review_by or "",
            "ai_reason": comment.ai_reason or "",
            "created_at": comment.created_at.strftime("%Y-%m-%d %H:%M") if comment.created_at else "",
            "user": user.display_name,
            "avatar_url": user.avatar_url,
            "attraction": {"id": attraction.id, "name": attr_field(attraction, "name"), "slug": attraction.slug},
        }
        for comment, user, attraction in rows
    ])


@bp.post("/admin/comments/<int:comment_id>/approve")
@admin_required_api
def admin_comment_action(comment_id):
    comment = db.session.get(Comment, comment_id)
    if comment is None:
        return fail("not_found", t("评论不存在"), 404)
    data = request.get_json(silent=True) or {}
    action = data.get("action")
    if action not in ("approve", "reject"):
        return fail("invalid_params", t("action 须为 approve 或 reject"))
    comment.status = "approved" if action == "approve" else "rejected"
    comment.review_by = "human"
    db.session.commit()
    return ok({"id": comment.id, "status": comment.status, "review_by": comment.review_by})


@bp.delete("/admin/comments/<int:comment_id>")
@admin_required_api
def admin_comment_delete(comment_id):
    comment = db.session.get(Comment, comment_id)
    if comment is None:
        return fail("not_found", t("评论不存在"), 404)
    db.session.delete(comment)
    db.session.commit()
    return ok({"deleted": True})


# ---------------- AI 小球 ----------------
_ASSISTANT_HITS = defaultdict(deque)


def _assistant_rate_limited(session_id):
    """同一会话 + 来源 IP 60 秒内最多 AI_RATE_LIMIT 次。"""
    limit = int(current_app.config.get("AI_RATE_LIMIT", 20) or 0)
    if limit <= 0:
        return False
    key = (session_id, request.remote_addr or "")
    now = time.time()
    if len(_ASSISTANT_HITS) > 1000:
        for stale_key, hits in list(_ASSISTANT_HITS.items()):
            if not hits or now - hits[-1] > 120:
                _ASSISTANT_HITS.pop(stale_key, None)
    bucket = _ASSISTANT_HITS[key]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


def _assistant_context(raw):
    """校验前端带上来的行程上下文；不合法就当没传，绝不因此报错。"""
    if not isinstance(raw, dict):
        return None
    days = raw.get("days")
    if not isinstance(days, list) or not days or len(days) > 5:
        return None
    cleaned_days = []
    for day in days[:5]:
        if not isinstance(day, dict):
            continue
        slots = []
        for slot in (day.get("slots") or [])[:8]:
            if not isinstance(slot, dict):
                continue
            slots.append({
                "period": str(slot.get("period") or "")[:12],
                "title": str(slot.get("title") or "")[:60],
                "slug": str(slot.get("slug") or "")[:60],
                "city": str(slot.get("city") or "")[:20],
                "detail": str(slot.get("detail") or "")[:120],
            })
        cleaned_days.append({
            "day": day.get("day") if isinstance(day.get("day"), int) else len(cleaned_days) + 1,
            "theme": str(day.get("theme") or "")[:60],
            "slots": slots,
            "tips": str(day.get("tips") or "")[:160],
        })
    if not cleaned_days:
        return None

    def _num(value, default=0):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    return {
        "days": cleaned_days,
        "budget": max(0.0, _num(raw.get("budget"))),
        "people": max(1, min(int(_num(raw.get("people"), 2) or 2), 8)),
        "start_date": str(raw.get("start_date") or "")[:10],
        "hotel_price": max(0.0, _num(raw.get("hotel_price"))),
    }


@bp.post("/assistant")
def assistant_chat():
    data = request.get_json(silent=True) or {}
    raw_message = data.get("message")
    raw_session = data.get("session_id")
    if not isinstance(raw_message, str) or not isinstance(raw_session, (str, type(None))):
        return fail("invalid_params", t("消息需为 1–500 字"))
    message = raw_message.strip()
    session_id = (raw_session or "anon")[:64]
    if not (1 <= len(message) <= 500):
        return fail("invalid_params", t("消息需为 1–500 字"))
    if _assistant_rate_limited(session_id):
        return fail("rate_limited", t("问得太快了，请稍后再试"), 429)

    # 可选上下文：前端把「当前页面上的行程」带上来，助手的
    # check_conflicts / estimate_budget 两个工具才有东西可算。
    context = _assistant_context(data.get("context"))

    started = time.time()
    result = None
    if llm_available():
        try:
            result = answer_with_llm(message, current_user if current_user.is_authenticated else None, context)
        except Exception:
            result = None
    if result is None:
        result = assistant_answer(message, current_user if current_user.is_authenticated else None)
    latency = int((time.time() - started) * 1000)

    try:
        db.session.add(AssistantLog(
            user_id=current_user.id if current_user.is_authenticated else None,
            session_id=session_id,
            message=message,
            intent=result.get("intent"),
            action={"action": result.get("action"), "links": result.get("links")},
            latency_ms=latency,
        ))
        db.session.commit()
    except Exception:
        db.session.rollback()

    return ok(result)


# ---------------- 浏览足迹 ----------------
@bp.get("/history")
@login_required_api
def history_list():
    return ok([
        {**serialise_attraction(row["attraction"]),
         "viewed_at": row["viewed_at"].strftime("%Y-%m-%d %H:%M") if row["viewed_at"] else ""}
        for row in recent_views(current_user.id)
    ])


# ---------------- 天气与统计 ----------------
_WEEK_CHARS = "一二三四五六日"


def _forecast_week(day):
    week = day.get("week")
    if week:
        if week in _WEEK_CHARS:
            return t("周" + week)
        if week.startswith("周") and len(week) == 2:
            return t(week)
        if week in "1234567":
            return t("周" + _WEEK_CHARS[int(week) - 1])
        return week
    try:
        weekday = datetime.strptime(day["fxDate"], "%Y-%m-%d").weekday()
    except (KeyError, TypeError, ValueError):
        return ""
    return t("周" + _WEEK_CHARS[weekday])


@bp.get("/weather/<int:attraction_id>")
def attraction_weather(attraction_id):
    attraction = _get_attraction(attraction_id)
    if attraction is None:
        return fail("not_found", t("景点不存在"), 404)

    weather = get_weather(attraction.city or "", attraction.weather_code)
    if weather is None:
        return fail("weather_unavailable", t("天气服务暂不可用"), 502)

    live = weather["live"]
    forecast = weather["forecast"]
    return ok({
        "city": city_label(attraction.city) or weather.get("city", ""),
        "live": {
            "weather": live.get("text", ""),
            "temperature": live.get("temp", ""),
            "humidity": live.get("humidity", ""),
            "winddirection": live.get("windDir", ""),
            "windpower": live.get("windScale", ""),
            "obsTime": live.get("obsTime", ""),
        },
        "forecast": [
            {
                "date": day.get("fxDate", ""),
                "week": _forecast_week(day),
                "dayweather": day.get("textDay", ""),
                "nightweather": day.get("textNight", ""),
                "daytemp": day.get("tempMax", ""),
                "nighttemp": day.get("tempMin", ""),
            }
            for day in forecast
        ],
        "advice": build_advice(live),
        "source": "hefeng",
    })


@bp.get("/attractions/<int:attraction_id>/stats")
def attraction_stats(attraction_id):
    if _get_attraction(attraction_id) is None:
        return fail("not_found", t("景点不存在"), 404)

    rating_rows = (
        db.session.query(Rating.rating, Rating.created_at)
        .filter(Rating.attraction_id == attraction_id)
        .all()
    )
    counts = {rating: 0 for rating in range(1, 6)}
    by_week = defaultdict(list)
    today = datetime.utcnow().date()
    # 按月分桶：本月往前共 8 个月（含本月）
    months_back = 7
    total_month = today.year * 12 + (today.month - 1) - months_back
    window_start = today.replace(year=total_month // 12, month=total_month % 12 + 1, day=1)

    for rating, created_at in rating_rows:
        if rating in counts:
            counts[rating] += 1
        if created_at is None:
            continue
        created_date = created_at.date() if isinstance(created_at, datetime) else created_at
        if window_start <= created_date <= today:
            # (年, 月) 元组做 key：中文标签按字符串排序会乱
            by_week[(created_date.year, created_date.month)].append(rating)

    month_keys = sorted(by_week)
    same_year = len({year for year, _ in month_keys}) <= 1
    if current_lang() == "en":
        months = [f"{year}-{month:02d}" for year, month in month_keys] if not same_year             else [f"{month:02d}" for _, month in month_keys]
    else:
        months = [f"{month} 月" for _, month in month_keys] if same_year             else [f"{year} 年 {month} 月" for year, month in month_keys]
    weeks = months
    averages = [round(sum(by_week[key]) / len(by_week[key]), 2) for key in month_keys]
    ratings = [rating for rating, _ in rating_rows if rating in counts]
    total = len(ratings)
    return ok({
        "pie": [{"rating": rating, "count": counts[rating]} for rating in range(1, 6)],
        "weeks": weeks,
        "averages": averages,
        "total": total,
        "avg": round(sum(ratings) / total, 2) if total else 0.0,
    })


def _order_data(booking):
    attraction = db.session.get(Attraction, booking.attraction_id)
    return {
        "id": booking.id,
        "attraction": {"id": attraction.id, "name": attr_field(attraction, "name"), "slug": attraction.slug},
        "visit_date": booking.visit_date.isoformat(),
        "quantity": booking.quantity,
        "unit_price": float(booking.unit_price),
        "total": float(booking.total),
        "status": booking.status,
        "created_at": booking.created_at.isoformat() if booking.created_at else None,
    }


@bp.post("/bookings")
@login_required_api
def bookings_create():
    data = request.get_json(silent=True) or {}
    attraction_id, visit_date, quantity = data.get("attraction_id"), data.get("visit_date"), data.get("quantity")
    if isinstance(attraction_id, bool) or not isinstance(attraction_id, int):
        return fail("invalid_params", t("预订参数不正确"))
    if not isinstance(visit_date, str) or len(visit_date) != 10 or visit_date[4:5] != "-" or visit_date[7:8] != "-":
        return fail("invalid_params", t("预订参数不正确"))
    try:
        visit_date = date.fromisoformat(visit_date)
    except (TypeError, ValueError):
        return fail("invalid_params", t("预订参数不正确"))
    if visit_date < date.today() or isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 10:
        return fail("invalid_params", t("预订参数不正确"))
    attraction = db.session.get(Attraction, attraction_id)
    if attraction is None or attraction.status != "published":
        return fail("not_found", t("景点不存在"), 404)
    unit_price = float(attraction.price or 0)
    booking = Booking(
        user_id=current_user.id, attraction_id=attraction.id, visit_date=visit_date,
        quantity=quantity, unit_price=unit_price, total=unit_price * quantity,
        status="pending", payment_method="mock",
    )
    db.session.add(booking)
    db.session.commit()
    return jsonify({"ok": True, "data": {
        "id": booking.id, "total": float(booking.total), "unit_price": float(booking.unit_price), "status": booking.status,
    }, "error": None}), 201


@bp.get("/orders")
@login_required_api
def orders_list():
    bookings = Booking.query.filter_by(user_id=current_user.id).order_by(Booking.created_at.desc(), Booking.id.desc()).all()
    return ok([_order_data(booking) for booking in bookings])


@bp.post("/bookings/<int:booking_id>/pay")
@login_required_api
def bookings_pay(booking_id):
    updated = Booking.query.filter_by(
        id=booking_id, user_id=current_user.id, status="pending"
    ).update({"status": "paid"}, synchronize_session=False)
    if updated:
        db.session.commit()
        return ok({"id": booking_id, "status": "paid"})

    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.user_id != current_user.id:
        return fail("not_found", t("订单不存在"), 404)
    if booking.status == "paid":
        return fail("already_paid", t("订单已支付"), 409)
    return fail("invalid_status", t("订单当前不可支付"), 409)


@bp.post("/itinerary/generate")
def itinerary_generate():
    data = request.get_json(silent=True) or {}
    ids, days = data.get("attraction_ids"), data.get("days")
    if not isinstance(ids, list) or isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 5:
        return fail("invalid_params", t("行程参数不正确"))
    if any(isinstance(value, bool) or not isinstance(value, int) for value in ids):
        return fail("invalid_params", t("行程参数不正确"))
    ids = list(dict.fromkeys(ids))
    if not 1 <= len(ids) <= 8:
        return fail("invalid_params", t("行程参数不正确"))
    attractions = Attraction.query.filter(Attraction.id.in_(ids), Attraction.status == "published").all()
    if len(attractions) != len(ids):
        return fail("invalid_params", t("行程参数不正确"))
    return ok({"days": generate_itinerary(attractions, days)})


@bp.post("/itinerary/ai-plan")
def itinerary_ai_plan():
    """出发点 / 是否住宿 / 预算 / 景点 / 天数 → DeepSeek 生成完整行程；失败回退规则草案。"""
    data = request.get_json(silent=True) or {}
    ids, days = data.get("attraction_ids"), data.get("days")
    origin = str(data.get("origin") or "").strip()[:40]
    start_date = str(data.get("start_date") or "").strip()[:10]
    need_stay = data.get("need_stay", True)
    need_stay = bool(need_stay) if isinstance(need_stay, bool) else str(need_stay).lower() not in ("0", "false", "no")
    budget_raw = data.get("budget", 0)
    budget = budget_raw if isinstance(budget_raw, int) and not isinstance(budget_raw, bool) else 0
    budget = max(0, min(budget, 200000))

    if not isinstance(ids, list) or isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 5:
        return fail("invalid_params", t("行程参数不正确"))
    if any(isinstance(value, bool) or not isinstance(value, int) for value in ids):
        return fail("invalid_params", t("行程参数不正确"))
    ids = list(dict.fromkeys(ids))
    if not 1 <= len(ids) <= 8:
        return fail("invalid_params", t("行程参数不正确"))

    attractions = Attraction.query.filter(Attraction.id.in_(ids), Attraction.status == "published").all()
    if len(attractions) != len(ids):
        return fail("invalid_params", t("行程参数不正确"))

    plan = plan_with_llm(attractions, days, origin, need_stay, start_date, budget)
    if plan is not None:
        return ok(plan)

    # 回退：规则草案（结构与 AI 一致，前端只认一种）
    ordered = sorted(attractions, key=lambda item: (item.city or "", -float(item.rating or 0), item.id))
    fallback_days = []
    for index in range(days):
        group = ordered[index * 2:index * 2 + 2]
        slots = []
        for label, attraction in zip(("上午", "下午"), group):
            slots.append({
                "period": label,
                "title": attr_field(attraction, "name"),
                "slug": attraction.slug,
                "city": city_label(attraction.city),
                "detail": "",
            })
        if slots:
            slots.append({"period": "晚上", "title": t("自由安排"), "slug": "", "city": "", "detail": ""})
        fallback_days.append({
            "day": index + 1,
            "theme": "",
            "slots": slots,
            "tips": "",
        })

    cities = list(dict.fromkeys(item["city"] for item in fallback_days[0]["slots"] if item.get("city"))) if fallback_days else []
    return ok({
        "source": "rule",
        "summary": t("AI 暂不可用，已按城市和评分生成基础草案。"),
        "transport": "",
        "route": cities,
        "weather": "",
        "clothing": "",
        "lodging": t("需要安排住宿") if need_stay else t("无需住宿，当日往返"),
        "budget_plan": [{"item": t("人均预算"), "amount": f"￥{budget}"}] if budget else [],
        "days": fallback_days,
        "notes": [item for item in (
            f"{t('出发点')}：{origin}" if origin else "",
            f"{t('出发时间')}：{start_date}" if start_date else "",
        ) if item],
    })


def _coerce_budget(value, default=0):
    """预算入参：非负整数，非法值回默认，不抛异常。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(0, min(value, 200000))
    if isinstance(value, float):
        return max(0, min(int(value), 200000))
    if isinstance(value, str):
        try:
            return max(0, min(int(float(value.strip())), 200000))
        except ValueError:
            return default
    return default


def _coerce_people(value, default=2):
    """人数：0 合法（用于「先看人均」），非法值回默认 2。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return max(0, min(value, 50))
    if isinstance(value, float):
        return max(0, min(int(value), 50))
    if isinstance(value, str):
        try:
            return max(0, min(int(float(value.strip())), 50))
        except ValueError:
            return default
    return default


def _coerce_hotel_price(value, default=0):
    """房价：允许小数，负数/脏数据回 0（0 表示交给 lodging 文本或 300 兜底）。"""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 100000.0))
    if isinstance(value, str):
        try:
            return max(0.0, min(float(value.strip()), 100000.0))
        except ValueError:
            return default
    return default


@bp.post("/itinerary/conflicts")
def itinerary_conflicts():
    """只读：按契约检测行程冲突。任何异常都回空结果，绝不 500。"""
    try:
        data = request.get_json(silent=True) or {}
        days = data.get("days")
        if not isinstance(days, list) or len(days) > ANALYSIS_MAX_DAYS:
            return fail("invalid_params", t("行程参数不正确"))
        return ok(detect_conflicts(days, _coerce_budget(data.get("budget"))))
    except Exception:
        return ok({"conflicts": [], "count": 0})


@bp.post("/itinerary/precheck")
def itinerary_precheck():
    """只读：选择阶段预检（城市跨度 / 密度 / 门票占比）。任何异常都回空结果，绝不 500。"""
    empty = {"cities": [], "count": 0, "conflicts": []}
    try:
        data = request.get_json(silent=True) or {}
        ids, days = data.get("attraction_ids"), data.get("days")
        if not isinstance(ids, list) or isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= ANALYSIS_MAX_DAYS:
            return fail("invalid_params", t("行程参数不正确"))
        if any(isinstance(value, bool) or not isinstance(value, int) for value in ids):
            return fail("invalid_params", t("行程参数不正确"))
        ids = list(dict.fromkeys(ids))
        if not 1 <= len(ids) <= 8:
            return fail("invalid_params", t("行程参数不正确"))
        attractions = Attraction.query.filter(Attraction.id.in_(ids), Attraction.status == "published").all()
        if len(attractions) != len(ids):
            return fail("invalid_params", t("行程参数不正确"))
        # 按入参顺序回填，cities 的顺序才和用户勾选顺序一致
        by_id = {item.id: item for item in attractions}
        ordered = [by_id[item] for item in ids if item in by_id]
        return ok(precheck_selection(ordered, days, _coerce_budget(data.get("budget"))))
    except Exception:
        return ok(empty)


@bp.post("/itinerary/budget")
def itinerary_budget():
    """只读：按契约算出人均/总预算、分项与削减建议。异常回空结果，绝不 500。"""
    try:
        data = request.get_json(silent=True) or {}
        days = data.get("days")
        if not isinstance(days, list) or len(days) > ANALYSIS_MAX_DAYS:
            return fail("invalid_params", t("行程参数不正确"))
        return ok(build_budget(
            days,
            people=_coerce_people(data.get("people", 2)),
            budget=_coerce_budget(data.get("budget")),
            start_date=str(data.get("start_date") or "").strip()[:10],
            hotel_price=_coerce_hotel_price(data.get("hotel_price")),
        ))
    except Exception:
        return ok({
            "people": 0,
            "total_per_person": 0,
            "total_all": 0,
            "items": [],
            "cuts": [],
            "compare": {"budget": 0, "delta": 0, "status": "unknown"},
        })


@bp.post("/itinerary/hotels")
def itinerary_hotels():
    """行程落点 → 真实在售酒店。

    数据来自第三方公共代理（无需 Key），可能超时或挂掉：
    拿不到就返回空 + 一句可见提示，行程本身不受影响。
    """
    if _hotel_rate_limited():
        return fail("rate_limited", t("操作太频繁，请稍后再试"))
    data = request.get_json(silent=True) or {}
    day_cities = data.get("day_cities")
    start_date = str(data.get("start_date") or "").strip()[:10]
    budget_raw = data.get("budget", 0)
    budget = budget_raw if isinstance(budget_raw, int) and not isinstance(budget_raw, bool) else 0
    budget = max(0, min(budget, 200000))
    # 选了「需要安排住宿」就必须有住宿段；没传时按需要处理（老调用方行为不变）
    need_stay_raw = data.get("need_stay", True)
    need_stay = (
        need_stay_raw if isinstance(need_stay_raw, bool)
        else str(need_stay_raw).lower() not in ("0", "false", "no", "")
    )

    if not isinstance(day_cities, list) or not 1 <= len(day_cities) <= 6:
        return fail("invalid_params", t("行程参数不正确"))
    requested = [str(item or "").strip()[:20] for item in day_cities]

    # 只认库里真实存在的城市，避免把任意字符串当搜索词打到外部接口
    known = {row[0] for row in db.session.query(Attraction.city).distinct().all() if row[0]}
    cities = [city if city in known else "" for city in requested]

    # 「自由安排」那几天没有景点、也就没有落点：当晚仍住在上一座城，
    # 沿用前一天的城市。否则「1 个景点 + 3 天」会被算成只住 0 晚，
    # 住宿段整段被 _group_stays 丢掉，卡片就再也不出现。
    carried = ""
    filled = []
    for city in cities:
        if city:
            carried = city
        filled.append(city or carried)
    cities = filled

    if not any(cities):
        return ok({"source": "none", "stays": [], "note": ""})

    focus_map = {}
    for city in {item for item in cities if item}:
        best = (
            Attraction.query
            .filter(Attraction.city == city, Attraction.status == "published")
            .order_by(Attraction.rating.desc(), Attraction.id.asc())
            .first()
        )
        if best is not None:
            focus_map[city] = attr_field(best, "name")

    return ok(recommend_hotels(cities, focus_map, start_date, budget, need_stay=need_stay))


# ---------------- 住宿推荐限流 ----------------
_HOTEL_HITS = defaultdict(deque)


def _hotel_rate_limited():
    """同一 IP 60 秒内最多 20 次，保护第三方公共代理。"""
    limit = int(current_app.config.get("AI_RATE_LIMIT", 20) or 0)
    if limit <= 0:
        return False
    now = time.time()
    if len(_HOTEL_HITS) > 1000:
        for stale_key, hits in list(_HOTEL_HITS.items()):
            if not hits or now - hits[-1] > 120:
                _HOTEL_HITS.pop(stale_key, None)
    bucket = _HOTEL_HITS[request.remote_addr or ""]
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= limit:
        return True
    bucket.append(now)
    return False


@bp.post("/itineraries")
@login_required_api
def itineraries_create():
    data = request.get_json(silent=True) or {}
    title, days, items = data.get("title"), data.get("days"), data.get("items")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 120:
        return fail("invalid_params", t("行程参数不正确"))
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 5:
        return fail("invalid_params", t("行程参数不正确"))
    # items 可以是老结构的列表，也可以是新结构 {"brief": {...}, "days": [...]}
    if isinstance(items, dict):
        if not isinstance(items.get("days"), list):
            return fail("invalid_params", t("行程参数不正确"))
    elif not isinstance(items, list):
        return fail("invalid_params", t("行程参数不正确"))
    # 防重：同用户 + 同标题 + 内容一致 → 返回已有记录。
    # 必须放在翻译之前：重复保存不该再白花一次模型调用。
    # 比较时要排除 _en（存进去的会带英文缓存，新请求不会带，否则永远比不相等）。
    def _core(value):
        if isinstance(value, dict):
            return {key: item for key, item in value.items() if key != "_en"}
        return value

    core_items = _core(items)
    same_title = (
        Itinerary.query.filter_by(user_id=current_user.id, title=title.strip())
        .order_by(Itinerary.id.desc())
        .limit(5)
        .all()
    )
    for row in same_title:
        if _core(row.items) == core_items:
            return ok({"id": row.id, "duplicate": True})

    # 保存时就顺手把英文版翻好并缓存，之后英文站打开是秒开（否则首访要等模型翻译）
    if isinstance(items, dict) and not items.get("_en"):
        translated = translate_plan(
            {"brief": items.get("brief") or {}, "days": items.get("days") or []}, "en"
        )
        if translated and (translated.get("brief") or translated.get("days")):
            cached = {"brief": translated.get("brief") or {}, "days": translated.get("days") or []}
            raw_conflicts = (items.get("brief") or {}).get("conflicts")
            if raw_conflicts and not cached["brief"].get("conflicts"):
                conflicts_en = translate_conflicts(raw_conflicts, "en")
                if conflicts_en:
                    cached["brief"]["conflicts"] = conflicts_en
            items = dict(items, _en=cached)

    itinerary = Itinerary(user_id=current_user.id, title=title.strip(), days=days, items=items)
    db.session.add(itinerary)
    db.session.commit()
    return ok({"id": itinerary.id})


@bp.get("/itineraries")
@login_required_api
def itineraries_list():
    rows = Itinerary.query.filter_by(user_id=current_user.id).order_by(Itinerary.created_at.desc(), Itinerary.id.desc()).all()
    return ok([{"id": row.id, "title": row.title, "days": row.days, "items": row.items,
                "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows])


@bp.delete("/itineraries/<int:itinerary_id>")
@login_required_api
def itineraries_delete(itinerary_id):
    row = Itinerary.query.filter_by(id=itinerary_id, user_id=current_user.id).first()
    if row is None:
        return fail("not_found", t("行程不存在"), 404)
    db.session.delete(row)
    db.session.commit()
    return ok({"id": itinerary_id})


@bp.post("/bookings/<int:booking_id>/cancel")
@login_required_api
def bookings_cancel(booking_id):
    updated = Booking.query.filter_by(
        id=booking_id, user_id=current_user.id, status="pending"
    ).update({"status": "cancelled"}, synchronize_session=False)
    if updated:
        db.session.commit()
        return ok({"id": booking_id, "status": "cancelled"})

    booking = db.session.get(Booking, booking_id)
    if booking is None or booking.user_id != current_user.id:
        return fail("not_found", t("订单不存在"), 404)
    if booking.status == "cancelled":
        return fail("already_cancelled", t("订单已取消"), 409)
    if booking.status == "paid":
        return fail("cannot_cancel_paid", t("已支付订单不可取消"), 409)
    return fail("invalid_status", t("订单当前不可取消"), 409)
