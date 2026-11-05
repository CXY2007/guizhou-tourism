"""创建演示管理员账号（幂等）。

运行：python scripts/seed_admin.py
账号：admin（首次创建时随机生成口令并打印一次，之后不重置密码）
"""
import os
import secrets
import sys

import pymysql
from werkzeug.security import generate_password_hash

DB = dict(host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
          user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
          database="tourism_v2", charset="utf8mb4", autocommit=True)

USERNAME = "admin"
# 口令随机生成并只打印一次，不再硬编码（避免随仓库公开）
PASSWORD = "Gz#" + secrets.token_urlsafe(12)


def main() -> int:
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute("SELECT id, role FROM users WHERE username=%s", (USERNAME,))
    row = cur.fetchone()
    if row:
        cur.execute("UPDATE users SET role='admin', status='active' WHERE id=%s", (row[0],))
        print(f"admin exists (id={row[0]}), role ensured. password unchanged.")
    else:
        cur.execute(
            "INSERT INTO users (username, password_hash, role, nickname, status) VALUES (%s, %s, 'admin', %s, 'active')",
            (USERNAME, generate_password_hash(PASSWORD), "管理员"),
        )
        print(f"created admin id={cur.lastrowid} username={USERNAME} password={PASSWORD}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

