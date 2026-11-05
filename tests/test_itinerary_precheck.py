"""选点预检（team task-7 契约）+ budget 人数回显。

覆盖契约里的固定阈值：跨城 >100km、密度 > days×3、门票 > 预算一半；
外加 400 分支、异常兜底、只读、英文文案与耗时。
"""
import re
import time

import pytest

from app import create_app
from app.blueprints import api as api_module
from app.config import Config
from app.extensions import db
from app.models import Attraction
from app.services import itinerary_analysis as analysis


class SQLiteConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AI_API_KEY = ""


@pytest.fixture()
def seeded_app():
    """建库 + 真实量级的贵州数据；整个用例期间压着 app context，纯函数可直接读库。"""
    app = create_app(SQLiteConfig)
    context = app.app_context()
    context.push()
    try:
        db.create_all()
        db.session.add_all([
            Attraction(slug="huangguoshu", name="黄果树瀑布", category="自然", city="安顺",
                       summary="s", description="d", cover_image="",
                       longitude=105.6832, latitude=25.9976, rating=4.8, price=160, status="published"),
            Attraction(slug="huajiang-bridge", name="花江峡谷大桥", category="科技", city="安顺",
                       summary="s", description="d", cover_image="",
                       longitude=105.55, latitude=25.65, rating=4.6, price=0, status="published"),
            Attraction(slug="zhaoxing-dong", name="肇兴侗寨", category="人文", city="黔东南",
                       summary="s", description="d", cover_image="",
                       longitude=109.17, latitude=25.9, rating=4.7, price=80, status="published"),
            Attraction(slug="xijiang-miao", name="西江千户苗寨", category="人文", city="黔东南",
                       summary="s", description="d", cover_image="",
                       longitude=108.1725, latitude=26.4963, rating=4.7, price=90, status="published"),
            Attraction(slug="qingyan", name="青岩古镇", category="人文", city="贵阳",
                       summary="s", description="d", cover_image="",
                       longitude=106.68, latitude=26.33, rating=4.5, price=10, status="published"),
            # 草稿景点：不该被预检读到
            Attraction(slug="draft-spot", name="草稿景点", category="自然", city="安顺",
                       summary="s", description="d", cover_image="",
                       longitude=110.0, latitude=27.0, price=999, status="draft"),
        ])
        db.session.commit()
        yield app
    finally:
        db.session.remove()
        db.drop_all()
        context.pop()


# ---------------------------------------------------------------- 构造工具
def picks(*ids):
    return Attraction.query.filter(Attraction.id.in_(ids)).all()


def pick(attraction_id, name="", city="", price=0):
    """同形字典，方便把纯函数当单元测（不必每次都过 DB）。"""
    return {"id": attraction_id, "name": name, "city": city, "price": price}


def codes(result):
    return [item["code"] for item in result["conflicts"]]


EMPTY = {"cities": [], "count": 0, "conflicts": []}


# ---------------------------------------------------------------- 跨城规则
def test_selection_cross_city_reports_real_distance(seeded_app):
    """安顺 + 黔东南 ⇒ selection_cross_city（high），距离应是 300km 量级。"""
    result = analysis.precheck_selection(picks(1, 3), days=2)

    assert set(result) == {"cities", "count", "conflicts"}
    assert result["cities"] == ["安顺", "黔东南"]
    assert result["count"] == len(result["conflicts"]) == 1

    conflict = result["conflicts"][0]
    assert set(conflict) == {"code", "severity", "title", "detail", "suggestion"}
    assert conflict["code"] == "selection_cross_city"
    assert conflict["severity"] == "high"
    assert "2 个景点分布在 2 个城市" in conflict["title"]
    assert "安顺" in conflict["title"] and "黔东南" in conflict["title"]
    assert conflict["suggestion"]

    km = int(re.search(r"(\d+)\s*公里", conflict["detail"]).group(1))
    assert 250 < km < 400, f"cross-city distance looks wrong: {km} km"
    assert "2 天要来回跑" in conflict["detail"]


def test_selection_lists_all_three_cities_in_title(seeded_app):
    result = analysis.precheck_selection(picks(1, 3, 5), days=3)
    conflict = next(item for item in result["conflicts"] if item["code"] == "selection_cross_city")
    assert result["cities"] == ["安顺", "黔东南", "贵阳"]
    assert "3 个景点分布在 3 个城市（安顺、黔东南、贵阳）" in conflict["title"]


def test_same_city_selection_is_clean(seeded_app):
    result = analysis.precheck_selection(picks(1, 2), days=2)
    assert result == {"cities": ["安顺"], "count": 0, "conflicts": []}


def test_nearby_cities_under_100km_are_not_reported(seeded_app):
    """贵阳 ↔ 黔南 约 32km：两个城市但没超过 100km，不报跨城。"""
    db.session.add(Attraction(
        slug="nearby-qiannan", name="近邻景点", category="自然", city="黔南",
        summary="s", description="d", cover_image="",
        longitude=107.0, latitude=26.3, price=20, status="published",
    ))
    db.session.commit()

    nearby = Attraction.query.filter_by(slug="nearby-qiannan").one()
    result = analysis.precheck_selection([*picks(5), nearby], days=2)
    assert result["cities"] == ["贵阳", "黔南"]
    assert "selection_cross_city" not in codes(result)
    assert result == {"cities": ["贵阳", "黔南"], "count": 0, "conflicts": []}


def test_unknown_city_never_invents_distance(seeded_app):
    """坐标查不到就跳过跨城规则，不编造距离（城市名照常回显）。"""
    rows = [pick(1, "火星营地", "火星"), pick(2, "月球基地", "月球")]
    result = analysis.precheck_selection(rows, days=2)
    assert result["cities"] == ["火星", "月球"]
    assert result["count"] == 0 and result["conflicts"] == []


# ---------------------------------------------------------------- 密度规则
def test_selection_too_dense_threshold(seeded_app):
    """4 个景点塞 1 天：超过 1×3，报密集；正好 3 个不报。"""
    dense = analysis.precheck_selection(picks(1, 2, 3, 4), days=1)
    conflict = next(item for item in dense["conflicts"] if item["code"] == "selection_too_dense")
    assert conflict["severity"] == "medium"
    assert conflict["title"] == "1 天要跑 4 个景点，平均每天 4 个"
    assert "最多安排 3 个" in conflict["detail"]
    assert conflict["suggestion"]

    exactly = analysis.precheck_selection(picks(1, 2, 3), days=1)
    assert "selection_too_dense" not in codes(exactly)

    spread = analysis.precheck_selection(picks(1, 2, 3, 4), days=2)
    assert "selection_too_dense" not in codes(spread)


# ---------------------------------------------------------------- 门票规则
def test_selection_tickets_heavy_threshold(seeded_app):
    """门票 240：预算 400（一半 200）报；预算 480（一半 240）不报；budget=0 不报。"""
    heavy = analysis.precheck_selection(picks(1, 3), days=2, budget=400)
    conflict = next(item for item in heavy["conflicts"] if item["code"] == "selection_tickets_heavy")
    assert conflict["severity"] == "medium"
    assert conflict["title"] == "门票合计 ¥240，超过预算 ¥400 的一半"
    assert "¥240" in conflict["detail"]

    assert "selection_tickets_heavy" not in codes(
        analysis.precheck_selection(picks(1, 3), days=2, budget=480)
    )
    assert "selection_tickets_heavy" not in codes(
        analysis.precheck_selection(picks(1, 3), days=2, budget=0)
    )


def test_free_attractions_do_not_trigger_tickets_rule(seeded_app):
    rows = [pick(1, "免费甲", "安顺", 0), pick(2, "免费乙", "安顺", "0")]
    assert codes(analysis.precheck_selection(rows, days=2, budget=1)) == []


# ---------------------------------------------------------------- 稳定性
def test_precheck_is_read_only_and_deterministic(seeded_app):
    before = Attraction.query.count()
    first = analysis.precheck_selection(picks(1, 3), days=2, budget=500)
    second = analysis.precheck_selection(picks(1, 3), days=2, budget=500)
    assert first == second
    assert Attraction.query.count() == before


def test_bad_inputs_fall_back_to_empty(seeded_app):
    assert analysis.precheck_selection(None, 2) == EMPTY
    assert analysis.precheck_selection([], 2) == EMPTY
    assert analysis.precheck_selection("nope", 2) == EMPTY
    assert analysis.precheck_selection([{"name": None}, 3, "x"], 2) == EMPTY
    # 重复 / 不足 2 个去重后没有比较价值
    assert analysis.precheck_selection([pick(1, "甲", "安顺"), pick(1, "甲", "安顺")], 2) == EMPTY
    # days 非法：bool / 字符串 / 越界
    two = picks(1, 3)
    for bad_days in (True, "abc", 0, 6):
        assert analysis.precheck_selection(two, bad_days) == EMPTY


# ---------------------------------------------------------------- 端点
def test_precheck_endpoint_returns_contract_payload(seeded_app):
    client = seeded_app.test_client()
    response = client.post("/api/itinerary/precheck", json={
        "attraction_ids": [1, 3], "days": 2, "budget": 1500,
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True and payload["error"] is None

    data = payload["data"]
    assert set(data) == {"cities", "count", "conflicts"}
    assert data["cities"] == ["安顺", "黔东南"]
    assert data["count"] == len(data["conflicts"]) == 1
    assert data["conflicts"][0]["code"] == "selection_cross_city"
    km = int(re.search(r"(\d+)\s*公里", data["conflicts"][0]["detail"]).group(1))
    assert 250 < km < 400


def test_precheck_endpoint_rejects_invalid_params(seeded_app):
    client = seeded_app.test_client()
    bad_payloads = [
        {},
        {"attraction_ids": "1,2", "days": 2},
        {"attraction_ids": [], "days": 2},          # 一个都没选仍然拒绝
        {"attraction_ids": list(range(1, 10)), "days": 2},
        {"attraction_ids": [1, 2], "days": 0},
        {"attraction_ids": [1, 2], "days": 6},
        {"attraction_ids": [1, 2], "days": True},
        {"attraction_ids": [1, 2], "days": "2"},
        {"attraction_ids": [1, "2"], "days": 2},
        {"attraction_ids": [True, 2], "days": 2},
        {"attraction_ids": [1, 999], "days": 2},   # 不存在
        {"attraction_ids": [1, 6], "days": 2},     # 草稿
    ]
    for payload in bad_payloads:
        response = client.post("/api/itinerary/precheck", json=payload)
        assert response.status_code == 400, payload
        assert response.get_json()["error"]["code"] == "invalid_params"
    # 只读 POST：GET 不该存在
    assert client.get("/api/itinerary/precheck").status_code == 405


def test_precheck_endpoint_swallows_service_exceptions(seeded_app, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("service exploded")

    monkeypatch.setattr(api_module, "precheck_selection", boom)
    client = seeded_app.test_client()
    response = client.post("/api/itinerary/precheck", json={"attraction_ids": [1, 3], "days": 2})
    assert response.status_code == 200
    assert response.get_json()["data"] == EMPTY


def test_precheck_endpoint_translates_in_english(seeded_app):
    client = seeded_app.test_client()
    with client.session_transaction() as session:
        session["lang"] = "en"

    data = client.post("/api/itinerary/precheck", json={"attraction_ids": [1, 3], "days": 2}).get_json()["data"]
    conflict = data["conflicts"][0]
    assert conflict["title"].startswith("Your 2 picks span 2 cities")
    assert "Anshun" in conflict["title"] and "Qiandongnan" in conflict["title"]
    assert "km apart" in conflict["detail"]
    # cities 是数据字段，保持库里的原文，方便前端做匹配
    assert data["cities"] == ["安顺", "黔东南"]


def test_precheck_endpoint_stays_under_50ms(seeded_app):
    client = seeded_app.test_client()
    payload = {"attraction_ids": [1, 3], "days": 2, "budget": 500}
    samples = []
    for _ in range(8):
        started = time.perf_counter()
        response = client.post("/api/itinerary/precheck", json=payload)
        samples.append((time.perf_counter() - started) * 1000)
        assert response.status_code == 200
    average = sum(samples) / len(samples)
    assert average < 50, f"precheck avg {average:.2f}ms >= 50ms"
    assert max(samples) < 200, f"precheck worst {max(samples):.2f}ms"


# ---------------------------------------------------------------- budget 人数回显
def test_budget_echoes_people(seeded_app):
    days = [
        {"day": 1, "theme": "", "slots": [
            {"period": "上午", "title": "黄果树瀑布", "slug": "huangguoshu", "city": "安顺", "detail": ""},
        ], "tips": ""},
        {"day": 2, "theme": "", "slots": [
            {"period": "上午", "title": "肇兴侗寨", "slug": "zhaoxing-dong", "city": "黔东南", "detail": ""},
        ], "tips": ""},
    ]
    client = seeded_app.test_client()

    three = client.post("/api/itinerary/budget", json={"days": days, "people": 3, "budget": 1500}).get_json()["data"]
    assert three["people"] == 3
    assert three["total_all"] == three["total_per_person"] * 3
    assert set(three) == {"people", "total_per_person", "total_all", "items", "cuts", "compare"}

    defaulted = client.post("/api/itinerary/budget", json={"days": days}).get_json()["data"]
    assert defaulted["people"] == 2
    assert defaulted["total_all"] == defaulted["total_per_person"] * 2

    zero = client.post("/api/itinerary/budget", json={"days": days, "people": 0}).get_json()["data"]
    assert zero["people"] == 0 and zero["total_all"] == 0

    clamped = client.post("/api/itinerary/budget", json={"days": days, "people": 99}).get_json()["data"]
    assert clamped["people"] == 50


def test_budget_people_echo_in_pure_function(seeded_app):
    result = analysis.build_budget([], people=4, budget=1000)
    assert result["people"] == 4
    assert result["total_per_person"] == 0 and result["total_all"] == 0
    assert result["compare"]["budget"] == 1000


def test_precheck_accepts_single_attraction(seeded_app):
    """只选 1 个景点也要能预检（产品决策：不再强制 2 个起）。"""
    client = seeded_app.test_client()
    response = client.post("/api/itinerary/precheck", json={"attraction_ids": [1], "days": 2})
    assert response.status_code == 200
    assert response.get_json()["ok"] is True
