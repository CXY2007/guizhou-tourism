from datetime import datetime, timedelta

import pytest

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Attraction, Rating, User
from app.blueprints import api


class SQLiteConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}


@pytest.fixture()
def d3c_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
        attraction = Attraction(slug="test-spot", name="测试景点", category="自然", city="贵阳")
        users = [User(username=f"d3c-test-{index}", password_hash="unused") for index in range(3)]
        db.session.add_all([attraction, *users])
        db.session.flush()
        for user, value, days_ago in zip(users, (5, 3, 4), (2, 9, 70)):
            db.session.add(Rating(
                user_id=user.id,
                attraction_id=attraction.id,
                rating=value,
                created_at=datetime.utcnow() - timedelta(days=days_ago),
            ))
        db.session.commit()
        attraction_id = attraction.id
    with app.test_client() as client:
        yield client, attraction_id
    with app.app_context():
        db.drop_all()


def test_attraction_stats_returns_distribution_and_recent_month_averages(d3c_client):
    client, attraction_id = d3c_client

    response = client.get(f"/api/attractions/{attraction_id}/stats")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["pie"] == [
        {"rating": 1, "count": 0},
        {"rating": 2, "count": 0},
        {"rating": 3, "count": 1},
        {"rating": 4, "count": 1},
        {"rating": 5, "count": 1},
    ]
    # 趋势口径已从「按周」改成「按月」：样本落在 2 / 9 / 70 天前，
    # 正常情况下跨 3 个自然月；正好压在月初时可能只有 2 个，所以不断言死。
    assert len(data["weeks"]) == len(data["averages"])
    assert 2 <= len(data["weeks"]) <= 3
    assert all("月" in label for label in data["weeks"])
    assert data["total"] == 3
    assert data["avg"] == 4.0


@pytest.mark.parametrize("path", [
    "/api/attractions/99999/stats",
    "/api/weather/99999",
])
def test_d3c_endpoints_return_not_found_for_missing_attraction(d3c_client, path):
    client, _ = d3c_client

    response = client.get(path)

    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_weather_endpoint_formats_monkeypatched_service_response(d3c_client, monkeypatch):
    client, attraction_id = d3c_client
    monkeypatch.setattr(api, "get_weather", lambda city, weather_code: {
        "city": city,
        "live": {
            "text": "小雨", "temp": "18", "humidity": "80",
            "windDir": "东风", "windScale": "2", "obsTime": "2026-10-29T10:00+08:00",
        },
        "forecast": [{
            "fxDate": "2026-10-30", "textDay": "小雨",
            "textNight": "阴", "tempMax": "20", "tempMin": "14",
        }],
    })

    response = client.get(f"/api/weather/{attraction_id}")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["city"] == "贵阳"
    assert data["live"]["temperature"] == "18"
    assert data["forecast"][0]["date"] == "2026-10-30"
    assert data["forecast"][0]["week"] == "周五"
    assert data["advice"]
    assert data["source"] == "hefeng"


def test_weather_week_localized_en(d3c_client, monkeypatch):
    client, attraction_id = d3c_client
    monkeypatch.setattr(api, "get_weather", lambda city, weather_code: {
        "city": city,
        "live": {"text": "小雨", "temp": "18", "humidity": "80", "windDir": "东风", "windScale": "2"},
        "forecast": [{"fxDate": "2026-10-30", "textDay": "小雨", "textNight": "阴", "tempMax": "20", "tempMin": "14"}],
    })
    client.get("/?lang=en", follow_redirects=True)

    data = client.get(f"/api/weather/{attraction_id}").get_json()["data"]

    assert data["forecast"][0]["week"] == "Fri"


def test_weather_numeric_week_is_localized(d3c_client, monkeypatch):
    client, attraction_id = d3c_client
    monkeypatch.setattr(api, "get_weather", lambda city, weather_code: {
        "city": city,
        "live": {"text": "晴", "temp": "20", "humidity": "50", "windDir": "东风", "windScale": "2"},
        "forecast": [{"fxDate": "2026-10-30", "week": "5", "textDay": "晴", "textNight": "晴", "tempMax": "22", "tempMin": "12"}],
    })

    data = client.get(f"/api/weather/{attraction_id}").get_json()["data"]

    assert data["forecast"][0]["week"] == "周五"
