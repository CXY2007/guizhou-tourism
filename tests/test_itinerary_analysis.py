"""行程分析（team task-2 契约）：冲突检测 + 预算沙盘的规则、端点和兜底。

覆盖契约要求的 6 个场景：同日跨城 / 时间重叠 / 超预算 / 过密 / 空行程 / people=0，
外加两个端点的 400 分支、异常兜底、只读与耗时。
"""
import math
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
    """建库 + 造真实量级的贵州数据集；整个用例期间压着 app context，纯函数可直接读库。"""
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
            # 草稿景点：不该参与城市坐标均值，也不该算出票价
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
def slot(period, title="", slug="", city="", detail=""):
    return {"period": period, "title": title, "slug": slug, "city": city, "detail": detail}


def day(number, *slots, tips=""):
    return {"day": number, "theme": "", "slots": list(slots), "tips": tips}


CROSS_CITY_DAYS = [day(
    1,
    slot("上午", "黄果树瀑布", "huangguoshu", "安顺"),
    slot("下午", "肇兴侗寨", "zhaoxing-dong", "黔东南"),
)]

TWO_CITY_DAYS = [
    day(1, slot("上午", "黄果树瀑布", "huangguoshu", "安顺"),
        slot("下午", "花江峡谷大桥", "huajiang-bridge", "安顺")),
    day(2, slot("上午", "肇兴侗寨", "zhaoxing-dong", "黔东南"),
        slot("下午", "西江千户苗寨", "xijiang-miao", "黔东南")),
]


def codes(result):
    return [item["code"] for item in result["conflicts"]]


def item_by_key(budget_result, key):
    return next(item for item in budget_result["items"] if item["key"] == key)


def haversine(lng1, lat1, lng2, lat2):
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * 6371.0 * math.asin(min(1.0, math.sqrt(a)))


# ---------------------------------------------------------------- 冲突规则
def test_cross_city_conflict_reports_plausible_distance(seeded_app):
    """安顺 + 黔东南同日 ⇒ cross_city（high），距离应在真实量级。"""
    result = analysis.detect_conflicts(CROSS_CITY_DAYS)
    matched = [item for item in result["conflicts"] if item["code"] == "cross_city"]
    assert len(matched) == 1

    conflict = matched[0]
    assert conflict["severity"] == "high"
    assert conflict["day"] == 1
    assert set(conflict) == {"code", "severity", "day", "title", "detail", "suggestion"}
    assert conflict["suggestion"]

    km = int(re.search(r"(\d+)\s*公里", conflict["title"]).group(1))
    assert 100 < km < 500, f"cross-city distance looks wrong: {km} km"
    assert "安顺" in conflict["detail"] and "黔东南" in conflict["detail"]
    assert result["count"] == len(result["conflicts"])


def test_same_city_day_is_not_cross_city(seeded_app):
    days = [day(
        1,
        slot("上午", "黄果树瀑布", "huangguoshu", "安顺"),
        slot("下午", "花江峡谷大桥", "huajiang-bridge", "安顺"),
    )]
    assert "cross_city" not in codes(analysis.detect_conflicts(days))


def test_unknown_cities_never_invent_distance(seeded_app):
    """查不到城市坐标 ⇒ 跳过跨城规则，不编造距离。"""
    days = [day(
        1,
        slot("上午", "火星营地", "", "火星"),
        slot("下午", "月球基地", "", "月球"),
    )]
    assert analysis.detect_conflicts(days) == {"conflicts": [], "count": 0}


def test_overlap_in_same_period(seeded_app):
    days = [day(
        1,
        slot("上午", "黄果树瀑布", "huangguoshu", "安顺"),
        slot("上午", "花江峡谷大桥", "huajiang-bridge", "安顺"),
    )]
    matched = [item for item in analysis.detect_conflicts(days)["conflicts"] if item["code"] == "overlap"]
    assert len(matched) == 1
    assert matched[0]["severity"] == "high"
    assert "2 个行程" in matched[0]["title"]


def test_too_dense_more_than_three_attractions(seeded_app):
    days = [day(
        1,
        slot("上午", "黄果树瀑布", "huangguoshu", "安顺"),
        slot("下午", "花江峡谷大桥", "huajiang-bridge", "安顺"),
        slot("晚上", "肇兴侗寨", "zhaoxing-dong", "安顺"),
        slot("夜间", "青岩古镇", "qingyan", "安顺"),
    )]
    matched = [item for item in analysis.detect_conflicts(days)["conflicts"] if item["code"] == "too_dense"]
    assert len(matched) == 1
    assert matched[0]["severity"] == "low"
    assert "4 个景点" in matched[0]["title"]

    three = [day(1, *[slot("上午", "x", "huangguoshu", "安顺"),
                      slot("下午", "y", "huajiang-bridge", "安顺"),
                      slot("晚上", "z", "zhaoxing-dong", "安顺")])]
    assert "too_dense" not in codes(analysis.detect_conflicts(three))


def test_over_budget_only_when_budget_is_set(seeded_app):
    with_budget = analysis.detect_conflicts(TWO_CITY_DAYS, budget=100)
    matched = [item for item in with_budget["conflicts"] if item["code"] == "over_budget"]
    assert len(matched) == 1
    assert matched[0]["severity"] == "medium"
    assert matched[0]["day"] == 0
    assert "超出预算" in matched[0]["title"]

    assert "over_budget" not in codes(analysis.detect_conflicts(TWO_CITY_DAYS, budget=0))
    assert "over_budget" not in codes(analysis.detect_conflicts(TWO_CITY_DAYS, budget=100000))


def test_no_return_on_multi_city_trip(seeded_app):
    multi = [
        day(1, slot("上午", "黄果树瀑布", "huangguoshu", "安顺")),
        day(2, slot("下午", "肇兴侗寨", "zhaoxing-dong", "黔东南")),
    ]
    assert "no_return" in codes(analysis.detect_conflicts(multi))

    with_return = [
        day(1, slot("上午", "黄果树瀑布", "huangguoshu", "安顺")),
        day(2, slot("下午", "肇兴侗寨", "zhaoxing-dong", "黔东南", detail="下午返程回贵阳"), tips="返程"),
    ]
    assert "no_return" not in codes(analysis.detect_conflicts(with_return))

    single_city = [
        day(1, slot("上午", "黄果树瀑布", "huangguoshu", "安顺")),
        day(2, slot("下午", "花江峡谷大桥", "huajiang-bridge", "安顺")),
    ]
    assert "no_return" not in codes(analysis.detect_conflicts(single_city))


# ---------------------------------------------------------------- 空 / 脏输入
def test_empty_and_malformed_days_do_not_crash(seeded_app):
    assert analysis.detect_conflicts([]) == {"conflicts": [], "count": 0}
    assert analysis.detect_conflicts(None) == {"conflicts": [], "count": 0}
    assert analysis.detect_conflicts("not-a-list") == {"conflicts": [], "count": 0}
    assert analysis.detect_conflicts(["nope", 3, {"day": 1, "slots": "bad"}]) == {
        "conflicts": [], "count": 0,
    }
    dirty = analysis.detect_conflicts([
        {"day": 1, "slots": [{"period": None, "title": None, "slug": None, "city": None}]},
        {"day": "x", "slots": [None, 3]},
    ])
    assert dirty == {"conflicts": [], "count": 0}

    empty_budget = analysis.build_budget([])
    assert empty_budget["total_per_person"] == 0
    assert empty_budget["total_all"] == 0
    assert empty_budget["items"] == [] and empty_budget["cuts"] == []
    assert empty_budget["compare"] == {"budget": 0, "delta": 0, "status": "unknown"}


# ---------------------------------------------------------------- 预算算法
def test_budget_components_follow_formula(seeded_app):
    days = [
        # 同一天同景点出现两次：门票只算一次
        day(1, slot("上午", "黄果树瀑布", "huangguoshu", "安顺"),
            slot("上午", "黄果树瀑布", "huangguoshu", "安顺")),
        day(2, slot("上午", "肇兴侗寨", "zhaoxing-dong", "黔东南")),
    ]
    result = analysis.build_budget(days, people=2, budget=1500, start_date="2026-11-10")

    assert [item["key"] for item in result["items"]] == ["ticket", "hotel", "transport", "meal", "other"]
    assert item_by_key(result, "ticket")["per_person"] == 160 + 80
    assert item_by_key(result, "hotel")["per_person"] == 300            # 1 晚，300 兜底
    assert item_by_key(result, "meal")["per_person"] == 2 * 120

    # 城际 = 安顺坐标均值 → 黔东南坐标均值 的直线距离 × 0.6，市内 2×50
    lng_anshun = (105.6832 + 105.55) / 2
    lat_anshun = (25.9976 + 25.65) / 2
    lng_qiandongnan = (109.17 + 108.1725) / 2
    lat_qiandongnan = (25.9 + 26.4963) / 2
    intercity = haversine(lng_anshun, lat_anshun, lng_qiandongnan, lat_qiandongnan) * 0.6
    expected_transport = round(intercity + 100)
    assert item_by_key(result, "transport")["per_person"] == expected_transport
    assert "公里" in item_by_key(result, "transport")["detail"]

    raw_subtotal = 240 + 300 + (intercity + 100) + 240
    assert item_by_key(result, "other")["per_person"] == round(raw_subtotal * 0.08)

    components = sum(item["per_person"] for item in result["items"])
    assert result["total_per_person"] == components
    assert result["total_all"] == components * 2

    compare = result["compare"]
    assert compare["budget"] == 1500
    assert compare["delta"] == components - 1500
    assert compare["status"] == ("under" if components < 1500 else "over" if components > 1500 else "even")

    assert len(result["cuts"]) >= 2
    for cut in result["cuts"]:
        assert cut["label"] and isinstance(cut["saving"], int) and cut["saving"] >= 0


def test_budget_people_zero_and_hotel_overrides(seeded_app):
    days = [
        day(1, slot("上午", "黄果树瀑布", "huangguoshu", "安顺")),
        day(2, slot("上午", "肇兴侗寨", "zhaoxing-dong", "黔东南")),
    ]
    baseline = analysis.build_budget(days, people=2)

    zero = analysis.build_budget(days, people=0)
    assert zero["total_per_person"] == baseline["total_per_person"]
    assert zero["total_all"] == 0

    priced = analysis.build_budget(days, people=2, hotel_price=500)
    assert item_by_key(priced, "hotel")["per_person"] == 500

    from_text = analysis.build_budget(days, people=2, lodging="建议住 ¥420/晚 的客栈")
    assert item_by_key(from_text, "hotel")["per_person"] == 420

    no_stay = analysis.build_budget(days, people=2, lodging="无需住宿，当日往返")
    assert item_by_key(no_stay, "hotel")["per_person"] == 0
    assert item_by_key(no_stay, "hotel")["detail"].startswith("0 晚")


def test_budget_is_deterministic_and_read_only(seeded_app):
    before = Attraction.query.count()
    first = analysis.build_budget(TWO_CITY_DAYS, people=2, budget=1500)
    second = analysis.build_budget(TWO_CITY_DAYS, people=2, budget=1500)
    assert first == second
    assert analysis.detect_conflicts(TWO_CITY_DAYS, budget=1500) == analysis.detect_conflicts(
        TWO_CITY_DAYS, budget=1500
    )
    assert Attraction.query.count() == before
    assert TWO_CITY_DAYS[0]["slots"][0]["period"] == "上午"


# ---------------------------------------------------------------- 端点
def test_conflicts_endpoint_returns_contract_payload(seeded_app):
    client = seeded_app.test_client()
    response = client.post("/api/itinerary/conflicts", json={"days": CROSS_CITY_DAYS, "budget": 0})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True and payload["error"] is None

    data = payload["data"]
    assert set(data) == {"conflicts", "count"}
    assert data["count"] == len(data["conflicts"]) == 1
    conflict = data["conflicts"][0]
    assert set(conflict) == {"code", "severity", "day", "title", "detail", "suggestion"}
    assert conflict["code"] == "cross_city"


def test_budget_endpoint_returns_contract_payload(seeded_app):
    client = seeded_app.test_client()
    response = client.post("/api/itinerary/budget", json={
        "days": CROSS_CITY_DAYS,
        "people": 2,
        "budget": 1500,
        "start_date": "2026-11-10",
        "hotel_price": 0,
    })
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True and payload["error"] is None

    data = payload["data"]
    assert set(data) == {"people", "total_per_person", "total_all", "items", "cuts", "compare"}
    assert data["people"] == 2  # task-7：人数回显，供「N 人合计」展示
    assert set(data["compare"]) == {"budget", "delta", "status"}
    assert data["compare"]["budget"] == 1500
    assert data["compare"]["status"] in {"under", "over", "even"}
    assert data["total_all"] == data["total_per_person"] * 2
    assert len(data["cuts"]) >= 2
    assert {item["key"] for item in data["items"]} == {"ticket", "hotel", "transport", "meal", "other"}


def test_endpoints_reject_invalid_days(seeded_app):
    client = seeded_app.test_client()
    for endpoint in ("/api/itinerary/conflicts", "/api/itinerary/budget"):
        for payload in ({}, {"days": "2026"}, {"days": None}, {"days": [{}] * 6}):
            response = client.post(endpoint, json=payload)
            assert response.status_code == 400, (endpoint, payload)
            assert response.get_json()["error"]["code"] == "invalid_params"
        # 只读 POST：GET 不该存在
        assert client.get(endpoint).status_code == 405


def test_endpoints_swallow_service_exceptions(seeded_app, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("service exploded")

    monkeypatch.setattr(api_module, "detect_conflicts", boom)
    monkeypatch.setattr(api_module, "build_budget", boom)

    client = seeded_app.test_client()
    conflicts = client.post("/api/itinerary/conflicts", json={"days": CROSS_CITY_DAYS})
    assert conflicts.status_code == 200
    assert conflicts.get_json()["data"] == {"conflicts": [], "count": 0}

    budget = client.post("/api/itinerary/budget", json={"days": CROSS_CITY_DAYS})
    assert budget.status_code == 200
    data = budget.get_json()["data"]
    assert data["total_per_person"] == 0 and data["total_all"] == 0
    assert data["items"] == [] and data["cuts"] == []


def test_endpoints_translate_labels_in_english(seeded_app):
    client = seeded_app.test_client()
    with client.session_transaction() as session:
        session["lang"] = "en"

    conflicts = client.post("/api/itinerary/conflicts", json={"days": CROSS_CITY_DAYS}).get_json()["data"]
    assert any(item["title"].startswith("Day 1") for item in conflicts["conflicts"])

    budget = client.post("/api/itinerary/budget", json={"days": CROSS_CITY_DAYS, "people": 2}).get_json()["data"]
    assert [item["label"] for item in budget["items"]] == ["Tickets", "Stay", "Transport", "Meals", "Other"]


def test_both_endpoints_stay_under_50ms(seeded_app):
    """契约要求单次 <50ms：同一进程里连打，取平均与最慢。"""
    client = seeded_app.test_client()
    payloads = {
        "conflicts": {"days": TWO_CITY_DAYS, "budget": 1500},
        "budget": {"days": TWO_CITY_DAYS, "people": 2, "budget": 1500,
                   "start_date": "2026-11-10", "hotel_price": 0},
    }
    timings = {}
    for endpoint, payload in payloads.items():
        samples = []
        for _ in range(8):
            started = time.perf_counter()
            response = client.post(f"/api/itinerary/{endpoint}", json=payload)
            samples.append((time.perf_counter() - started) * 1000)
            assert response.status_code == 200
        timings[endpoint] = samples

    for endpoint, samples in timings.items():
        average = sum(samples) / len(samples)
        assert average < 50, f"{endpoint} avg {average:.2f}ms >= 50ms"
        assert max(samples) < 200, f"{endpoint} worst {max(samples):.2f}ms"
