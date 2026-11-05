import pytest
from flask import session

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Attraction, AttractionTranslation
from app.services import llm_assistant
from app.services.llm_assistant import answer_with_llm, llm_available, run_tool


class SQLiteConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AI_API_KEY = "test-key"
    AI_BASE_URL = "https://example.invalid"
    AI_MODEL = "deepseek-chat"


@pytest.fixture()
def llm_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
        db.session.add(Attraction(
            slug="test-spot", name="测试景点", category="自然", city="贵阳",
            summary="测试简介", description="测试详情", status="published", rating=4.5,
        ))
        db.session.commit()
    with app.test_client() as client:
        yield app, client
    with app.app_context():
        db.drop_all()


def test_navigate_tool_rejects_admin_and_external(llm_client):
    app, _ = llm_client
    with app.test_request_context("/"):
        assert run_tool("navigate", {"path": "/attractions/test-spot"})["ok"] is True
        assert run_tool("navigate", {"path": "/itinerary"})["ok"] is True
        assert run_tool("navigate", {"path": "/admin"})["ok"] is False
        assert run_tool("navigate", {"path": "//evil.example"})["ok"] is False


def test_search_tool_returns_attractions(llm_client):
    app, _ = llm_client
    with app.test_request_context("/"):
        result = run_tool("search_attractions", {"query": "测试"})
        assert result["ok"] is True
        assert result["items"][0]["slug"] == "test-spot"


def test_search_tool_matches_red_culture_category(llm_client):
    app, _ = llm_client
    with app.app_context():
        db.session.add(Attraction(
            slug="red-spot", name="红色景点", category="红色文化", city="遵义",
            summary="红色文化测试", status="published", rating=4.8,
        ))
        db.session.commit()

    with app.test_request_context("/"):
        category = run_tool("search_attractions", {"category": "红色"})
        english = run_tool("search_attractions", {"category": "red"})

    assert [item["slug"] for item in category["items"]] == ["red-spot"]
    assert [item["slug"] for item in english["items"]] == ["red-spot"]


def test_llm_navigate_tool_flow(llm_client, monkeypatch):
    app, _ = llm_client
    responses = [
        {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "call-1", "type": "function", "function": {"name": "navigate", "arguments": '{"path":"/itinerary"}'}}
        ]}}]},
        {"choices": [{"message": {"content": "Opening the itinerary page."}}]},
    ]
    monkeypatch.setattr(llm_assistant, "_chat", lambda messages, tool_choice="auto": responses.pop(0))

    with app.test_request_context("/?lang=en"):
        result = answer_with_llm("plan a trip")

    assert result["intent"] == "llm"
    assert result["action"] == {"type": "navigate", "url": "/itinerary"}
    assert result["reply"] == "Opening the itinerary page."


def test_llm_search_tool_flow(llm_client, monkeypatch):
    app, _ = llm_client
    responses = [
        {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "call-2", "type": "function", "function": {"name": "search_attractions", "arguments": '{"query":"测试"}'}}
        ]}}]},
        {"choices": [{"message": {"content": "Found one."}}]},
    ]
    monkeypatch.setattr(llm_assistant, "_chat", lambda messages, tool_choice="auto": responses.pop(0))

    with app.test_request_context("/?lang=en"):
        result = answer_with_llm("find a spot")

    assert result["links"] == [{"name": "测试景点", "url": "/attractions/test-spot"}]


def test_llm_failure_returns_none(llm_client, monkeypatch):
    app, _ = llm_client
    monkeypatch.setattr(llm_assistant, "_chat", lambda messages, tool_choice="auto": None)
    with app.test_request_context("/"):
        assert answer_with_llm("hello") is None


def test_llm_unavailable_without_key(llm_client):
    app, _ = llm_client
    app.config["AI_API_KEY"] = ""
    with app.test_request_context("/"):
        assert llm_available() is False
        assert answer_with_llm("hello") is None


def test_api_falls_back_to_rules_when_llm_fails(llm_client, monkeypatch):
    app, client = llm_client
    monkeypatch.setattr(llm_assistant, "_chat", lambda messages, tool_choice="auto": None)

    response = client.post("/api/assistant", json={"message": "带我去测试景点", "session_id": "test"})

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["intent"] == "navigate"
    assert data["action"]["url"] == "/attractions/test-spot"


def test_english_names_resolve_in_search_and_fact(llm_client):
    app, _ = llm_client
    with app.app_context():
        attraction = Attraction.query.first()
        db.session.add(AttractionTranslation(
            attraction_id=attraction.id, lang="en", name="Test Spot", summary="A test spot",
        ))
        db.session.commit()

    with app.test_request_context("/?lang=en"):
        session["lang"] = "en"
        fact = run_tool("get_attraction_fact", {"name": "Test Spot", "field": "ticket"})
        search = run_tool("search_attractions", {"query": "Test Spot"})
        slug_fact = run_tool("get_attraction_fact", {"name": "test spot ticket", "field": "ticket"})

    assert fact["ok"] is True and fact["name"] == "Test Spot"
    assert search["ok"] is True and search["items"][0]["slug"] == "test-spot"
    assert slug_fact["ok"] is True


def test_llm_markup_reply_is_retried_as_plain_text(llm_client, monkeypatch):
    app, _ = llm_client
    responses = [
        {"choices": [{"message": {"content": '<｜｜DSML｜｜ calls>\n<｜｜DSML｜｜ invoke name="get_attraction">'}}]},
        {"choices": [{"message": {"content": "Zunyi Conference Site is free to visit."}}]},
    ]
    monkeypatch.setattr(llm_assistant, "_chat", lambda messages, tool_choice="auto": responses.pop(0))

    with app.test_request_context("/?lang=en"):
        result = answer_with_llm("is the red site free?")

    assert result["reply"] == "Zunyi Conference Site is free to visit."


def test_llm_persistent_markup_falls_back(llm_client, monkeypatch):
    app, _ = llm_client
    markup = '<｜｜DSML｜｜ calls><｜｜DSML｜｜ invoke name="get_attraction">'
    responses = [
        {"choices": [{"message": {"content": markup}}]},
        {"choices": [{"message": {"content": markup}}]},
    ]
    monkeypatch.setattr(llm_assistant, "_chat", lambda messages, tool_choice="auto": responses.pop(0))

    with app.test_request_context("/?lang=en"):
        assert answer_with_llm("is the red site free?") is None


def test_llm_three_round_chain_keeps_action_and_links(llm_client, monkeypatch):
    app, _ = llm_client
    responses = [
        {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "call-1", "type": "function", "function": {"name": "search_attractions", "arguments": '{"query":"测试"}'}}
        ]}}]},
        {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "call-2", "type": "function", "function": {"name": "navigate", "arguments": '{"path":"/attractions/test-spot"}'}}
        ]}}]},
        {"choices": [{"message": {"content": "On my way."}}]},
    ]
    monkeypatch.setattr(llm_assistant, "_chat", lambda messages, tool_choice="auto": responses.pop(0))

    with app.test_request_context("/?lang=en"):
        result = answer_with_llm("take me to the test spot")

    assert result["reply"] == "On my way."
    assert result["action"] == {"type": "navigate", "url": "/attractions/test-spot"}
    assert result["links"] == [{"name": "测试景点", "url": "/attractions/test-spot"}]


def test_llm_forces_text_reply_after_round_limit(llm_client, monkeypatch):
    app, _ = llm_client
    calls = []
    tool_call = {"choices": [{"message": {"content": None, "tool_calls": [
        {"id": "call-x", "type": "function", "function": {"name": "search_attractions", "arguments": '{"query":"测试"}'}}
    ]}}]}

    def fake_chat(messages, tool_choice="auto"):
        calls.append(tool_choice)
        if tool_choice == "none":
            return {"choices": [{"message": {"content": "Here is what I found."}}]}
        return tool_call

    monkeypatch.setattr(llm_assistant, "_chat", fake_chat)
    with app.test_request_context("/?lang=en"):
        result = answer_with_llm("find the test spot")

    assert result["reply"] == "Here is what I found."
    assert calls.count("auto") == llm_assistant.MAX_TOOL_ROUNDS
    assert calls[-1] == "none"


class _FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_chat_posts_openai_compatible_payload(llm_client, monkeypatch):
    app, _ = llm_client
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured.update(url=url, headers=headers, payload=json, timeout=timeout)
        return _FakeResponse({"choices": [{"message": {"content": "Hi there."}}]})

    monkeypatch.setattr(llm_assistant.requests, "post", fake_post)
    with app.test_request_context("/?lang=en"):
        result = answer_with_llm("hello")

    assert result["reply"] == "Hi there."
    assert captured["url"] == "https://example.invalid/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["payload"]["model"] == "deepseek-chat"
    assert captured["payload"]["tools"] == llm_assistant.TOOLS
    assert captured["payload"]["tool_choice"] == "auto"
    assert captured["timeout"] == 15


def test_fact_tool_returns_fields(llm_client):
    app, _ = llm_client
    with app.test_request_context("/"):
        ticket = run_tool("get_attraction_fact", {"name": "测试景点", "field": "ticket"})
        rating = run_tool("get_attraction_fact", {"name": "测试景点", "field": "rating"})
        missing = run_tool("get_attraction_fact", {"name": "不存在", "field": "ticket"})

    assert ticket["ok"] is True and ticket["value"]
    assert rating["ok"] is True and rating["value"].startswith("4.5")
    assert missing["ok"] is False


def test_plan_tool_builds_days_and_links(llm_client):
    app, _ = llm_client
    with app.test_request_context("/"):
        result = run_tool("plan_itinerary", {"days": 2})

    assert result["ok"] is True
    assert len(result["days"]) == 2
    assert result["links"] == [{"name": "测试景点", "url": "/attractions/test-spot"}]


def test_weather_tool_uses_service_and_rejects_bool(llm_client, monkeypatch):
    app, _ = llm_client
    fake = {
        "live": {"text": "阴", "temp": "12", "humidity": "90"},
        "forecast": [{"fxDate": "2026-10-30", "textDay": "阴", "textNight": "阴", "tempMax": "20", "tempMin": "13"}],
    }
    monkeypatch.setattr(llm_assistant, "get_weather", lambda city, code: fake)
    with app.app_context():
        attraction_id = Attraction.query.first().id

    with app.test_request_context("/"):
        result = run_tool("get_weather", {"attraction_id": attraction_id})
        rejected = run_tool("get_weather", {"attraction_id": True})

    assert result["ok"] is True and result["name"] == "测试景点"
    assert result["advice"]
    assert rejected["ok"] is False


def test_assistant_rate_limit_returns_429(llm_client):
    app, client = llm_client
    app.config["AI_RATE_LIMIT"] = 3
    app.config["AI_API_KEY"] = ""
    payload = {"message": "你好", "session_id": "rate-limit-session"}

    for _ in range(3):
        assert client.post("/api/assistant", json=payload).status_code == 200

    response = client.post("/api/assistant", json=payload)
    assert response.status_code == 429
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "rate_limited"
