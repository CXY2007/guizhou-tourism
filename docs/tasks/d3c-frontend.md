# 任务包：D3-C 前端（Claude Code）

## 角色与边界
- 你只负责详情页的天气卡、地图、评分图表前端。
- **不要修改**任何 Python 文件（`app/*.py`、`tests/**`、`scripts/**`）。
- 允许修改/新建：`app/templates/pages/attraction_detail.html`、`app/static/js/detail_extras.js`、`app/static/css/src/input.css`（只追加）。
- 图表库已由 DSH 放在 `app/static/vendor/echarts.min.js`，直接引用，不要用 CDN。

## 接口契约（后端并行实现，按此编码）
- `GET /api/weather/<attraction_id>` → 200 `{ok,data:{city,live:{weather,temperature,humidity,winddirection,windpower,obsTime},forecast:[{date,week,dayweather,nightweather,daytemp,nighttemp}],advice,source}}`；失败 502 `weather_unavailable`。
- `GET /api/attractions/<attraction_id>/stats` → 200 `{ok,data:{pie:[{rating,count}],weeks:[...],averages:[...],total,avg}}`。

## 页面改动（详情页）
1. **天气卡**：放在正文 facts 之后、评论之前。
   - 容器 `data-weather data-attraction-id="{{ attraction.id }}"`，初始 loading 文案。
   - JS 拉接口，渲染：城市、实时天气/温度/湿度/风、3 天预报（日期 + 白天/夜间 + 温度）、`advice`。
   - 失败显示“天气暂不可用”，不阻塞页面。
2. **地图**：
   - 在右侧栏评分卡下方加地图容器 `id="detail-map"`，带 `data-lng`、`data-lat`、`data-name`、`data-amap-key="{{ config.AMAP_JS_KEY }}"`、`data-amap-security="{{ config.AMAP_SECURITY_CODE }}"`。
   - JS 动态加载 `https://webapi.amap.com/maps?v=2.0&key=<key>`；设置 `window._AMapSecurityConfig = { securityJsCode }` 后再加载；打点 + 缩放 13。
   - key 为空或加载失败：显示“地图暂不可用”，不报错。
3. **评分图表**：
   - 在详情页正文下方加两栏图表：饼图（1–5 星分布）+ 折线（近 8 周平均分）。
   - 用 `app/static/vendor/echarts.min.js`；容器有固定高度（桌面 220px，移动 180px）。
   - 无数据时显示“暂无评分数据”。
4. **样式**：用现有 tokens（ink/teal/cinnabar/paper/gold/mist），风格与站点一致；移动端单列。
5. **脚本引用**：详情页加 `echarts.min.js` 与 `detail_extras.js`（defer）。

## 验收
- 详情页 200；天气/图表在有数据时渲染、失败时降级。
- `npx tailwindcss -i app/static/css/src/input.css -o app/static/css/app.css --minify` 构建通过。
- 不要跑 Python 测试；不要改后端；不要执行 `git commit`。
- **运行环境说明**：8900 上是旧代码，不会自动重载；不要重启它。你可以只做静态检查与构建，DSH 会在合并后重启并做最终截图/验证。
- 完成后报告：改动文件、构建结果、页面自测情况。
