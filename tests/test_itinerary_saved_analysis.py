"""已保存行程的 conflicts / budget 存档清洗。"""
from app.blueprints import user as user_module


GOOD_CONFLICT = {
    "code": "cross_city",
    "severity": "high",
    "day": 1,
    "title": "第 1 天跨城 318 公里",
    "detail": "上午在安顺、下午在黔东南",
    "suggestion": "把黔东南的行程挪到相邻的一天",
}

GOOD_BUDGET = {
    "total_per_person": 1254,
    "total_all": 2508,
    "people": 2,
    "items": [{"key": "ticket", "label": "门票", "per_person": 330, "detail": "黄果树 160"}],
    "cuts": [{"label": "舍掉黄果树门票，省 ¥160", "saving": 160}],
    "compare": {"budget": 300, "delta": 954, "status": "over"},
}


def _plan(brief):
    return user_module._saved_plan({"brief": brief, "days": []})["brief"]


# ---------------------------------------------------------------- 正常往返


def test_keeps_clean_conflicts_and_budget():
    brief = _plan({"conflicts": [GOOD_CONFLICT], "budget": GOOD_BUDGET})
    assert brief["conflicts"][0]["code"] == "cross_city"
    assert brief["conflicts"][0]["severity"] == "high"
    assert brief["conflicts"][0]["day"] == 1
    assert brief["budget"]["total_per_person"] == 1254
    assert brief["budget"]["compare"]["status"] == "over"
    assert brief["budget"]["items"][0]["label"] == "门票"


# ---------------------------------------------------------------- 冲突清洗


def test_conflicts_truncate_and_limit():
    long = dict(GOOD_CONFLICT, title="标" * 400, detail="细" * 400, suggestion="建" * 400)
    brief = _plan({"conflicts": [long] * 20})
    assert len(brief["conflicts"]) == 10
    assert len(brief["conflicts"][0]["title"]) == 120
    assert len(brief["conflicts"][0]["detail"]) == 200
    assert len(brief["conflicts"][0]["suggestion"]) == 200


def test_illegal_severity_falls_back_to_low():
    brief = _plan({"conflicts": [dict(GOOD_CONFLICT, severity="CRITICAL")]})
    assert brief["conflicts"][0]["severity"] == "low"


def test_day_is_clamped_and_coerced():
    brief = _plan({"conflicts": [
        dict(GOOD_CONFLICT, day="3"),
        dict(GOOD_CONFLICT, day=99),
        dict(GOOD_CONFLICT, day="abc"),
    ]})
    assert [item["day"] for item in brief["conflicts"]] == [3, 5, 0]


def test_conflicts_require_title():
    brief = _plan({"conflicts": [{"code": "x", "severity": "high"}, GOOD_CONFLICT]})
    assert len(brief["conflicts"]) == 1


# ---------------------------------------------------------------- 预算清洗


def test_budget_numbers_are_finite():
    dirty = dict(GOOD_BUDGET, total_per_person="abc", total_all=float("nan"),
                 items=[{"key": "ticket", "label": "门票", "per_person": "x"}])
    brief = _plan({"budget": dirty})
    # 数值全废 + 有 items 标签 → 仍然保留，但数值归 0
    assert brief["budget"]["total_per_person"] == 0
    assert brief["budget"]["total_all"] == 0
    assert brief["budget"]["items"][0]["per_person"] == 0


def test_budget_items_and_cuts_are_capped():
    many = dict(GOOD_BUDGET,
                items=[{"key": "k", "label": "门票", "per_person": 1}] * 30,
                cuts=[{"label": "省一点", "saving": 1}] * 30)
    brief = _plan({"budget": many})
    assert len(brief["budget"]["items"]) == 8
    assert len(brief["budget"]["cuts"]) == 6


def test_budget_status_whitelist():
    for raw, expected in (("OVER", "over"), ("weird", "unknown"), ("even", "even")):
        budget = dict(GOOD_BUDGET, compare={"budget": 1, "delta": 0, "status": raw})
        assert _plan({"budget": budget})["budget"]["compare"]["status"] == expected


def test_budget_people_clamped():
    budget = dict(GOOD_BUDGET, people=999)
    assert _plan({"budget": budget})["budget"]["people"] == 20


def test_empty_budget_dropped():
    assert "budget" not in _plan({"budget": {}})
    assert "budget" not in _plan({"budget": "nonsense"})
    assert "conflicts" not in _plan({"conflicts": []})
    assert "conflicts" not in _plan({"conflicts": "nonsense"})


def test_dirty_structures_do_not_raise():
    brief = _plan({"conflicts": [None, 1, "x", GOOD_CONFLICT], "budget": {"items": [None, 2]}})
    assert len(brief["conflicts"]) == 1
    assert "budget" not in brief  # 没有可用数值也没有有效 items

# ---------------------------------------------------------------- 老存档兼容


def test_old_itinerary_without_analysis_keys():
    brief = _plan({"summary": "老行程", "transport": "高铁"})
    assert brief["summary"] == "老行程"
    assert "conflicts" not in brief and "budget" not in brief
