"""给 users 表补头像字段（avatar_data / avatar_mime / avatar_version）。

    python scripts/migrate_avatar.py

幂等：字段已存在就跳过。MySQL 用 LONGBLOB，SQLite 用 BLOB。
"""
from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, text  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


def main() -> None:
    app = create_app()
    with app.app_context():
        inspector = inspect(db.engine)
        existing = {column["name"] for column in inspector.get_columns("users")}
        blob_type = "LONGBLOB" if db.engine.dialect.name == "mysql" else "BLOB"

        statements = {
            "avatar_data": f"ALTER TABLE users ADD COLUMN avatar_data {blob_type} NULL",
            "avatar_mime": "ALTER TABLE users ADD COLUMN avatar_mime VARCHAR(30) NULL",
            "avatar_version": "ALTER TABLE users ADD COLUMN avatar_version INT DEFAULT 0",
        }
        for name, sql in statements.items():
            if name in existing:
                print(f"跳过 {name}（已存在）")
                continue
            with db.engine.begin() as connection:
                connection.execute(text(sql))
            print(f"已添加 {name}")

        print("完成；当前字段：", ", ".join(sorted(col["name"] for col in inspect(db.engine).get_columns("users"))))


if __name__ == "__main__":
    main()
