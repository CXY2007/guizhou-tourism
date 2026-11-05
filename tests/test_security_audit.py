from datetime import date

import pytest

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Attraction, AttractionTranslation, Favorite, User, ViewLog


class SQLiteConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}


@pytest.fixture()
def sec_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
        user = User(username="sec-user", password_hash="unused", role="user", status="active")
        attraction = Attraction(slug="sec-spot", name="测试景点", category="自然", city="贵阳", status="published")
        db.session.add_all([user, attraction])
        db.session.flush()
        db.session.add(AttractionTranslation(
            attraction_id=attraction.id, lang="en", name="Test Spot", summary="English summary",
            description="English description", address="Guiyang", open_time="09:00-17:00",
        ))
        db.session.add(Favorite(user_id=user.id, attraction_id=attraction.id))
        db.session.add(ViewLog(id=1, user_id=user.id, attraction_id=attraction.id, view_date=date.today()))
        db.session.commit()
        ids = {"user": user.id, "attraction": attraction.id}
    with app.test_client() as client:
        yield client, ids
    with app.app_context():
        db.drop_all()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def test_comment_rejects_boolean_attraction_id(sec_client):
    client, ids = sec_client
    _login(client, ids["user"])
    response = client.post("/api/comments", json={"attraction_id": True, "content": "hello"})
    assert response.status_code == 400


def test_comment_rejects_non_string_content(sec_client):
    client, ids = sec_client
    _login(client, ids["user"])
    response = client.post("/api/comments", json={"attraction_id": ids["attraction"], "content": 123})
    assert response.status_code == 400


def test_rating_rejects_boolean_id_or_rating(sec_client):
    client, ids = sec_client
    _login(client, ids["user"])
    assert client.post("/api/ratings", json={"attraction_id": True, "rating": 5}).status_code == 400
    assert client.post("/api/ratings", json={"attraction_id": ids["attraction"], "rating": True}).status_code == 400


def test_profile_rejects_non_string_nickname(sec_client):
    client, ids = sec_client
    _login(client, ids["user"])
    assert client.put("/api/profile", json={"nickname": 1}).status_code == 400


def test_favorite_status_missing_attraction_returns_404(sec_client):
    client, ids = sec_client
    _login(client, ids["user"])
    response = client.get("/api/favorites/99999/status")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_favorites_localized_in_english(sec_client):
    client, ids = sec_client
    _login(client, ids["user"])
    client.get("/?lang=en", follow_redirects=True)

    data = client.get("/api/favorites").get_json()["data"]

    assert data[0]["name"] == "Test Spot"
    assert data[0]["city"] == "Guiyang"
    assert data[0]["category"] == "Nature"


def test_history_localized_in_english(sec_client):
    client, ids = sec_client
    _login(client, ids["user"])
    client.get("/?lang=en", follow_redirects=True)

    data = client.get("/api/history").get_json()["data"]

    assert data[0]["name"] == "Test Spot"
    assert data[0]["city"] == "Guiyang"
