from datetime import datetime
from urllib.parse import urlsplit

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import generate_password_hash

from ..extensions import db
from ..i18n import t
from ..models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")


def _safe_next(target: str | None) -> str:
    if not target:
        return url_for("public.home")
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return url_for("public.home")
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("public.home"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            flash(t("用户名或密码错误"), "error")
        elif not user.is_active:
            flash(t("账号已被禁用"), "error")
        else:
            login_user(user, remember=True)
            user.last_login = datetime.utcnow()
            db.session.commit()
            return redirect(_safe_next(request.args.get("next")))

    return render_template("auth/login.html")


@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("public.home"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""

        if len(username) < 3 or len(username) > 20:
            flash(t("登录名长度需为 3–20 个字符"), "error")
        elif len(password) < 6:
            flash(t("密码至少 6 位"), "error")
        elif password != confirm:
            flash(t("两次输入的密码不一致"), "error")
        elif User.query.filter_by(username=username).first():
            flash(t("登录名已被占用，请换一个"), "error")
        else:
            user = User(username=username,
                        password_hash=generate_password_hash(password), role="user")
            db.session.add(user)
            db.session.commit()
            flash(t("注册成功，请登录"), "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash(t("已退出登录"), "success")
    return redirect(url_for("public.home"))
