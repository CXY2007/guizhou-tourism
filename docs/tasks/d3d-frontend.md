# 任务包：D3-D 前端（前端开发）

## 边界
- 只改模板/静态：`app/templates/**`、`app/static/js/**`、`app/static/css/src/input.css`（追加）。
- **不要改**任何 Python、`.env`、`tests/**`、`scripts/**`；不要 `git commit`。
- 后端并行实现，按下面契约编码；8900 是旧代码，不要重启它。

## 新增页面（Jinja，继承 base.html）

### 1. 行程页 `/itinerary`（公开）
- 上下文：`attractions`（published 列表）。
- 顶部标题 + 说明；景点多选卡片（封面/名称/城市/评分），至少选 2 个。
- 天数下拉 1–5；「生成行程」按钮。
- JS `static/js/itinerary.js`：
  - `POST /api/itinerary/generate` `{attraction_ids:[...], days}`（带 `X-CSRFToken`）。
  - 渲染按天分组：上午/下午/晚上；每个景点名可点进详情。
  - 登录用户显示标题输入 + 「保存行程」→ `POST /api/itineraries` `{title, days, items}`；未登录显示“登录后可保存”链接。
  - 容器上放 `data-logged-in="{{ '1' if current_user.is_authenticated else '0' }}"`。
- 失败/空态提示。

### 2. 预订页 `/booking/<attraction_id>`（登录）
- 上下文：`attraction`。
- 左：景点封面/名称/城市/门票；右：表单（日期 `min=今天`、人数 1–10、合计金额实时计算）。
- JS `static/js/booking.js`：`POST /api/bookings` `{attraction_id, visit_date, quantity}`（CSRF）；成功后跳 `/orders`。
- 金额 = 单价 × 人数；免费景点显示“免费”。

### 3. 我的订单 `/orders`（登录）
- 上下文：`orders`，每条 dict：`{id, attraction:{name,slug}, visit_date, quantity, unit_price, total, status, created_at}`。
- 表格/卡片：景点、日期、人数、金额、状态（待支付/已支付/已取消）。
- `pending` 行显示「模拟支付」按钮 → `POST /api/bookings/<id>/pay`，成功后刷新。
- 空态 + 去景点列表链接。

## 后台页面（继承 base.html，含 `components/admin_nav.html`）

`admin_nav.html`：标签「仪表盘 /admin」「景点管理 /admin/attractions」「评论审核 /admin/comments」「订单 /admin/orders」，当前页高亮（用 `request.path` 判断）。

### 4. 仪表盘 `/admin`
- 上下文：`counts` `{attractions,pending_comments,orders,users}`。
- 四张统计卡 + 快捷入口。

### 5. 景点管理 `/admin/attractions`
- 上下文：`items`（景点列表）、`total`、`q`、`status`。
- 搜索表单 GET（`q`）、状态筛选（全部/published/draft）。
- 表格：封面缩略图、名称、城市/分类、票价、状态；操作：编辑、上架/下架（POST `/admin/attractions/<id>/status`，hidden `status` 为目标状态）、删除（POST `/admin/attractions/<id>/delete`，`onsubmit` 确认）。
- 「新增景点」→ `/admin/attractions/new`。

### 6. 景点表单 `/admin/attractions/new` 与 `/admin/attractions/<id>/edit`
- 上下文：`attraction`（新建为 None）。
- 字段名必须与后端一致：
  `slug,name,summary,description,category,city,region,price,open_time,ticket_note,visit_duration,best_months,seasonal,transport,tips,address,lng,lat,cover_image,tags,status`
- `category` 下拉：自然/人文/红色/科技/季节；`status`：draft/published；`seasonal` checkbox；`tags` 逗号分隔字符串（编辑时用 `attraction.tags|join(',')`，空则空）。
- 两列布局、移动端单列；提交 POST 到当前 URL。

### 7. 订单管理 `/admin/orders`
- 上下文：`orders`，每条 dict：`{id,user,attraction,visit_date,quantity,total,status,created_at}`。
- 表格展示 + 状态徽标，只读。

## 需要顺手改的两处
- `components/nav.html`：主导航加「行程」→ `/itinerary`；管理员「后台」链接改为 `/admin`。
- `pages/attraction_detail.html`：把「预订」按钮改成链接 `/booking/{{ attraction.id }}`（端点名 `url_for('user.booking', attraction_id=attraction.id)`）。

## 样式与脚本
- 只追加 `input.css`；沿用现有 tokens（ink/teal/cinnabar/paper/gold/mist），移动端单列。
- 脚本用 `defer`，放在各页面 content 末尾；CSRF 从 `meta[name="csrf-token"]` 读。
- 所有动态文本用 `textContent` 或转义，避免 innerHTML 注入。

## 验收
- `npx tailwindcss -i app/static/css/src/input.css -o app/static/css/app.css --minify` 通过。
- `node --check` 新 JS 通过。
- 不跑 Python 测试、不重启服务；DSH 合并后统一验证。
- 报告：改动文件、构建结果、页面清单。
