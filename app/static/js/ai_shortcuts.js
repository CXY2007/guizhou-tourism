/* 站内 AI 助手小球：按当前页面切换快捷指令（中英双语）。
 *
 * - 景点详情页：附近有什么 / 怎么去 / 要爬多久 / 适合老人小孩吗
 * - 行程规划页：查冲突 / 算预算（直连本地接口，不调大模型）/ 换掉太远的那个 / 这行程赶不赶
 * - 首页与列表页：推荐 3 天行程 / 本月最适合去哪 / 雨天备选
 * - 后台页：隐藏建议，不给管理员推旅游问题
 * - 其它页：保持 base 里的默认建议不动（绝不出现空白）
 *
 * 依赖 app.js 已经绑定好的面板开合与发送逻辑：
 * 普通指令 = 填进输入框 + 触发 submit；查冲突/算预算 = 自己 fetch 接口 + 渲染结果。
 *
 * 语言判定：base.html 的 <html lang> 已按 current_lang() 输出 en / zh-CN，
 * body[data-lang] 是同一份信息的显式钩子（给 CSS 用）。两者任一为 en 即走英文。
 *
 * 双语边界：
 * - 按钮文案、小节标题、结果块里「我们自己写的」文案（备注、人均、合计、省/超预算）
 *   都在本文件里翻译。
 * - 接口返回的 title / detail / suggestion 由后端 i18n.py 按 session 语言翻译好了，
 *   这里原样显示，绝不二次加工。
 * - 中文站：所有函数走的仍是原来的中文原文，一个字符都不变。
 *
 * 注意：本文件不允许改 i18n.py，所以英文文案只存在于浏览器侧；
 * 发出去的指令 message 仍沿用现有中文 data 约定（与 base 默认建议一致）。
 */
(() => {
  "use strict";

  const body = document.body;
  if (!body) return;

  const suggestions = document.querySelector("[data-ai-suggestions]");
  if (!suggestions) return;

  const suggestLabel = document.querySelector(".ai-suggest-label");
  const panel = document.querySelector("[data-ai-panel]");
  const messages = document.querySelector("[data-ai-messages]");
  const form = document.querySelector("[data-ai-form]");
  const input = document.querySelector("[data-ai-input]");
  const openBtn = document.querySelector(".ai-btn[data-ai-open]");
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";

  const T = (text) => {
    if (typeof window.T === "function") return window.T(text);
    const dict = window.__I18N || {};
    return dict[text] || text;
  };

  /* ---------- 语言 ---------- */

  const htmlLang = (document.documentElement.lang || "").toLowerCase();
  const bodyLang = (body.dataset.lang || "").toLowerCase();
  const LANG_EN = htmlLang.indexOf("en") === 0 || bodyLang.indexOf("en") === 0;

  // 我们自己写的界面文案（按钮、小节标题、结果块备注）。
  // 中文站在 EN_TEXT 里查不到时走 T()，返回的仍是中文原文。
  const EN_TEXT = {
    // 小节标题
    "这个景点，可以这样问：": "Ask about this spot:",
    "这份行程，我可以帮你核一下：": "I can check this plan for you:",
    "接下来想去哪？试试这些：": "Where to next? Try these:",

    // 景点页
    "附近有什么": "Nearby",
    "怎么去": "How to get there",
    "要爬多久": "How long to climb",
    "适合老人小孩吗": "Kid & elder friendly",

    // 行程页
    "查冲突": "Check conflicts",
    "算预算": "Estimate budget",
    "换掉太远的那个": "Drop the far one",
    "这行程赶不赶": "Is it too rushed",

    // 首页 / 列表页
    "推荐 3 天行程": "Plan 3 days",
    "本月最适合去哪": "Best this month",
    "雨天备选": "Rainy-day backup",
    "帮我排 3 天行程": "Plan a 3-day trip",
    "黄果树门票多少": "Huangguoshu ticket price",
    "贵阳明天下雨吗": "Rain in Guiyang tomorrow?",
    "帮我跳转评分最高的景点": "Top-rated attraction",

    // 结果块备注（我们自己的口径，必须跟着语言走）
    "本地规则检查 · 未调用大模型": "Local rules · no LLM call",
    "本地计算 · 未调用大模型": "Local calculation · no LLM call",
  };

  const L = (text) => (LANG_EN ? EN_TEXT[text] || T(text) : T(text));

  // 带插值的句式：中文原文必须逐字保持，英文另一套。
  const Lx = (zh, en) => (LANG_EN ? en : zh);

  // 结果块里我们自己写的中文句子（整句、无插值）
  const EN_SENTENCES = {
    "暂时找不到景点，稍后再试。": "Could not find an attraction. Please try again later.",
    "没查出冲突：每天的城市、时段和节奏都还算稳。":
      "No conflicts found — cities, time slots and pace all look reasonable.",
    "没拿到预算结果，稍后再试。": "No budget result. Please try again.",
    "发现一处冲突": "A conflict was found",
    "先在页面上选几个景点、点「生成 AI 行程」，我就能帮你查冲突、算预算了。":
      "Pick a few attractions on this page and tap “Generate with AI”, then I can check conflicts and estimate the budget.",
    "分析接口暂不可用": "The analysis service is unavailable",
    "分析接口暂不可用，稍后再试。": "The analysis service is unavailable. Please try again.",
    "正在算预算…": "Calculating the budget…",
    "正在核对行程…": "Checking the itinerary…",
  };
  const Ls = (text) => (LANG_EN ? EN_SENTENCES[text] || L(text) : text);

  /* ---------- 当前页面识别 ---------- */

  const page = (body.dataset.page || "").trim();
  const path = location.pathname.replace(/\/+$/, "") || "/";
  const pathSlug = (path.match(/^\/attractions\/([^/]+)$/) || [])[1] || "";
  const slug = (body.dataset.attractionSlug || "").trim() || pathSlug;
  const isAdmin = page.indexOf("admin") === 0 || path.indexOf("/admin") === 0;
  const isDetail = Boolean(slug) && (page === "detail" || Boolean(pathSlug));
  const isItinerary = page === "itinerary" || path === "/itinerary";
  const isBrowse = !isAdmin && !isDetail && !isItinerary && (path === "/" || path === "/attractions");

  const attractionName = (() => {
    const fromBody = (body.dataset.attractionName || "").trim();
    if (fromBody) return fromBody;
    const title = document.querySelector(".detail-title");
    const text = title ? (title.textContent || "").trim() : "";
    return text || slug;
  })();

  /* ---------- 指令集 ---------- */
  /* label 走双语；message 是发给后端的中文原始指令，保持既有约定不变。 */

  const CONTEXT_ATTRACTION = {
    key: "attraction",
    label: "这个景点，可以这样问：",
    items: [
      { label: "附近有什么", message: `${attractionName}附近还有什么值得去的地方？` },
      { label: "怎么去", message: `${attractionName}怎么去？从贵阳出发怎么安排交通？` },
      { label: "要爬多久", message: `${attractionName}要爬多久？大概要预留几个小时？` },
      { label: "适合老人小孩吗", message: `${attractionName}适合带老人小孩去吗？` },
    ],
  };

  const CONTEXT_ITINERARY = {
    key: "itinerary",
    label: "这份行程，我可以帮你核一下：",
    items: [
      { label: "换掉太远的那个", message: "帮我看看这份行程里哪个景点最远、最折腾，换个近一点的" },
      { label: "这行程赶不赶", message: "帮我看看这份行程赶不赶，每天安排是不是太满" },
    ],
  };

  const CONTEXT_BROWSE = {
    key: "browse",
    label: "接下来想去哪？试试这些：",
    items: [
      // 三条分别指向「排行程 / 查事实 / 查天气」三种能力，让用户顺带发现小球能做什么
      { label: "帮我排 3 天行程", message: "帮我排一份 3 天的贵州行程" },
      { label: "黄果树门票多少", message: "黄果树瀑布门票多少钱？开放到几点？" },
      { label: "贵阳明天下雨吗", message: "贵阳明天下雨吗？下雨还能玩什么？" },
      // 直连：不走大模型，查评分最高景点后直接跳转
      { label: "帮我跳转评分最高的景点", action: "top-attraction" },
    ],
  };

  const context = isDetail
    ? CONTEXT_ATTRACTION
    : isItinerary
    ? CONTEXT_ITINERARY
    : isBrowse
    ? CONTEXT_BROWSE
    : null;

  /* 后台页：直接收起建议区，不给管理员推旅游问题 */
  if (isAdmin) {
    suggestions.hidden = true;
    if (suggestLabel) suggestLabel.hidden = true;
    return;
  }

  /* 查不到映射：保留 base.html 里的默认建议，什么都不改 */
  if (!context) return;

  /* ---------- 面板内消息（结构对齐 app.js 的 addMsg） ---------- */

  function scrollMessages() {
    if (messages) messages.scrollTop = messages.scrollHeight;
  }

  function addPlainMsg(text, who) {
    if (!messages) return;
    const div = document.createElement("div");
    div.className = "ai-msg " + (who === "user" ? "ai-msg-user" : "ai-msg-bot");
    div.textContent = text;
    messages.appendChild(div);
    scrollMessages();
    return div;
  }

  function addResultBlock(rows, note) {
    if (!messages) return null;
    const wrap = document.createElement("div");
    wrap.className = "ai-msg ai-msg-bot ai-shortcut-msg";
    rows.forEach((row, index) => {
      const p = document.createElement("p");
      p.className = "ai-sc-row" + (index === 0 ? " ai-sc-title" : "");
      if (row && typeof row === "object") {
        if (row.tone) p.classList.add("is-" + row.tone);
        p.textContent = row.text;
      } else {
        p.textContent = String(row);
      }
      wrap.appendChild(p);
    });
    if (note) {
      const foot = document.createElement("p");
      foot.className = "ai-sc-note";
      foot.textContent = note;
      wrap.appendChild(foot);
    }
    messages.appendChild(wrap);
    scrollMessages();
    return wrap;
  }

  function ensurePanelOpen() {
    if (!panel) return;
    if (!panel.hidden) return;
    if (openBtn) openBtn.click();
    else panel.hidden = false;
  }

  /* ---------- 普通指令：沿用现有逻辑（填输入框 + 发送） ---------- */

  function sendToAssistant(text) {
    ensurePanelOpen();
    if (!input) return;
    input.value = text;
    if (form) {
      form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    } else {
      input.focus();
    }
  }

  /* ---------- 行程页：从已渲染的 DOM 里还原行程对象 ---------- */

  function collectDaysFromDom() {
    const nodes = document.querySelectorAll("[data-result] .itin-day");
    const days = [];
    nodes.forEach((node, index) => {
      const titleEl = node.querySelector(".itin-day-title");
      const titleText = titleEl ? (titleEl.textContent || "") : "";
      const match = titleText.match(/(\d+)/);
      const day = {
        day: match ? Number(match[1]) : index + 1,
        theme: "",
        slots: [],
        tips: "",
      };
      const themeEl = node.querySelector(".itin-day-theme");
      if (themeEl) day.theme = (themeEl.textContent || "").trim();

      node.querySelectorAll(".itin-slot").forEach((slot) => {
        const labelEl = slot.querySelector(".itin-slot-label");
        const nameEl = slot.querySelector(".itin-slot-name");
        const cityEl = slot.querySelector(".itin-slot-city");
        const detailEl = slot.querySelector(".itin-slot-detail");
        let slotSlug = "";
        const link = nameEl && nameEl.matches("a") ? nameEl : slot.querySelector("a.itin-slot-name");
        if (link) {
          const href = link.getAttribute("href") || "";
          const hrefMatch = href.match(/\/attractions\/([^/?#]+)/);
          if (hrefMatch) {
            try {
              slotSlug = decodeURIComponent(hrefMatch[1]);
            } catch (error) {
              slotSlug = hrefMatch[1];
            }
          }
        }
        day.slots.push({
          period: labelEl ? (labelEl.textContent || "").trim() : "",
          title: nameEl ? (nameEl.textContent || "").trim() : "",
          slug: slotSlug,
          city: cityEl ? (cityEl.textContent || "").trim() : "",
          detail: detailEl ? (detailEl.textContent || "").trim() : "",
        });
      });

      const tipsEl = node.querySelector(".itin-day-tips");
      if (tipsEl) day.tips = (tipsEl.textContent || "").trim();
      days.push(day);
    });
    return days;
  }

  function readBudgetInput() {
    const el = document.querySelector("[data-budget]");
    const value = el ? Number(el.value) : 0;
    return Number.isFinite(value) && value > 0 ? Math.round(value) : 0;
  }

  function readStartDate() {
    const el = document.querySelector("[data-start-date]");
    return el ? el.value || "" : "";
  }

  /* 人数以页面上的「出行人数」控件为准，控件不存在才兜底 2（后端契约默认值） */
  const DEFAULT_PEOPLE = 2;
  function readPeople() {
    const el = document.querySelector("[data-people]");
    const n = Math.round(Number(el ? el.value : DEFAULT_PEOPLE));
    if (!Number.isFinite(n) || n < 1) return DEFAULT_PEOPLE;
    return Math.min(20, n);
  }

  async function postJson(pathname, payload) {
    const response = await fetch(pathname, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
      body: JSON.stringify(payload),
    });
    let payloadBody = null;
    try {
      payloadBody = await response.json();
    } catch (error) {
      payloadBody = null;
    }
    if (!response.ok || !payloadBody || payloadBody.ok === false) {
      throw new Error(
        (payloadBody && payloadBody.error && payloadBody.error.message) ||
          Ls("分析接口暂不可用")
      );
    }
    return payloadBody.data || payloadBody;
  }

  function money(value) {
    const num = Number(value) || 0;
    return "¥" + num.toLocaleString(LANG_EN ? "en-US" : "zh-CN");
  }

  function renderConflicts(data) {
    const list = (data && data.conflicts) || [];
    if (!list.length) {
      addResultBlock(
        [Ls("没查出冲突：每天的城市、时段和节奏都还算稳。")],
        L("本地规则检查 · 未调用大模型")
      );
      return;
    }
    const rows = [
      Lx(
        `查出 ${list.length} 处需要留意：`,
        list.length === 1 ? "1 thing to watch:" : `${list.length} things to watch:`
      ),
    ];
    list.slice(0, 3).forEach((item) => {
      let head = (item && item.title) || Ls("发现一处冲突");
      const day = Number(item && item.day) || 0;
      // day === 0 是全局问题（超预算这类），不出现「第 0 天」；
      // day >= 1 且标题里还没有「第 N 天 / Day N」时才补前缀，避免和后端文案重复。
      // 后端 title 已按 session 语言翻好：中文是「第 N 天…」，英文是「Day N…」。
      const hasDayPrefix = LANG_EN
        ? new RegExp("\\bday\\s*" + day + "\\b", "i").test(head)
        : new RegExp("第\\s*" + day + "\\s*天").test(head);
      if (day >= 1 && !hasDayPrefix) {
        head = Lx(`第 ${day} 天：${head}`, `Day ${day}: ${head}`);
      }
      const fix = item && item.suggestion ? " → " + item.suggestion : "";
      rows.push({ text: head + fix, tone: item && item.severity ? item.severity : "" });
    });
    if (list.length > 3) {
      rows.push(
        Lx(
          `…还有 ${list.length - 3} 处，可以先按上面的改。`,
          `…and ${list.length - 3} more. Start with the fixes above.`
        )
      );
    }
    addResultBlock(rows, L("本地规则检查 · 未调用大模型"));
  }

  function renderBudget(data) {
    if (!data) {
      addResultBlock([Ls("没拿到预算结果，稍后再试。")], L("本地计算 · 未调用大模型"));
      return;
    }
    const perPerson = Number(data.total_per_person) || 0;
    const people = readPeople();
    const totalAll = Number(data.total_all) || perPerson * people;
    const rows = [
      Lx(
        `人均 ${money(perPerson)} · ${people} 人合计 ${money(totalAll)}`,
        `${money(perPerson)} per person · ${money(totalAll)} for ${people} people`
      ),
    ];

    const items = (data.items || [])
      .map((item) => `${item.label} ${money(item.per_person)}`)
      .join(" · ");
    if (items) rows.push(items);

    const compare = data.compare || {};
    const budget = Number(compare.budget) || 0;
    const status = compare.status || "";
    // budget=0 时后端给 status="unknown"，只报总人均，不编「省/超 0 元」
    if (budget > 0 && status !== "unknown") {
      const delta = Number(compare.delta) || 0;
      if (delta > 0) {
        rows.push(
          Lx(
            `超出预算 ${money(delta)}（预算 ${money(budget)}）`,
            `${money(delta)} over budget (budget ${money(budget)})`
          )
        );
      } else if (delta < 0) {
        rows.push(
          Lx(
            `比预算省 ${money(Math.abs(delta))}（预算 ${money(budget)}）`,
            `${money(Math.abs(delta))} under budget (budget ${money(budget)})`
          )
        );
      } else {
        rows.push(
          Lx(
            `刚好卡在预算上（${money(budget)}）`,
            `Right on budget (${money(budget)})`
          )
        );
      }
    }

    const cuts = data.cuts || [];
    if (cuts.length) {
      const cut = cuts[0] || {};
      const label = cut.label || "";
      // 后端有的 cuts 文案里已经带了「省 ¥xxx」/「save ¥xxx」，避免重复追加
      const hasSavingInLabel = LANG_EN
        ? /(?:save|saving)\s*¥?\s*\d/i.test(label)
        : /省\s*¥?\s*\d/.test(label);
      if (label && cut.saving && !hasSavingInLabel) {
        rows.push(
          Lx(
            `省法：${label}（省 ${money(cut.saving)}）`,
            `Saving: ${label} (save ${money(cut.saving)})`
          )
        );
      } else if (label) {
        rows.push(Lx(`省法：${label}`, `Saving: ${label}`));
      }
    }

    addResultBlock(rows, L("本地计算 · 未调用大模型"));
  }

  let localBusy = false;

  /* AI 不可用时的降级直连：保持原样，只是加了 echo 开关 */
  /* 先交给 AI：带上当前页面上的行程作为上下文；
     AI 成功就结束，失败（网络/限流/模型不可用）才降级到本地直连。 */
  async function runLocalAction(action) {
    if (localBusy) return;
    localBusy = true;
    ensurePanelOpen();

    const question =
      action === "budget" ? L("算预算") : action === "conflicts" ? L("查冲突") : L("帮我跳转评分最高的景点");
    let handled = false;

    try {
      const send = window.aiSend;
      const result = typeof send === "function" ? await send(question) : { ok: false };
      if (result && result.ok) {
        const structured = (result.data && result.data.structured) || {};
        if (structured.conflicts) renderConflicts(structured.conflicts);
        if (structured.budget) renderBudget(structured.budget);
        const navigated = !!(result.data && result.data.action && result.data.action.type === "navigate");
        handled = navigated || action !== "top-attraction";
      }
    } catch (error) {
      handled = false;
    }

    try {
      if (!handled) await runLocalFallback(action, false);
    } finally {
      localBusy = false;
    }
  }

  async function runLocalFallback(action, echo) {
    const showEcho = echo !== false;
    ensurePanelOpen();

    // 直连：跳转评分最高的景点
    if (action === "top-attraction") {
      ensurePanelOpen();
      if (showEcho) addPlainMsg(L("帮我跳转评分最高的景点"), "user");
      const progress = window.aiProgress.addProgress();
      try {
        const res = await fetch("/api/attractions/top", { headers: { Accept: "application/json" } });
        const body = await res.json();
        if (progress && progress.stop) progress.stop();
        if (!res.ok || !body.ok) {
          addPlainMsg(Ls("暂时找不到景点，稍后再试。"), "bot");
          return;
        }
        const d = body.data;
        const suffix = LANG_EN ? "?lang=en" : "";
        addPlainMsg(
          Lx(
            `评分最高的是 ${d.name}（★${d.rating}），正在带你去…`,
            `Top rated: ${d.name} (★${d.rating}). Taking you there…`
          ),
          "bot"
        );
        window.setTimeout(() => {
          window.location.href = d.url + suffix;
        }, 700);
      } catch (err) {
        if (progress && progress.stop) progress.stop();
        addPlainMsg(Ls("暂时找不到景点，稍后再试。"), "bot");
      } finally {
        localBusy = false;
      }
      return;
    }

    const isBudget = action === "budget";
    // 用户消息回显用按钮上的那套文案，跟着语言走
    if (showEcho) addPlainMsg(L(isBudget ? "算预算" : "查冲突"), "user");

    const days = collectDaysFromDom();
    if (!days.length) {
      addPlainMsg(
        Ls("先在页面上选几个景点、点「生成 AI 行程」，我就能帮你查冲突、算预算了。"),
        "bot"
      );
      return;
    }

    const budget = readBudgetInput();
    const payload = { days, budget };
    if (isBudget) {
      payload.people = readPeople();
      payload.start_date = readStartDate();
      payload.hotel_price = 0;
    }

    const progress = window.aiProgress.addProgress();
    try {
      const data = await postJson(
        isBudget ? "/api/itinerary/budget" : "/api/itinerary/conflicts",
        payload
      );
      progress.stop();
      if (isBudget) renderBudget(data);
      else renderConflicts(data);
    } catch (error) {
      progress.stop();
      addPlainMsg(
        (error && error.message) || Ls("分析接口暂不可用，稍后再试。"),
        "bot"
      );
      window.aiProgress.addFailureChoices(
        () => runLocalAction(action),
        () => runLocalAction(isBudget ? "conflicts" : "budget"),
        L(isBudget ? "查冲突" : "算预算")
      );
    } finally {
      localBusy = false;
    }
  }

  /* 助手工具需要的上下文：当前页面上的行程 + 预算/人数/出发日 */
  window.__aiContext = function () {
    const days = collectDaysFromDom();
    if (!days.length) return null;
    return {
      days: days,
      budget: readBudgetInput(),
      people: readPeople(),
      start_date: readStartDate(),
      hotel_price: 0,
    };
  };

  /* ---------- 渲染按钮 ---------- */

  suggestions.textContent = "";
  context.items.forEach((item) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = L(item.label);
    if (item.action) {
      btn.classList.add("is-direct");
      btn.dataset.aiAction = item.action;
      btn.addEventListener("click", () => runLocalAction(item.action));
    } else {
      btn.addEventListener("click", () => sendToAssistant(item.message));
    }
    suggestions.appendChild(btn);
  });

  if (suggestLabel) {
    suggestLabel.textContent = L(context.label);
    suggestLabel.hidden = false;
  }
})();
