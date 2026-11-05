from functools import wraps

from flask import abort, redirect, request, url_for
from flask_login import current_user

from .i18n import t


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login", next=request.full_path))
        if not current_user.is_admin:
            abort(403, description=t("你不是管理员，无法进入后台"))
        return view(*args, **kwargs)

    return wrapped
