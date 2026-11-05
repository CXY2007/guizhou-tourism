"""给 comments 表补 AI 审核字段（review_by / ai_reason）。

    python scripts/migrate_comment_review.py

幂等：字段已存在就跳过；历史评论标记为 seed（预置数据）。
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
        statements = {
            "review_by": "ALTER TABLE comments ADD COLUMN review_by VARCHAR(10) DEFAULT 'human'",
            "ai_reason": "ALTER TABLE comments ADD COLUMN ai_reason VARCHAR(255) NULL",
        }
        for name, sql in statements.items():
            if name in existing:
                print(f"跳过 {name}（已存在）")
                continue
            with db.engine.begin() as connection:
                connection.execute(text(sql))
            print(f"已添加 {name}")

        with db.engine.begin() as connection:
            updated = connection.execute(
                text("UPDATE comments SET review_by = 'seed' WHERE review_by = 'human' AND ai_reason IS NULL")
            ).rowcount
        print(f"历史评论标记为 seed：{updated} 条")
        print("当前字段:", ", ".join(sorted(c["name"] for c in inspect(db.engine).get_columns("comments"))))


if __name__ == "__main__":
    main()
