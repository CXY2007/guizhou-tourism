import base64
import io
import pathlib
import shutil
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Attraction, AttractionImage, Booking, User


class SQLiteConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}


@pytest.fixture()
def d3d_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
        user = User(username="d3d-user", password_hash="unused", role="user")
        other = User(username="d3d-other", password_hash="unused", role="user")
        admin = User(username="d3d-admin", password_hash="unused", role="admin")
        first = Attraction(slug="first", name="First", summary="Summary", description="Description", cover_image="/first.jpg",
                           category="自然", city="贵阳", rating=Decimal("4.0"), price=Decimal("20.00"), status="published")
        second = Attraction(slug="second", name="Second", summary="Summary", description="Description", cover_image="/second.jpg",
                            category="人文", city="遵义", rating=Decimal("5.0"), price=Decimal("0"), status="published")
        draft = Attraction(slug="draft", name="Draft", category="自然", city="贵阳", status="draft")
        db.session.add_all([user, other, admin, first, second, draft])
        db.session.commit()
        ids = {"user": user.id, "other": other.id, "admin": admin.id, "first": first.id, "second": second.id, "draft": draft.id}
    with app.test_client() as client:
        yield client, ids
    with app.app_context():
        db.drop_all()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def test_booking_create_pay_duplicate_and_owner_access(d3d_client):
    client, ids = d3d_client
    _login(client, ids["user"])
    created = client.post("/api/bookings", json={"attraction_id": ids["first"], "visit_date": (date.today() + timedelta(days=1)).isoformat(), "quantity": 2})
    assert created.status_code == 201, created.get_data(as_text=True)
    payload = created.get_json()["data"]
    assert payload["total"] == 40 and payload["unit_price"] == 20 and payload["status"] == "pending"
    booking_id = payload["id"]
    assert client.post(f"/api/bookings/{booking_id}/pay").status_code == 200
    duplicate = client.post(f"/api/bookings/{booking_id}/pay")
    assert duplicate.status_code == 409
    assert duplicate.get_json()["error"]["code"] == "already_paid"
    orders = client.get("/api/orders").get_json()["data"]
    assert orders[0]["id"] == booking_id and orders[0]["status"] == "paid"

    with client.application.app_context():
        booking = db.session.get(Booking, booking_id)
        foreign_id = booking.id
    _login(client, ids["other"])
    assert client.post(f"/api/bookings/{foreign_id}/pay").status_code == 404
    assert client.post("/api/bookings/99999/pay").status_code == 404


def test_booking_rejects_invalid_dates_quantities_and_unpublished_attractions(d3d_client):
    client, ids = d3d_client
    _login(client, ids["user"])
    for payload in (
        {"attraction_id": ids["first"], "visit_date": "2026-1-1", "quantity": 1},
        {"attraction_id": ids["first"], "visit_date": (date.today() - timedelta(days=1)).isoformat(), "quantity": 1},
        {"attraction_id": ids["first"], "visit_date": date.today().isoformat(), "quantity": 11},
        {"attraction_id": ids["draft"], "visit_date": date.today().isoformat(), "quantity": 1},
    ):
        assert client.post("/api/bookings", json=payload).status_code in (400, 404)


def test_itinerary_generate_sorts_groups_and_rejects_invalid_params(d3d_client):
    client, ids = d3d_client
    response = client.post("/api/itinerary/generate", json={"attraction_ids": [ids["first"], ids["second"], ids["first"]], "days": 2})
    assert response.status_code == 200, response.get_data(as_text=True)
    days = response.get_json()["data"]["days"]
    assert days[0]["morning"]["id"] == ids["first"]
    assert days[0]["afternoon"]["id"] == ids["second"]
    assert days[0]["evening"] is None and days[1]["morning"] is None
    invalid = client.post("/api/itinerary/generate", json={"attraction_ids": [ids["first"], ids["draft"]], "days": 1})
    assert invalid.status_code == 400
    assert invalid.get_json()["error"]["code"] == "invalid_params"


def test_itinerary_generate_accepts_single_attraction(d3d_client):
    """只勾 1 个景点也能生成（产品决策：不再要求 2 个起）。"""
    client, ids = d3d_client
    response = client.post("/api/itinerary/generate",
                           json={"attraction_ids": [ids["first"]], "days": 1})
    assert response.status_code == 200, response.get_data(as_text=True)
    days = response.get_json()["data"]["days"]
    assert days[0]["morning"]["id"] == ids["first"]

    # 一个都没选仍然拒绝：下限从 2 降到 1，不是取消下限
    empty = client.post("/api/itinerary/generate", json={"attraction_ids": [], "days": 1})
    assert empty.status_code == 400
    assert empty.get_json()["error"]["code"] == "invalid_params"


def test_admin_access_and_attraction_post_actions(d3d_client):
    client, ids = d3d_client
    response = client.get("/admin")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]
    _login(client, ids["user"])
    denied = client.get("/admin")
    assert denied.status_code == 403
    assert "管理员" in denied.get_data(as_text=True)

    _login(client, ids["admin"])
    form = {"slug": "new-spot", "name": "New spot", "summary": "A summary", "description": "Details", "category": "\u81ea\u7136",
            "city": "贵阳", "price": "12.50", "visit_duration": "3", "lng": "106.7", "lat": "26.6",
            "tags": "water, forest", "status": "draft"}
    created = client.post("/admin/attractions/new", data=form)
    assert created.status_code == 302, created.get_data(as_text=True)
    with client.application.app_context():
        attraction = Attraction.query.filter_by(slug="new-spot").one()
        new_id = attraction.id
        assert attraction.tags == ["water", "forest"] and attraction.visit_duration == 3
    edited = client.post(f"/admin/attractions/{new_id}/edit", data={**form, "name": "Edited spot", "price": "18"})
    assert edited.status_code == 302
    with client.application.app_context():
        assert db.session.get(Attraction, new_id).name == "Edited spot"
    assert client.post(f"/admin/attractions/{new_id}/delete").status_code == 302
    with client.application.app_context():
        assert db.session.get(Attraction, new_id) is None
    with client.application.app_context():
        db.session.add(Booking(user_id=ids["user"], attraction_id=ids["first"], visit_date=date.today(), quantity=1,
                               unit_price=Decimal("20"), total=Decimal("20"), status="pending"))
        db.session.commit()
    # 彻底删除：即使有订单，也连同景点与订单一起从库里删掉
    assert client.post(f"/admin/attractions/{ids['first']}/delete").status_code == 302
    with client.application.app_context():
        assert db.session.get(Attraction, ids["first"]) is None
        assert Booking.query.filter_by(attraction_id=ids["first"]).count() == 0


def test_admin_upload_and_delete_cover(d3d_client):
    client, ids = d3d_client
    _login(client, ids["admin"])
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z3YwAAAAASUVORK5CYII="
    )
    form = {
        "slug": "first", "name": "First", "category": "自然", "city": "贵阳",
        "price": "20", "status": "published", "visit_duration": "3",
        "lng": "106.7", "lat": "26.6",
    }
    response = client.post(
        f"/admin/attractions/{ids['first']}/edit",
        data={**form, "cover_file": (io.BytesIO(png), "cover.png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 302, response.get_data(as_text=True)

    with client.application.app_context():
        image = AttractionImage.query.filter_by(attraction_id=ids["first"]).first()
        assert image is not None
        image_id = image.id
        upload_url = image.image_url
    upload_path = pathlib.Path(client.application.static_folder) / upload_url.replace("/static/", "", 1)
    assert upload_path.exists()

    assert client.post(f"/admin/attractions/{ids['first']}/images/{image_id}/delete").status_code == 302
    assert not upload_path.exists()
    shutil.rmtree(upload_path.parent, ignore_errors=True)
