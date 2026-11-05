"""为演示库重置/创建演示账号口令（SQLite 与 MySQL 通用）。

用法：
    python scripts/seed_demo_accounts.py            # 有则重置口令，无则创建
    python scripts/seed_demo_accounts.py --keep      # 只创建缺失的账号，不重置已有口令

口令随机生成，只在终端打印一次；不写入任何文件。
"""
from __future__ import annotations

import argparse
import pathlib
import secrets
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402

ACCOUNTS = [("admin", "admin", "管理员")] + [(f"demo", "user", "小旅")] + [
    (f"tourist{i}", "user", f"游客{i}") for i in range(1, 9)
]
ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789!@#%^&*"


def new_password() -> str:
    return "Gz#" + "".join(secrets.choice(ALPHABET) for _ in range(14))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="不重置已有账号的口令")
    args = parser.parse_args()

    app = create_app()
    created, reset, kept = [], [], []
    with app.app_context():
        for username, role, nickname in ACCOUNTS:
            user = User.query.filter_by(username=username).first()
            if user is None:
                plain = new_password()
                db.session.add(User(username=username, password_hash=generate_password_hash(plain),
                                    role=role, nickname=nickname, status="active"))
                created.append((username, plain))
            elif args.keep:
                kept.append(username)
            else:
                plain = new_password()
                user.password_hash = generate_password_hash(plain)
                user.role = role
                user.status = "active"
                reset.append((username, plain))
        db.session.commit()

    print(f"\n{'账号':<12}{'角色':<8}口令（只显示这一次）")
    print("-" * 46)
    for username, plain in created + reset:
        role = dict((name, r) for name, r, _ in ACCOUNTS)[username]
        print(f"{username:<12}{role:<8}{plain}")
    if kept:
        print(f"\n保留未改动：{', '.join(kept)}")
    print("\n请立刻把这些口令改掉，或删除本终端记录。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
