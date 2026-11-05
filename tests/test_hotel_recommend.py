"""住宿推荐：落点分组、结果清洗、降级、接口参数校验、存档清洗。"""
import pytest

from app import create_app
from app.config import Config
from app.extensions import db
from app.models import Attraction, User
from app.services import hotels as hotel_service
from app.blueprints import api as api_module
from app.blueprints import user as user_module


class SQLiteConfig(Config):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    AI_API_KEY = ""
    AI_BASE_URL = ""


GOOD_HOTEL = {
    "hotelId": 109259,
    "name": "贵阳喜来登贵航酒店 (甲秀楼青云市集店)",
    "starRating": 5.0,
    "address": "中华南路49号",
    "imageUrl": "https://image-cdn.rollinggo.cn/v2/109259/x.jpg",
    "bookingUrl": "https://rollinggo.cn/pages/hotel/detail/index?id=109259",
    "price": {"hasPrice": True, "lowestPrice": 524.0, "currency": "CNY"},
    "tags": ["商务中心", "室内恒温泳池", "健身房"],
}

EVIL_HOTEL = {
    "hotelId": 2,
    "name": "坏链接酒店",
    "starRating": 4.0,
    "address": "某路1号",
    "imageUrl": "javascript:alert(1)",
    "bookingUrl": "https://evil.example.com/steal",
    "price": {"hasPrice": True, "lowestPrice": 199},
}


@pytest.fixture(autouse=True)
def _clear_hotel_cache():
    """模块级记忆缓存会跨用例残留，每个用例前后都清一次。"""
    hotel_service._memory_cache.clear()
    yield
    hotel_service._memory_cache.clear()


@pytest.fixture()
def hotel_client():
    app = create_app(SQLiteConfig)
    with app.app_context():
        db.create_all()
        user = User(username="hoteluser", password_hash="unused", role="user", status="active")
        db.session.add(user)
        db.session.add_all([
            Attraction(slug="hz-gy", name="甲秀楼", category="人文", city="贵阳",
                       summary="s", description="d", cover_image="",
                       longitude=106.7, latitude=26.5, rating=4.6, status="published"),
            Attraction(slug="hz-as", name="黄果树瀑布", category="自然", city="安顺",
                       summary="s", description="d", cover_image="",
                       longitude=105.6, latitude=25.9, rating=4.8, status="published"),
        ])
        db.session.commit()
        user_id = user.id
    hotel_service._memory_cache.clear()
    with app.test_client() as client:
        yield client, user_id
    hotel_service._memory_cache.clear()
    with app.app_context():
        db.drop_all()


def _payload(hotels_list):
    return {"success": True, "hotelInformationList": hotels_list}


# ---------------------------------------------------------------- 落点分组


def test_group_stays_drops_return_day():
    """两天两城＝1 晚；最后一天在返程，不该凭空多算一晚。"""
    stays = hotel_service._group_stays(["贵阳", "安顺"])
    assert len(stays) == 1
    assert stays[0]["city"] == "贵阳"
    assert stays[0]["nights"] == 1


def test_group_stays_counts_nights_per_city():
    stays = hotel_service._group_stays(["贵阳", "贵阳", "贵阳"])
    assert len(stays) == 1
    assert stays[0]["nights"] == 2

    stays = hotel_service._group_stays(["贵阳", "贵阳", "安顺", "安顺"])
    assert [(s["city"], s["nights"]) for s in stays] == [("贵阳", 2), ("安顺", 1)]


def test_group_stays_single_day_has_no_overnight():
    assert hotel_service._group_stays(["贵阳"]) == []
    assert hotel_service._group_stays([]) == []


# ---------------------------------------------------------------- 结果清洗


def test_normalize_hotel_price_and_tags(monkeypatch):
    monkeypatch.setattr(hotel_service, "_rpc", lambda *a, **k: _payload([GOOD_HOTEL]))
    data = hotel_service.search_stay("贵阳", nights=2)
    assert data and data["hotels"]
    hotel = data["hotels"][0]
    assert hotel["price"] == 524.0
    assert hotel["price_text"] == "¥524/晚"
    assert hotel["star"] == 5.0
    assert hotel["tags"] == ["商务中心", "室内恒温泳池", "健身房"]
    assert hotel["booking_url"].startswith("https://rollinggo.cn/")


def test_normalize_hotel_drops_untrusted_links(monkeypatch):
    monkeypatch.setattr(hotel_service, "_rpc", lambda *a, **k: _payload([EVIL_HOTEL]))
    data = hotel_service.search_stay("贵阳")
    hotel = data["hotels"][0]
    # 非 rollinggo 域名的外链和 javascript: 一律丢弃，模板里就不会渲染成可点按钮
    assert hotel["image"] == ""
    assert hotel["booking_url"] == ""


def test_normalize_hotel_skips_missing_name_and_price(monkeypatch):
    monkeypatch.setattr(hotel_service, "_rpc", lambda *a, **k: _payload([
        {"hotelId": 3, "name": "", "price": {"lowestPrice": 100}},
        {"hotelId": 4, "name": "无价酒店", "price": {"hasPrice": False}},
    ]))
    data = hotel_service.search_stay("贵阳")
    names = [item["name"] for item in data["hotels"]]
    assert names == ["无价酒店"]
    assert data["hotels"][0]["price_text"] == ""


# ---------------------------------------------------------------- 降级与缓存


def test_proxy_failure_returns_none(monkeypatch):
    monkeypatch.setattr(hotel_service, "_rpc", lambda *a, **k: None)
    assert hotel_service.search_stay("贵阳") is None


def test_recommend_hotels_empty_when_no_city():
    result = hotel_service.recommend_hotels([])
    assert result["source"] == "none"
    assert result["stays"] == []


def test_recommend_hotels_survives_exception(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("代理炸了")

    monkeypatch.setattr(hotel_service, "search_stay", boom)
    result = hotel_service.recommend_hotels(["贵阳", "安顺"])
    assert result["source"] == "none"


def test_search_stay_uses_cache(monkeypatch):
    calls = []

    def fake_rpc(*args, **kwargs):
        calls.append(1)
        return _payload([GOOD_HOTEL])

    monkeypatch.setattr(hotel_service, "_rpc", fake_rpc)
    hotel_service.search_stay("贵阳", nights=2)
    hotel_service.search_stay("贵阳", nights=2)
    assert len(calls) == 1


def test_recommend_hotels_falls_back_to_city_when_poi_empty(monkeypatch):
    """景点 POI 查不到时退回按城市查（西江千户苗寨就是这种情况）。"""
    places = []

    def fake_rpc(tool, arguments):
        places.append(arguments["place"])
        if arguments["place"].startswith("西江千户苗寨"):
            return _payload([])
        return _payload([GOOD_HOTEL])

    monkeypatch.setattr(hotel_service, "_rpc", fake_rpc)
    data = hotel_service.search_stay("黔东南", attraction="西江千户苗寨")
    assert places[0] == "西江千户苗寨 黔东南"
    assert places[-1] == "黔东南 中国"
    assert data["place_type"] == "城市"


def test_failed_lookup_is_only_cached_for_a_minute(monkeypatch):
    """上游抖一次只压 60 秒 —— 否则这个城市会连续 3 小时都「没有酒店」。"""
    calls = []
    state = {"ok": False}

    def fake_rpc(*args, **kwargs):
        calls.append(1)
        return _payload([GOOD_HOTEL]) if state["ok"] else None

    monkeypatch.setattr(hotel_service, "_rpc", fake_rpc)
    assert hotel_service.search_stay("贵阳", nights=2) is None
    assert len(calls) == 1

    # 60 秒内仍然命中失败缓存：抖动期间不反复打上游
    assert hotel_service.search_stay("贵阳", nights=2) is None
    assert len(calls) == 1

    # 过了 60 秒就重查，上游恢复后马上能拿到酒店
    for bucket in hotel_service._memory_cache.values():
        bucket["ts"] -= hotel_service.FAIL_TTL_SECONDS + 1
    state["ok"] = True
    data = hotel_service.search_stay("贵阳", nights=2)
    assert data and data["hotels"]
    assert len(calls) == 2


def test_recommend_hotels_explains_empty_result(monkeypatch):
    """有住宿段却一条都没查到：给一句可见原因，前端才不用「静默消失」。"""
    app = create_app(SQLiteConfig)
    with app.app_context():
        monkeypatch.setattr(hotel_service, "search_stay", lambda *a, **k: None)
        result = hotel_service.recommend_hotels(["贵阳", "贵阳"])
    assert result["source"] == "none"
    assert result["stays"] == []
    assert result["note"]


# ---------------------------------------------------------------- 接口


def test_hotels_endpoint_rejects_bad_city_list(hotel_client):
    client, _ = hotel_client
    assert client.post("/api/itinerary/hotels", json={"day_cities": "贵阳"}).status_code == 400
    assert client.post("/api/itinerary/hotels",
                       json={"day_cities": ["贵阳"] * 7}).status_code == 400


def test_hotels_endpoint_ignores_unknown_cities(hotel_client):
    client, _ = hotel_client
    response = client.post("/api/itinerary/hotels", json={"day_cities": ["火星", "月球"]})
    assert response.status_code == 200
    assert response.get_json()["data"]["source"] == "none"


def test_hotels_endpoint_returns_stays(hotel_client, monkeypatch):
    client, _ = hotel_client
    captured = {}

    def fake_recommend(day_cities, focus_map=None, start_date="", budget=0, size=3, max_stays=2,
                       need_stay=True):
        captured["cities"] = day_cities
        captured["focus"] = focus_map
        captured["budget"] = budget
        captured["need_stay"] = need_stay
        return {"source": "live", "note": "n", "stays": [
            {"city": "安顺", "nights": 1, "place": "黄果树瀑布 安顺", "hotels": [{"name": "某酒店"}]}
        ]}

    monkeypatch.setattr(api_module, "recommend_hotels", fake_recommend)
    response = client.post("/api/itinerary/hotels", json={
        "day_cities": ["安顺", "安顺"], "budget": 1000, "start_date": "2026-11-10",
    })
    body = response.get_json()["data"]
    assert body["source"] == "live"
    assert captured["cities"] == ["安顺", "安顺"]
    # 只把库里真实存在的城市传下去，并按评分挑一个景点做 POI 查询
    assert captured["focus"]["安顺"] == "黄果树瀑布"
    assert captured["budget"] == 1000
    assert captured["need_stay"] is True


def test_recommend_hotels_gives_single_day_trip_one_night(monkeypatch):
    """只玩 1 天但选了「需要住宿」→ 住一晚再返程，不能整段没有。"""
    seen = []

    def fake_search(city, attraction="", check_in="", nights=1, adults=2, max_price=0, size=3, lang=None):
        seen.append((city, nights))
        return {"city": city, "place": city, "check_in": check_in, "nights": nights,
                "hotels": [{"name": f"{city}某酒店"}]}

    monkeypatch.setattr(hotel_service, "search_stay", fake_search)
    app = create_app(SQLiteConfig)
    with app.app_context():
        result = hotel_service.recommend_hotels(["贵阳"], need_stay=True)
    assert result["source"] == "live"
    assert [(s["city"], s["nights"]) for s in result["stays"]] == [("贵阳", 1)]
    assert seen == [("贵阳", 1)]


def test_recommend_hotels_no_stay_has_no_lodging(monkeypatch):
    """选「不需要住宿，当日往返」时本来就不该有住宿段。"""
    monkeypatch.setattr(hotel_service, "search_stay", lambda *a, **k: None)
    app = create_app(SQLiteConfig)
    with app.app_context():
        result = hotel_service.recommend_hotels(["贵阳"], need_stay=False)
    assert result["source"] == "none"
    assert result["stays"] == []


def test_hotels_endpoint_carries_city_into_free_days(hotel_client, monkeypatch):
    """「自由安排」那天没有落点：沿用上一座城。

    否则「1 个景点 + 3 天」只有第 1 天有城市 → 只住 0 晚 → 住宿段被整段丢掉，
    卡片就再也不出现。
    """
    client, _ = hotel_client
    captured = {}

    def fake_recommend(day_cities, focus_map=None, start_date="", budget=0, size=3, max_stays=2,
                       need_stay=True):
        captured["cities"] = day_cities
        return {"source": "live", "note": "", "stays": []}

    monkeypatch.setattr(api_module, "recommend_hotels", fake_recommend)
    response = client.post("/api/itinerary/hotels", json={"day_cities": ["安顺", "", ""]})
    assert response.status_code == 200
    assert captured["cities"] == ["安顺", "安顺", "安顺"]


def test_hotels_endpoint_passes_need_stay_through(hotel_client, monkeypatch):
    client, _ = hotel_client
    captured = {}

    def fake_recommend(day_cities, focus_map=None, start_date="", budget=0, size=3, max_stays=2,
                       need_stay=True):
        captured["need_stay"] = need_stay
        return {"source": "none", "stays": [], "note": ""}

    monkeypatch.setattr(api_module, "recommend_hotels", fake_recommend)
    client.post("/api/itinerary/hotels", json={"day_cities": ["安顺", "安顺"], "need_stay": False})
    assert captured["need_stay"] is False
    client.post("/api/itinerary/hotels", json={"day_cities": ["安顺", "安顺"]})
    assert captured["need_stay"] is True  # 老调用方没传时按「需要住宿」处理


# ---------------------------------------------------------------- 存档清洗


def test_saved_plan_keeps_clean_hotels():
    brief = user_module._saved_plan({
        "brief": {"hotels": {"stays": [{
            "city": "贵阳", "nights": 2, "place": "贵阳 中国",
            "hotels": [
                {"name": "喜来登", "star": 5.0, "price_text": "¥524/晚", "address": "中华南路",
                 "image": "https://image-cdn.rollinggo.cn/a.jpg",
                 "booking_url": "https://rollinggo.cn/pages/hotel/detail/index?id=1"},
                {"name": "坏链接", "booking_url": "javascript:alert(1)",
                 "image": "https://evil.example.com/x.jpg"},
            ],
        }], "note": "价格为实时查询"}},
        "days": [],
    })
    stays = brief["brief"]["hotels"]["stays"]
    assert stays[0]["city"] == "贵阳" and stays[0]["nights"] == 2
    assert stays[0]["hotels"][0]["booking_url"].startswith("https://rollinggo.cn/")
    assert stays[0]["hotels"][1]["booking_url"] == ""
    assert stays[0]["hotels"][1]["image"] == ""


def test_saved_plan_ignores_empty_hotel_block():
    brief = user_module._saved_plan({"brief": {"hotels": {"stays": []}}, "days": []})
    assert "hotels" not in brief["brief"]
