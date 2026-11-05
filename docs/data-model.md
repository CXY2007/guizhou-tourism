# 数据模型（ERD + 数据字典）

- 版本：v1.0（D1 冻结）
- 库：MySQL 8.0.46 / `tourism_data` / utf8mb4
- 原则：**保留现有 8 条景点与关联数据**，只做增量迁移；新表用 InnoDB + 外键。

---

## 1. ERD

```
users 1 ──< favorites >── 1 attractions 1 ──< attraction_images
  │                          │ 1
  │                          └──< attraction_translations
  ├──< comments >────────────┘
  ├──< ratings >─────────────┘
  ├──< bookings >────────────┘
  ├──< itineraries
  └──< assistant_logs (user_id 可空)
```

## 2. 表定义

### 2.1 users（改）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | INT | PK, AI | |
| username | VARCHAR(50) | UNIQUE, NOT NULL | 登录名 |
| password_hash | VARCHAR(255) | NOT NULL | werkzeug 哈希 |
| role | ENUM('user','admin') | NOT NULL DEFAULT 'user' | 三级权限中的两级（游客=未登录） |
| nickname | VARCHAR(50) | NULL | 展示名 |
| avatar | VARCHAR(255) | NULL | 头像 URL |
| status | ENUM('active','disabled') | NOT NULL DEFAULT 'active' | 禁用后不能登录 |
| created_at | DATETIME | DEFAULT CURRENT_TIMESTAMP | |
| last_login | DATETIME | NULL | |

```sql
ALTER TABLE users
  ADD COLUMN role ENUM('user','admin') NOT NULL DEFAULT 'user' AFTER password_hash,
  ADD COLUMN nickname VARCHAR(50) NULL AFTER role,
  ADD COLUMN avatar VARCHAR(255) NULL AFTER nickname,
  ADD COLUMN status ENUM('active','disabled') NOT NULL DEFAULT 'active' AFTER avatar,
  ADD COLUMN last_login DATETIME NULL;
```

### 2.2 attractions（改）

保留现有字段：`id, name, description, address, city, province, longitude, latitude, cover_image, category, rating, rating_count, price, open_time, best_months, visit_duration, poetic_description, weather_code`。

新增：

| 字段 | 类型 | 说明 |
|---|---|---|
| slug | VARCHAR(120) UNIQUE | URL 标识，如 `huangguoshu` |
| summary | VARCHAR(200) | 一句话卖点（列表/卡片） |
| tags | JSON | `["瀑布","亲子","5A"]` |
| transport | TEXT | 交通提示 |
| tips | TEXT | 避坑/贴士 |
| region | VARCHAR(50) | 区县，如“镇宁” |
| ticket_note | VARCHAR(255) | 含观光车/预约制等说明 |
| seasonal | TINYINT(1) | 1=季节型（樱花/杜鹃） |
| sources | JSON | 官方/新闻来源 URL 数组 |
| verified_at | DATE | 事实核实日期 |
| status | ENUM('draft','published') | 默认 published |
| created_at / updated_at | DATETIME | |

> 英文内容统一存 `attraction_translations(lang='en')`，不在 `attractions` 表内重复。

```sql
ALTER TABLE attractions
  ADD COLUMN slug VARCHAR(120) NULL UNIQUE AFTER id,
  ADD COLUMN summary VARCHAR(200) NULL AFTER name,
  ADD COLUMN tags JSON NULL AFTER category,
  ADD COLUMN transport TEXT NULL AFTER address,
  ADD COLUMN tips TEXT NULL AFTER description,
  ADD COLUMN region VARCHAR(50) NULL AFTER city,
  ADD COLUMN ticket_note VARCHAR(255) NULL AFTER price,
  ADD COLUMN seasonal TINYINT(1) NOT NULL DEFAULT 0 AFTER best_months,
  ADD COLUMN sources JSON NULL,
  ADD COLUMN verified_at DATE NULL,
  ADD COLUMN status ENUM('draft','published') NOT NULL DEFAULT 'published',
  ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
```

### 2.2b attraction_images（改）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT PK AI | |
| attraction_id | INT FK → attractions.id | ON DELETE CASCADE |
| image_url | VARCHAR(255) | 静态路径，建议 WebP |
| caption | VARCHAR(120) NULL | 图注/版权说明 |
| sort_order | INT DEFAULT 0 | 排序 |
| width / height | INT NULL | 原图尺寸，供 srcset |

现有 48 行保留；补 `caption/width/height` 三列（可空），索引 `(attraction_id, sort_order)`。

### 2.3 attraction_translations（新）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT PK AI | |
| attraction_id | INT FK → attractions.id | ON DELETE CASCADE |
| lang | ENUM('zh','en') | |
| name / summary / description / poetic | VARCHAR/TEXT | 对应中文内容 |
| UNIQUE(attraction_id, lang) | | |

### 2.4 comments（改）

新增 `status ENUM('pending','approved','rejected') DEFAULT 'pending'`、`parent_id INT NULL`（回复）。查询前台只取 approved。

### 2.5 favorites / ratings（改）

补唯一约束 `UNIQUE(user_id, attraction_id)`，防重复；ratings 保留 1–5 检查。

> 评分聚合（`attractions.rating/rating_count`）在写评分的同一事务内重算；收藏是幂等切换。景点删除采用软删除：有订单/收藏/评论引用时置 `status=draft`。

### 2.6 bookings（新）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT PK AI | |
| user_id | INT FK → users.id | |
| attraction_id | INT FK → attractions.id | |
| visit_date | DATE | 游玩日期 |
| quantity | INT | 人数/票数 |
| unit_price | DECIMAL(10,2) | 下单时快照 |
| total | DECIMAL(10,2) | |
| status | ENUM('pending','paid','cancelled') | |
| payment_method | VARCHAR(20) | `mock`（演示） |
| created_at | DATETIME | |

### 2.7 itineraries（新）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INT PK AI | |
| user_id | INT FK | |
| title | VARCHAR(120) | |
| days | INT | 1–5 |
| items | JSON | `[{day:1, morning:{attraction_id}, afternoon:{...}, evening:{...}}]` |
| created_at / updated_at | DATETIME | |

### 2.8 assistant_logs（新）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | BIGINT PK AI | |
| user_id | INT NULL | 游客为空 |
| session_id | VARCHAR(64) | 前端生成 |
| message | TEXT | 用户输入 |
| intent | VARCHAR(20) | 7 类意图 |
| action | JSON NULL | 返回的跳转动作 |
| latency_ms | INT | |
| created_at | DATETIME | |

## 3. 数据字典：景点 20 字段（内容侧）

| 字段 | 必填 | 来源 | 示例 |
|---|---|---|---|
| slug | ✅ | 拼音/约定 | `huangguoshu` |
| name_zh / name_en | ✅ | 官方 | 黄果树瀑布 / Huangguoshu Waterfall |
| city / region | ✅ | 行政区划 | 安顺 / 镇宁 |
| category | ✅ | 自然/人文/红色/科技/季节 | 自然 |
| summary_zh/en | ✅ | 60–80 字 | — |
| description_zh/en | ✅ | 300–500 字 | — |
| poetic_zh | ✅ | 80–120 字 | — |
| address | ✅ | 官方 | — |
| lng / lat | ✅ | 高德地理编码 | 105.667, 25.990 |
| open_time | ✅ | 官方 | 07:00–18:00 |
| ticket_price | ✅ | 官方 | 160 |
| ticket_note | ✅ | 含观光车/预约制 | 含观光车 |
| visit_duration | ✅ | 分钟 | 300 |
| best_months | ✅ | 1–12 | 6–10 月 |
| seasonal | ✅ | 是否季节型 | false |
| transport | ✅ | 交通 | 贵阳出发约 2h |
| tips | ✅ | 贴士 | 雨季水大 |
| cover_image / gallery | ✅ | 自有/授权 | — |
| tags | ✅ | 3–5 个 | 瀑布,亲子,5A |
| sources / verified_at | ✅ | 官方链接 + 日期 | — |

## 4. 索引与约束

- `attractions(slug)` UNIQUE；`attractions(city)`、`attractions(category)`、`attractions(status)` 普通索引
- `comments(attraction_id, status)`、`comments(user_id)`
- `favorites/ratings` UNIQUE(user_id, attraction_id)
- `bookings(user_id, status)`、`bookings(attraction_id)`
- 所有外键 `ON DELETE CASCADE`（用户内容）或 `RESTRICT`（景点被引用时）

## 5. 迁移策略

用 **Alembic（Flask-Migrate）** 管理版本，禁止重复执行裸 `ALTER`。每个阶段一个 revision，可回滚：

1. **扩展**：新增列/表（可空或带默认），不收紧约束
2. **回填**：
   - `slug`：拼音；冲突时追加 `-<id>`
   - `summary`：取 `description` 前 60 字
   - `tags`：`[]`；`seasonal`：按景点人工标记
   - `status`：`published`
3. **收紧**：唯一索引/非空约束，只在全量校验通过后执行
4. **导入**：10 个新景点 + 翻译 + 图片

**校验脚本** `scripts/verify_data.py`：18 条 published、slug 唯一、每条 ≥4 图、中英翻译齐全；不通过不进入下一阶段。迁移失败时回滚该 revision，并保留数据库备份 `tourism_data_backup_<date>.sql`。
