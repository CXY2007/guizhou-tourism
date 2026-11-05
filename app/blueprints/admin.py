import os
import threading
import uuid
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import func, or_

from ..decorators import admin_required
from ..extensions import db
from ..i18n import attr_field, t
from ..models import (
    Attraction,
    AttractionImage,
    AttractionTranslation,
    Booking,
    Comment,
    Favorite,
    Rating,
    TrafficDaily,
    User,
    ViewLog,
)
from ..services.traffic import summary

bp = Blueprint("admin", __name__, url_prefix="/admin")
_ADMIN_STATUS_LOCK = threading.Lock()


@bp.get("/comments")
@admin_required
def comments():
    return render_template("admin/comments.html")


@bp.get("/users")
@admin_required
def users():
    q = (request.args.get("q") or "").strip()
    status = request.args.get("status") or ""
    role = request.args.get("role") or ""
    page = max(1, request.args.get("page", 1, type=int) or 1)

    query = User.query
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(or_(
            User.username.ilike(f"%{escaped}%", escape="\\"),
            User.nickname.ilike(f"%{escaped}%", escape="\\"),
        ))
    if status in ("active", "disabled"):
        query = query.filter_by(status=status)
    if role in ("user", "admin"):
        query = query.filter_by(role=role)

    total = query.count()
    pages = max(1, (total + 19) // 20)
    page = min(page, pages)
    items = query.order_by(User.created_at.desc(), User.id.desc()).offset((page - 1) * 20).limit(20).all()
    return render_template("admin/users.html", users=items, total=total, q=q, status=status,
                           role=role, page=page, pages=pages)


def _users_redirect():
    q = (request.form.get("back_q") or "").strip()
    status = request.form.get("back_status") or ""
    role = request.form.get("back_role") or ""
    page = request.form.get("back_page", 1, type=int) or 1
    return redirect(url_for("admin.users", q=q or None, status=status or None, role=role or None, page=page))


@bp.post("/users/<int:user_id>/status")
@admin_required
def user_status(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        return t("用户不存在"), 404

    status = request.form.get("status")
    if status not in ("active", "disabled"):
        flash(t("状态不合法"), "error")
    elif user.id == current_user.id and status == "disabled":
        flash(t("不能禁用自己"), "error")
    elif status == "disabled" and user.role == "admin" and user.status == "active":
        # Serialize within this process and lock active admin rows for multi-process safety.
        with _ADMIN_STATUS_LOCK:
            active_admins = User.query.filter_by(role="admin", status="active").with_for_update().all()
            if len(active_admins) <= 1:
                flash(t("不能禁用最后一个管理员"), "error")
            else:
                user.status = status
                db.session.commit()
                flash(t("用户状态已更新"), "success")
    else:
        user.status = status
        db.session.commit()
        flash(t("用户状态已更新"), "success")
    return _users_redirect()


@bp.get("")
@admin_required
def dashboard():
    return render_template("admin/dashboard.html", counts={"attractions": Attraction.query.count(), "pending_comments": Comment.query.filter_by(status="pending").count(), "orders": Booking.query.count(), "users": User.query.count()})


@bp.get("/traffic")
@admin_required
def traffic():
    days = request.args.get("days", type=int) or 30
    days = 7 if days < 7 else (90 if days > 90 else days)
    data = summary(days=days)
    return render_template("admin/traffic.html", data=data)


def _reference_counts(attraction_ids):
    """每个景点有多少关联数据，用来在删除确认里写清楚要删什么。"""
    counts = {attraction_id: {"ratings": 0, "comments": 0, "favorites": 0, "bookings": 0, "views": 0, "traffic": 0, "images": 0}
              for attraction_id in attraction_ids}
    if not attraction_ids:
        return counts

    def bump(model, key):
        rows = (
            db.session.query(model.attraction_id, func.count(model.id))
            .filter(model.attraction_id.in_(attraction_ids))
            .group_by(model.attraction_id)
            .all()
        )
        for attraction_id, total in rows:
            if attraction_id in counts:
                counts[attraction_id][key] = int(total or 0)

    bump(Rating, "ratings")
    bump(Comment, "comments")
    bump(Favorite, "favorites")
    bump(Booking, "bookings")
    bump(ViewLog, "views")
    bump(TrafficDaily, "traffic")
    bump(AttractionImage, "images")
    return counts


@bp.get("/attractions")
@admin_required
def attractions():
    q, status = (request.args.get("q") or "").strip(), request.args.get("status") or ""
    query = Attraction.query
    if q:
        escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(or_(
            Attraction.name.ilike(f"%{escaped}%", escape="\\"),
            Attraction.city.ilike(f"%{escaped}%", escape="\\"),
        ))
    if status in ("draft", "published"):
        query = query.filter_by(status=status)
    items = query.order_by(Attraction.created_at.desc(), Attraction.id.desc()).all()
    return render_template("admin/attractions.html", items=items, total=len(items), q=q, status=status,
                           refs=_reference_counts([item.id for item in items]))


@bp.get("/attractions/new")
@admin_required
def attraction_new():
    return render_template("admin/attraction_form.html", attraction=None)


FIELDS = ("slug", "name", "summary", "description", "category", "city", "region", "price", "open_time", "ticket_note", "visit_duration", "best_months", "transport", "tips", "address", "lng", "lat", "cover_image", "status")


def _values(form):
    values = {field: (form.get(field) or "").strip() for field in FIELDS}
    values["seasonal"] = "seasonal" in form
    values["tags"] = [tag.strip() for tag in (form.get("tags") or "").split(",") if tag.strip()]
    return values


def _validate(values, attraction=None):
    if not values["slug"] or not values["name"]:
        return t("Slug 和名称必填")
    duplicate = Attraction.query.filter_by(slug=values["slug"]).first()
    if duplicate and (attraction is None or duplicate.id != attraction.id):
        return t("Slug 已存在")
    if values["category"] not in ("\u81ea\u7136", "\u4eba\u6587", "\u7ea2\u8272", "\u79d1\u6280", "\u5b63\u8282"):
        return t("分类不合法")
    if values["status"] not in ("draft", "published"):
        return t("状态不合法")
    # 数字逐项校验：报错必须点名是哪一格，否则「数字格式不正确」让人无从下手
    try:
        price = Decimal(values["price"] or "0")
    except (InvalidOperation, TypeError, ValueError):
        return t("票价必须是数字")
    if price < 0:
        return t("票价不能为负")
    if values["visit_duration"]:
        try:
            int(values["visit_duration"])
        except (TypeError, ValueError):
            return t("游玩时长必须是整数")
    if not values["lng"] or not values["lat"]:
        return t("经度/纬度必填")
    try:
        lng = float(values["lng"])
    except (TypeError, ValueError):
        return t("经度必须是数字（例：106.7134）")
    try:
        lat = float(values["lat"])
    except (TypeError, ValueError):
        return t("纬度必须是数字（例：26.5783）")
    if not -180 <= lng <= 180:
        return t("经度超出范围（-180 ~ 180）")
    if not -90 <= lat <= 90:
        return t("纬度超出范围（-90 ~ 90）")


def _save(attraction, values):
    fields = {"slug": values["slug"], "name": values["name"], "summary": values["summary"], "description": values["description"], "category": values["category"], "city": values["city"], "region": values["region"], "price": Decimal(values["price"] or "0"), "open_time": values["open_time"], "ticket_note": values["ticket_note"], "visit_duration": int(values["visit_duration"] or 0), "best_months": values["best_months"], "seasonal": values["seasonal"], "transport": values["transport"], "address": values["address"], "tips": values["tips"], "longitude": float(values["lng"]) if values["lng"] else None, "latitude": float(values["lat"]) if values["lat"] else None, "cover_image": values["cover_image"], "tags": values["tags"], "status": values["status"]}
    for key, value in fields.items():
        setattr(attraction, key, value)


ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


def _looks_like_image(data, ext):
    if ext == "png":
        return data.startswith(b"\x89PNG\r\n\x1a\n")
    if ext in ("jpg", "jpeg"):
        return data.startswith(b"\xff\xd8")
    if ext == "webp":
        return len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    return False


def _save_upload(file, slug):
    if not file or not file.filename:
        return None
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        return None
    data = file.read()
    if not data or len(data) > MAX_UPLOAD_BYTES or not _looks_like_image(data, ext):
        return None
    folder = os.path.join(current_app.static_folder, "uploads", "attractions", slug)
    os.makedirs(folder, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(folder, filename), "wb") as handle:
        handle.write(data)
    return f"/static/uploads/attractions/{slug}/{filename}"


def _process_uploads(attraction):
    warnings = 0
    cover = request.files.get("cover_file")
    if cover and cover.filename:
        url = _save_upload(cover, attraction.slug)
        if url:
            attraction.cover_image = url
            db.session.add(AttractionImage(attraction_id=attraction.id, image_url=url, sort_order=-1))
        else:
            warnings += 1
    for file in request.files.getlist("images"):
        if not file or not file.filename:
            continue
        url = _save_upload(file, attraction.slug)
        if not url:
            warnings += 1
            continue
        order = (db.session.query(func.max(AttractionImage.sort_order)).filter_by(attraction_id=attraction.id).scalar() or 0) + 1
        db.session.add(AttractionImage(attraction_id=attraction.id, image_url=url, sort_order=order))
    return warnings


def _form(attraction=None):
    values = _values(request.form)
    error = _validate(values, attraction)
    if error:
        flash(error, "error")
        # 回填：表单字段名是 lng/lat，模型属性是 longitude/latitude，
        # 这里补齐别名，模板就能用同一套写法渲染「已填内容」而不是空白表单
        shown = dict(values)
        shown["longitude"] = values["lng"]
        shown["latitude"] = values["lat"]
        return render_template("admin/attraction_form.html", attraction=attraction, values=shown), 400
    if attraction is None:
        attraction = Attraction()
        db.session.add(attraction)
    _save(attraction, values)
    db.session.flush()
    warnings = _process_uploads(attraction)
    db.session.commit()
    flash(t("景点已保存"), "success")
    if warnings:
        flash(t("部分图片未上传：格式或大小不符合"), "error")
    return redirect(url_for("admin.attractions"))


@bp.post("/attractions/new")
@admin_required
def attraction_create():
    return _form()


@bp.route("/attractions/<int:attraction_id>/edit", methods=["GET", "POST"])
@admin_required
def attraction_edit(attraction_id):
    attraction = db.session.get(Attraction, attraction_id)
    if attraction is None:
        return t("景点不存在"), 404
    return _form(attraction) if request.method == "POST" else render_template("admin/attraction_form.html", attraction=attraction)


@bp.post("/attractions/<int:attraction_id>/status")
@admin_required
def attraction_status(attraction_id):
    attraction = db.session.get(Attraction, attraction_id)
    if attraction is None:
        return t("景点不存在"), 404
    status = request.form.get("status")
    if status not in ("draft", "published"):
        flash(t("状态不合法"), "error")
    elif status == "published" and not all((attraction.name, attraction.summary, attraction.description, attraction.cover_image)):
        flash(t("发布前请补全名称、简介、详情与封面"), "error")
    else:
        attraction.status = status
        db.session.commit()
        flash(t("状态已更新"), "success")
    return redirect(url_for("admin.attractions"))


@bp.post("/attractions/<int:attraction_id>/delete")
@admin_required
def attraction_delete(attraction_id):
    """彻底删除：景点本身 + 所有关联数据（评分/评论/收藏/订单/足迹/流量/翻译/图集）。"""
    attraction = db.session.get(Attraction, attraction_id)
    if attraction is None:
        return t("景点不存在"), 404

    name = attraction.name
    image_urls = [row.image_url for row in AttractionImage.query.filter_by(attraction_id=attraction_id).all()]
    comment_images = [
        row[0] for row in db.session.query(Comment.image_url)
        .filter(Comment.attraction_id == attraction_id, Comment.image_url.isnot(None)).all()
    ]

    removed = {
        "ratings": Rating.query.filter_by(attraction_id=attraction_id).delete(synchronize_session=False),
        "comments": Comment.query.filter_by(attraction_id=attraction_id).delete(synchronize_session=False),
        "favorites": Favorite.query.filter_by(attraction_id=attraction_id).delete(synchronize_session=False),
        "bookings": Booking.query.filter_by(attraction_id=attraction_id).delete(synchronize_session=False),
        "views": ViewLog.query.filter_by(attraction_id=attraction_id).delete(synchronize_session=False),
        "traffic": TrafficDaily.query.filter_by(attraction_id=attraction_id).delete(synchronize_session=False),
        "translations": AttractionTranslation.query.filter_by(attraction_id=attraction_id).delete(synchronize_session=False),
        "images": AttractionImage.query.filter_by(attraction_id=attraction_id).delete(synchronize_session=False),
    }
    db.session.delete(attraction)
    db.session.commit()

    files = _remove_orphan_images(image_urls)
    files += _remove_orphan_images(comment_images)
    flash(
        t("已彻底删除")
        + f"「{name}」"
        + t("评分 {r} · 评论 {c} · 收藏 {f} · 订单 {b} · 足迹 {v} · 流量 {tr} · 图片 {im} · 删除文件 {fi} 个").format(
            r=removed["ratings"], c=removed["comments"], f=removed["favorites"], b=removed["bookings"],
            v=removed["views"], tr=removed["traffic"], im=removed["images"], fi=files,
        ),
        "success",
    )
    return redirect(url_for("admin.attractions"))


def _remove_orphan_images(image_urls):
    """删掉只属于这个景点的本地图片文件；仍被别处引用的跳过。返回删除个数。"""
    removed = 0
    for url in image_urls:
        if not url or not url.startswith("/static/"):
            continue
        still_used = (
            AttractionImage.query.filter_by(image_url=url).first() is not None
            or Attraction.query.filter_by(cover_image=url).first() is not None
        )
        if still_used:
            continue
        path = os.path.join(current_app.static_folder, url[len("/static/"):])
        try:
            os.remove(path)
            removed += 1
        except OSError:
            pass
    return removed


@bp.post("/attractions/<int:attraction_id>/images/<int:image_id>/delete")
@admin_required
def image_delete(attraction_id, image_id):
    attraction = db.session.get(Attraction, attraction_id)
    image = db.session.get(AttractionImage, image_id)
    if attraction is None or image is None or image.attraction_id != attraction_id:
        return t("图片不存在"), 404
    if image.image_url.startswith("/static/"):
        path = os.path.join(current_app.static_folder, image.image_url[len("/static/"):])
        try:
            os.remove(path)
        except OSError:
            pass
    was_cover = attraction.cover_image == image.image_url
    db.session.delete(image)
    db.session.flush()
    if was_cover:
        first = AttractionImage.query.filter_by(attraction_id=attraction_id).order_by(AttractionImage.sort_order, AttractionImage.id).first()
        attraction.cover_image = first.image_url if first else ""
    db.session.commit()
    flash(t("图片已删除"), "success")
    return redirect(url_for("admin.attraction_edit", attraction_id=attraction_id))


@bp.get("/orders")
@admin_required
def orders():
    payload = []
    for row in Booking.query.order_by(Booking.created_at.desc(), Booking.id.desc()).all():
        attraction, user = db.session.get(Attraction, row.attraction_id), db.session.get(User, row.user_id)
        payload.append({"id": row.id, "user": user.display_name if user else "", "attraction": attr_field(attraction, "name") if attraction else "", "visit_date": row.visit_date, "quantity": row.quantity, "total": float(row.total), "status": row.status, "created_at": row.created_at})
    return render_template("admin/orders.html", orders=payload)
