# Task: admin user management — backend

## Boundaries
- Allowed: `app/blueprints/admin.py` (append routes/helper), `tests/test_admin_users.py` (new).
- Forbidden: `app/templates/**`, `app/static/**`, `app/models.py`, `app/config.py`, other blueprints, `app/i18n.py`.
- Do not run `git commit`.
- The frontend template `admin/users.html` is owned by another 协作流程 and may not exist while you run pytest. Do NOT create it. Do NOT test `GET /admin/users` rendering; test POST/DB behavior only.

## Contract

### GET `/admin/users`
Admin only (use `@admin_required`). Query params:
- `q`: optional; case-insensitive match on `username` OR `nickname`.
- `status`: optional; `active` or `disabled`.
- `role`: optional; `user` or `admin`.
- `page`: int >= 1, page size **20**.
- Order: `created_at desc, id desc`.
- Context for `admin/users.html`:
  `users` (User list), `total` (int), `q` (str), `status` (str), `role` (str), `page` (int), `pages` (int).

### POST `/admin/users/<int:user_id>/status`
Admin only. Form fields:
- `status`: target `active` or `disabled`.
Behavior:
- Missing user -> `t("用户不存在")`, 404.
- Invalid status -> flash `t("状态不合法")`, no change, redirect `/admin/users`.
- Target is current user AND target status `disabled` -> flash `t("不能禁用自己")`, no change, redirect.
- Target is an **active admin** being disabled, and active admin count <= 1 -> flash `t("不能禁用最后一个管理员")`, no change, redirect.
- Otherwise set status, commit, flash `t("用户状态已更新")`, redirect `/admin/users`.

## Tests
Create `tests/test_admin_users.py` using SQLite in-memory, mirroring `tests/test_d3d.py`:
- admin disable normal user -> 302, DB status `disabled`
- admin enable disabled user -> 302, DB status `active`
- admin disable self -> no change, still `active`
- last-admin guard: log in as admin A, set A.status disabled in DB (session remains), then disable the only other active admin B -> blocked, B stays `active`
- non-admin (logged in user) posting -> 302 redirect (admin_required)
- missing user -> 404
- invalid status -> no change
- anonymous -> 302

## Acceptance
- `python -m pytest tests -q` passes.
- Do not restart port 8900.
- Final report: changed files, pytest result, curl command DSH should run.
