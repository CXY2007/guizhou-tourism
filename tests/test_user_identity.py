"""用户名（登录名）唯一 + 显示名可重名，每个人有独立 UID。"""
import pytest

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import User


class SQLiteConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AI_API_KEY = ""
    AI_BASE_URL = ""


@pytest.fixture()
def identity_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
    with app.test_client() as client:
        yield client
    with app.app_context():
        db.drop_all()


def _register(client, username):
    """注册只需要登录名 + 密码；显示名默认等于登录名，之后在个人中心改。"""
    return client.post("/auth/register", data={
        "username": username,
        "password": "secret123", "confirm_password": "secret123",
    }, follow_redirects=False)


def _set_nickname(client, username, nickname):
    """登录后通过 /api/profile 改显示名。"""
    from app.models import User as _User

    with client.application.app_context():
        uid = _User.query.filter_by(username=username).first().id
    with client.session_transaction() as session:
        session["_user_id"] = str(uid)
        session["_fresh"] = True
    return client.put("/api/profile", json={"nickname": nickname})


def test_display_name_defaults_to_login_name(identity_client):
    """注册只需登录名：显示名默认就是登录名。"""
    assert _register(identity_client, "alice01").status_code in (302, 200)

    with identity_client.application.app_context():
        alice = User.query.filter_by(username="alice01").first()
        assert alice and alice.nickname is None
        assert alice.display_name == "alice01"


def test_same_display_name_allowed_with_distinct_uids(identity_client):
    """注册后各自设置同一个显示名 → 都成功，UID 不同。"""
    assert _register(identity_client, "alice02").status_code in (302, 200)
    assert _register(identity_client, "bob02").status_code in (302, 200)
    assert _set_nickname(identity_client, "alice02", "旅行者").status_code == 200
    assert _set_nickname(identity_client, "bob02", "旅行者").status_code == 200

    with identity_client.application.app_context():
        alice = User.query.filter_by(username="alice02").first()
        bob = User.query.filter_by(username="bob02").first()
        assert alice and bob
        assert alice.display_name == bob.display_name == "旅行者"
        assert alice.id != bob.id


def test_duplicate_login_name_rejected(identity_client):
    _register(identity_client, "carol03")
    response = _register(identity_client, "carol03")
    with identity_client.application.app_context():
        assert User.query.filter_by(username="carol03").count() == 1


def test_profile_can_take_name_of_another_user(identity_client):
    _register(identity_client, "dave04")
    _register(identity_client, "erin05")
    _set_nickname(identity_client, "dave04", "甲")

    with identity_client.application.app_context():
        erin = User.query.filter_by(username="erin05").first()
        erin_id = erin.id

    with identity_client.session_transaction() as session:
        session["_user_id"] = str(erin_id)
        session["_fresh"] = True

    response = identity_client.put("/api/profile", json={"nickname": "甲"})
    assert response.status_code == 200
    assert response.get_json()["data"]["display_name"] == "甲"
    assert response.get_json()["data"]["uid"] == erin_id


def test_nickname_length_limited(identity_client):
    with identity_client.application.app_context():
        user = User(username="frank06", password_hash="unused", role="user", status="active")
        db.session.add(user)
        db.session.commit()
        uid = user.id

    with identity_client.session_transaction() as session:
        session["_user_id"] = str(uid)
        session["_fresh"] = True

    too_long = identity_client.put("/api/profile", json={"nickname": "名" * 31})
    assert too_long.status_code == 400


def test_admin_users_page_shows_uid(identity_client):
    with identity_client.application.app_context():
        admin = User(username="root", password_hash="unused", role="admin", status="active")
        member = User(username="member01", nickname="旅行者", password_hash="unused", role="user", status="active")
        db.session.add_all([admin, member])
        db.session.commit()
        ids = {"admin": admin.id, "member": member.id}

    with identity_client.session_transaction() as session:
        session["_user_id"] = str(ids["admin"])
        session["_fresh"] = True

    page = identity_client.get("/admin/users").get_data(as_text=True)
    assert f"#{ids['admin']}" in page
    assert f"#{ids['member']}" in page
    assert "旅行者" in page
