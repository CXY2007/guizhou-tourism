# 内容基线 v0

18 个景点的结构化数据，站点详情页、搜索、行程与 AI 回答的共同数据源。

## 目录

```
content/
├─ manifest.json              # 18 条总清单（8 已导出 / 10 待补）
└─ attractions/<slug>.json    # 单景点数据
```

## 状态

| 状态 | 数量 | 说明 |
|---|---|---|
| exported | 8 | 来自现有 MySQL，字段已导出，英文/tags/sources 待补 |
| pending | 10 | 新增景点，待事实核查与内容生产 |

高风险待补：
- `huajiang-bridge`（花江峡谷大桥）：2025 新地标，资料少，必须多源交叉
- `pingba-cherry` / `baili-dujuan`：季节型，花期与票价以官方公告为准

## 单景点字段（20 项）

| 字段 | 必填 | 说明 |
|---|---|---|
| `slug` | ✅ | URL 标识，稳定不改 |
| `name_zh` / `name_en` | ✅ | 中英文名 |
| `city` / `region` / `province` | ✅ | 市州 / 区县 / 省 |
| `category` | ✅ | 自然 / 人文 / 红色 / 科技 / 季节 |
| `summary_zh/en` | ✅ | 60–80 字 |
| `description_zh/en` | ✅ | 300–500 字 |
| `poetic_zh` | ✅ | 80–120 字 |
| `address` / `lng` / `lat` | ✅ | 地图用 |
| `open_time` | ✅ | 如 07:00–18:00 |
| `ticket_price` / `ticket_note` | ✅ | 票价与说明（含观光车/预约制） |
| `visit_duration` | ✅ | 分钟 |
| `best_months` | ✅ | 如 6–10 月 |
| `seasonal` | ✅ | 季节型为 true |
| `transport` / `tips` | ✅ | 交通与贴士 |
| `cover_image` / `gallery` | ✅ | 图源；建议 WebP |
| `tags` | ✅ | 3–5 个 |
| `sources` / `verified_at` | ✅ | 来源 URL 与核实日期 |
| `status` | ✅ | `draft` / `published` |

## 工作流

1. 补字段 → 存回 `<slug>.json`
2. 事实核查：`sources` 至少 1 条官方来源，`verified_at` 更新
3. 校验：`python scripts/verify_data.py`（待实现）
4. 导入：`python scripts/import_content.py`（待实现）
5. 发布：`status=published` 后前台可见

## 图片规范

- 命名：`static/images/webp/<slug>-1.webp`、`-2`…
- 卡片封面 4:3，详情 16:9，缩略 1:1
- 版权：自有 / 免费图库 / AI 生成（标注“示意图”）
