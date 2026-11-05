"""一次性脚本：给历史行程补英文版缓存（items._en）。

保存时预翻译只对之后新建的行程生效，这个脚本把存量补齐，
之后英文站打开任何一条都不会再等模型。

用法：
    $env:PYTHONPATH="."; python scripts/backfill_itinerary_en.py [--dry-run] [--limit N]

安全点：
- 只写 items._en，不动 brief / days 原文
- 已有 _en 的跳过
- 翻译失败跳过并记下来，不中断
- --dry-run 只统计不写库
"""
from __future__ import annotations

import argparse
import os
import sys
import time

os.environ.setdefault("SITE_PORT", "8900")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少条（0 = 全部）")
    args = parser.parse_args()

    from app import create_app
    from app.extensions import db
    from app.models import Itinerary
    from app.services.ai_itinerary import translate_conflicts, translate_plan

    app = create_app()
    done = skipped = failed = 0
    started = time.monotonic()

    with app.app_context():
        rows = db.session.query(Itinerary).order_by(Itinerary.id.asc()).all()
        targets = []
        for row in rows:
            items = row.items
            if not isinstance(items, dict):
                skipped += 1  # 老结构（纯 days 数组），没有 brief 可译，跳过
                continue
            if items.get("_en"):
                skipped += 1
                continue
            targets.append(row)

        print(f"总行程 {len(rows)} 条，待翻译 {len(targets)} 条，跳过 {skipped} 条")
        if args.dry_run:
            for row in targets:
                print(f"  [dry-run] id={row.id} title={row.title[:20]} days={row.days}")
            return 0

        if args.limit:
            targets = targets[: args.limit]

        for index, row in enumerate(targets, start=1):
            items = row.items
            t0 = time.monotonic()
            translated = translate_plan(
                {"brief": items.get("brief") or {}, "days": items.get("days") or []}, "en"
            )
            if not translated or not (translated.get("brief") or translated.get("days")):
                failed += 1
                print(f"  [{index}/{len(targets)}] id={row.id} 翻译失败，跳过")
                continue

            cached = {
                "brief": translated.get("brief") or {},
                "days": translated.get("days") or [],
            }
            raw_conflicts = (items.get("brief") or {}).get("conflicts")
            if raw_conflicts and not cached["brief"].get("conflicts"):
                conflicts_en = translate_conflicts(raw_conflicts, "en")
                if conflicts_en:
                    cached["brief"]["conflicts"] = conflicts_en

            stored = dict(items)
            stored["_en"] = cached
            row.items = stored
            db.session.commit()
            done += 1
            print(
                f"  [{index}/{len(targets)}] id={row.id} ok "
                f"{int((time.monotonic() - t0) * 1000)}ms "
                f"brief={len(cached['brief'])} days={len(cached['days'])}"
            )

    total = int(time.monotonic() - started)
    print(f"\n完成：成功 {done}，失败 {failed}，跳过 {skipped}，耗时 {total}s")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
