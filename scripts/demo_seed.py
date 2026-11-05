"""演示数据：生成一个普通用户 demo + 收藏/评分/评论/浏览记录，便于截图与演示。

用法：
    python scripts/demo_seed.py seed
    python scripts/demo_seed.py cleanup
"""
import os
import secrets
import sys
from datetime import date, timedelta

import pymysql
from werkzeug.security import generate_password_hash

DB = dict(host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
          user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
          database="tourism_v2", charset="utf8mb4", autocommit=True)

USERNAME = "demo"
PASSWORD = "Gz#" + secrets.token_urlsafe(12)


def recompute(cur, attraction_ids):
    for aid in attraction_ids:
        cur.execute(
            "UPDATE attractions a SET rating=(SELECT ROUND(AVG(rating),1) FROM ratings WHERE attraction_id=a.id), "
            "rating_count=(SELECT COUNT(*) FROM ratings WHERE attraction_id=a.id) WHERE a.id=%s",
            (aid,),
        )


def cleanup(cur):
    cur.execute("SELECT id FROM users WHERE username=%s", (USERNAME,))
    row = cur.fetchone()
    if row:
        cur.execute("DELETE FROM users WHERE id=%s", (row[0],))
    recompute(cur, [1, 3, 4])
    print("cleanup done")


def seed(cur):
    cleanup(cur)
    cur.execute(
        "INSERT INTO users (username, password_hash, role, nickname, status) VALUES (%s, %s, 'user', %s, 'active')",
        (USERNAME, generate_password_hash(PASSWORD), "小旅"),
    )
    uid = cur.lastrowid

    for aid in (1, 3, 4):
        cur.execute("INSERT INTO favorites (user_id, attraction_id) VALUES (%s, %s)", (uid, aid))

    for aid, score in ((1, 5), (3, 5), (4, 4)):
        cur.execute("INSERT INTO ratings (user_id, attraction_id, rating) VALUES (%s, %s, %s)", (uid, aid, score))

    comments = [
        (1, "瀑布比照片更震撼，建议早上进园，人少水汽也好看。", "approved"),
        (1, "天星桥那段路很值得慢慢走，穿防滑鞋。", "approved"),
        (3, "金顶日出要提前看天气，山上风大，外套一定带。", "approved"),
        (3, "索道排队较久，建议错峰上山。", "pending"),
    ]
    for aid, content, status in comments:
        cur.execute(
            "INSERT INTO comments (user_id, attraction_id, content, status) VALUES (%s, %s, %s, %s)",
            (uid, aid, content, status),
        )

    today = date.today()
    logs = [(1, 0), (3, 0), (5, 1), (1, 2), (3, 3), (4, 5)]
    for aid, days_ago in logs:
        cur.execute(
            "INSERT INTO view_logs (user_id, attraction_id, view_date, viewed_at) VALUES (%s, %s, %s, NOW())",
            (uid, aid, today - timedelta(days=days_ago)),
        )

    recompute(cur, [1, 3, 4])
    print(f"seeded demo user id={uid} username={USERNAME} password={PASSWORD}")


def main():
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    action = sys.argv[1] if len(sys.argv) > 1 else "seed"
    if action == "cleanup":
        cleanup(cur)
    else:
        seed(cur)
    conn.close()


if __name__ == "__main__":
    main()

