# 贵州文旅 · Guizhou Tourism

> 外发安全说明：本项目已移除 Git 历史、真实环境文件、生成的密钥和用户运行数据。首次运行请复制 `.env.example` 为 `.env`，只填写你自己的 API Key；`SECRET_KEY` 可留空并由本机自动生成。

沉浸式贵州文旅网站：18 个目的地，覆盖自然山水、人文村寨、红色记忆、科技奇观与当季花海。

- 技术栈：Flask 3 + Jinja2 + Tailwind CSS + 原生 JS + SQLAlchemy + MySQL 8
- 设计方向：沉浸式大图叙事（墨绿 / 石青 / 朱砂 / 米白 / 金），玻璃拟态面板 + 按分类换主题
- 当前阶段：**18 个景点全部上线、中英双语完整、179 条测试通过、可生产启动**

## 快速开始

```bash
# 1. 依赖
python -m pip install -r requirements.txt
npm install

# 2. 数据库（源库 tourism_data 只读复制到 tourism_v2）
python scripts/setup_db.py
python scripts/migrate_v2.py
python scripts/migrate_d3.py      # view_logs 表
python scripts/seed_admin.py      # 管理员账号

# 3. 环境变量
copy .env.example .env   # 填写 SECRET_KEY / DATABASE_URL；AI_API_KEY 可留空（走规则兜底）
#   HEFENG_KEY   和风天气（留空则天气卡显示“天气暂不可用”）
#   AI_API_KEY   DeepSeek（留空则 AI 小球走规则引擎）
#   XHS_COOKIE   小红书 cookie（AI 行程参考笔记；留空用 content/xhs-notes.json 兜底）

# 4. 构建样式
npx tailwindcss -i app/static/css/src/input.css -o app/static/css/app.css --minify

# 5. 运行
python run.py            # 开发：http://127.0.0.1:8900（FLASK_DEBUG=1 时自动重载）
python wsgi.py           # 生产：waitress 多线程，见下方“部署”

# 6. 测试
python -m pytest tests -q
```

## 部署（生产启动）

开发服务器（`app.run`）不适合交付演示，用 waitress：

```bash
python -m pip install -r requirements.txt
npx tailwindcss -i app/static/css/src/input.css -o app/static/css/app.css --minify
python wsgi.py                       # 默认 127.0.0.1:8900，线程数 4

# 等价写法
python -m waitress --host=127.0.0.1 --port=8900 --threads=4 wsgi:app
```

可用环境变量覆盖：`SITE_HOST` / `SITE_PORT` / `SITE_THREADS`。

**静态资源缓存**（`app/__init__.py` 的 `after_request`）：

| 类型 | Cache-Control | 说明 |
|---|---|---|
| 图片、字体（jpg/png/webp/svg/ico/woff…） | `public, max-age=2592000` | 30 天，图片基本不变 |
| CSS / JS | `public, max-age=0, must-revalidate` | 带 ETag，改完刷新立即生效（页面不会吃到旧样式） |

## 演示账号

| 角色 | 账号 | 密码 | 说明 |
|---|---|---|---|
| 管理员 | `admin` | 首次运行后执行 `python scripts/seed_demo_accounts.py` 打印的随机口令 | 可进 `/admin` 全部后台页面 |
| 登录用户 | `demo` | 同上（随机生成，见脚本输出） | 含收藏/评分/评论/浏览足迹的演示数据 |
| 普通用户 | `tourist1` … `tourist8` | 同上 | 刷图表用的 8 个账号，各景点评分就是它们打的 |
| 游客 | — | — | 不登录即可浏览、搜索、看详情、看天气 |

> 演示账号口令：`python scripts/seed_demo_accounts.py`（随机生成，只在终端打印一次，不写文件、不入库）。
> 演示数据脚本：`python scripts/demo_seed.py seed` / `cleanup`；评分/评论用 `python scripts/seed_ratings.py`。
> `SECRET_KEY` 未配置时首次启动自动生成到 `instance/.secret_key`（不入库）；换掉会让所有登录态失效。

## 目录

```
app/
  __init__.py        应用工厂（含静态缓存头）
  config.py          .env 配置
  extensions.py      db / login / babel / csrf
  models.py          User / Attraction / Comment / Rating / Favorite / ViewLog ...
  decorators.py      admin_required
  services/
    history.py       浏览记录、分类偏好、每日推荐
    weather.py       和风天气 + 规则出行建议（10 分钟缓存）
    assistant.py     规则版 AI 助手（无 key 时兜底）
    llm_assistant.py DeepSeek 函数调用（只读工具，失败回退规则）
  blueprints/
    public.py        首页（轮播 + 今日推荐 + 当季卡片）、列表、详情
    auth.py          登录、注册、退出
    user.py          个人中心、预订、订单
    admin.py         后台仪表盘、景点 CRUD、用户/订单/评论管理
    api.py           收藏/评论/评分/订单/天气/统计/助手 JSON API
  templates/         base + components + pages + admin + auth + errors
  static/            Tailwind 产物、app.js、interactions.js、图片
content/             18 景点内容基线
docs/                PRD / IA / 设计 tokens / 数据模型 / API 契约 / 图片版权 / 截图
scripts/             setup_db / migrate_* / seed_* / make_* / 截图 / 联调探针
tests/               冒烟 + 权限 + 功能 + i18n + AI 测试（179 条）
wsgi.py              waitress 生产入口
```

## 已实现

### D2 基础
- 应用工厂 + 蓝图 + SQLAlchemy 模型 + Flask-Login + CSRF
- 首页：实景照片自动轮播（2s/张，悬停继续）+ 缩略图条 + 滚动入场动画
- 景点列表：分类筛选、分页、搜索、空态
- 景点详情：实景首图、诗意文案、事实信息、天气卡、地图、图集、同类推荐
- 图片灯箱：点详情首图或图集缩略图放大（左右切换、Esc/点背景关闭，封面与图集首图自动去重）
- 登录 / 注册 / 退出

### D3-A 互动
- 收藏、评分（1–5 星，实时重算）、评论（提交 → 待审 → 管理员通过/拒绝/删除）
- 个人中心：收藏、评论、评分、浏览足迹、我的行程、头像、改密、退出
- 资料页不再同时摆「用户名 / 昵称」两个重复项：用户名只读展示，展示名统一走 `display_name`
- 头像上传存数据库：`POST /api/profile/avatar`（jpg/png/webp ≤3MB）→ Pillow 居中裁 256×256 JPEG → `users.avatar_data`；
  `GET /avatar/<user_id>` 带 ETag 缓存返回，模板回落到昵称首字；可移除（`DELETE /api/profile/avatar`）
- 迁移脚本：`python scripts/migrate_avatar.py`（幂等，MySQL 用 LONGBLOB）
- 浏览记录与个性化每日推荐（按最近 30 天分类偏好）
- 三级权限：游客只读；用户可互动；管理员可审核

### D3-B AI 小球
- `POST /api/assistant`：规则引擎（意图：导航、分类/关键词搜索、事实问答、行程草案、帮助兜底）
- “说一句就跳页”：识别页面意图后 0.65s 自动跳转；景点名支持别名
- 每次请求写 `assistant_logs`（会话、意图、动作、耗时）

### D3-C 详情页增强
- 天气：和风实时 + 3 天预报 + 规则出行建议，10 分钟缓存，失败降级“天气暂不可用”
- 地图：高德 JS 动态加载 + 标记；key 缺失/失败降级“地图暂不可用”
- 评分概览：ECharts 饼图 + 近 8 周折线（本地 vendor，不依赖 CDN）

### D3-D 交易与后台
- 后台：`/admin` 仪表盘、景点 CRUD（搜索/上下架/**彻底删除**/图片上传）、订单列表、评论审核、用户管理、浏览流量
- 景点「彻底删除」= 真删：景点 + 评分/评论/收藏/订单/足迹/流量/翻译/图集全部删除，本地图片文件也一并移除；
  删除前弹二次确认（列出将删除的具体条数；有订单时再确认一次），测试见 `tests/test_admin_delete.py`
- 用户管理：搜索、状态/角色筛选、分页；不能禁用自己、不能禁用最后一个管理员；禁用后旧 session 立即失效
- 预订：详情页「预订」→ 日期 + 人数 + 合计 → `POST /api/bookings`
- 订单：状态徽标、模拟支付、待支付取消；状态变更用原子 `UPDATE ... WHERE status='pending'`
- 行程页 `/itinerary`：填**出发地 / 住宿 / 游玩天数 / 出发日期** + 勾选 1–8 个景点 → AI 排行程（见下）
- 保存行程：`POST /api/itineraries` 写入 `itineraries` 表（`items` 存每天的 slots JSON）
- 个人中心新增 **「我的行程」** 标签：列出已保存行程（标题 / 天数 / 日期 / 每天上午·下午·晚上），可删除（`DELETE /api/itineraries/<id>`，仅本人）；老格式行程也能正常渲染

### AI 行程规划（DeepSeek）
- `POST /api/itinerary/ai-plan`：**出发点 + 是否需要住宿 + 天数 + 出发时间 + 人均预算** + 候选景点 → DeepSeek 输出结构化 JSON
- 先查**和风天气**（候选城市去重，最多 3 个城市，实况 + 未来 3 天）和**小红书笔记**，把事实塞进提示词，模型只许引用给定天气
- 返回：`summary` + `transport`（出行方式）+ `route`（途经）+ `weather` + `clothing`（穿衣）+ `lodging`（住宿，按是否住宿与预算给价位）+ `budget_plan`（交通/门票/住宿/餐饮/机动）+ `days` + `notes`
- 模型偶发返回夹带文字的 JSON → 自动重试 1 次，仍失败才回退规则草案
- 约束：只能从候选景点里选（slug 校验）、按地理动线分天、每天 2–3 个点并留交通时间、出发/住宿体现在首尾两天
- 返回：`summary` + 每天 `theme` / `slots`（上午·下午·晚上，含具体动作）/ `tips` + 整体 `notes`
- 无 key、超时或 JSON 不合法 → 自动回退**规则草案**（按城市与评分分组），前端同一套渲染
- 服务层 `app/services/ai_itinerary.py`；提示词在第 20 行的 `SYSTEM_PROMPT`
- 实测（3 个景点 / 2 天）：约 3–4 秒返回，动线与交通/门票提示完整

### 小红书笔记参考（AI 行程的"人情味"）
- 配 `XHS_COOKIE`（浏览器里整段 Cookie）后，行程生成前会按景点搜小红书笔记，把「机位 / 避坑 / 时间」塞进提示词
- 命中实时笔记 → 结果页标注「已参考小红书实时笔记 N 条」；cookie 缺失/过期/被风控 → 用 `content/xhs-notes.json` 本地笔记兜底（标注「本地缓存」）
- 实时结果按关键词缓存 6 小时到 `instance/xhs_cache.json`，避免频繁请求
- 小红书接口有签名风控，**仅凭 cookie 不保证成功**；失败不影响行程生成（`app/services/xhs.py`，状态码 `no_cookie/expired/empty/http_error`）
- 本地兜底笔记：`content/xhs-notes.json`（18 个景点 × 2 条，可自行替换）

### 浏览流量（后台）
- 新表 `traffic_daily`：按「景点 × 天」汇总 `views`（浏览量）与 `visitors`（访客数）
- 详情页每次打开都计数：登录用户 + 游客都算；同一会话当天同一景点只计一次访客
- 后台「浏览流量」`/admin/traffic`：今日 / 近 7 天 / 近 30 天 / 累计卡片、近 7/30/90 天趋势折线（浏览量 + 访客量）、18 个景点排行与占比条
- 服务层 `app/services/traffic.py`；演示数据 `python scripts/seed_traffic.py 30`（带周末与热点景点权重）

### 大屏地图
- 详情页地图卡右上角「查看大图 ↗」→ `/attractions/<slug>/map`
- 整屏高德地图：缩放控件、比例尺、标记气泡、标准图 / 卫星图切换，Esc 或按钮返回详情
- 没配 `AMAP_JS_KEY` 或加载失败 → 地图区域显示「地图暂不可用」，页面其余部分正常

### 演示数据（图表的扇形 / 折线）
- `python scripts/seed_ratings.py`：批量建 8 个演示账号 + 每景点 6–8 条评分（按 8 个 ISO 周铺开）+ 部分已通过评论
- 评分分布按 5★45% / 4★30% / 3★15% / 2★7% / 1★3% 取样，扇形图与近 8 个月折线都有数据
- `--reset` 先清空这些账号的历史评分再重建；脚本幂等，可重复执行

### AI 工具调用（DeepSeek Function Calling）
- 配 `AI_API_KEY` 后 `POST /api/assistant` 优先走 DeepSeek；未配置、失败或超时 → 自动回退规则引擎
- 5 个只读工具：`navigate`（站内白名单）/`search_attractions`/`get_weather`/`get_attraction_fact`/`plan_itinerary`
- 最多 3 轮工具调用；工具结果转成可点景点链接；中英文都能问
- 同一 session + IP 限流 20 次/分钟（`AI_RATE_LIMIT`）

### 中英双语
- 任意页面「中 / EN」或 `?lang=en`，选择存 session
- 界面、首页、列表、详情、登录注册、个人中心、预订、订单、行程、后台、AI 小球全部英文化
- 内容：**18 / 18 景点**的名称/简介/详情/诗意/地址/开放时间/门票说明写入 `attraction_translations`
- 天气：城市、天气、风向、周几、出行建议英文化
- 脚本：`migrate_i18n.py`、`seed_en.py`、`seed_en_extra.py`

### 内容与图片
- 18 个景点全部已发布：原有 8 个 + 新增 10 个（万峰林、平坝樱花、花江峡谷大桥、肇兴侗寨、镇远古镇、青岩古镇、乌蒙大草原、百里杜鹃、小七孔、织金洞）
- **10 个新增景点各 6 张实景图**：来自项目素材库 `新十大风景图/十大风景图/`，脚本裁成 1200×800 后写入 `app/static/images/<缩写><序号>.jpg`
- 版权与来源：[docs/IMAGE-CREDITS.md](docs/IMAGE-CREDITS.md)
- 后台景点编辑支持上传封面 + 图集（jpg/png/webp，单张 ≤5MB）

### 视觉主题（近几轮）
- 分类主题：自然=雾绿 / 人文=夯土米 / 红色=深灰水墨 / 科技=深空蓝 / 当季=樱花粉
- **详情页跟随所属分类**：页面底色、引文竖条、天气卡小块/温度/建议竖条都用该分类的一套色
- 玻璃拟态：AI 面板、登录卡、行程选卡/结果卡（半透明白 + 磨砂 + 内高光）
- 首页「当季 · 花海」卡片：樱花粉玻璃 + 实景图 + 票价/开放时间
- 分类页背景图：自然山水 / 人文村寨 / 科技奇观 / 当季花海 各用一张实景大图（`app/static/images/category/`），
  叠同色系薄罩保证文字可读；红色记忆维持原深红水墨，不加照片
- 进入「探索景点」有 2 秒全屏海报开场，切分类不重复播放
- 登录 / 注册页：整页海报原图 + 全透明卡片 + 深墨字白柔光

### 协作流程 协作流水线
- Playbook：[docs/协作流程-playbook.md](docs/协作流程-playbook.md)
- 该流水线的本机脚本（施工看门狗 / 交叉复核 / 截图与联调探针）依赖开发者自己的路径与 key，
  **不属于交付内容，未随仓库发布**；复现流程见 Playbook 的说明。

## 图片说明

源素材里 `.png` 多为带文字的成品海报，`.jpg` 多为实景照片。卡片与详情首图统一取图集第一张实景图。
新十景的 60 张图由 `scripts/make_attraction_images.py` 从素材库生成（原图不进仓库，见 `.gitignore`），
版权与来源见 [docs/IMAGE-CREDITS.md](docs/IMAGE-CREDITS.md)。

## 待办

- AI 多轮对话记忆（现在每次请求只带单条消息，不能追问“那它的门票呢”）
- 图片转 WebP + `srcset`（`app/static/images` 现状约 36MB）
- `docs/shots` 历史截图瘦身（171 个文件 / 123MB，交付可只留最终一组）
- favicon 与 `og:image`（浏览器页签、分享卡片目前是空的）
- 和风天气 `devapi.qweather.com` 迁到新域名（官方给了过渡期，改 `.env` 的 `HEFENG_HOST` 即可）

## 文档

- [PRD](docs/PRD.md) · [信息架构](docs/IA.md) · [设计 tokens](docs/design-tokens.md)
- [数据模型](docs/data-model.md) · [API 契约](docs/api.md) · [环境基线](docs/env.md)
- [图片版权](docs/IMAGE-CREDITS.md)
- 截图：`docs/shots/`（D2）、`docs/shots/d3*/`（D3）、`docs/shots/en/`（英文）、`docs/shots/bg/`（近几轮视觉）

> 课程设计作品，非商业站点。图片版权归原作者所有。
