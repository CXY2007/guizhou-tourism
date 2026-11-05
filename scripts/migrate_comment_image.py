"""给 comments 表补 image_url 字段（评论区发图）。

    python scripts/migrate_comment_image.py

幂等：字段已存在就跳过。
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
        existing = {column["name"] for column in inspect(db.engine).get_columns("comments")}
        if "image_url" in existing:
            print("跳过 image_url（已存在）")
        else:
            with db.engine.begin() as connection:
                connection.execute(text("ALTER TABLE comments ADD COLUMN image_url VARCHAR(255) NULL"))
            print("已添加 comments.image_url")
        print("当前字段:", ", ".join(sorted(c["name"] for c in inspect(db.engine).get_columns("comments"))))


if __name__ == "__main__":
    main()
