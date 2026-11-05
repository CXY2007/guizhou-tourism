"""全站 GET 路由健康检查：游客 / 普通用户 / 管理员三种身份各跑一遍。

只看副作用安全的 GET；记录状态码、耗时、异常堆栈（如果有）。
"""
import os
import re
import sys
import time

os.environ.setdefault("SITE_PORT", "8900")

import requests

BASE = "http://127.0.0.1:8900"


def routes():
    from app import create_app

    app = create_app()
    out = []
    for rule in app.url_map.iter_rules():
        if "GET" not in (rule.methods or set()):
            continue
        if rule.endpoint == "static":
            continue
        # 跳过需要真实 id 的动态路由，单独造几条
        out.append((rule.rule, rule.endpoint))
    return out


def login(session, username, password):
    page = session.get(BASE + "/auth/login", timeout=15)
    m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', page.text)
    token = m.group(1) if m else ""
    data = {"username": username, "password": password}
    if token:
        data["csrf_token"] = token
    r = session.post(BASE + "/auth/login", data=data, allow_redirects=True, timeout=15)
    logged = "/auth/login" not in r.url
    return r.status_code, logged


def probe(session, path, label, results):
    try:
        t0 = time.monotonic()
        r = session.get(BASE + path, timeout=25, allow_redirects=False)
        ms = int((time.monotonic() - t0) * 1000)
        body = r.text or ""
        hint = ""
        if r.status_code == 500:
            m = re.search(r"<title>(.*?)</title>", body, re.S)
            hint = (m.group(1).strip()[:120] if m else body[:120])
        results.append((label, path, r.status_code, ms, hint))
        return r.status_code
    except Exception as exc:  # noqa: BLE001
        results.append((label, path, "EXC", 0, str(exc)[:120]))
        return "EXC"


def main():
    all_routes = routes()
    print("GET 路由总数:", len(all_routes))

    results = []

    # 游客
    guest = requests.Session()
    for rule, endpoint in all_routes:
        path = rule
        if "<int:" in path or "<slug:" in path:
            continue  # 动态路由单独测
        probe(guest, path, "guest", results)

    # 登录用户（口令从环境变量读，源码里不留明文）
    demo = requests.Session()
    demo_password = os.getenv("DEMO_PASSWORD", "")
    if demo_password:
        code, ok = login(demo, "demo", demo_password)
        print("demo 登录:", code, ok)
        for rule, endpoint in all_routes:
            path = rule
            if "<int:" in path or "<slug:" in path:
                continue
            probe(demo, path, "demo", results)
    else:
        print("跳过登录用户检查：未设置 DEMO_PASSWORD")

    # 动态路由：用真实数据造样例
    from app import create_app
    from app.extensions import db
    from app.models import Attraction, Comment, Itinerary

    app = create_app()
    with app.app_context():
        slug = db.session.query(Attraction.slug).filter_by(status="published").first()
        slug = slug[0] if slug else "huangguoshu"
        aid = db.session.query(Attraction.id).filter_by(status="published").first()
        aid = aid[0] if aid else 1
        it = db.session.query(Itinerary.id).filter_by(user_id=2).first()
        it_id = it[0] if it else 1
        cid = db.session.query(Comment.id).first()
        cid = cid[0] if cid else 1

    dynamic = [
        f"/attractions/{slug}",
        f"/attractions/{slug}/map",
        f"/itinerary/{it_id}",
        f"/booking/{aid}",
        f"/comments/{cid}" if True else "",
    ]
    for path in dynamic:
        probe(guest, path, "guest+dynamic", results)
        probe(demo, path, "demo+dynamic", results)

    # 汇总
    bad = [r for r in results if r[2] not in (200, 302, 304, 404, 403)]
    print("\n=== 异常状态（非 200/302/304/404/403）===")
    if not bad:
        print("  无")
    for label, path, code, ms, hint in bad:
        print(f"  [{label}] {code} {path} ({ms}ms) {hint}")

    print("\n=== 403/404 清单（确认是否预期）===")
    for label, path, code, ms, hint in results:
        if code in (403, 404):
            print(f"  [{label}] {code} {path}")

    print("\n=== 慢接口（>1500ms）===")
    slow = sorted([r for r in results if isinstance(r[3], int) and r[3] > 1500], key=lambda x: -x[3])
    if not slow:
        print("  无")
    for label, path, code, ms, hint in slow[:12]:
        print(f"  {ms}ms [{label}] {path} ({code})")

    print(f"\n探测总数: {len(results)}  异常: {len(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
