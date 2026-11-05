"""评论区发图：上传校验 + 评论带图 + 外链拦截。"""
import io
import pathlib

import pytest
from PIL import Image

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Attraction, Comment, User


class SQLiteConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AI_API_KEY = ""      # 测试不真调 DeepSeek
    AI_BASE_URL = ""


def _png_bytes(size=(300, 200), color=(30, 70, 90)):
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


@pytest.fixture()
def comment_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
        user = User(username="user", password_hash="unused", role="user", status="active")
        admin = User(username="admin", password_hash="unused", role="admin", status="active")
        db.session.add_all([user, admin])
        db.session.flush()
        attraction = Attraction(
            slug="tmp-comment", name="评论测试景点", category="自然", city="贵阳",
            summary="s", description="d", cover_image="", longitude=106.6, latitude=26.6,
            status="published",
        )
        db.session.add(attraction)
        db.session.commit()
        ids = {"user": user.id, "admin": admin.id, "attraction": attraction.id}

    created_files = []
    with app.test_client() as client:
        yield client, ids, created_files
    with app.app_context():
        db.drop_all()
    for path in created_files:
        try:
            pathlib.Path(path).unlink()
        except OSError:
            pass


def _login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def test_upload_requires_login(comment_client):
    client, ids, _ = comment_client
    response = client.post("/api/comments/upload", data={"file": (_png_bytes(), "a.png")},
                           content_type="multipart/form-data")
    assert response.status_code in (401, 403)


def test_upload_rejects_non_image(comment_client):
    client, ids, _ = comment_client
    _login(client, ids["user"])
    response = client.post(
        "/api/comments/upload",
        data={"file": (io.BytesIO(b"not-an-image"), "a.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["ok"] is False


def test_upload_returns_static_url(comment_client):
    client, ids, created_files = comment_client
    _login(client, ids["user"])
    response = client.post(
        "/api/comments/upload",
        data={"file": (_png_bytes(), "a.png")},
        content_type="multipart/form-data",
    )
    data = response.get_json()["data"]
    assert response.status_code == 200
    assert data["url"].startswith("/static/uploads/comments/")
    assert data["url"].endswith(".jpg")

    stored = pathlib.Path(client.application.static_folder) / data["url"].replace("/static/", "")
    created_files.append(stored)
    assert stored.exists() and stored.stat().st_size > 0


def test_comment_can_carry_image_and_show_after_approval(comment_client):
    client, ids, created_files = comment_client
    _login(client, ids["user"])

    upload = client.post(
        "/api/comments/upload",
        data={"file": (_png_bytes(), "a.png")},
        content_type="multipart/form-data",
    ).get_json()["data"]["url"]
    stored = pathlib.Path(client.application.static_folder) / upload.replace("/static/", "")
    created_files.append(stored)

    created = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "看图说话", "image_url": upload,
    })
    assert created.status_code == 200
    comment_id = created.get_json()["data"]["id"]

    with client.application.app_context():
        comment = db.session.get(Comment, comment_id)
        assert comment.image_url == upload
        comment.status = "approved"
        db.session.commit()

    listing = client.get(f"/api/comments?attraction_id={ids['attraction']}").get_json()["data"]
    assert listing[0]["image_url"] == upload


def test_comment_allows_image_only(comment_client):
    client, ids, _ = comment_client
    _login(client, ids["user"])
    upload = client.post(
        "/api/comments/upload",
        data={"file": (_png_bytes(), "a.png")},
        content_type="multipart/form-data",
    ).get_json()["data"]["url"]

    response = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "", "image_url": upload,
    })
    assert response.status_code == 200

    with client.application.app_context():
        comment = db.session.get(Comment, response.get_json()["data"]["id"])
        assert comment.image_url == upload
        assert comment.content == ""


def test_comment_rejects_external_image_url(comment_client):
    client, ids, _ = comment_client
    _login(client, ids["user"])
    response = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "外链图片",
        "image_url": "https://evil.example.com/a.jpg",
    })
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_params"


def test_comment_rejects_path_traversal(comment_client):
    client, ids, _ = comment_client
    _login(client, ids["user"])
    response = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "越界",
        "image_url": "/static/uploads/comments/../../app.py",
    })
    assert response.status_code == 400


def test_delete_comment_removes_image_file(comment_client):
    """删评论时把孤儿配图一起删掉。"""
    client, ids, created_files = comment_client
    _login(client, ids["user"])

    upload = client.post(
        "/api/comments/upload",
        data={"file": (_png_bytes(), "a.png")},
        content_type="multipart/form-data",
    ).get_json()["data"]["url"]
    stored = pathlib.Path(client.application.static_folder) / upload.replace("/static/", "")
    created_files.append(stored)

    comment_id = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "带图评论", "image_url": upload,
    }).get_json()["data"]["id"]
    assert stored.exists()

    response = client.delete(f"/api/comments/{comment_id}")
    assert response.status_code == 200
    assert response.get_json()["data"]["file_removed"] is True
    assert not stored.exists()


def test_comments_expose_avatar(comment_client):
    """评论接口要带出用户头像地址（有头像时非空）。"""
    client, ids, created_files = comment_client

    with client.application.app_context():
        user = db.session.get(User, ids["user"])
        user.avatar_data = b"fake-jpeg-bytes"
        user.avatar_mime = "image/jpeg"
        user.avatar_version = 1
        attraction = db.session.get(Attraction, ids["attraction"])
        db.session.add(Comment(user_id=user.id, attraction_id=attraction.id,
                               content="带头像的评论", status="approved"))
        db.session.commit()

    listing = client.get(f"/api/comments?attraction_id={ids['attraction']}").get_json()["data"]
    assert listing
    assert listing[0]["avatar_url"] == f"/avatar/{ids['user']}?v=1"


def _approve_all(app):
    with app.app_context():
        for row in Comment.query.all():
            row.status = "approved"
        db.session.commit()


def test_reply_nested_under_parent(comment_client):
    """回复挂在主评论下面，列表返回 replies。"""
    client, ids, _ = comment_client
    _login(client, ids["user"])

    parent_id = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "主评论",
    }).get_json()["data"]["id"]

    with client.application.app_context():
        parent = db.session.get(Comment, parent_id)
        parent.status = "approved"
        db.session.commit()

    reply = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "回复一下", "parent_id": parent_id,
    })
    assert reply.status_code == 200
    assert reply.get_json()["data"]["parent_id"] == parent_id

    _approve_all(client.application)
    listing = client.get(f"/api/comments?attraction_id={ids['attraction']}").get_json()["data"]
    tops = [row for row in listing if row["parent_id"] is None]
    assert len(tops) >= 1
    target = next(row for row in tops if row["id"] == parent_id)
    assert any(item["content"] == "回复一下" for item in target["replies"])


def test_reply_rejects_unknown_or_nested_parent(comment_client):
    client, ids, _ = comment_client
    _login(client, ids["user"])

    bad = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "回复不存在的", "parent_id": 999999,
    })
    assert bad.status_code == 404

    parent_id = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "主评论2",
    }).get_json()["data"]["id"]
    with client.application.app_context():
        db.session.get(Comment, parent_id).status = "approved"
        db.session.commit()
    child_id = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "子回复", "parent_id": parent_id,
    }).get_json()["data"]["id"]

    deeper = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "回复的回复", "parent_id": child_id,
    })
    assert deeper.status_code == 400
    assert deeper.get_json()["error"]["code"] == "invalid_params"


def test_reply_requires_approved_parent(comment_client):
    client, ids, _ = comment_client
    _login(client, ids["user"])
    pending_id = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "还没过审",
    }).get_json()["data"]["id"]

    response = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "抢着回复", "parent_id": pending_id,
    })
    assert response.status_code == 400


def test_delete_parent_removes_replies(comment_client):
    client, ids, _ = comment_client
    _login(client, ids["user"])

    parent_id = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "会被删的主评论",
    }).get_json()["data"]["id"]
    with client.application.app_context():
        db.session.get(Comment, parent_id).status = "approved"
        db.session.commit()
    client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "跟着被删的回复", "parent_id": parent_id,
    })

    response = client.delete(f"/api/comments/{parent_id}")
    assert response.status_code == 200
    assert response.get_json()["data"]["replies_deleted"] == 1

    with client.application.app_context():
        assert Comment.query.filter_by(parent_id=parent_id).count() == 0


def test_ai_pass_publishes_immediately(comment_client, monkeypatch):
    """AI 判定没问题 → 直接 approved，并记录 review_by=ai。"""
    client, ids, _ = comment_client
    _login(client, ids["user"])
    monkeypatch.setattr("app.blueprints.api.review_comment",
                        lambda content, name="": {"verdict": "pass", "reason": "正常评论"})

    response = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "景色不错，值得一去",
    })
    data = response.get_json()["data"]
    assert data["status"] == "approved"
    assert data["auto_passed"] is True

    with client.application.app_context():
        comment = db.session.get(Comment, data["id"])
        assert comment.review_by == "ai"
        assert comment.ai_reason == "正常评论"


def test_ai_flag_goes_to_manual_review(comment_client, monkeypatch):
    """AI 存疑 → pending，保留 AI 理由给管理员看。"""
    client, ids, _ = comment_client
    _login(client, ids["user"])
    monkeypatch.setattr("app.blueprints.api.review_comment",
                        lambda content, name="": {"verdict": "flag", "reason": "疑似广告"})

    data = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "加微信 xxx 订票便宜",
    }).get_json()["data"]
    assert data["status"] == "pending"
    assert data["auto_passed"] is False
    assert data["ai_reason"] == "疑似广告"

    with client.application.app_context():
        comment = db.session.get(Comment, data["id"])
        assert comment.status == "pending"
        assert comment.ai_reason == "疑似广告"


def test_ai_unavailable_falls_back_to_manual(comment_client, monkeypatch):
    """AI 不可用（无 key/超时）→ 保守进人工审核。"""
    client, ids, _ = comment_client
    _login(client, ids["user"])
    monkeypatch.setattr("app.blueprints.api.review_comment",
                        lambda content, name="": {"verdict": "unavailable", "reason": "未配置 AI key"})

    data = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "普通评论一条",
    }).get_json()["data"]
    assert data["status"] == "pending"
    assert data["auto_passed"] is False


def test_manual_approval_marks_human(comment_client, monkeypatch):
    """管理员通过后 review_by 变成 human，后台列表带审核来源。"""
    client, ids, _ = comment_client
    _login(client, ids["admin"])
    monkeypatch.setattr("app.blueprints.api.review_comment",
                        lambda content, name="": {"verdict": "flag", "reason": "拿不准"})

    data = client.post("/api/comments", json={
        "attraction_id": ids["attraction"], "content": "需要人工看",
    }).get_json()["data"]

    response = client.post(f"/api/admin/comments/{data['id']}/approve", json={"action": "approve"})
    assert response.status_code == 200
    assert response.get_json()["data"]["review_by"] == "human"

    listing = client.get("/api/admin/comments?status=approved").get_json()["data"]
    row = next(item for item in listing if item["id"] == data["id"])
    assert row["review_by"] == "human"
    assert row["ai_reason"] == "拿不准"
