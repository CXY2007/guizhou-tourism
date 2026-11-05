# Task: admin user management — frontend (前端开发)

## Boundaries
- Allowed: `app/templates/admin/users.html` (new), `app/templates/components/admin_nav.html`, `app/static/js/admin_users.js` (new), `app/static/css/src/input.css` (append only).
- Forbidden: any Python, `app/models.py`, `app/config.py`, `app/i18n.py`, other templates/JS.
- Do not run `git commit`. Do not restart the server on 8900 (old code).
- The backend route is being written by another 协作流程 in parallel; code against the contract below.

## Contract
`GET /admin/users` context:
- `users`: User objects with `id, username, nickname, role, status, created_at`.
- `total`, `q`, `status`, `role`, `page`, `pages`.
- Page size 20.

`POST /admin/users/<id>/status` (form):
- `csrf_token`, `status` = `active` or `disabled`.
- Backend guards: cannot disable self, cannot disable the last active admin.

## Page `/admin/users`
- `page-head`: eyebrow `USERS`, title 用户管理.
- Include `components/admin_nav.html` (add a 用户 tab linking `/admin/users`).
- Toolbar:
  - search form GET `/admin/users` with `q` (placeholder 搜索用户名 / 昵称), `status` select (全部/正常/禁用), `role` select (全部/管理员/普通用户), 筛选 button.
  - total: `共 {total} 个`.
- Table (`.data-table-wrap` / `.data-table`):
  - columns: ID, 用户名, 昵称, 角色, 状态, 注册时间, 操作.
  - role: 管理员 / 普通用户.
  - status badge: 正常 (`status-active`) / 禁用 (`status-disabled`).
  - created_at: `%Y-%m-%d`.
  - action: if `user.id == current_user.id`, show `当前账号` text; else a POST form to `/admin/users/<id>/status` with hidden `csrf_token` and hidden `status` = `disabled` if active else `active`; button 禁用/启用; add `data-confirm` and confirm on submit.
- Empty state: 没有匹配的用户.
- Pagination: prev/next preserving `q,status,role`.
- Mobile: single-column/scrollable table; use existing tokens (ink/teal/cinnabar/paper/gold/mist).

## JS
`admin_users.js`: attach `submit` confirm using `data-confirm` (no inline JS), nothing else.

## Acceptance
- `npx tailwindcss -i app/static/css/src/input.css -o app/static/css/app.css --minify` passes.
- `node --check app/static/js/admin_users.js` passes.
- No Python edits; no template for other pages.
- Report changed files + build result.
