# 任务包：D3-C 后端（Codex）

## 角色与边界
- 你只负责后端：天气服务、两个 GET API、测试。
- **不要修改**：`app/templates/**`、`app/static/**`、`app/models.py`、`app/services/assistant.py`、`app/services/history.py`、`app/blueprints/*` 中除 `api.py` 以外的文件。
- 允许修改/新建：`app/services/weather.py`、`app/blueprints/api.py`（只追加）、`app/config.py`、`.env.example`、`tests/test_d3c.py`。
- 不要改 `.env`（DSH 已写好真实 key）。

## 目标
1. 天气服务 `app/services/weather.py`
   - 读取 `HEFENG_KEY` / `HEFENG_HOST`（来自 `current_app.config` 或环境变量）。
   - `get_weather(city: str, weather_code: str | None = None) -> dict | None`
     - 和风天气：城市 lookup（有 weather_code 时直接用它作为 location）、实时 `/v7/weather/now`、3 天 `/v7/weather/3d`。
     - 超时 5s，异常/非 200 返回 None，不向上抛。
     - 进程内缓存 10 分钟，key 用 location_id 或 city。
   - `build_advice(live: dict) -> str`：规则生成 1–2 句中文建议（温度、降雨、风力、防晒/保暖/雨具），不调用 LLM。
2. API（追加到 `app/blueprints/api.py`）
   - `GET /api/weather/<int:attraction_id>`
     - 404 `not_found`：景点不存在。
     - 502 `weather_unavailable`：服务失败。
     - 200：`{ok:true,data:{city,live:{weather,temperature,humidity,winddirection,windpower,obsTime},forecast:[{date,week,dayweather,nightweather,daytemp,nighttemp}],advice,source:"hefeng"}}`
   - `GET /api/attractions/<int:attraction_id>/stats`
     - 404：景点不存在。
     - 200：`{ok:true,data:{pie:[{rating:1..5,count}],weeks:[...],averages:[...],total:int,avg:float}}`
     - 统计 `ratings` 表：1–5 星分布；最近 8 周每周平均分（用 `DATE_FORMAT(created_at,'%x-W%v')` 或等价周标签），无数据时返回空数组。
3. 配置
   - `app/config.py` 增加 `HEFENG_KEY`、`HEFENG_HOST`（从环境变量）。
   - `.env.example` 补上这两项占位。

## 验收
- `python -m pytest tests -q` 全过（含你新增的测试）。
- 新测试覆盖：stats 正常/404、weather 404、weather 用 monkeypatch 避免真实网络。
- **运行环境说明**：8900 上跑的是旧代码（不会自动重载），不要重启它，也不要依赖它的 curl 结果；请用 `pytest` 验证，或临时用 `SITE_PORT=8901 python run.py` 起一个测试实例（用完关掉）。DSH 会在合并后统一重启并跑 curl。
- 不要执行 `git commit`，不要修改 `.env`。
- 完成后报告：改动文件、测试结果、需要的最终 curl 命令（DSH 会执行）。
