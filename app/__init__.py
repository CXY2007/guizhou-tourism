from datetime import datetime
from urllib.parse import urlencode

from flask import Flask, flash, redirect, render_template, request, session, url_for

from .config import Config
from .extensions import babel, csrf, db, login_manager
from .i18n import EN, SUPPORTED, attr_field, category_label, city_label, current_lang, lang_url, price_text, region_label, t


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    login_manager.init_app(app)
    babel.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message = None

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        user = db.session.get(User, int(user_id))
        return user if user is not None and user.is_active else None

    @login_manager.unauthorized_handler
    def unauthorized():
        flash(t("请先登录"), "info")
        target = request.full_path
        if target.endswith("?"):
            target = target[:-1]
        return redirect(url_for("auth.login", next=target))

    from .blueprints.admin import bp as admin_bp
    from .blueprints.api import bp as api_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.public import bp as public_bp
    from .blueprints.user import bp as user_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.before_request
    def apply_language():
        lang = request.args.get("lang")
        if lang not in SUPPORTED:
            return None
        session["lang"] = lang
        args = request.args.to_dict(flat=True)
        args.pop("lang", None)
        target = request.path
        if args:
            target = f"{target}?{urlencode(args)}"
        return redirect(target)

    @app.context_processor
    def inject_globals():
        return {
            "current_year": datetime.now().year,
            "site_name": t("贵州文旅"),
            "t": t,
            "attr_field": attr_field,
            "category_label": category_label,
            "city_label": city_label,
            "region_label": region_label,
            "price_text": price_text,
            "current_lang": current_lang,
            "lang_url": lang_url,
            "i18n": EN if current_lang() == "en" else {},
        }

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(error):
        message = getattr(error, "description", None) or t("没有权限访问这个页面")
        return render_template("errors/403.html", message=message), 403

    # 静态资源缓存策略：图片长缓存，CSS/JS 每次校验（改完刷新即生效）
    long_cache_suffixes = {"jpg", "jpeg", "png", "webp", "svg", "ico", "woff", "woff2", "ttf"}

    @app.after_request
    def static_cache_headers(response):
        if not request.path.startswith("/static/"):
            return response
        suffix = request.path.rsplit(".", 1)[-1].lower()
        if suffix in long_cache_suffixes:
            response.cache_control.no_cache = None
            response.cache_control.public = True
            response.cache_control.max_age = 30 * 24 * 60 * 60
        elif suffix in {"css", "js"}:
            response.cache_control.public = True
            response.cache_control.max_age = 0
            response.cache_control.must_revalidate = True
        return response

    return app
