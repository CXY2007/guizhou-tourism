"""D3 迁移：浏览记录表（用于个性化每日推荐）。

运行：python scripts/migrate_d3.py
只操作 tourism_v2。
"""
import os
import sys

import pymysql

DB = dict(host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
          user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
          database="tourism_v2", charset="utf8mb4", autocommit=True)


def main() -> int:
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS view_logs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id INT UNSIGNED NOT NULL,
        attraction_id INT NOT NULL,
        view_date DATE NOT NULL,
        viewed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_view_user_attr_day (user_id, attraction_id, view_date),
        KEY idx_view_user_date (user_id, view_date),
        CONSTRAINT fk_view_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT fk_view_attr FOREIGN KEY (attraction_id) REFERENCES attractions(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
    cur.execute("SELECT COUNT(*) FROM view_logs")
    print("view_logs rows:", cur.fetchone()[0])
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

