(() => {
  const root = document.querySelector("[data-itinerary]");
  const savedRoot = document.querySelector("[data-saved-itinerary]");

  /* =====================================================================
     双语：语言判定 + 三层文案（EN_TEXT / Lx / Ls），与 ai_shortcuts.js 同一套约定
     - 本文件自己写的文案（提示条、按钮、预算沙盘标签、住宿卡片说明、校验提示）
       都走 L() / Lx() / Ls()
     - 接口返回的字段（conflict.title / detail / suggestion、item.label、
       cuts[].label、hotel.name / address）后端已按 session 语言 t() 过，
       这里原样渲染，绝不二次加工
     - 中文站：每个分支返回的仍是原来的中文原文，逐字节不变
     语言钩子：base.html 的 <html lang> 输出 en / zh-CN，body[data-lang] 兜底
     ===================================================================== */
  const docEl = document.documentElement;
  const bodyEl = document.body;
  const htmlLang = (docEl.lang || "").toLowerCase();
  const bodyLang = ((bodyEl && bodyEl.dataset.lang) || "").toLowerCase();
  const LANG_EN = htmlLang.indexOf("en") === 0 || bodyLang.indexOf("en") === 0;

  const T = (text) => {
    if (typeof window.T === "function") return window.T(text);
    const dict = window.__I18N || {};
    return dict[text] || text;
  };

  /* 短文案：按钮字、标签、小节标题。中文站在表里查不到，仍走 T() 返回中文原文 */
  const EN_TEXT = {
    "行程提醒": "Itinerary alert",
    "详情": "Details",
    "收起": "Hide",
    "建议": "Tip",
    "提醒": "Heads-up",

    // 预算沙盘
    "预算沙盘": "Budget breakdown",
    "按当前行程估算 · 附可执行削减建议": "Estimated from this itinerary · with actionable savings",
    "按当前行程估算": "Estimated from this itinerary",
    "正好用完预算": "Right on budget",
    "人均": "Per person",
    "总合计": "Total",
    "你的预算": "Your budget",
    "可以这样省": "How to save",

    // 概要卡片
    "出发推荐方式": "Suggested transport",
    "路途经过": "Route",
    "天气": "Weather",
    "穿衣推荐": "Clothing",
    "住宿安排": "Where to stay",
    "预算分配": "Budget split",

    // 住宿推荐
    "价格以预订页为准": "Price shown at booking",
    "查看房价": "See rates",
  };
  const L = (text) => (LANG_EN ? EN_TEXT[text] || T(text) : T(text));

  /* 带插值的句式：中文原文逐字保持，英文另给一套；单复数走 plural() */
  const Lx = (zh, en) => (LANG_EN ? en : zh);
  const plural = (n, one, many) => (Number(n) === 1 ? one : many);

  /* 整句（无插值）：提示语与校验错误 */
  const EN_SENTENCES = {
    "选择上还有可以优化的地方": "A few things to improve in your picks",
    "点开可看详情与建议": "Open for details and tips",
    "操作失败，请稍后再试": "Something went wrong. Please try again.",
    "请先选择景点": "Pick an attraction first",
    "住宿查询暂时不可用，稍后会自动重试。": "Hotel lookup is temporarily unavailable. We will retry automatically.",
    "AI 正在排行程，通常 5–15 秒…": "AI is planning your trip — usually 5–15 seconds…",
    "没有生成可用的行程，请换几个景点试试": "No usable itinerary generated — try other attractions",
    "AI 行程已生成": "AI itinerary ready",
    "AI 暂不可用，已生成基础草案": "AI unavailable — a basic draft was generated",
    "请先填写行程标题": "Please enter an itinerary title first",
    "行程已保存，可在个人中心「我的行程」查看": "Itinerary saved — find it under “My trips” in your account",
    "行程已保存在个人页面中": "Itinerary saved — see it on your personal page",
    "这份行程已经保存过了，不用重复保存": "This itinerary is already saved",
    "正在保存行程…": "Saving itinerary…",
    // 失败备选入口
    "换 3 个景点试试": "Try 3 different attractions",
    "多加一天再试": "Add a day and retry",
  };
  const Ls = (text) => (LANG_EN ? EN_SENTENCES[text] || L(text) : text);

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  };
  const num = (value) => {
    const n = Number(value);
    return Number.isFinite(n) ? n : 0;
  };
  const money = (value) => "¥" + Math.round(num(value)).toLocaleString(LANG_EN ? "en-US" : "zh-CN");
  const clearNode = (node) => {
    if (!node) return;
    node.textContent = "";
    node.hidden = true;
  };

  /* =====================================================================
     冲突提示 + 预算沙盘：行程页和已保存详情页共用同一套渲染
     契约见 task-2（T0）：字段名逐字对齐，前端不改名
     ===================================================================== */
  const SEV_LABEL = { high: "高", medium: "中", low: "低" };
  const SEV_LABEL_EN = { high: "High", medium: "Medium", low: "Low" };
  const SEV_WEIGHT = { high: 3, medium: 2, low: 1 };
  const sevOf = (conflict) => (SEV_LABEL[conflict.severity] ? conflict.severity : "low");
  // 展示用标签单独一套：SEV_LABEL 的键仍是 severity code（sevOf 用它判合法性）
  const sevText = (sev) =>
    LANG_EN ? SEV_LABEL_EN[sev] || SEV_LABEL_EN.low : SEV_LABEL[sev] || SEV_LABEL.low;

  function findDayCard(resultEl, day) {
    if (!resultEl) return null;
    const cards = resultEl.querySelectorAll(".itin-day");
    const index = Number(day);
    if (!Number.isInteger(index) || index < 1 || index > cards.length) return null;
    return cards[index - 1];
  }

  /* 单条冲突：按钮展开 detail + suggestion */
  function conflictNode(conflict, global) {
    const sev = sevOf(conflict);
    const bar = el("div", `itin-conflict itin-conflict-${sev}${global ? " itin-conflict-global" : ""}`);
    bar.dataset.conflictCode = conflict.code || "";

    const head = el("button", "itin-conflict-head");
    head.type = "button";
    head.setAttribute("aria-expanded", "false");
    head.appendChild(el("span", "itin-conflict-dot"));
    head.appendChild(el("span", "itin-conflict-title", conflict.title || L("行程提醒")));
    head.appendChild(el("span", "itin-conflict-sev", sevText(sev)));
    const more = el("span", "itin-conflict-more", L("详情"));
    head.appendChild(more);
    bar.appendChild(head);

    const body = el("div", "itin-conflict-body");
    body.hidden = true;
    if (conflict.detail) body.appendChild(el("p", "itin-conflict-detail", conflict.detail));
    if (conflict.suggestion) {
      const tip = el("p", "itin-conflict-suggestion");
      tip.appendChild(el("span", "itin-conflict-suggestion-label", L("建议")));
      tip.appendChild(document.createTextNode(conflict.suggestion));
      body.appendChild(tip);
    }
    if (!body.children.length) head.disabled = true;
    bar.appendChild(body);

    head.addEventListener("click", () => {
      const open = body.hidden;
      body.hidden = !open;
      bar.classList.toggle("is-open", open);
      head.setAttribute("aria-expanded", open ? "true" : "false");
      more.textContent = open ? L("收起") : L("详情");
    });
    return bar;
  }

  function conflictSummary(conflicts) {
    const box = el("div", "itin-conflict-summary");
    box.appendChild(el("span", "itin-conflict-summary-icon", "⚠"));
    box.appendChild(
      el(
        "span",
        "itin-conflict-summary-text",
        Lx(
          `行程有 ${conflicts.length} 处待优化`,
          plural(conflicts.length, "1 thing to review", `${conflicts.length} things to review`)
        )
      )
    );
    const highs = conflicts.filter((c) => sevOf(c) === "high").length;
    box.appendChild(
      el(
        "span",
        "itin-conflict-summary-meta",
        highs
          ? Lx(`其中 ${highs} 处高优先`, plural(highs, "1 high priority", `${highs} high priority`))
          : Ls("点开可看详情与建议")
      )
    );
    return box;
  }

  /* 渲染冲突：逐条插到对应 .itin-day 卡片顶部，匹配不到日期的放到汇总区 */
  function renderConflicts(host, resultEl, data) {
    if (resultEl) {
      resultEl.querySelectorAll(".itin-conflict").forEach((node) => node.remove());
      resultEl.querySelectorAll(".itin-day").forEach((card) => {
        card.classList.remove("has-conflict-high", "has-conflict-medium", "has-conflict-low");
      });
    }
    clearNode(host);

    const list =
      data && Array.isArray(data.conflicts)
        ? data.conflicts
            .filter((c) => c && (c.title || c.detail || c.suggestion))
            .slice()
            .sort((a, b) => (SEV_WEIGHT[b.severity] || 0) - (SEV_WEIGHT[a.severity] || 0))
        : [];
    if (!list.length || !host) return;

    // 先按卡片分组，再用同一个 fragment 插入，保证高优先级在上
    const byCard = new Map();
    list.forEach((conflict) => {
      const card = findDayCard(resultEl, conflict.day);
      if (card) {
        if (!byCard.has(card)) byCard.set(card, []);
        byCard.get(card).push(conflict);
      } else {
        // 没有对应日期（或已保存行程缺该天）→ 汇总区里单独列出
        host.appendChild(conflictNode(conflict, true));
      }
    });
    byCard.forEach((conflicts, card) => {
      const fragment = document.createDocumentFragment();
      conflicts.forEach((conflict) => fragment.appendChild(conflictNode(conflict)));
      card.insertBefore(fragment, card.firstChild);
      card.classList.add("has-conflict-" + sevOf(conflicts[0]));
    });

    host.insertBefore(conflictSummary(list), host.firstChild);
    host.hidden = false;
  }

  function budgetStat(label, value, extraClass) {
    const box = el("div", "itin-budget-stat" + (extraClass ? " " + extraClass : ""));
    box.appendChild(el("span", "itin-budget-stat-label", label));
    box.appendChild(el("span", "itin-budget-stat-value", value));
    return box;
  }

  /* 渲染预算沙盘：总人均 / 人数合计 / 分项 / cuts / 与预算差额染色 */
  function renderBudget(host, data) {
    clearNode(host);
    if (!host || !data) return;

    const items = Array.isArray(data.items) ? data.items.filter((i) => i && (i.label || i.key)) : [];
    const cuts = Array.isArray(data.cuts) ? data.cuts.filter((c) => c && (c.label || num(c.saving))) : [];
    const compare = data.compare && typeof data.compare === "object" ? data.compare : null;
    const perPerson = num(data.total_per_person);
    const totalAll = num(data.total_all);
    if (!items.length && !perPerson && !totalAll) return;

    // T5 起 budget 出参回显 people；老存档没有该字段时按总额/人均反推兜底
    const echoedPeople = num(data.people) > 0 ? Math.max(1, Math.round(num(data.people))) : 0;
    const people = echoedPeople || (perPerson > 0 ? Math.max(1, Math.round(totalAll / perPerson)) : 0);
    const budget = compare ? num(compare.budget) : 0;
    const delta = compare ? num(compare.delta) : 0;
    // T1 补充：budget=0 时 status 为 unknown（delta=0），此时不显示任何预算对比
    const cmpStatus = compare && typeof compare.status === "string" ? compare.status : "";
    const hasCompare = budget > 0 && cmpStatus !== "unknown";
    const diffStatus =
      cmpStatus === "under" || cmpStatus === "over" || cmpStatus === "even"
        ? cmpStatus
        : delta < 0
          ? "under"
          : delta > 0
            ? "over"
            : "even";

    const card = el("div", "itin-budget-card");

    const head = el("div", "itin-budget-head");
    const titles = el("div", "itin-budget-titles");
    titles.appendChild(el("h3", "itin-budget-title", L("预算沙盘")));
    titles.appendChild(
      el("p", "itin-budget-sub", cuts.length ? L("按当前行程估算 · 附可执行削减建议") : L("按当前行程估算"))
    );
    head.appendChild(titles);
    if (hasCompare) {
      const chip = el("span", `itin-budget-compare is-${diffStatus}`);
      if (delta < 0) chip.textContent = Lx(`比预算省 ${money(-delta)}`, `Under budget by ${money(-delta)}`);
      else if (delta > 0) chip.textContent = Lx(`超预算 ${money(delta)}`, `Over budget by ${money(delta)}`);
      else chip.textContent = L("正好用完预算");
      head.appendChild(chip);
    }
    card.appendChild(head);

    const stats = el("div", "itin-budget-stats");
    stats.appendChild(budgetStat(L("人均"), money(perPerson), "itin-budget-stat-primary"));
    if (totalAll) {
      stats.appendChild(
        budgetStat(
          people
            ? Lx(`${people} 人合计`, plural(people, "1 person total", `${people} people total`))
            : L("总合计"),
          money(totalAll)
        )
      );
    }
    if (hasCompare) stats.appendChild(budgetStat(L("你的预算"), Lx(`${money(budget)}/人`, `${money(budget)}/person`)));
    card.appendChild(stats);

    if (items.length) {
      const bars = el("div", "itin-budget-bars");
      const base =
        perPerson > 0 ? perPerson : items.reduce((sum, item) => sum + num(item.per_person), 0) || 1;
      items.forEach((item) => {
        const row = el("div", "itin-budget-item");
        const top = el("div", "itin-budget-item-top");
        top.appendChild(el("span", "itin-budget-item-label", item.label || item.key));
        top.appendChild(el("span", "itin-budget-item-value", money(item.per_person)));
        row.appendChild(top);
        const track = el("div", "itin-budget-track");
        const fill = el("span", "itin-budget-fill");
        const pct = Math.max(2, Math.min(100, (num(item.per_person) / base) * 100));
        fill.style.width = pct.toFixed(1) + "%";
        track.appendChild(fill);
        row.appendChild(track);
        if (item.detail) row.appendChild(el("span", "itin-budget-item-detail", item.detail));
        bars.appendChild(row);
      });
      card.appendChild(bars);
    }

    if (cuts.length) {
      const box = el("div", "itin-budget-cuts");
      box.appendChild(el("span", "itin-budget-cuts-title", L("可以这样省")));
      const list = el("ul", "itin-budget-cut-list");
      cuts.forEach((cut) => {
        const li = el("li", "itin-budget-cut");
        const label = cut.label || "";
        li.appendChild(el("span", "itin-budget-cut-label", label));
        // 后端部分话术已自带「省 ¥160」/「save ¥160」，再追加一次就重复了；
        // 按当前语言各自的写法判断（后端已按 session 语言 t() 过）
        const hasSavingInLabel = LANG_EN
          ? /(?:save|saving)\s*[¥￥]?\s*\d/i.test(label)
          : /省\s*[¥￥]/.test(label);
        if (num(cut.saving) > 0 && !hasSavingInLabel) {
          li.appendChild(
            el("span", "itin-budget-cut-saving", Lx("省 " + money(cut.saving), "Save " + money(cut.saving)))
          );
        }
        list.appendChild(li);
      });
      box.appendChild(list);
      card.appendChild(box);
    }

    if (people) {
      card.appendChild(
        el(
          "p",
          "itin-budget-note",
          Lx(
            `按 ${people} 人出行估算，不含个人购物`,
            `Estimated for ${people} ${plural(people, "person", "people")}, excluding personal shopping`
          )
        )
      );
    }
    host.appendChild(card);
    host.hidden = false;
  }

  /* -------- 已保存行程详情页：读模板里内嵌的 brief.conflicts / brief.budget -------- */
  function initSaved(scope) {
    const readJson = (selector) => {
      const node = scope.querySelector(selector);
      if (!node) return null;
      try {
        return JSON.parse(node.textContent || "null");
      } catch (e) {
        return null;
      }
    };
    const resultEl = scope.querySelector(".itin-result");
    renderConflicts(scope.querySelector("[data-conflicts]"), resultEl, readJson("[data-saved-conflicts]"));
    renderBudget(scope.querySelector(".itin-budget-slot[data-budget]"), readJson("[data-saved-budget]"));
  }

  if (savedRoot) initSaved(savedRoot);
  if (!root) return;

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const checks = Array.from(root.querySelectorAll(".itin-check"));
  const daysSelect = root.querySelector("[data-days]");
  const originInput = root.querySelector("[data-origin]");
  const staySelect = root.querySelector("[data-stay]");
  const budgetInput = root.querySelector("input[data-budget]");
  const dateInput = root.querySelector("[data-start-date]");
  const genBtn = root.querySelector("[data-generate]");
  const retryEl = root.querySelector("[data-retry]");
  const peopleSelect = root.querySelector("[data-people]");
  const precheckEl = root.querySelector("[data-precheck]");
  const countEl = root.querySelector("[data-selected-count]");
  const msgEl = root.querySelector("[data-itin-msg]");
  const briefEl = root.querySelector("[data-brief]");
  const hotelsEl = root.querySelector("[data-hotels]");
  const hotelsLoadingEl = root.querySelector("[data-hotels-loading]");
  const conflictsHost = root.querySelector("[data-conflicts]");
  const budgetHost = root.querySelector(".itin-budget-slot[data-budget]");
  const summaryEl = root.querySelector("[data-summary]");
  const resultEl = root.querySelector("[data-result]");
  const notesEl = root.querySelector("[data-notes]");
  const saveBox = root.querySelector("[data-save-box]");
  const titleInput = root.querySelector("[data-title]");
  const saveBtn = root.querySelector("[data-save]");
  const saveMsgEl = root.querySelector("[data-save-msg]");
  const DEFAULT_PEOPLE = 2; // 人数控件缺失时的兜底（契约默认 2 人）
  let current = null;
  let lastPlan = null;
  let lastHotels = null;
  let lastConflicts = null;
  let lastBudget = null;
  let hotelsToken = 0;
  let analysisToken = 0;
  let budgetToken = 0;
  let precheckToken = 0;
  let precheckTimer = 0;

  async function post(path, payload) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify(payload),
    });
    let body = null;
    try {
      body = await res.json();
    } catch (e) {
      body = null;
    }
    if (!res.ok || !body || body.ok === false) {
      throw new Error((body && body.error && body.error.message) || Ls("操作失败，请稍后再试"));
    }
    return body.data;
  }

  /* 浮动提示：不依赖页面里是否有反馈节点，旧模板也能看见 */
  const showToast = (text) => {
    if (!text) return;
    let el = document.querySelector(".itin-toast");
    if (!el) {
      el = document.createElement("div");
      el.className = "toast itin-toast";
      document.body.appendChild(el);
    }
    el.textContent = text;
    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => el.remove(), 2800);
  };

  const setMsg = (text, isError) => {
    msgEl.textContent = text || "";
    msgEl.classList.toggle("is-error", Boolean(isError));
  };

  const selectedIds = () => checks.filter((c) => c.checked).map((c) => Number(c.value));

  const peopleCount = () => {
    const n = Math.round(Number(peopleSelect ? peopleSelect.value : DEFAULT_PEOPLE));
    return Number.isFinite(n) ? Math.max(1, Math.min(n, 6)) : DEFAULT_PEOPLE;
  };

  function updateCount() {
    countEl.textContent = Lx(`已选 ${selectedIds().length} 个`, `${selectedIds().length} selected`);
    checks.forEach((c) => c.closest(".itin-card").classList.toggle("is-selected", c.checked));
  }

  /* =====================================================================
     选择阶段预检：勾选 ≥1 时 debounce 400ms 调 /api/itinerary/precheck
     无冲突 / 请求失败 / 勾选不足 → 整块隐藏；失败只影响自己，绝不阻塞生成
     ===================================================================== */
  function resetPrecheck() {
    precheckToken += 1; // 让在途响应作废，避免旧结果覆盖新选择
    if (precheckTimer) {
      clearTimeout(precheckTimer);
      precheckTimer = 0;
    }
    if (precheckEl) {
      precheckEl.textContent = "";
      precheckEl.hidden = true;
      precheckEl.classList.remove("is-open");
    }
  }

  function schedulePrecheck() {
    resetPrecheck(); // 重新勾选先清掉上一次结果
    if (!selectedIds().length) return; // 没勾选不发请求
    precheckTimer = setTimeout(runPrecheck, 400);
  }

  async function runPrecheck() {
    precheckTimer = 0;
    if (!precheckEl) return;
    const ids = selectedIds();
    if (!ids.length) return;
    const token = precheckToken;
    try {
      const data = await post("/api/itinerary/precheck", {
        attraction_ids: ids,
        days: daysSelect ? Number(daysSelect.value) || 1 : 1,
        budget: budgetInput ? Number(budgetInput.value) || 0 : 0,
      });
      if (token !== precheckToken) return; // 已被下一次勾选取代
      renderPrecheck(data);
    } catch (e) {
      if (token !== precheckToken) return;
      // 预检只是锦上添花：失败静默隐藏，生成按钮和其它模块完全不受影响
      if (precheckEl) {
        precheckEl.textContent = "";
        precheckEl.hidden = true;
        precheckEl.classList.remove("is-open");
      }
    }
  }

  function renderPrecheck(data) {
    if (!precheckEl) return;
    precheckEl.textContent = "";
    precheckEl.hidden = true;
    precheckEl.classList.remove("is-open");

    const list =
      data && Array.isArray(data.conflicts)
        ? data.conflicts
            .filter((c) => c && (c.title || c.detail || c.suggestion))
            .slice()
            .sort((a, b) => (SEV_WEIGHT[b.severity] || 0) - (SEV_WEIGHT[a.severity] || 0))
        : [];
    if (!list.length) return; // 无冲突：整块隐藏

    const top = list[0];
    const rest = list.slice(1);
    const sev = sevOf(top);

    const card = el("div", `itin-precheck-bar itin-precheck-${sev}`);
    const head = el("button", "itin-precheck-head");
    head.type = "button";
    head.setAttribute("aria-expanded", "false");
    head.appendChild(el("span", "itin-precheck-dot"));
    head.appendChild(el("span", "itin-precheck-title", top.title || Ls("选择上还有可以优化的地方")));
    head.appendChild(el("span", "itin-precheck-sev", sevText(sev)));
    if (rest.length) {
      head.appendChild(el("span", "itin-precheck-more", Lx(`还有 ${rest.length} 条`, `${rest.length} more`)));
    }
    const toggle = el("span", "itin-precheck-toggle", L("详情"));
    head.appendChild(toggle);

    const body = el("div", "itin-precheck-body");
    body.hidden = true;
    if (top.detail) body.appendChild(el("p", "itin-precheck-detail", top.detail));
    if (top.suggestion) {
      const tip = el("p", "itin-precheck-suggestion");
      tip.appendChild(el("span", "itin-precheck-suggestion-label", L("建议")));
      tip.appendChild(document.createTextNode(top.suggestion));
      body.appendChild(tip);
    }
    if (rest.length) {
      const more = el("ul", "itin-precheck-extra");
      rest.forEach((conflict) => {
        const li = el("li", "itin-precheck-extra-item");
        li.appendChild(el("span", "itin-precheck-extra-title", conflict.title || L("提醒")));
        if (conflict.detail) li.appendChild(el("span", "itin-precheck-extra-text", conflict.detail));
        if (conflict.suggestion) {
          li.appendChild(
            el("span", "itin-precheck-extra-tip", Lx(`建议：${conflict.suggestion}`, `Tip: ${conflict.suggestion}`))
          );
        }
        more.appendChild(li);
      });
      body.appendChild(more);
    }

    if (!body.children.length) {
      toggle.hidden = true;
      head.disabled = true; // 只有标题时没有可展开内容
    }
    head.addEventListener("click", () => {
      const open = body.hidden;
      body.hidden = !open;
      precheckEl.classList.toggle("is-open", open);
      head.setAttribute("aria-expanded", open ? "true" : "false");
      toggle.textContent = open ? L("收起") : L("详情");
    });

    card.appendChild(head);
    card.appendChild(body);
    precheckEl.appendChild(card);
    precheckEl.hidden = false;
  }

  /* ---------- 概要卡片：出行方式 / 途经 / 天气 / 穿衣 / 住宿 / 预算 ---------- */
  function renderBrief(plan) {
    briefEl.textContent = "";
    const blocks = [];
    if (plan.transport) blocks.push(["", L("出发推荐方式"), plan.transport]);
    if ((plan.route || []).length) blocks.push(["", L("路途经过"), plan.route.join(" → ")]);
    if (plan.weather) blocks.push(["", L("天气"), plan.weather]);
    if (plan.clothing) blocks.push(["🧥", L("穿衣推荐"), plan.clothing]);
    if (plan.lodging) blocks.push(["🛏", L("住宿安排"), plan.lodging]);
    if ((plan.budget_plan || []).length) {
      const text = plan.budget_plan.map((item) => `${item.item} ${item.amount}`).join(" · ");
      blocks.push(["", L("预算分配"), text]);
    }

    blocks.forEach((parts) => {
      const card = el("div", "itin-brief-card");
      const body = el("div", "itin-brief-body");
      body.appendChild(el("span", "itin-brief-label", parts[1]));
      body.appendChild(el("span", "itin-brief-text", parts[2]));
      card.appendChild(body);
      briefEl.appendChild(card);
    });

    briefEl.hidden = !blocks.length;
  }

  function renderDay(day) {
    const card = el("div", "itin-day");
    card.dataset.day = String(day.day || "");
    const head = el("div", "itin-day-head");
    head.appendChild(el("h3", "itin-day-title", Lx(`第 ${day.day} 天`, `Day ${day.day}`)));
    if (day.theme) head.appendChild(el("span", "itin-day-theme", day.theme));
    card.appendChild(head);

    (day.slots || []).forEach((slot) => {
      const row = el("div", "itin-slot");
      row.appendChild(el("span", "itin-slot-label", slot.period || ""));
      const body = el("div", "itin-slot-body");
      if (slot.slug) {
        const link = el("a", "itin-slot-name", slot.title);
        link.href = `/attractions/${encodeURIComponent(slot.slug)}`;
        body.appendChild(link);
      } else {
        body.appendChild(el("span", "itin-slot-name", slot.title));
      }
      if (slot.city) body.appendChild(el("span", "itin-slot-city", slot.city));
      if (slot.detail) body.appendChild(el("span", "itin-slot-detail", slot.detail));
      row.appendChild(body);
      card.appendChild(row);
    });

    if (day.tips) card.appendChild(el("p", "itin-day-tips", day.tips));
    return card;
  }

  /* ---------- 住宿推荐：按落点查真实在售房价（失败就整块隐藏） ---------- */

  /* price_text 与 note 的本地化由后端 hotels.py 用 t() 完成，
     这里一律原样渲染，不再做任何二次翻译。 */

  function planDayCities(plan) {
    return (plan.days || []).map((day) => {
      const counts = new Map();
      (day.slots || []).forEach((slot) => {
        if (!slot.city) return;
        counts.set(slot.city, (counts.get(slot.city) || 0) + 1);
      });
      let best = "";
      let bestCount = 0;
      counts.forEach((count, city) => {
        if (count > bestCount) {
          best = city;
          bestCount = count;
        }
      });
      return best;
    });
  }

  function resetHotels() {
    lastHotels = null;
    hotelsToken += 1;
    if (hotelsEl) {
      hotelsEl.textContent = "";
      hotelsEl.hidden = true;
    }
    if (hotelsLoadingEl) hotelsLoadingEl.hidden = true;
  }

  function renderHotels(data) {
    if (!hotelsEl) return;
    hotelsEl.textContent = "";
    const stays = (data && data.stays) || [];
    if (!stays.length) {
      // 上游没查到但给了原因 → 显示原因，别静默消失让用户以为功能坏了
      const note = data && data.note;
      if (note) {
        hotelsEl.appendChild(el("p", "itin-lodging-note", note));
        hotelsEl.hidden = false;
      } else {
        hotelsEl.hidden = true;
      }
      return;
    }
    stays.forEach((stay) => {
      const group = el("div", "itin-lodging-group");
      const head = el("div", "itin-lodging-head");
      head.appendChild(el("span", "itin-lodging-city", Lx(`${stay.city} · 住宿推荐`, `${stay.city} · Places to stay`)));
      if (stay.nights) {
        head.appendChild(
          el(
            "span",
            "itin-lodging-nights",
            Lx(`住 ${stay.nights} 晚`, `${stay.nights} ${plural(stay.nights, "night", "nights")}`)
          )
        );
      }
      if (stay.place) {
        head.appendChild(el("span", "itin-lodging-place", Lx(`按「${stay.place}」查询`, `Searched “${stay.place}”`)));
      }
      group.appendChild(head);

      const grid = el("div", "itin-lodging-grid");
      (stay.hotels || []).forEach((hotel) => {
        const card = el("div", "itin-lodging-card");
        if (hotel.image) {
          const img = el("img", "itin-lodging-photo");
          img.alt = hotel.name;
          img.loading = "lazy";
          // 图挂了就整块去掉，不留破图标 + 灰色占位
          img.addEventListener("error", () => img.remove());
          img.src = hotel.image;
          card.appendChild(img);
        }
        const body = el("div", "itin-lodging-body");
        body.appendChild(el("span", "itin-lodging-name", hotel.name));
        const metaBits = [];
        if (hotel.star) metaBits.push(`★ ${hotel.star}`);
        if (hotel.address) metaBits.push(hotel.address);
        if (metaBits.length) body.appendChild(el("span", "itin-lodging-meta", metaBits.join(" · ")));
        const foot = el("div", "itin-lodging-foot");
        foot.appendChild(
          el("span", "itin-lodging-price", hotel.price_text || L("价格以预订页为准"))
        );
        if (hotel.booking_url) {
          const go = el("a", "itin-lodging-go", L("查看房价"));
          go.href = hotel.booking_url;
          go.target = "_blank";
          go.rel = "noopener noreferrer";
          foot.appendChild(go);
        }
        body.appendChild(foot);
        card.appendChild(body);
        grid.appendChild(card);
      });
      group.appendChild(grid);
      hotelsEl.appendChild(group);
    });
    if (data.note) hotelsEl.appendChild(el("p", "itin-lodging-note", data.note));
    hotelsEl.hidden = false;
  }

  async function loadHotels(plan) {
    if (!hotelsEl) return;
    resetHotels();
    if (staySelect && staySelect.value !== "1") return;
    const dayCities = planDayCities(plan);
    if (!dayCities.some(Boolean)) return;
    const token = hotelsToken;
    if (hotelsLoadingEl) hotelsLoadingEl.hidden = false;
    try {
      const data = await post("/api/itinerary/hotels", {
        day_cities: dayCities,
        budget: budgetInput ? Number(budgetInput.value) || 0 : 0,
        start_date: dateInput ? dateInput.value : "",
        // 选了「需要住宿」就必须有住宿段（只玩 1 天也是住一晚再返程）
        need_stay: staySelect ? staySelect.value === "1" : true,
      });
      if (token !== hotelsToken) return; // 已被下一次生成取代
      lastHotels = data && data.stays && data.stays.length ? data : null;
      renderHotels(data);
    } catch (e) {
      // 连自己的接口都没通：也给一句可见提示，不要静默消失
      if (token === hotelsToken) {
        renderHotels({
          stays: [],
          note: Ls("住宿查询暂时不可用，稍后会自动重试。"),
        });
      }
    } finally {
      if (token === hotelsToken && hotelsLoadingEl) hotelsLoadingEl.hidden = true;
    }
  }

  /* ---------- 冲突 + 预算：两路并行，各自失败各自静默隐藏 ---------- */
  function resetAnalysis() {
    analysisToken += 1;
    lastConflicts = null;
    renderConflicts(conflictsHost, resultEl, null);
    resetBudget();
  }

  /* 预算单独一把 token：人数变化时只重拉预算，不重跑冲突、不重生成行程 */
  function resetBudget() {
    budgetToken += 1;
    lastBudget = null;
    renderBudget(budgetHost, null);
  }

  function loadBudget(plan) {
    resetBudget();
    const token = budgetToken;
    const days = (plan && plan.days) || [];
    if (!days.length || !budgetHost) return;
    post("/api/itinerary/budget", {
      days,
      people: peopleCount(),
      budget: budgetInput ? Number(budgetInput.value) || 0 : 0,
      start_date: dateInput ? dateInput.value : "",
      hotel_price: 0,
    })
      .then((data) => {
        if (token !== budgetToken) return;
        lastBudget = data || null;
        renderBudget(budgetHost, lastBudget);
      })
      .catch(() => {
        if (token !== budgetToken) return;
        lastBudget = null;
        renderBudget(budgetHost, null); // 失败静默隐藏，行程本体不动
      });
  }

  function loadAnalysis(plan) {
    resetAnalysis();
    const token = analysisToken;
    const days = (plan && plan.days) || [];
    if (!days.length) return;
    const budget = budgetInput ? Number(budgetInput.value) || 0 : 0;

    // 并行发出：谁先回来谁先画，互不阻塞主行程
    post("/api/itinerary/conflicts", { days, budget })
      .then((data) => {
        if (token !== analysisToken) return;
        lastConflicts = data && Array.isArray(data.conflicts) ? data : null;
        renderConflicts(conflictsHost, resultEl, lastConflicts);
      })
      .catch(() => {
        if (token !== analysisToken) return;
        lastConflicts = null;
        renderConflicts(conflictsHost, resultEl, null); // 失败静默隐藏，行程本体不动
      });

    loadBudget(plan);
  }

  function render(plan) {
    const days = plan.days || [];
    renderBrief(plan);

    resultEl.textContent = "";
    days.forEach((day) => resultEl.appendChild(renderDay(day)));
    resultEl.hidden = !days.length;

    summaryEl.textContent = plan.summary || "";
    summaryEl.hidden = !plan.summary;

    notesEl.textContent = "";
    (plan.notes || []).forEach((note) => notesEl.appendChild(el("li", null, note)));

    const xhs = plan.xhs || null;
    if (xhs && xhs.count) {
      const label =
        xhs.source === "live"
          ? Lx(`已参考小红书实时笔记 ${xhs.count} 条`, `Referenced ${xhs.count} live Xiaohongshu notes`)
          : Lx(`已参考小红书风格笔记 ${xhs.count} 条（本地缓存）`, `Referenced ${xhs.count} Xiaohongshu-style notes (cached)`);
      notesEl.appendChild(el("li", "itin-xhs", label));
    }
    notesEl.hidden = notesEl.children.length === 0;

    saveBox.hidden = !days.length;
    loadHotels(plan);
    loadAnalysis(plan);
  }

  checks.forEach((c) =>
    c.addEventListener("change", () => {
      updateCount();
      schedulePrecheck();
    })
  );
  updateCount();

  // 人数变化：只重拉预算（不重新生成行程），沙盘里的「N 人合计」跟着接口回显走
  if (peopleSelect) {
    peopleSelect.addEventListener("change", () => {
      if (!lastPlan || !Array.isArray(lastPlan.days) || !lastPlan.days.length) return;
      loadBudget(lastPlan);
    });
  }

  /* ---------- 失败备选入口 ---------- */
  function clearRetry() {
    if (!retryEl) return;
    retryEl.textContent = "";
    retryEl.hidden = true;
  }

  function pickRandom(count) {
    const pool = checks.slice();
    for (let i = pool.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      const tmp = pool[i];
      pool[i] = pool[j];
      pool[j] = tmp;
    }
    const chosen = new Set(pool.slice(0, Math.max(2, Math.min(count, pool.length))));
    checks.forEach((box) => {
      box.checked = chosen.has(box);
    });
    updateCount();
  }

  function showRetry() {
    if (!retryEl) return;
    retryEl.textContent = "";
    const add = (label, action) => {
      const btn = el("button", "itin-retry-btn", Ls(label));
      btn.type = "button";
      btn.addEventListener("click", () => {
        clearRetry();
        action();
      });
      retryEl.appendChild(btn);
    };
    add("换 3 个景点试试", () => {
      pickRandom(3);
      runGenerate();
    });
    add("多加一天再试", () => {
      if (daysSelect) {
        const next = Math.min(5, Number(daysSelect.value || 1) + 1);
        daysSelect.value = String(next);
      }
      runGenerate();
    });
    retryEl.hidden = false;
  }

  async function runGenerate() {
    const ids = selectedIds();
    if (!ids.length) {
      setMsg(Ls("请先选择景点"), true);
      return;
    }
    clearRetry();
    setMsg(Ls("AI 正在排行程，通常 5–15 秒…"));
    // 住宿要等行程出来才开始查（还要再等几秒），先把「正在生成」摆出来，
    // 否则这段时间住宿那块是空的，看着像功能没生效
    if (hotelsLoadingEl && (!staySelect || staySelect.value === "1")) {
      hotelsLoadingEl.hidden = false;
    }
    genBtn.disabled = true;
    try {
      const plan = await post("/api/itinerary/ai-plan", {
        attraction_ids: ids,
        days: Number(daysSelect.value),
        origin: originInput ? originInput.value.trim() : "",
        need_stay: staySelect ? staySelect.value === "1" : true,
        budget: budgetInput ? Number(budgetInput.value) || 0 : 0,
        start_date: dateInput ? dateInput.value : "",
      });
      const days = plan && plan.days;
      if (!days || !days.length) {
        briefEl.hidden = true;
        summaryEl.hidden = true;
        resultEl.hidden = true;
        notesEl.hidden = true;
        saveBox.hidden = true;
        resetHotels();
        resetAnalysis();
        setMsg(Ls("没有生成可用的行程，请换几个景点试试"), true);
        showRetry();
        return;
      }
      current = days;
      lastPlan = plan;
      render(plan);
      setMsg(plan.source === "ai" ? Ls("AI 行程已生成") : Ls("AI 暂不可用，已生成基础草案"));
    } catch (e) {
      setMsg(e.message, true);
      if (hotelsLoadingEl) hotelsLoadingEl.hidden = true; // 整单失败，别留个假进度
      showRetry();
    } finally {
      genBtn.disabled = false;
    }
  }

  genBtn.addEventListener("click", runGenerate);

  if (saveBtn) {
    /* 内容没变时再点保存不再新建记录（标题或行程变了才会存新的一份） */
    let savedSignature = "";

    saveBtn.addEventListener("click", async () => {
      const title = (titleInput.value || "").trim();
      if (!current) return;
      if (!title) {
        setMsg(Ls("请先填写行程标题"), true);
        return;
      }
      saveBtn.disabled = true;
      setMsg(Ls("正在保存行程…"));
      if (saveMsgEl) { saveMsgEl.hidden = true; saveMsgEl.textContent = ""; }
      try {
        const brief = lastPlan
          ? {
              summary: lastPlan.summary || "",
              transport: lastPlan.transport || "",
              route: lastPlan.route || [],
              weather: lastPlan.weather || "",
              clothing: lastPlan.clothing || "",
              lodging: lastPlan.lodging || "",
              budget_plan: lastPlan.budget_plan || [],
              notes: lastPlan.notes || [],
              xhs: lastPlan.xhs || null,
              hotels: lastHotels || null,
              conflicts: lastConflicts || null,
              budget: lastBudget || null,
            }
          : {};
        const payload = { title, days: Number(daysSelect.value), items: { brief, days: current } };
        const signature = JSON.stringify(payload);
        if (signature === savedSignature) {
          setMsg("");
          if (saveMsgEl) {
            saveMsgEl.textContent = Ls("这份行程已经保存过了，不用重复保存");
            saveMsgEl.hidden = false;
            saveMsgEl.classList.remove("is-error");
          }
          showToast(Ls("这份行程已经保存过了，不用重复保存"));
          return;
        }
        const saved = await post("/api/itineraries", payload);
        savedSignature = signature;
        const isDup = Boolean(saved && saved.duplicate);
        const tip = isDup
          ? Ls("这份行程已经保存过了，不用重复保存")
          : Ls("行程已保存在个人页面中");
        setMsg("");
        if (saveMsgEl) {
          saveMsgEl.textContent = tip;
          saveMsgEl.hidden = false;
          saveMsgEl.classList.remove("is-error");
        }
        showToast(tip);
      } catch (e) {
        setMsg(e.message, true);
        if (saveMsgEl) {
          saveMsgEl.textContent = e.message;
          saveMsgEl.hidden = false;
          saveMsgEl.classList.add("is-error");
        }
        showToast(e.message);
      } finally {
        saveBtn.disabled = false;
      }
    });
  }
})();



