from datetime import date
from decimal import Decimal

import pytest

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Attraction, Booking, User


class SQLiteConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}


@pytest.fixture()
def booking_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
        user = User(username="booking-user", password_hash="unused", role="user")
        other = User(username="booking-other", password_hash="unused", role="user")
        attraction = Attraction(slug="booking-place", name="Booking place", category="自然", status="published")
        db.session.add_all([user, other, attraction])
        db.session.commit()
        pending = Booking(
            user_id=user.id, attraction_id=attraction.id, visit_date=date.today(), quantity=1,
            unit_price=Decimal("10"), total=Decimal("10"), status="pending",
        )
        paid = Booking(
            user_id=user.id, attraction_id=attraction.id, visit_date=date.today(), quantity=1,
            unit_price=Decimal("10"), total=Decimal("10"), status="paid",
        )
        db.session.add_all([pending, paid])
        db.session.commit()
        ids = {"user": user.id, "other": other.id, "pending": pending.id, "paid": paid.id}
    with app.test_client() as client:
        yield client, ids
    with app.app_context():
        db.drop_all()


def _login(client, user_id):
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True


def _status(client, booking_id):
    with client.application.app_context():
        return db.session.get(Booking, booking_id).status


def test_pending_booking_can_be_cancelled_once(booking_client):
    client, ids = booking_client
    _login(client, ids["user"])

    response = client.post(f"/api/bookings/{ids['pending']}/cancel")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["data"] == {"id": ids["pending"], "status": "cancelled"}
    assert _status(client, ids["pending"]) == "cancelled"

    response = client.post(f"/api/bookings/{ids['pending']}/cancel")
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["code"] == "already_cancelled"
    assert error["message"] == "订单已取消"
    assert _status(client, ids["pending"]) == "cancelled"


def test_paid_booking_cannot_be_cancelled(booking_client):
    client, ids = booking_client
    _login(client, ids["user"])

    response = client.post(f"/api/bookings/{ids['paid']}/cancel")
    assert response.status_code == 409
    error = response.get_json()["error"]
    assert error["code"] == "cannot_cancel_paid"
    assert error["message"] == "已支付订单不可取消"
    assert _status(client, ids["paid"]) == "paid"


def test_booking_cancel_requires_owner(booking_client):
    client, ids = booking_client
    _login(client, ids["other"])

    response = client.post(f"/api/bookings/{ids['pending']}/cancel")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"
    assert _status(client, ids["pending"]) == "pending"


def test_booking_cancel_missing_booking(booking_client):
    client, ids = booking_client
    _login(client, ids["user"])

    response = client.post("/api/bookings/999999/cancel")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "not_found"


def test_booking_cancel_requires_login(booking_client):
    client, ids = booking_client

    response = client.post(f"/api/bookings/{ids['pending']}/cancel")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "login_required"
    assert _status(client, ids["pending"]) == "pending"
