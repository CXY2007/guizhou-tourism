"""把 tourism_v2 升级到 D1 冻结的数据模型（幂等）。

运行：python scripts/migrate_v2.py
只操作 tourism_v2，源库 tourism_data 不写入。
"""
import os
import sys

import pymysql

DB = dict(host=os.getenv("DB_HOST", "127.0.0.1"), port=int(os.getenv("DB_PORT", "3306")),
          user=os.getenv("DB_USER", "root"), password=os.getenv("DB_PASSWORD", ""),
          database="tourism_v2", charset="utf8mb4", autocommit=True)

SLUGS = {
    1: "huangguoshu", 2: "xijiang-miao", 3: "fanjingshan", 4: "fast-tianyan",
    5: "zunyi-conference", 6: "loushanguan", 7: "xifeng-camp", 8: "liping-conference",
}


def column_exists(cur, table, column):
    cur.execute("""SELECT COUNT(*) FROM information_schema.columns
                   WHERE table_schema=%s AND table_name=%s AND column_name=%s""",
                (DB["database"], table, column))
    return cur.fetchone()[0] > 0


def add_column(cur, table, column, ddl):
    if not column_exists(cur, table, column):
        cur.execute(f"ALTER TABLE `{table}` ADD COLUMN {ddl}")
        print(f"+ {table}.{column}")


def index_exists(cur, table, index):
    cur.execute("""SELECT COUNT(*) FROM information_schema.statistics
                   WHERE table_schema=%s AND table_name=%s AND index_name=%s""",
                (DB["database"], table, index))
    return cur.fetchone()[0] > 0


def main() -> int:
    conn = pymysql.connect(**DB)
    cur = conn.cursor()

    # users
    add_column(cur, "users", "role", "role ENUM('user','admin') NOT NULL DEFAULT 'user' AFTER password_hash")
    add_column(cur, "users", "nickname", "nickname VARCHAR(50) NULL AFTER role")
    add_column(cur, "users", "avatar", "avatar VARCHAR(255) NULL AFTER nickname")
    add_column(cur, "users", "status", "status ENUM('active','disabled') NOT NULL DEFAULT 'active' AFTER avatar")
    add_column(cur, "users", "last_login", "last_login DATETIME NULL")

    # attractions
    add_column(cur, "attractions", "slug", "slug VARCHAR(120) NULL AFTER id")
    add_column(cur, "attractions", "summary", "summary VARCHAR(200) NULL AFTER name")
    add_column(cur, "attractions", "region", "region VARCHAR(50) NULL AFTER city")
    add_column(cur, "attractions", "ticket_note", "ticket_note VARCHAR(255) NULL AFTER price")
    add_column(cur, "attractions", "seasonal", "seasonal TINYINT(1) NOT NULL DEFAULT 0 AFTER best_months")
    add_column(cur, "attractions", "tags", "tags JSON NULL AFTER category")
    add_column(cur, "attractions", "transport", "transport TEXT NULL AFTER address")
    add_column(cur, "attractions", "tips", "tips TEXT NULL AFTER description")
    add_column(cur, "attractions", "sources", "sources JSON NULL")
    add_column(cur, "attractions", "verified_at", "verified_at DATE NULL")
    add_column(cur, "attractions", "status", "status ENUM('draft','published') NOT NULL DEFAULT 'published'")
    add_column(cur, "attractions", "created_at", "created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
    add_column(cur, "attractions", "updated_at", "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")

    # attraction_images
    add_column(cur, "attraction_images", "caption", "caption VARCHAR(120) NULL")
    add_column(cur, "attraction_images", "width", "width INT NULL")
    add_column(cur, "attraction_images", "height", "height INT NULL")

    # comments
    add_column(cur, "comments", "status", "status ENUM('pending','approved','rejected') NOT NULL DEFAULT 'pending'")
    add_column(cur, "comments", "parent_id", "parent_id INT NULL")

    # indexes
    if not index_exists(cur, "attractions", "uk_attractions_slug"):
        cur.execute("CREATE UNIQUE INDEX uk_attractions_slug ON attractions(slug)")
        print("+ index attractions.slug")
    for table in ("favorites", "ratings"):
        name = f"uk_{table}_user_attraction"
        if not index_exists(cur, table, name):
            try:
                cur.execute(f"CREATE UNIQUE INDEX {name} ON {table}(user_id, attraction_id)")
                print(f"+ index {name}")
            except Exception as e:
                print(f"! skip {name}: {e}")

    # new tables
    cur.execute("""CREATE TABLE IF NOT EXISTS attraction_translations (
        id INT AUTO_INCREMENT PRIMARY KEY,
        attraction_id INT NOT NULL,
        lang ENUM('zh','en') NOT NULL,
        name VARCHAR(120) NULL,
        summary VARCHAR(200) NULL,
        description TEXT NULL,
        poetic TEXT NULL,
        UNIQUE KEY uk_attr_lang (attraction_id, lang),
        CONSTRAINT fk_tr_attr FOREIGN KEY (attraction_id) REFERENCES attractions(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT UNSIGNED NOT NULL,
        attraction_id INT NOT NULL,
        visit_date DATE NOT NULL,
        quantity INT NOT NULL,
        unit_price DECIMAL(10,2) NOT NULL,
        total DECIMAL(10,2) NOT NULL,
        status ENUM('pending','paid','cancelled') NOT NULL DEFAULT 'pending',
        payment_method VARCHAR(20) NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        KEY idx_bookings_user (user_id, status),
        CONSTRAINT fk_bk_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        CONSTRAINT fk_bk_attr FOREIGN KEY (attraction_id) REFERENCES attractions(id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS itineraries (
        id INT AUTO_INCREMENT PRIMARY KEY,
        user_id INT UNSIGNED NOT NULL,
        title VARCHAR(120) NOT NULL,
        days INT NOT NULL,
        items JSON NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        CONSTRAINT fk_it_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    cur.execute("""CREATE TABLE IF NOT EXISTS assistant_logs (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        user_id INT UNSIGNED NULL,
        session_id VARCHAR(64) NOT NULL,
        message TEXT NOT NULL,
        intent VARCHAR(20) NULL,
        action JSON NULL,
        latency_ms INT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        KEY idx_logs_created (created_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    # backfill
    for aid, slug in SLUGS.items():
        cur.execute("UPDATE attractions SET slug=%s WHERE id=%s AND (slug IS NULL OR slug='')", (slug, aid))
    cur.execute("UPDATE attractions SET summary=LEFT(description,60) WHERE summary IS NULL")
    cur.execute("UPDATE attractions SET tags=JSON_ARRAY() WHERE tags IS NULL")
    cur.execute("UPDATE comments SET status='approved' WHERE status='pending'")
    conn.commit()

    print("--- verify attractions ---")
    cur.execute("SELECT id, slug, status, seasonal FROM attractions ORDER BY id")
    for row in cur.fetchall():
        print(row)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

