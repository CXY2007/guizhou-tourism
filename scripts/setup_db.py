"""创建 tourism_v2 并从只读源库 tourism_data 复制结构与数据。

运行：python scripts/setup_db.py
源库只读，不做任何写入。
"""
import os
import sys

import pymysql

HOST = os.getenv("DB_HOST", "127.0.0.1")
PORT = int(os.getenv("DB_PORT", "3306"))
USER = os.getenv("DB_USER", "root")
PASSWORD = os.getenv("DB_PASSWORD", "")
SRC = "tourism_data"
DST = "tourism_v2"

TABLES = ["users", "attractions", "attraction_images", "comments", "favorites", "ratings"]


def main() -> int:
    conn = pymysql.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, charset="utf8mb4", autocommit=True)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DST}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
    cur.execute(f"USE `{DST}`")
    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for table in TABLES:
        cur.execute(f"SHOW CREATE TABLE `{SRC}`.`{table}`")
        ddl = cur.fetchone()[1]
        cur.execute(f"DROP TABLE IF EXISTS `{table}`")
        cur.execute(ddl)
        cur.execute(f"SELECT * FROM `{SRC}`.`{table}`")
        rows = cur.fetchall()
        if rows:
            cols = len(rows[0])
            placeholders = ",".join(["%s"] * cols)
            cur.executemany(f"INSERT INTO `{table}` VALUES ({placeholders})", rows)
        print(f"{table}: {len(rows)} rows")
    cur.execute("SET FOREIGN_KEY_CHECKS=1")
    print("--- verify ---")
    for table in TABLES:
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
        print(table, cur.fetchone()[0])
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

