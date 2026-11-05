# API 契约

- 版本：v1.0（D1 冻结）
- 风格：服务端渲染（Jinja 页面）+ 少量 JSON API（异步交互）
- 鉴权：Flask session cookie（`HttpOnly`、`SameSite=Lax`）；写操作校验 CSRF
- 基础路径：同源 `/`

---

## 1. 约定

### 1.1 响应包裹

```json
{ "ok": true,  "data": { }, "error": null }
{ "ok": false, "data": null, "error": { "code": "login_required", "message": "请先登录" } }
```

### 1.2 状态码

| 码 | 含义 |
|---|---|
| 200 | 成功 |
| 201 | 创建成功 |
| 400 | 参数错误 |
| 401 | 未登录 / `login_required` |
| 403 | 无权限（角色不足） |
| 404 | 资源不存在 |
| 409 | 冲突（重复收藏/评分） |
| 429 | 限流（AI / 登录尝试） |
| 500 | 服务异常 |

> 页面路由（SSR）未登录时 **302 到 `/login?next=<原路径>`**；JSON API 返回 401 + 统一包裹。两者不混用。

### 1.3 写操作

`POST/PUT/DELETE` 需带 CSRF token（`X-CSRFToken` 或表单 `_csrf_token`）。

## 2. 页面路由

| 方法 | 路由 | 角色 | 说明 |
|---|---|---|---|
| GET | `/` | 全部 | 首页 |
| GET | `/attractions` | 全部 | 列表（`?category=&city=&sort=&page=`） |
| GET | `/attractions/<slug>` | 全部 | 详情 |
| GET | `/routes` | 全部 | 主题线路 |
| GET | `/itinerary` | 全部 | 行程规划页 |
| GET | `/search` | 全部 | 搜索（`?q=`） |
| GET | `/about` | 全部 | 关于 |
| GET/POST | `/login` | 游客 | 登录 |
| GET/POST | `/register` | 游客 | 注册 |
| POST | `/logout` | 用户 | 退出（POST + CSRF） |
| GET | `/profile` | 用户 | 个人中心 |
| GET | `/favorites` | 用户 | 收藏页 |
| GET | `/orders` | 用户 | 订单页 |
| GET/POST | `/booking/<id>` | 用户 | 预订（演示） |
| GET | `/admin` | 管理员 | 仪表盘 |
| GET/POST | `/admin/attractions` | 管理员 | 列表/新增 |
| GET/POST | `/admin/attractions/<id>/edit` | 管理员 | 编辑 |
| POST | `/admin/attractions/<id>/status` | 管理员 | 上下架 |
| GET | `/admin/comments` | 管理员 | 审核列表 |
| GET | `/admin/users` | 管理员 | 用户管理 |
| GET | `/admin/orders` | 管理员 | 订单管理 |

## 3. JSON API

### 3.1 景点

**GET `/api/attractions`**

| 参数 | 类型 | 说明 |
|---|---|---|
| `category` | string | 自然/人文/红色/科技/季节 |
| `city` | string | 市州 |
| `q` | string | 关键词（name/summary） |
| `sort` | enum | `rating`(默认) / `price` / `newest` |
| `page` / `size` | int | 默认 1 / 12，size ≤ 48 |

> `city` 指**市州**（筛选维度，如“安顺”）；`region` 指**区县**（仅展示，不参与筛选）。

```json
{ "ok": true, "data": { "items": [
  { "id": 1, "slug": "huangguoshu", "name": "黄果树瀑布", "summary": "亚洲第一大瀑布",
    "city": "安顺", "category": "自然", "price": 160, "rating": 4.8,
    "rating_count": 128, "cover_image": "/static/images/webp/huangguoshu-cover.webp",
    "tags": ["瀑布","5A"] }
], "total": 18, "page": 1, "size": 12 }, "error": null }
```

**GET `/api/attractions/<slug>`** → 详情（含 gallery、天气占位、`can_favorite`）

### 3.2 搜索

**GET `/api/search?q=瀑布`** → `{ items, total, suggestions }`；支持 `category` 过滤；无结果时 `suggestions` 返回热门 3 条。

### 3.3 天气

**GET `/api/weather/<attraction_id>`**

```json
{ "ok": true, "data": {
  "city": "安顺",
  "live": {"weather":"阴","temperature":"12","humidity":"92","winddirection":"东北风","windpower":"3","obsTime":"2026-10-29T18:15+08:00"},
  "forecast": [{"date":"2026-10-30","week":"五","dayweather":"阴","nightweather":"阴","daytemp":"21","nighttemp":"14"}],
  "advice": "早晚偏凉，建议带件外套。", "source": "hefeng" }, "error": null }
```

失败时 `ok:false, error.code:"weather_unavailable"`（502），前端展示兜底文案，不阻塞页面。

### 3.4 AI 小球

**POST `/api/assistant`**

```json
{ "message": "带我去黄果树", "session_id": "s-20261029-001" }
```

```json
{ "ok": true, "data": {
  "reply": "黄果树瀑布在安顺，门票 160 元，建议玩 4–6 小时。",
  "intent": "navigate",
  "action": { "type": "navigate", "url": "/attractions/huangguoshu" },
  "confidence": 0.92
}, "error": null }
```

**调度方式**

- 配置 `AI_API_KEY` 时优先走 **DeepSeek 函数调用**：5 个只读工具（导航 / 搜索 / 天气 / 景点事实 / 行程），最多 3 轮；用尽后强制一次纯文本收尾
- 未配置 key、请求失败或超时（`AI_TIMEOUT`，默认 15s）→ 自动回退规则意图路由
- 英文提问可用：景点名走 `attraction_translations`，slug 兼容连字符/空格；分类「红色」同时匹配库里的「红色文化」
- 模型偶发把工具调用语法写进正文时，会要求它用纯文本重答一次；仍不干净则回退规则引擎
- LLM 模式下 `intent` 为 `llm`，并额外返回 `links`（工具结果生成的可点景点链接）

```json
{ "ok": true, "data": {
  "reply": "黄果树瀑布在安顺，门票 160 元，建议玩 4–6 小时。",
  "intent": "llm",
  "action": { "type": "navigate", "url": "/attractions/huangguoshu" },
  "confidence": 0.9,
  "links": [{ "name": "黄果树瀑布", "url": "/attractions/huangguoshu" }]
}, "error": null }
```

**意图枚举**：`navigate | search | itinerary | qa | weather | booking | help | llm`

> 语言：`?lang=en` 优先，其次 cookie `lang`，默认 `zh`。`/api/attractions*` 按语言返回 `name/summary/description/poetic`，缺失回退中文；模板字符串由 Flask-Babel 翻译。

**动作类型**

| type | 参数 | 前端行为 |
|---|---|---|
| `navigate` | `url`（站内白名单） | 路由跳转 |
| `search` | `keyword` / `category` | 跳 `/search` 或 `/attractions` |
| `itinerary` | `attraction_ids[]`、`days` | 跳 `/itinerary` 并预填 |
| `booking` | `attraction_id` | 跳 `/booking/<id>` |
| `null` | — | 只回复，不跳转 |

**约束**

- `action.url` 与工具 `navigate` 的路径都必须以 `/` 开头且属于白名单（`/`、`/attractions`、`/attractions/<slug>`、`/itinerary`、`/profile`、`/orders`、`/booking/<id>`），`/admin` 与站外地址一律拒绝
- `links` 只由工具结果生成，不由模型自由编造
- 服务端对 message 限长 500 字；同一 session + 来源 IP 限流 20 次/分钟（`AI_RATE_LIMIT`），超限 429 `rate_limited`
- 工具只读：不写库、不下单、不修改用户数据

### 3.5 收藏

| 方法 | 路由 | 说明 |
|---|---|---|
| GET | `/api/favorites` | 我的收藏列表 |
| POST | `/api/favorites/<attraction_id>` | 切换收藏，返回 `{favorited: true|false}` |
| GET | `/api/favorites/<attraction_id>/status` | 是否已收藏 |

未登录：401 `login_required`。

> 切换收藏是幂等的：重复请求不返回 409，以最终状态为准。

### 3.6 评论

| 方法 | 路由 | 说明 |
|---|---|---|
| GET | `/api/comments?attraction_id=1` | 仅返回 `approved`，按时间倒序 |
| POST | `/api/comments` | `{attraction_id, content, parent_id?}`；入库 `pending` |
| DELETE | `/api/comments/<id>` | 作者本人或管理员 |

### 3.7 评分

| 方法 | 路由 | 说明 |
|---|---|---|
| POST | `/api/ratings` | `{attraction_id, rating:1..5}`；重复提交为更新 |
| GET | `/api/ratings/<attraction_id>` | 返回我的评分、平均分、人数 |

> 写评分与重算 `attractions.rating/rating_count` 在**同一事务**内完成。

**GET `/api/attractions/<attraction_id>/stats`**

```json
{ "ok": true, "data": {
  "pie": [{"rating":1,"count":0},{"rating":2,"count":0},{"rating":3,"count":1},
          {"rating":4,"count":3},{"rating":5,"count":2}],
  "weeks": ["2026-W44"], "averages": [4.17], "total": 6, "avg": 4.17 }, "error": null }
```

1–5 星分布 + 最近 8 周平均分；无数据返回空数组；景点不存在 404。

### 3.8 预订（演示）

| 方法 | 路由 | 说明 |
|---|---|---|
| POST | `/api/bookings` | `{attraction_id, visit_date, quantity}`；校验日期 ≥ 今天、1 ≤ 人数 ≤ 10 |
| GET | `/api/orders` | 我的订单 |
| POST | `/api/bookings/<booking_id>/pay` | 模拟支付，`pending → paid`；已支付再付返回 409 `already_paid` |

> 页面 `/booking/<attraction_id>` 的参数是**景点 ID**；提交订单后返回 `booking_id`，支付接口使用 `booking_id`。

### 3.9 行程

| 方法 | 路由 | 说明 |
|---|---|---|
| POST | `/api/itinerary/generate` | **游客可用**。`{attraction_ids:[1,2,3], days:3}` → 按天分组的建议日程（不落库） |
| POST | `/api/itineraries` | 需登录。`{title, days, items}` 保存 |
| GET | `/api/itineraries` | 需登录。我的行程 |

`generate` 响应：

```json
{ "ok": true, "data": { "days": [
  { "day": 1, "morning": {"slug":"huangguoshu","name":"黄果树瀑布"},
    "afternoon": {"slug":"longgong","name":"龙宫"}, "evening": null }
] }, "error": null }
```

规则：`attraction_ids` 去重、2–8 个；`days` 1–5；按“同市州优先、单日不跨 2 个市州”排布；不足时留空并提示。

### 3.10 管理员

后台页面（`/admin/*`）用 **SSR 表单**提交，负责景点创建/编辑；本节 JSON 端点只供页面内异步动作。

| 方法 | 路由 | 说明 |
|---|---|---|
| GET | `/api/admin/attractions` | 列表（搜索/分页） |
| POST | `/api/admin/attractions/<id>/status` | `{status: draft|published}`；发布前校验 en 翻译、tags、≥4 图，不满足 400 `incomplete` |
| POST | `/api/admin/attractions/<id>/images` | multipart `file`：jpg/png/webp ≤ 5MB，存 `static/uploads/attractions/<slug>/`，返回 `{id,url}`；要求景点已存在 |
| DELETE | `/api/admin/images/<image_id>` | 删除图片记录与文件 |
| POST | `/api/admin/attractions/<id>/delete` | 无引用时硬删；被订单/收藏/评论引用时 409 `in_use`，建议改 `status=draft` |
| POST | `/api/admin/comments/<id>/approve` | `{action: approve|reject}` |
| POST | `/api/admin/users/<id>/role` | `{role: user|admin}` |
| POST | `/api/admin/users/<id>/status` | `{status: active|disabled}`；不能禁用自己或最后一个管理员 |
| GET | `/api/admin/orders` | 全量订单 |

创建表单字段：`slug/name/city/region/category/summary/description/poetic/address/lng/lat/open_time/price/ticket_note/visit_duration/best_months/seasonal/transport/tips/tags/sources` + 英译（`name/summary/description/poetic`）；图片在创建成功拿到 id/slug 后上传。

全部要求 `role=admin`，否则 403 `forbidden`。

### 3.11 个人资料

| 方法 | 路由 | 说明 |
|---|---|---|
| GET | `/api/profile` | 当前用户资料 |
| PUT | `/api/profile` | `{nickname, avatar}` |
| POST | `/api/profile/password` | `{old_password, new_password}`；校验旧密码，成功 200 |

## 4. 权限矩阵

| 端点组 | 游客 | 用户 | 管理员 |
|---|---|---|---|
| `/api/attractions*`、`/api/search`、`/api/weather/*` | ✅ | ✅ | ✅ |
| `/api/assistant` | ✅（20 次/分钟） | ✅ | ✅ |
| `/api/favorites*`、`/api/comments`(POST)、`/api/ratings`(POST)、`/api/bookings`、`/api/itineraries`、`/api/profile*` | ❌ 401 | ✅ | ✅ |
| `/api/admin/*` | ❌ 401 | ❌ 403 | ✅ |

## 5. 错误码

| code | 场景 |
|---|---|
| `invalid_params` | 缺参/类型错/越界 |
| `login_required` | 未登录 |
| `forbidden` | 角色不足 |
| `not_found` | 资源不存在 |
| `duplicate` | 重复评分（收藏为幂等切换） |
| `incomplete` | 发布前校验不通过（翻译 / 图片 / tags） |
| `in_use` | 资源被引用，不能删除 |
| `already_paid` | 订单已支付 |
| `rate_limited` | AI 或登录尝试超限 |
| `weather_unavailable` | 和风失败 |
| `ai_unavailable` | LLM 失败，返回兜底 |
| `internal_error` | 未捕获异常 |

## 6. 非功能约定

- 所有列表分页，默认 12 条，最大 48。
- 响应时间目标：页面 < 300ms（本地），JSON < 200ms；AI 规则模式 < 300ms，LLM 模式 2–6s（含工具轮次）。
- 图片走静态目录 + 长缓存；JSON 不缓存（`Cache-Control: no-store`）。
- 日志记录：AI 请求写 `assistant_logs`；后台写操作记录操作者与时间。
