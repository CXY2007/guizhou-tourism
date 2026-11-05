"""把当前 MySQL 数据整份导出成 SQLite 文件，供“他机源码运行”的交付副本使用。

    python scripts/export_sqlite.py                 # 默认写到 instance/guizhou.db
    python scripts/export_sqlite.py 路径/x.db       # 自定义目标

只读源库，不会改动 MySQL。
"""
from __future__ import annotations

import pathlib
import sys

from sqlalchemy import create_engine, select

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> None:
    target = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "instance" / "guizhou.db"
    if not target.is_absolute():
        target = (ROOT / target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()

    app = create_app()
    source_uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if source_uri.startswith("sqlite"):
        raise SystemExit(f"源库已经是 SQLite：{source_uri}")

    source = create_engine(source_uri, pool_pre_ping=True)
    destination = create_engine(f"sqlite:///{target.as_posix()}")

    db.metadata.create_all(destination)

    with source.connect() as src, destination.begin() as dst:
        for table in db.metadata.sorted_tables:
            rows = src.execute(select(table)).mappings().all()
            if rows:
                dst.execute(table.insert(), [dict(row) for row in rows])
            print(f"{table.name:24} {len(rows):5} 行")

    size_kb = target.stat().st_size / 1024
    print(f"\n导出完成：{target}  {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
