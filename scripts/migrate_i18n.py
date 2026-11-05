"""为 attraction_translations 补齐英文字段（幂等）。"""
import os

import pymysql

DB = dict(host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
          user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
          database="tourism_v2", charset="utf8mb4", autocommit=True)

COLUMNS = {
    "address": "VARCHAR(255) NULL",
    "transport": "TEXT NULL",
    "tips": "TEXT NULL",
    "open_time": "VARCHAR(100) NULL",
    "ticket_note": "VARCHAR(255) NULL",
}


def main():
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute("show columns from attraction_translations")
    existing = {row[0] for row in cur.fetchall()}
    for name, ddl in COLUMNS.items():
        if name not in existing:
            cur.execute(f"alter table attraction_translations add column {name} {ddl}")
            print("added", name)
        else:
            print("exists", name)
    cur.execute("alter table attraction_translations modify summary varchar(400) null")
    print("summary widened")
    conn.close()


if __name__ == "__main__":
    main()

