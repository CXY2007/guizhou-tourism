# 任务包：D3-D 后端（后端开发）

## 边界
- 只改 Python：`app/blueprints/api.py`（追加）、`app/blueprints/admin.py`（扩展）、`app/blueprints/user.py`（追加页面路由）、`app/services/itinerary.py`（新建）、`tests/test_d3d.py`（新建）。
- **不要改** `app/templates/**`、`app/static/**`、`app/models.py`、`app/config.py`、`.env`、其他 service。
- 不要 `git commit`。输出保持简短，不要打印整份文件或完整 diff。

## 一、预订 API
- `POST /api/bookings`（登录）：`{attraction_id:int, visit_date:"YYYY-MM-DD", quantity:1..10}`
  - 景点必须 published；日期 ≥ 今天；`unit_price=attraction.price or 0`，`total=unit_price*quantity`。
  - 写 `bookings(status='pending', payment_method='mock')`；返回 201 `{ok,data:{id,total,unit_price,status}}`。
- `GET /api/orders`（登录）：自己的订单倒序；每条 `{id, attraction:{id,name,slug}, visit_date, quantity, unit_price, total, status, created_at}`。
- `POST /api/bookings/<id>/pay`（登录）：只能付自己的；`pending→paid`；已付返回 409 `already_paid`；不存在 404。

## 二、行程 API
- `POST /api/itinerary/generate`（公开）：`{attraction_ids:[int], days:1..5}`
  - 去重后 2–8 个，全部 published；非法 400 `invalid_params`。
  - 规则：按 `(city, rating desc)` 排序，每 2 个一组分到 `morning`/`afternoon`，`evening` 恒为 null；不足留 null。
  - 返回 `{days:[{day:1,morning:{id,name,slug,city},afternoon:{...}|null,evening:null}]}`。
- `POST /api/itineraries`（登录）：`{title, days, items}`，写 `itineraries`；返回 `{id}`。
- `GET /api/itineraries`（登录）：自己的行程列表。

## 三、后台 SSR 路由（全部 `admin_required`，函数名即端点名）
- `GET /admin` → `admin.dashboard`：仪表盘，渲染 `admin/dashboard.html`，上下文 `{counts:{attractions,pending_comments,orders,users}}`。
- `GET /admin/attractions` → `admin.attractions`：列表，渲染 `admin/attractions.html`，上下文 `{items,total,q,status}`。
- `GET /admin/attractions/new` → `admin.attraction_new`：渲染 `admin/attraction_form.html`，`attraction=None`。
- `GET /admin/attractions/<id>/edit` → `admin.attraction_edit`：同上，带 attraction。
- `POST /admin/attractions/new`、`POST /admin/attractions/<id>/edit`：同上端点，从 `request.form` 读取字段：
  `slug,name,summary,description,category,city,region,price,open_time,ticket_note,visit_duration,best_months,seasonal,transport,tips,address,lng,lat,cover_image,tags,status`
  - 校验：slug 必填且唯一、name 必填、category ∈ 自然/人文/红色/科技/季节、price≥0、lng/lat 范围、visit_duration 整数。
  - `tags` 逗号分隔 → JSON 数组；`seasonal` 复选框存在即 True；`status` 只能 draft/published。
  - 成功 flash 并 redirect 到列表；失败 flash 错误并回填（render 同模板）。
- `POST /admin/attractions/<id>/status` → `admin.attraction_status`：表单 `status`（draft/published）；发布前校验 name/summary/description/cover_image，不满足 flash 错误不切换。
- `POST /admin/attractions/<id>/delete` → `admin.attraction_delete`：被 bookings/comments/favorites/ratings 引用 → 置 `status='draft'` 并 flash；否则硬删。
- `GET /admin/orders` → `admin.orders`：全部订单倒序，渲染 `admin/orders.html`，上下文 `{orders}`（每条 dict：`{id,user,attraction,visit_date,quantity,total,status,created_at}`）。

## 四、用户页面路由（渲染模板，由前端负责写模板）
- `GET /booking/<int:attraction_id>` → `user.booking`（登录）：published 景点；渲染 `pages/booking.html`，上下文 `{attraction}`；不存在 404。
- `GET /orders` → `user.orders`（登录）：自己的订单；渲染 `pages/orders.html`，上下文 `{orders}`（每条 dict 同 API：`{id,attraction:{id,name,slug},visit_date,quantity,unit_price,total,status,created_at}`）。
- `GET /itinerary` → `user.itinerary`（公开）：published 景点；渲染 `pages/itinerary.html`，上下文 `{attractions}`。

## 五、测试
- 新建 `tests/test_d3d.py`，复用 `test_d3c.py` 的 SQLite 内存库 + `client` fixture 风格。
- 覆盖：预订创建/支付/重复支付 409、行程 generate 正常与非法、admin 非管理员被重定向、admin 新建/编辑/删除景点（POST）、后台订单 GET 需要模板——**跳过依赖新模板的 GET 断言**，DSH 会在前端完成后统一验。
- `python -m pytest tests -q` 全过。

## 运行环境
- 8900 上跑旧代码，不要重启；用 pytest 验证。
- 若模板不存在导致 GET 渲染失败，不要创建模板（前端负责），只测 API/POST。
