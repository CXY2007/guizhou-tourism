# 环境基线（D0）

> 记录时间：2026-10-29 · 分支：`v2` · 基线提交：`2928f30`
> 用途：换机复现、排错、答辩时说明运行环境。

## 1. 项目

| 项 | 值 |
|---|---|
| 源码路径 | 仓库根目录（本机绝对路径不入库） |
| 数据库 | MySQL 8.0.46，库名 `tourism_data` |
| 启动命令 | `python run.py`（开发）/ `python wsgi.py`（waitress 生产） |
| 基线截图 | `docs/baseline/`（login / home / detail × 1440 / 768 / 375） |

## 2. 运行时

| 组件 | 版本 |
|---|---|
| Python | 3.13.2 |
| Flask | 3.1.3 |
| PyMySQL | 1.2.0 |
| dashscope | 1.25.13 |
| requests | 2.32.5 |
| Node | 24.20.0 |
| pnpm | 11.25.0 |
| pyright | 1.1.414 |
| bsk | 0.3.2 |
| Playwright + Chromium | 本机自行安装（截图脚本未随仓库发布） |

## 3. 数据现状

| 表 | 行数 |
|---|---|
| attractions | 8 |
| attraction_images | 48 |
| users | 6（基线截图期间临时账号已删除） |
| comments | 11 |
| favorites | 4 |
| ratings | 6 |

## 4. 外部服务

| 服务 | 状态 | 说明 |
|---|---|---|
| 高德 Web 服务 key | ✅ 有效 | geocode 返回 `status=1` |
| 和风天气 key | ✅ 有效 | 实时 + 3 天预报正常 |
| DashScope（qwen-turbo） | ❌ 429 | `Throttling.RateQuota`，站点 AI 走兜底文案 |
| DeepSeek 函数调用 | ✅ 已配置 | key 在 `.env`（不提交），无 key 时自动回退规则引擎 |
| 站点 secret_key | ✅ 自动生成 | 未配 `.env` 时首次启动生成到 `instance/.secret_key`（不入库） |
| 高德 JS key（详情页） | ⚠️ 未验证 | 无头截图时外部 CDN 被中断，需真机确认 |


|---|---|---|---|
| DSH | 0.1.2-rc.1 | DeepSeek V4.1-Flash | ✅ 本会话 |

## 6. 已知问题

1. 站点 AI 已改为 DeepSeek 函数调用（只读工具），`AI_API_KEY` 已配置并完成真实联调；无 key 的机器会自动走规则兜底。
2. pytest 未安装，冒烟测试待补。
3. bsk 守护进程未启动（`BSK_AUTO_START=0`）。
4. 现有 `app.py` 含明文密钥（DB 密码、和风/高德 key、DashScope key 路径），重构时迁 `.env` 并轮换。
