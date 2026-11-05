import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402


class TestConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    AI_API_KEY = ""  # 冒烟测试只走规则引擎，不依赖真实模型


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.test_client() as client:
        yield client


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True


def test_home_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "贵州".encode("utf-8") in r.data


def test_attractions_list(client):
    r = client.get("/attractions")
    assert r.status_code == 200
    assert "探索景点".encode("utf-8") in r.data


def test_attractions_red_category_matches_db_value(client):
    r = client.get("/attractions?category=红色")
    assert r.status_code == 200
    assert "遵义会议会址".encode("utf-8") in r.data


def test_attraction_detail(client):
    r = client.get("/attractions/huangguoshu")
    assert r.status_code == 200
    assert "黄果树".encode("utf-8") in r.data


def test_login_page(client):
    r = client.get("/auth/login")
    assert r.status_code == 200
    assert b"<form" in r.data


def test_unknown_returns_404(client):
    r = client.get("/attractions/not-exist")
    assert r.status_code == 404


def test_profile_requires_login(client):
    r = client.get("/profile")
    assert r.status_code == 302
    assert "/auth/login" in r.headers["Location"]


def test_admin_page_requires_login(client):
    r = client.get("/admin/comments")
    assert r.status_code == 302
    assert "/auth/login" in r.headers["Location"]


def test_api_requires_login(client):
    r = client.get("/api/favorites")
    assert r.status_code == 401
    assert r.get_json()["error"]["code"] == "login_required"


def test_api_comment_validation(client):
    r = client.post("/api/comments", json={"attraction_id": 1, "content": ""})
    assert r.status_code == 401


def test_assistant_navigate(client):
    r = client.post("/api/assistant", json={"message": "带我去黄果树", "session_id": "test"})
    assert r.status_code == 200
    data = r.get_json()["data"]
    assert data["intent"] == "navigate"
    assert data["action"]["url"] == "/attractions/huangguoshu"


def test_assistant_price(client):
    r = client.post("/api/assistant", json={"message": "黄果树门票多少", "session_id": "test"})
    data = r.get_json()["data"]
    assert data["intent"] == "qa"
    assert "160" in data["reply"]


def test_assistant_category(client):
    r = client.post("/api/assistant", json={"message": "找红色景点", "session_id": "test"})
    data = r.get_json()["data"]
    assert data["intent"] == "search"
    assert "category=" in data["action"]["url"]


def test_assistant_itinerary(client):
    r = client.post("/api/assistant", json={"message": "帮我排 3 天行程", "session_id": "test"})
    data = r.get_json()["data"]
    assert data["intent"] == "itinerary"
    assert len(data["links"]) >= 4


def test_assistant_pending_spot(client):
    r = client.post("/api/assistant", json={"message": "带我去小七孔", "session_id": "test"})
    data = r.get_json()["data"]
    assert data["intent"] == "navigate"
    assert data["action"]["url"] == "/attractions/xiaoqikong"


def test_language_switch_en_and_back(client):
    r = client.get("/?lang=en", follow_redirects=True)
    assert r.status_code == 200
    assert b"Guizhou Tourism" in r.data
    r = client.get("/attractions/huangguoshu")
    assert b"Huangguoshu Waterfall" in r.data
    client.get("/?lang=zh", follow_redirects=True)
    r = client.get("/")
    assert "贵州".encode("utf-8") in r.data


def test_api_error_localized_en(client):
    client.get("/?lang=en", follow_redirects=True)
    r = client.get("/api/favorites")
    assert r.status_code == 401
    assert r.get_json()["error"]["message"] == "Please sign in"


def test_auth_flash_localized_en(client):
    client.get("/?lang=en", follow_redirects=True)
    r = client.post("/auth/login", data={"username": "nobody", "password": "wrong"}, follow_redirects=True)
    assert "Incorrect username or password" in r.get_data(as_text=True)


def test_login_required_flash_localized_en(client):
    client.get("/?lang=en", follow_redirects=True)
    r = client.get("/profile", follow_redirects=True)
    assert "Please sign in" in r.get_data(as_text=True)


def test_assistant_rejects_non_string_payload(client):
    assert client.post("/api/assistant", json={"message": 1}).status_code == 400
    assert client.post("/api/assistant", json={"message": "hello", "session_id": []}).status_code == 400
