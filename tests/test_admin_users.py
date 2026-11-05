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


class CSRFConfig(SQLiteConfig):
    WTF_CSRF_ENABLED = True


@pytest.fixture()
def users_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
        admin = User(username="admin", password_hash="unused", role="admin", status="active")
        other_admin = User(username="other-admin", password_hash="unused", role="admin", status="active")
        user = User(username="user", password_hash="unused", role="user", status="active")
        disabled = User(username="disabled", password_hash="unused", role="user", status="disabled")
        db.session.add_all([admin, other_admin, user, disabled])
        db.session.commit()
        ids = {item.username: item.id for item in (admin, other_admin, user, disabled)}
    with app.test_client() as client:
        yield client, ids
    with app.app_context():
        db.drop_all()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def test_admin_can_disable_and_enable_user(users_client):
    client, ids = users_client
    _login(client, ids["admin"])

    assert client.post(f"/admin/users/{ids['user']}/status", data={"status": "disabled"}).status_code == 302
    with client.application.app_context():
        assert db.session.get(User, ids["user"]).status == "disabled"

    assert client.post(f"/admin/users/{ids['disabled']}/status", data={"status": "active"}).status_code == 302
    with client.application.app_context():
        assert db.session.get(User, ids["disabled"]).status == "active"


def test_admin_cannot_disable_self(users_client):
    client, ids = users_client
    _login(client, ids["admin"])

    assert client.post(f"/admin/users/{ids['admin']}/status", data={"status": "disabled"}).status_code == 302
    with client.application.app_context():
        assert db.session.get(User, ids["admin"]).status == "active"


def test_disabled_session_is_rejected(users_client):
    client, ids = users_client
    _login(client, ids["admin"])
    with client.application.app_context():
        db.session.get(User, ids["admin"]).status = "disabled"
        db.session.commit()

    response = client.get("/admin/users")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_admin_can_disable_other_admin_but_not_the_last(users_client):
    client, ids = users_client
    _login(client, ids["admin"])

    # Two active admins: disabling the other leaves one.
    assert client.post(f"/admin/users/{ids['other-admin']}/status", data={"status": "disabled"}).status_code == 302
    with client.application.app_context():
        assert db.session.get(User, ids["other-admin"]).status == "disabled"

    # The disabled admin's old session must no longer work.
    _login(client, ids["other-admin"])
    assert client.get("/admin/users").status_code == 302


def test_non_admin_cannot_post_user_status(users_client):
    client, ids = users_client
    _login(client, ids["user"])

    assert client.post(f"/admin/users/{ids['disabled']}/status", data={"status": "active"}).status_code == 403
    with client.application.app_context():
        assert db.session.get(User, ids["disabled"]).status == "disabled"


def test_missing_user_returns_404(users_client):
    client, ids = users_client
    _login(client, ids["admin"])

    assert client.post("/admin/users/99999/status", data={"status": "disabled"}).status_code == 404


def test_invalid_status_does_not_change_user(users_client):
    client, ids = users_client
    _login(client, ids["admin"])

    assert client.post(f"/admin/users/{ids['user']}/status", data={"status": "unknown"}).status_code == 302
    with client.application.app_context():
        assert db.session.get(User, ids["user"]).status == "active"


def test_anonymous_cannot_get_or_post_admin_users(users_client):
    client, ids = users_client

    get_response = client.get("/admin/users")
    assert get_response.status_code == 302
    assert "/auth/login" in get_response.headers["Location"]

    post_response = client.post(f"/admin/users/{ids['user']}/status", data={"status": "disabled"})
    assert post_response.status_code == 302
    assert "/auth/login" in post_response.headers["Location"]


def test_admin_users_page_renders_and_filters(users_client):
    client, ids = users_client
    _login(client, ids["admin"])

    response = client.get("/admin/users")
    assert response.status_code == 200
    assert "用户管理" in response.get_data(as_text=True)
    assert "other-admin" in response.get_data(as_text=True)

    filtered = client.get("/admin/users?role=admin&status=active")
    assert filtered.status_code == 200
    text = filtered.get_data(as_text=True)
    assert "other-admin" in text
    tbody = text.split("<tbody>")[1].split("</tbody>")[0]
    assert tbody.count("<tr>") == 2

    escaped = client.get("/admin/users?q=%25")
    assert escaped.status_code == 200
    assert "没有匹配的用户" in escaped.get_data(as_text=True)


def test_admin_users_page_clamps_page_and_paginates(users_client):
    client, ids = users_client
    _login(client, ids["admin"])
    with client.application.app_context():
        for index in range(20):
            db.session.add(User(username=f"bulk-{index}", password_hash="unused", role="user", status="active"))
        db.session.commit()

    page_two = client.get("/admin/users?page=2")
    assert page_two.status_code == 200
    assert "2 / 2" in page_two.get_data(as_text=True)

    clamped = client.get("/admin/users?page=999")
    assert clamped.status_code == 200
    assert "2 / 2" in clamped.get_data(as_text=True)

    bad = client.get("/admin/users?page=abc")
    assert bad.status_code == 200


def test_admin_users_escapes_nickname(users_client):
    client, ids = users_client
    _login(client, ids["admin"])
    with client.application.app_context():
        db.session.add(User(username="xss", nickname="<script>alert(1)</script>", password_hash="unused",
                            role="user", status="active"))
        db.session.commit()

    text = client.get("/admin/users").get_data(as_text=True)
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in text
    assert "<script>alert(1)</script>" not in text


def test_csrf_required_for_status_post():
    app = create_app(CSRFConfig)
    with app.app_context():
        db.create_all()
        admin = User(username="csrf-admin", password_hash="unused", role="admin", status="active")
        target = User(username="csrf-target", password_hash="unused", role="user", status="active")
        db.session.add_all([admin, target])
        db.session.commit()
        admin_id, target_id = admin.id, target.id
    with app.test_client() as client:
        with client.session_transaction() as session:
            session["_user_id"] = str(admin_id)
            session["_fresh"] = True
        response = client.post(f"/admin/users/{target_id}/status", data={"status": "disabled"})
        assert response.status_code == 400
    with app.app_context():
        db.drop_all()
