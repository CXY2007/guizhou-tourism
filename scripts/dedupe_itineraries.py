"""一次性脚本：清理历史重复的行程记录。

重复的定义（三者全同才算重复）：
    user_id + title + items 内容（比较时排除 _en 英文缓存）
每组保留 id 最大的那条（最新），其余删除。

用法：
    $env:PYTHONPATH="."; python scripts/dedupe_itineraries.py            # 预览（默认，只读）
    $env:PYTHONPATH="."; python scripts/dedupe_itineraries.py --apply    # 真正删除

安全点：
- 默认只预览，必须显式 --apply 才写库
- 只删「组内除最新之外」的记录，永远保留最新一条
- 内容有任何差异都不算重复，不碰
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
from datetime import datetime
from collections import defaultdict

os.environ.setdefault("SITE_PORT", "8900")


def core(value):
    """剥掉 _en 之后的内容，用于比较。"""
    if isinstance(value, dict):
        return {key: item for key, item in value.items() if key != "_en"}
    return value


def fingerprint(row):
    return (
        row.user_id,
        row.title,
        json.dumps(core(row.items), sort_keys=True, ensure_ascii=False, default=str),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="真正执行删除（默认只预览）")
    parser.add_argument("--backup", default="", help="删除前把被删记录导出到此路径（默认写 logs/）")
    args = parser.parse_args()

    from app import create_app
    from app.extensions import db
    from app.models import Itinerary, User

    app = create_app()
    with app.app_context():
        rows = Itinerary.query.order_by(Itinerary.id.asc()).all()
        groups = defaultdict(list)
        for row in rows:
            groups[fingerprint(row)].append(row)

        users = {u.id: u.username for u in User.query.all()}
        total_del = 0
        dup_groups = [(key, items) for key, items in groups.items() if len(items) > 1]

        print(f"行程总数 {len(rows)}，完全重复的分组 {len(dup_groups)} 组\n")
        for (user_id, title, _content), items in dup_groups:
            keep = items[-1]
            drop = items[:-1]
            total_del += len(drop)
            print(f"[{users.get(user_id, user_id)}] {title!r}")
            print(f"   保留 id={keep.id}  删除 {[r.id for r in drop]}  （共 {len(items)} 条）")

        if not dup_groups:
            print("没有需要清理的重复记录")
            return 0

        print(f"\n合计：将删除 {total_del} 条，保留 {len(rows) - total_del} 条")
        if not args.apply:
            print("\n这是预览。确认无误后加 --apply 执行。")
            return 0

        # 删之前把要删的记录整份导出，万一想找回还能重建
        backup_path = pathlib.Path(args.backup) if args.backup else pathlib.Path(
            f"logs/dedupe_itineraries_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        dumped = []
        for (_uid, _title, _content), items in dup_groups:
            for row in items[:-1]:
                dumped.append({
                    "id": row.id,
                    "user_id": row.user_id,
                    "title": row.title,
                    "days": row.days,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "items": row.items,
                })
        backup_path.write_text(json.dumps(dumped, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已备份 {len(dumped)} 条到 {backup_path}")

        for (user_id, title, _content), items in dup_groups:
            for row in items[:-1]:
                db.session.delete(row)
        db.session.commit()
        print(f"已删除 {total_del} 条，剩余 {Itinerary.query.count()} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
