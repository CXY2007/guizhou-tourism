"""后台「彻底删除景点」：景点本身 + 全部关联数据都真的从库里消失。"""
from datetime import date

import pytest

from app import create_app
from app.config import Config
from app.extensions import db
import io
import pathlib

from PIL import Image

from app.models import (
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


class SQLiteConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}


@pytest.fixture()
def delete_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
        admin = User(username="admin", password_hash="unused", role="admin", status="active")
        user = User(username="user", password_hash="unused", role="user", status="active")
        db.session.add_all([admin, user])
        db.session.flush()

        attraction = Attraction(
            slug="tmp-attraction", name="测试景点", category="自然", city="贵阳",
            summary="s", description="d", cover_image="/static/images/none.jpg",
            longitude=106.6, latitude=26.6, status="published",
        )
        db.session.add(attraction)
        db.session.flush()

        db.session.add_all([
            AttractionImage(attraction_id=attraction.id, image_url="/static/images/none.jpg"),
            AttractionTranslation(attraction_id=attraction.id, lang="en", name="Test"),
            Rating(attraction_id=attraction.id, user_id=user.id, rating=5),
            Comment(attraction_id=attraction.id, user_id=user.id, content="很好", status="approved"),
            Favorite(attraction_id=attraction.id, user_id=user.id),
            Booking(attraction_id=attraction.id, user_id=user.id, visit_date=date.today(),
                    quantity=2, unit_price=100, total=200, status="paid"),
            ViewLog(attraction_id=attraction.id, user_id=user.id, view_date=date.today()),
            TrafficDaily(attraction_id=attraction.id, day=date.today(), views=3, visitors=2),
        ])
        db.session.commit()
        ids = {"admin": admin.id, "attraction": attraction.id}

    with app.test_client() as client:
        yield client, ids
    with app.app_context():
        db.drop_all()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


@pytest.mark.parametrize("model", [
    AttractionImage, AttractionTranslation, Rating,
    Comment, Favorite, Booking, ViewLog, TrafficDaily,
])
def test_delete_removes_every_related_row(delete_client, model):
    client, ids = delete_client
    _login(client, ids["admin"])
    attraction_id = ids["attraction"]

    with client.application.app_context():
        assert model.query.filter_by(attraction_id=attraction_id).count() == 1

    response = client.post(f"/admin/attractions/{attraction_id}/delete")
    assert response.status_code == 302

    with client.application.app_context():
        assert model.query.filter_by(attraction_id=attraction_id).count() == 0


def test_delete_removes_the_attraction_itself(delete_client):
    client, ids = delete_client
    _login(client, ids["admin"])

    client.post(f"/admin/attractions/{ids['attraction']}/delete")

    with client.application.app_context():
        assert db.session.get(Attraction, ids["attraction"]) is None


def test_delete_reports_what_was_removed(delete_client):
    client, ids = delete_client
    _login(client, ids["admin"])

    with client.session_transaction() as session:
        previous = session.get("_flashes") or []

    client.post(f"/admin/attractions/{ids['attraction']}/delete")

    with client.session_transaction() as session:
        flashes = session.get("_flashes") or []
    messages = [text for _, text in flashes]
    assert any("已彻底删除" in text for text in messages)
    assert any("订单 1" in text for text in messages)
    assert previous is not None


def test_delete_missing_attraction_returns_404(delete_client):
    client, ids = delete_client
    _login(client, ids["admin"])
    response = client.post("/admin/attractions/999999/delete")
    assert response.status_code == 404


def test_delete_removes_comment_images(delete_client, tmp_path):
    """彻底删除景点时，评论配图文件也要删掉。"""
    client, ids = delete_client
    _login(client, ids["admin"])
    attraction_id = ids["attraction"]

    folder = pathlib.Path(client.application.static_folder) / "uploads" / "comments"
    folder.mkdir(parents=True, exist_ok=True)
    image_path = folder / "del-test.jpg"
    Image.new("RGB", (40, 40), (10, 20, 30)).save(image_path, format="JPEG")
    url = "/static/uploads/comments/del-test.jpg"

    with client.application.app_context():
        comment = Comment.query.filter_by(attraction_id=attraction_id).first()
        comment.image_url = url
        db.session.commit()
    assert image_path.exists()

    client.post(f"/admin/attractions/{attraction_id}/delete")

    assert not image_path.exists()
