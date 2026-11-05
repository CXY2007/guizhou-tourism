# Agent 协作排版（Codex 施工 / Opus 评审 / GPT 复核 / DSH 集成）

> **说明：本文档描述的施工/复核脚本（`scripts/run_codex.ps1`、`scripts/gpt_review.py`、
> `scripts/probe_llm.py`、`scripts/*.cjs`）依赖开发者本机路径与本地模型代理，
> 不属于交付内容，已从仓库移除。流程本身仍可复用，脚本需自行按第 3、4 节的接口实现。**

> 目标：让强模型做判断，让 Codex 做施工，让 DSH 做集成；每个模块都可验证、可回滚、可复盘。
> 适用：本项目后续模块（后台用户管理、性能收尾、内容补齐、交付审计）。

## 0. 原则

1. **一个模块一个任务包、一份日志、一次提交。**
2. **Codex 只改任务包列出的文件**；不碰前端/模板（除非任务明确）。
3. **Opus 只读评审**，输出 findings，不改文件。
4. **GPT 只做定向交叉复核**，喂 3–6 个关键文件，不喂全仓库。
5. **DSH 是唯一提交者**；Codex/Opus/GPT 都不 commit。
6. **验收闸门**：`git diff` 人工过一遍 + `pytest` 全绿 + 页面/接口实测。

## 1. 目录排版

```
guizhou-tourism/
  docs/
    playbook.md              # 本方案
    tasks/                   # 任务包（Codex 读）
      d3e-backend.md
    reviews/                 # 评审结果（提交进 git）
      opus-d3e.md
      gpt-d3e.md
  logs/                      # Codex 运行日志（不进 git）
    codex-d3e-20261030-1015.log
  scripts/
    run_codex.ps1            # 看门狗（待建）
    gpt_review.py            # GPT 直连复核（待建）
```

`.gitignore` 增加：

```
logs/
```

## 2. 角色与边界

| 角色 | 谁 | 做 | 不做 |
|---|---|---|---|
| 指挥/集成 | DSH | 任务包、契约、合并、修错、pytest、截图、commit | 不独自写大模块（除非 fallback） |
| 施工 | Codex（GPT-6.1-sol） | 只改指定文件、跑 verify、报改动 | 不改前端、不 commit、不打印整份 diff |
| 评审 | Claude Opus 5-5 | 自己读文件、输出 findings | 不改文件、不 commit |
| 交叉复核 | GPT-6.1-sol 直连 | 只读关键文件、输出 findings | 不读全仓库、不施工 |
| 前端施工 | Claude Code（可选） | 页面/样式/交互 | 不碰后端 |
| 验收 | 人 | 决定优先级、给图/文案、最终验收 | — |

## 3. 单轮流程

```
DSH 写任务包（文件/契约/验收）
        ↓
Codex 施工（runner：检查代理 → 日志 → 看门狗）
        ↓ 改动 + pytest
DSH 初检（git diff / pytest / 起服务）
        ↓
Opus 评审（自己读文件）  ┐
GPT 交叉复核（关键文件） ┘ 可并行
        ↓ findings
DSH 修 + 回归 + 截图
        ↓
DSH commit
```

### 失败分支

- Codex 5 分钟无产出 → kill，DSH 接手已写文件
- Codex pytest 失败 → DSH 修，或带着失败日志重派
- Opus 超时/不可用 → 用 GPT 复核 + DSH 自审
- findings 冲突 → DSH 按测试结果裁决

## 4. Codex 任务包模板

```md
# 任务：<模块名>

## 边界
- 允许改：<文件列表>
- 禁止改：app/templates/**、app/static/**、app/models.py（按需调整）
- 不要 git commit

## 目标
<接口/行为，逐条>

## 验收
- python -m pytest tests -q
- curl <接口> 的期望返回

## 输出（只报这些）
- 改动文件
- pytest 结果
- 需要 DSH 执行的 curl
- 不要打印完整 diff
```

## 5. Codex Runner（看门狗）

`scripts/run_codex.ps1 -Module d3e -TaskFile docs/tasks/d3e-backend.md`

流程：

1. 检查 `127.0.0.1:15721`；未监听则启动 `cc-switch.exe`，等 8s
2. 日志：`logs/codex-<module>-<timestamp>.log`
3. 启动：
   ```
   codex exec --skip-git-repo-check --dangerously-bypass-approvals-and-sandbox `
     "Read <taskfile> and implement it exactly. Run pytest. Do not commit." `
     > <log> 2>&1
   ```
4. 看门狗：每 30s 检查
   - 进程是否存活
   - `~/.codex/sessions/**/*.jsonl` 最新 mtime；5 分钟无变化 → kill
   - 总超时 20 分钟
5. 结束打印：日志尾部 30 行、`git status --short`、日志路径
6. 退出码：0 成功；1 失败/超时（DSH 接手）

## 6. Opus 评审

```powershell
claude --model opus -p "Read docs/tasks/d3e-backend.md and the changed files. Review for correctness, security, edge cases. Output a markdown table: severity | file:line | problem | requiredFix. Do not modify files. Keep under 800 words." --output-format text
```

- 结果存 `docs/reviews/opus-<module>.md`
- 通过标准：无 `blocker` / `high`；`medium` 由 DSH 决定修不修

## 7. GPT 直连复核

`scripts/gpt_review.py --module d3e --files app/... app/... --checklist docs/reviews/checklist.md`

- 前置：检查 15721，必要时启动 CC Switch
- 输入：3–6 个关键文件 + checklist（截断到 ~30k 字符）
- 请求：`POST http://127.0.0.1:15721/v1/responses`
- 输出：`docs/reviews/gpt-<module>.md`，JSON findings
- 耗时目标：30–120 秒（实测受模型推理影响）

## 8. DSH 集成验收

1. `git diff --stat` + 逐 hunk 看
2. `python -m pytest tests -q`
3. 重启服务，curl/Playwright 实测
4. 应用 findings，再跑测试
5. 截图到 `docs/shots/<module>/`
6. commit：`feat(<module>): ... (Codex + Opus/GPT review)`
7. 更新 README

## 9. 时间/成本预算

| 模块 | Codex | Opus | GPT | DSH | 总计 |
|---|---|---|---|---|---|
| 后端模块 | 10–15m | 2–3m | 10s | 10–20m | 30–40m |
| 纯审计轮 | — | 3–5m | 10s | 30–60m | ~1h |
| 前端模块 | — | 2–3m | 10s | 10–20m | 用 Claude Code |

成本：Codex 5–12 万 token/模块；Opus 首轮约 $0.17，后续缓存更便宜；GPT 几千 token。

## 10. 任务类型路由

| 任务 | 主手 | 评审 |
|---|---|---|
| 后端服务/API/迁移 | Codex | Opus + GPT |
| 前端页面/样式 | Claude Code | Opus 或 DSH 截图 |
| 全仓库安全审计 | Codex（只读）或 Opus | 双向交叉 |
| 指定文件审计 | GPT/Opus 直连 | DSH 复核 |
| 英文文案 | Opus/Sonnet 直连 | DSH 校对 |
| 图片/内容/部署脚本 | DSH | 人验收 |

## 11. 禁止事项

- Codex/Opus/GPT 直接 commit
- 把整个仓库贴给 GPT
- 多个 agent 同时写同一文件
- 未跑 pytest 就合并
- 未经确认部署

## 12. 下一轮示范（后台用户管理）

1. DSH 写 `docs/tasks/d4-users.md`
2. `.\scripts\run_codex.ps1 -Module d4-users -TaskFile docs/tasks/d4-users.md`
3. `claude --model opus -p "..."` → `docs/reviews/opus-d4-users.md`
4. `python scripts/gpt_review.py ...` → `docs/reviews/gpt-d4-users.md`
5. DSH 修 findings → pytest → 截图 → commit
