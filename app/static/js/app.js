(() => {
  const nav = document.querySelector("[data-nav]");
  const onScroll = () => {
    if (!nav) return;
    nav.classList.toggle("is-scrolled", window.scrollY > 40);
  };
  onScroll();
  window.addEventListener("scroll", onScroll, { passive: true });

  const burger = document.querySelector("[data-burger]");
  const mobile = document.querySelector("[data-mobile-menu]");
  if (burger && mobile) {
    burger.addEventListener("click", () => {
      const open = mobile.hidden;
      mobile.hidden = !open;
      burger.setAttribute("aria-expanded", String(open));
    });
  }

  // 入场：全站卡片进入视口下缘时丝滑上滑（含 JS 动态插入的卡片）
  const REVEAL_SELECTOR = [
    ".attr-card",
    ".daily-band",
    ".side-card",
    ".weather-card",
    ".chart-card",
    ".comment-item",
    ".fav-item",
    ".itin-card",
    ".stat-card",
    ".auth-card",
    ".season-card",
    ".admin-item",
  ].join(",");

  const revealObserver =
    "IntersectionObserver" in window
      ? new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (!entry.isIntersecting) return;
              entry.target.classList.add("is-visible");
              revealObserver.unobserve(entry.target);
            });
          },
          { rootMargin: "0px 0px -14% 0px", threshold: 0.12 }
        )
      : null;

  const prepareReveal = (el) => {
    if (!el || el.nodeType !== 1) return;
    if (el.closest(".ai-panel, .mobile-menu, .site-nav")) return;
    if (!el.classList.contains("reveal")) el.classList.add("reveal");
    const parent = el.parentElement;
    if (parent && !el.style.getPropertyValue("--reveal-delay")) {
      const siblings = Array.from(parent.children).filter(
        (child) => child.matches && child.matches(REVEAL_SELECTOR)
      );
      const index = siblings.indexOf(el);
      if (index > 0) el.style.setProperty("--reveal-delay", `${Math.min(index, 4) * 60}ms`);
    }
    if (revealObserver) revealObserver.observe(el);
    else el.classList.add("is-visible");
  };

  const scanReveals = (root) => {
    if (!root || root.nodeType !== 1) return;
    if (root.matches && root.matches(`${REVEAL_SELECTOR}, .reveal`)) prepareReveal(root);
    root.querySelectorAll(REVEAL_SELECTOR).forEach(prepareReveal);
  };

  scanReveals(document.body);
  document.querySelectorAll(".reveal").forEach(prepareReveal);

  if ("MutationObserver" in window) {
    new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === 1) scanReveals(node);
        });
      });
    }).observe(document.body, { childList: true, subtree: true });
  }

  const toast = (message) => {
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2200);
  };
  window.showToast = toast;

  const T = (text, vars) => {
    let value = (window.__I18N && window.__I18N[text]) || text;
    if (vars) {
      Object.keys(vars).forEach((key) => {
        value = value.split("{" + key + "}").join(vars[key]);
      });
    }
    return value;
  };
  window.T = T;

  // 英文模式下，把页面里仍在的中文 UI 文案替换掉（含 JS 后插入的节点）。
  const i18nDict = window.__I18N || {};
  if (Object.keys(i18nDict).length) {
    const patterns = [
      [/^已选 (\d+) 个$/, (m) => `${m[1]} selected`],
      [/^第 (\d+) 天$/, (m) => `Day ${m[1]}`],
      [/^共 (\d+) 条$/, (m) => `${m[1]} total`],
      [/^你已打 (\d+) 星，可重新选择$/, (m) => `You rated ${m[1]} stars. Tap to change.`],
      [/^你已打 (\d+) 星$/, (m) => `You rated ${m[1]} stars.`],
      [/^已评分 (\d+) 星$/, (m) => `Rated ${m[1]} stars`],
      [/^(\d+) 星$/, (m) => `${m[1]} stars`],
      [/^(\d+) 天$/, (m) => `${m[1]} days`],
      [/^昵称已更新为 (.+)$/, (m) => `Nickname updated to ${m[1]}`],
      [/^周([一二三四五六日])$/, (m) => i18nDict["周" + m[1]] || m[0]],
    ];
    const translate = (text) => {
      const trimmed = text.trim();
      if (!trimmed) return text;
      let value = i18nDict[trimmed];
      if (!value) {
        for (const [re, fn] of patterns) {
          const match = trimmed.match(re);
          if (match) {
            value = fn(match);
            break;
          }
        }
      }
      return value ? text.replace(trimmed, value) : text;
    };
    const walk = (root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) =>
          node.parentElement && /^(SCRIPT|STYLE)$/.test(node.parentElement.tagName)
            ? NodeFilter.FILTER_REJECT
            : NodeFilter.FILTER_ACCEPT,
      });
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach((node) => {
        node.nodeValue = translate(node.nodeValue);
      });
      const scope = root.querySelectorAll ? root : document;
      scope.querySelectorAll("[placeholder],[aria-label],[title]").forEach((el) => {
        ["placeholder", "aria-label", "title"].forEach((attr) => {
          if (el.hasAttribute(attr)) el.setAttribute(attr, translate(el.getAttribute(attr)));
        });
      });
    };
    const startI18n = () => {
      walk(document.body);
      new MutationObserver((mutations) => {
        mutations.forEach((mutation) => {
          mutation.addedNodes.forEach((node) => {
            if (node.nodeType === 1) walk(node);
            else if (node.nodeType === 3) node.nodeValue = translate(node.nodeValue);
          });
        });
      }).observe(document.body, { childList: true, subtree: true });
    };
    if (document.body) startI18n();
    else document.addEventListener("DOMContentLoaded", startI18n);
  }

  document.querySelectorAll("[data-soon]").forEach((btn) => {
    btn.addEventListener("click", () => toast(btn.dataset.soon));
  });

  const panel = document.querySelector("[data-ai-panel]");
  const messages = document.querySelector("[data-ai-messages]");
  const form = document.querySelector("[data-ai-form]");
  const input = document.querySelector("[data-ai-input]");
  const openBtns = document.querySelectorAll("[data-ai-open]");
  const closeBtn = document.querySelector("[data-ai-close]");
  // 面板每次打开时执行的钩子（缩放提示等晚于此处初始化的逻辑挂在这里）
  const panelOpenHooks = [];

  const openPanel = () => {
    if (!panel) return;
    panel.hidden = false;
    const guideEl = document.querySelector("[data-ai-guide]");
    if (guideEl) guideEl.hidden = true;
    document.querySelector(".ai-btn")?.classList.remove("is-hint");
    try {
      sessionStorage.setItem(AI_GUIDE_SESSION_KEY, "1");
    } catch (error) {
      /* 忽略 */
    }
    panelOpenHooks.forEach((fn) => {
      try {
        fn();
      } catch (error) {
        /* 单个钩子失败不影响打开 */
      }
    });
    if (input) input.focus();
  };
  const closePanel = () => {
    if (!panel) return;
    panel.hidden = true;
  };
  openBtns.forEach((btn) => btn.addEventListener("click", openPanel));
  if (closeBtn) closeBtn.addEventListener("click", closePanel);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closePanel();
  });

  // ---- 面板缩放：鼠标贴近任意边/角即可拖拽；起始尺寸固定，不跨次记忆 ----
  const resizeHandle = document.querySelector("[data-ai-resize]");
  // 基础尺寸：每次打开面板都按这个开（拖大只在本次打开内有效）
  const AI_SIZE_DEFAULT = { w: 360, h: 520 };
  // 旧版本会把拖出来的尺寸存起来，这里只用来清理，不再读取
  const AI_SIZE_LEGACY_KEY = "gz_ai_size";
  const EDGE = 10; // 命中边距（px）：离边 10px 内就认为是「对着边距」
  const CURSORS = {
    n: "ns-resize", s: "ns-resize", e: "ew-resize", w: "ew-resize",
    nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize",
  };

  const clampSize = (w, h) => {
    const maxW = Math.min(window.innerWidth - 24, 720);
    const maxH = Math.min(window.innerHeight - 112, 720);
    return {
      w: Math.max(300, Math.min(Math.round(w), Math.max(300, maxW))),
      h: Math.max(340, Math.min(Math.round(h), Math.max(340, maxH))),
    };
  };
  const applySize = (w, h) => {
    if (!panel) return;
    const size = clampSize(w, h);
    panel.style.setProperty("--ai-w", size.w + "px");
    panel.style.setProperty("--ai-h", size.h + "px");
    return size;
  };
  // 一旦拖动过上下/左右边，就改用 left/top 定位，否则锚在右下角没法往外拉
  const pinPosition = (left, top) => {
    if (!panel) return;
    panel.style.left = left + "px";
    panel.style.top = top + "px";
    panel.style.right = "auto";
    panel.style.bottom = "auto";
  };
  const unpinPosition = () => {
    if (!panel) return;
    panel.style.left = "";
    panel.style.top = "";
    panel.style.right = "";
    panel.style.bottom = "";
  };
  const clampPosition = (left, top, w, h) => ({
    left: Math.max(8, Math.min(left, window.innerWidth - w - 8)),
    top: Math.max(8, Math.min(top, window.innerHeight - h - 8)),
  });
  /* 8 个实体把手：比「算鼠标到边的距离」可靠，圆角也不会吃掉命中区。
     inset 让角上的把手落在圆角以内，避免被 overflow:hidden 裁掉。 */
  const EDGE_HANDLES = [
    ["n", "left:14px;right:14px;top:0;height:10px;"],
    ["s", "left:14px;right:14px;bottom:0;height:10px;"],
    ["w", "top:14px;bottom:14px;left:0;width:10px;"],
    ["e", "top:14px;bottom:14px;right:0;width:10px;"],
    ["nw", "left:0;top:0;width:16px;height:16px;"],
    ["ne", "right:0;top:0;width:16px;height:16px;"],
    ["sw", "left:0;bottom:0;width:16px;height:16px;"],
    ["se", "right:0;bottom:0;width:16px;height:16px;"],
  ];

  /* 每次打开面板都回到基础尺寸：上一轮拖多大都不复用，
     起始大小永远等于 AI_SIZE_DEFAULT，位置也回到右下角锚点。
     打开后仍然可以拖四边放大（本次打开内有效），双击四边/角可还原。 */
  panelOpenHooks.push(() => {
    applySize(AI_SIZE_DEFAULT.w, AI_SIZE_DEFAULT.h);
    unpinPosition();
  });
  try {
    // 清掉旧版本存下的尺寸，避免它以后被别的代码读到
    localStorage.removeItem(AI_SIZE_LEGACY_KEY);
  } catch (error) {
    /* 隐私模式忽略 */
  }

  if (panel) {
    let drag = null;
    const onMove = (event) => {
      if (!drag) return;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      let left = drag.start.left;
      let top = drag.start.top;
      let w = drag.start.w;
      let h = drag.start.h;
      if (drag.dir.includes("e")) w = drag.start.w + dx;
      if (drag.dir.includes("s")) h = drag.start.h + dy;
      if (drag.dir.includes("w")) w = drag.start.w - dx;
      if (drag.dir.includes("n")) h = drag.start.h - dy;
      // 往右/往下拉时只受视口限制，不靠移动面板来「凑」尺寸
      if (drag.dir.includes("e")) w = Math.min(w, window.innerWidth - drag.start.left - 8);
      if (drag.dir.includes("s")) h = Math.min(h, window.innerHeight - drag.start.top - 8);
      const size = clampSize(w, h);
      // 尺寸被上下限夹住时，位置跟着修正，避免手感漂移
      if (drag.dir.includes("w")) left = drag.start.left + (drag.start.w - size.w);
      if (drag.dir.includes("n")) top = drag.start.top + (drag.start.h - size.h);
      // 只有真的在动左边/上边时才夹位置；拖右/下边要保持位置不动
      if (drag.dir.includes("w") || drag.dir.includes("n")) {
        const pos = clampPosition(left, top, size.w, size.h);
        left = pos.left;
        top = pos.top;
      }
      pinPosition(left, top);
      applySize(size.w, size.h);
    };
    const onUp = () => {
      panel.classList.remove("is-resizing");
      panel.style.cursor = "";
      // 不再记尺寸：下次打开统一回到 AI_SIZE_DEFAULT
      drag = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };

    // 实体把手：贴边 10px / 角 16px，各自带缩放光标与拖拽起点
    const edgeHandles = EDGE_HANDLES.map(([dir, style]) => {
      const node = document.createElement("div");
      node.className = "ai-edge";
      node.dataset.aiEdge = dir;
      node.style.cssText =
        "position:absolute;z-index:6;background:transparent;touch-action:none;cursor:" +
        CURSORS[dir] + ";" + style;
      node.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        event.stopPropagation();
        const rect = panel.getBoundingClientRect();
        drag = {
          dir,
          x: event.clientX,
          y: event.clientY,
          start: { left: rect.left, top: rect.top, w: rect.width, h: rect.height },
        };
        panel.classList.add("is-resizing");
        window.addEventListener("pointermove", onMove);
        window.addEventListener("pointerup", onUp);
      });
      panel.appendChild(node);
      return node;
    });

    // 双击任意边/角：本次打开内被拖大的，立刻还原成基础尺寸
    const resetSize = () => {
      const size = applySize(AI_SIZE_DEFAULT.w, AI_SIZE_DEFAULT.h);
      unpinPosition();
      if (size) toast(T("面板大小已还原"));
    };
    if (resizeHandle) resizeHandle.addEventListener("dblclick", resetSize);
    edgeHandles.forEach((node) => node.addEventListener("dblclick", resetSize));

    /* 首次打开面板时提示「可以拉大」：把四边把手短暂描边 + 冒一个气泡，
       用户一动鼠标或 6 秒后自动消失，只提示一次。 */
    const AI_RESIZE_HINT_KEY = "gz_ai_resize_hint_seen";
    const showResizeHint = () => {
      try {
        if (localStorage.getItem(AI_RESIZE_HINT_KEY)) return;
      } catch (error) {
        /* 存不了就每次都提示，不死循环即可 */
      }
      let tip = panel.querySelector(".ai-resize-tip");
      if (!tip) {
        tip = document.createElement("div");
        tip.className = "ai-resize-tip";
        tip.textContent = isEnglish() ? "Drag any edge to enlarge" : "拖动四边可以放大";
        panel.appendChild(tip);
      }
      edgeHandles.forEach((node) => node.classList.add("is-hinting"));
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        if (tip && tip.parentNode) tip.remove();
        edgeHandles.forEach((node) => node.classList.remove("is-hinting"));
        try {
          localStorage.setItem(AI_RESIZE_HINT_KEY, "1");
        } catch (error) {
          /* 忽略 */
        }
      };
      window.setTimeout(finish, 6000);
      window.addEventListener("pointerdown", finish, { once: true });
    };
    panelOpenHooks.push(showResizeHint);

    // 窗口变小后只需要把尺寸夹回可视范围（位置由 CSS 锚定）
    window.addEventListener("resize", () => {
      const rect = panel.getBoundingClientRect();
      applySize(rect.width, rect.height);
    });
  }

  // ---- AI 小球：拖拽移动 + 左右边缘吸附 ----
  const widget = document.querySelector("[data-ai-widget]");
  const ballBtn = document.querySelector(".ai-btn");
  const AI_BALL_KEY = "gz_ai_ball_pos";
  const BALL_MARGIN = 8;
  const BALL_SNAP = 24;

  if (widget && ballBtn) {
    let ballDrag = null;
    let ballMoved = false;
    let ballSuppressClick = false;

    const ballBox = () => {
      const r = ballBtn.getBoundingClientRect();
      return { w: r.width || 56, h: r.height || 56 };
    };
    const clampBall = (x, y) => {
      const { w, h } = ballBox();
      return {
        x: Math.max(BALL_MARGIN, Math.min(x, window.innerWidth - w - BALL_MARGIN)),
        y: Math.max(BALL_MARGIN, Math.min(y, window.innerHeight - h - BALL_MARGIN)),
      };
    };
    const applyBallPos = (x, y) => {
      widget.style.left = x + "px";
      widget.style.top = y + "px";
      widget.style.right = "auto";
      widget.style.bottom = "auto";
    };

    /* ---- 拖球到景点卡片上松手 = 直接问这个景点（只填不发） ---- */
    const DROP_CARD = ".attr-card, .daily-card, .season-card";
    const isEn = () => document.documentElement.lang === "en" || document.body.dataset.lang === "en";
    let dropTarget = null;

    const clearDropTarget = () => {
      if (dropTarget) {
        dropTarget.classList.remove("is-drop-target");
        dropTarget = null;
      }
    };
    // 小球在指针下方，先把自身让开才能探测到底下是哪张卡片
    const cardAt = (x, y) => {
      const list = document.elementsFromPoint(x, y) || [];
      for (const el of list) {
        if (el === widget || widget.contains(el)) continue;
        const card = el.closest ? el.closest(DROP_CARD) : null;
        if (card) return card;
      }
      return null;
    };
    const cardName = (card) => {
      const h = card.querySelector("h3, h2, .attr-title, .daily-card-title");
      const text = h ? h.textContent.trim() : (card.querySelector("img[alt]") || {}).alt || "";
      return text.trim();
    };
    const askAbout = (name) => {
      const zh = "介绍一下" + name + "，门票多少，适合什么时候去";
      const en = "Tell me about " + name + ": ticket price and the best season to visit.";
      return isEn() ? en : zh;
    };
    /* 面板永远固定在右下角（CSS 锚定），只有小球可以拖。
       这里只做一件事：清掉以前可能残留的内联定位，避免面板跑到别处去。
       用户手动拖拽 / 缩放到别处的面板（pinned）保持原样。 */
    const resetPanelAnchor = () => {
      if (!panel) return;
      panel.style.left = "";
      panel.style.right = "";
      panel.style.top = "";
      panel.style.bottom = "";
    };
    panelOpenHooks.push(resetPanelAnchor);

    const snapBall = () => {
      const r = ballBtn.getBoundingClientRect();
      const { w, h } = ballBox();
      const onLeft = r.left + w / 2 < window.innerWidth / 2;
      const x = onLeft ? BALL_SNAP : window.innerWidth - w - BALL_SNAP;
      const y = Math.max(BALL_MARGIN, Math.min(r.top, window.innerHeight - h - BALL_MARGIN));
      applyBallPos(x, y);
      resetPanelAnchor();
      try {
        localStorage.setItem(AI_BALL_KEY, JSON.stringify({ x: Math.round(x), y: Math.round(y) }));
      } catch (error) {
        /* 忽略 */
      }
    };

    /* 归位：回到页面默认的白板位置（右下角），并清掉记住的坐标 */
    const resetBallPos = () => {
      widget.style.left = "";
      widget.style.top = "";
      widget.style.right = "";
      widget.style.bottom = "";
      try {
        localStorage.removeItem(AI_BALL_KEY);
      } catch (error) {
        /* 忽略 */
      }
    };

    try {
      const saved = JSON.parse(localStorage.getItem(AI_BALL_KEY) || "null");
      if (saved && Number.isFinite(saved.x) && Number.isFinite(saved.y)) {
        const pos = clampBall(saved.x, saved.y);
        applyBallPos(pos.x, pos.y);
        /* 面板此刻多半是隐藏的，等打开时再摆位置 */
      }
    } catch (error) {
      /* 忽略损坏的本地位置 */
    }

    ballBtn.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      if (event.pointerType === "touch") return; // 触屏拖动会和页面滚动冲突
      const r = ballBtn.getBoundingClientRect();
      ballDrag = { dx: event.clientX - r.left, dy: event.clientY - r.top };
      ballMoved = false;
      try {
        ballBtn.setPointerCapture(event.pointerId);
      } catch (error) {
        /* 部分浏览器不支持，忽略 */
      }
    });

    window.addEventListener("pointermove", (event) => {
      if (!ballDrag) return;
      const pos = clampBall(event.clientX - ballDrag.dx, event.clientY - ballDrag.dy);
      const r = ballBtn.getBoundingClientRect();
      if (!ballMoved && Math.abs(pos.x - r.left) + Math.abs(pos.y - r.top) < 4) return;
      ballMoved = true;
      widget.classList.add("is-dragging");
      applyBallPos(pos.x, pos.y);
      const card = cardAt(event.clientX, event.clientY);
      if (card !== dropTarget) {
        clearDropTarget();
        if (card) {
          dropTarget = card;
          card.classList.add("is-drop-target");
        }
      }
    });

    const endBallDrag = () => {
      if (!ballDrag) return;
      const wasMoved = ballMoved;
      ballDrag = null;
      ballMoved = false;
      widget.classList.remove("is-dragging");
      clearDropTarget();
      if (wasMoved) {
        ballSuppressClick = true;
        snapBall();
      }
    };
    // 指针被系统抢走（来电、切窗口）时也要收尾，否则拖拽状态会卡住
    window.addEventListener("pointercancel", endBallDrag);
    window.addEventListener("blur", endBallDrag);

    window.addEventListener("pointerup", () => {
      if (!ballDrag) return;
      const wasMoved = ballMoved;
      ballDrag = null;
      ballMoved = false;
      widget.classList.remove("is-dragging");
      if (wasMoved) {
        ballSuppressClick = true;
        const card = dropTarget;
        const name = card ? cardName(card) : "";
        clearDropTarget();
        if (card && name && openPanel && input) {
          openPanel();
          input.value = askAbout(name);
          resetBallPos(); // 问完归位，不留在页面中间
          if (form) {
            if (typeof form.requestSubmit === "function") form.requestSubmit();
            else form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true }));
          }
        } else {
          snapBall();
        }
      }
    });

    // 拖完松手那一下别顺手把面板点开
    ballBtn.addEventListener(
      "click",
      (event) => {
        if (!ballSuppressClick) return;
        ballSuppressClick = false;
        event.preventDefault();
        event.stopPropagation();
      },
      true
    );

    window.addEventListener("resize", () => {
      if (!widget.style.left) return;
      const r = ballBtn.getBoundingClientRect();
      const pos = clampBall(r.left, r.top);
      applyBallPos(pos.x, pos.y);
    });
  }

  // ---- 首次使用引导 ----
  const guide = document.querySelector("[data-ai-guide]");
  const guideOk = document.querySelector("[data-ai-guide-ok]");
  const guideTry = document.querySelector("[data-ai-guide-try]");
  const helpBtn = document.querySelector("[data-ai-help]");
  const aiBall = document.querySelector(".ai-btn");
  /* 「知道了 / 先试一句」只在本次会话内压住，关掉标签页后会再出现一次 */
  const AI_GUIDE_SESSION_KEY = "gz_ai_guide_muted_session";
  /* 「今天不再提示」：只压当天，第二天会再出来一次 */
  const AI_GUIDE_SNOOZE_KEY = "gz_ai_guide_snooze";
  const todayStamp = () => {
    const d = new Date();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    return d.getFullYear() + "-" + mm + "-" + dd;
  };
  const snoozedToday = () => {
    try {
      return localStorage.getItem(AI_GUIDE_SNOOZE_KEY) === todayStamp();
    } catch (error) {
      return false;
    }
  };
  const showGuide = () => {
    if (guide) guide.hidden = false;
    if (aiBall) aiBall.classList.add("is-hint");
  };
  const hideGuide = (remember) => {
    if (guide) guide.hidden = true;
    if (aiBall) aiBall.classList.remove("is-hint");
    if (remember) {
      try {
        sessionStorage.setItem(AI_GUIDE_SESSION_KEY, "1");
      } catch (error) {
        /* 隐私模式存不了就只是这次关掉 */
      }
    }
  };
  try {
    const mutedThisSession = sessionStorage.getItem(AI_GUIDE_SESSION_KEY) === "1";
    if (!mutedThisSession && !snoozedToday()) window.setTimeout(showGuide, 1200);
  } catch (error) {
    /* 忽略 */
  }
  if (guideOk) guideOk.addEventListener("click", () => hideGuide(true));
  const guideSnooze = document.querySelector("[data-ai-guide-snooze]");
  if (guideSnooze) {
    guideSnooze.addEventListener("click", () => {
      hideGuide(false);
      try {
        localStorage.setItem(AI_GUIDE_SNOOZE_KEY, todayStamp());
      } catch (error) {
        /* 存不了就只是这次关掉 */
      }
    });
  }
  if (guideTry) {
    guideTry.addEventListener("click", () => {
      hideGuide(true);
      openPanel();
      if (input) input.focus();
    });
  }
  if (helpBtn) helpBtn.addEventListener("click", showGuide);

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const sessionId = (() => {
    let value = localStorage.getItem("gz_ai_sid");
    if (!value) {
      value = "s-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
      localStorage.setItem("gz_ai_sid", value);
    }
    return value;
  })();

  const addMsg = (text, who) => {
    if (!messages) return;
    const div = document.createElement("div");
    div.className = "ai-msg " + (who === "user" ? "ai-msg-user" : "ai-msg-bot");
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  };

  const addLinks = (links) => {
    if (!messages || !links || !links.length) return;
    const wrap = document.createElement("div");
    wrap.className = "ai-links";
    links.forEach((link) => {
      const anchor = document.createElement("a");
      anchor.className = "ai-link";
      anchor.href = link.url;
      anchor.textContent = link.name;
      wrap.appendChild(anchor);
    });
    messages.appendChild(wrap);
    messages.scrollTop = messages.scrollHeight;
  };

  const isEnglish = () => document.documentElement.lang === "en" || document.body.dataset.lang === "en";

  const addProgress = () => {
    if (!messages) return { stop: () => {} };
    /* 注意：这几步是定时展示的处理阶段，不是真实的实时工具调用，
       所以文案只说「在处理什么」，不说「正在查地图/比价」这类具体动作，避免误导。 */
    const steps = isEnglish()
      ? ["Understanding your question", "Looking things up", "Writing the answer"]
      : ["理解你的问题", "检索资料", "组织回答"];
    const wrap = document.createElement("div");
    wrap.className = "ai-msg ai-msg-bot ai-msg-thinking ai-progress";
    wrap.setAttribute("role", "status");
    const items = steps.map((step) => {
      const item = document.createElement("span");
      item.className = "ai-progress-step";
      item.textContent = step;
      wrap.appendChild(item);
      return item;
    });
    messages.appendChild(wrap);
    let current = 0;
    const paint = () => {
      items.forEach((item, index) => {
        item.classList.toggle("is-done", index < current);
        item.classList.toggle("is-active", index === current);
      });
      messages.scrollTop = messages.scrollHeight;
    };
    paint();
    const timer = window.setInterval(() => {
      current += 1;
      paint();
      if (current === items.length - 1) window.clearInterval(timer);
    }, 550);
    return { stop: () => { window.clearInterval(timer); wrap.remove(); } };
  };

  const addFailureChoices = (retry, simpler, alternativeLabel) => {
    if (!messages) return;
    const labels = isEnglish() ? ["Try again", "Ask a simpler question", "Plan it yourself"] : ["再试一次", "换个简单问题", "打开行程页自己排"];
    if (alternativeLabel) labels[1] = alternativeLabel;
    const actions = [retry, simpler, () => { window.location.href = "/itinerary"; }];
    const wrap = document.createElement("div");
    wrap.className = "ai-failure-actions";
    labels.forEach((label, index) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "ai-failure-action";
      button.textContent = label;
      button.addEventListener("click", () => { button.disabled = true; actions[index](); });
      wrap.appendChild(button);
    });
    messages.appendChild(wrap);
    messages.scrollTop = messages.scrollHeight;
  };
  window.aiProgress = { addProgress, addFailureChoices };

  let busy = false;

  /* 把一次提问跑完，并返回 {ok, data}：供快捷指令在 AI 失败时决定要不要降级本地方案 */
  const sendMessageCore = async (text, options) => {
    if (!text) return { ok: false, error: "empty" };
    if (busy) return { ok: false, error: "busy" };
    const echo = !(options && options.echo === false);
    busy = true;
    if (echo) addMsg(text, "user");
    if (input) input.value = "";

    const progress = addProgress();
    const context = typeof window.__aiContext === "function" ? window.__aiContext() : null;

    try {
      const response = await fetch("/api/assistant", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken },
        body: JSON.stringify({ message: text, session_id: sessionId, context: context }),
      });
      const body = await response.json();
      progress.stop();
      if (!response.ok || !body.ok) {
        const err = new Error((body && body.error && body.error.message) || "服务暂时不可用");
        err.payload = body;
        throw err;
      }
      const data = body.data || {};
      addMsg(data.reply, "bot");
      addLinks(data.links);
      const action = data.action;
      if (action && action.type === "navigate" && typeof action.url === "string" && action.url.startsWith("/")) {
        addMsg(isEnglish() ? "Taking you there…" : "正在带你去…", "bot");
        setTimeout(() => {
          window.location.href = action.url;
        }, 650);
      }
      return { ok: true, data };
    } catch (error) {
      progress.stop();
      addMsg(isEnglish() ? "The service is unavailable. Please try again later." : "服务暂时不可用，请稍后再试。", "bot");
      addFailureChoices(
        () => sendMessage(text),
        () => sendMessage(isEnglish() ? "What are two easy places to visit in Guizhou?" : "推荐两个轻松好玩的贵州景点")
      );
      return { ok: false, error };
    } finally {
      busy = false;
    }
  };

  const sendMessage = async (text, options) => {
    const result = await sendMessageCore(text, options);
    return result;
  };

  /* 快捷指令用：先问 AI，失败再走本地方案 */
  window.aiSend = (text, options) => sendMessageCore(text, options);

  document.querySelectorAll("[data-ai-suggest]").forEach((btn) => {
    btn.addEventListener("click", () => sendMessage(btn.dataset.aiSuggest));
  });

  if (form) {
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      sendMessage(((input && input.value) || "").trim());
    });
  }

  const carousel = document.querySelector("[data-carousel]");
  if (carousel) {
    let slides = Array.from(carousel.querySelectorAll("[data-slide]"));

    // 手机端跳过品牌海报（<640px）
    if (window.matchMedia("(max-width: 640px)").matches) {
      slides.forEach((slide) => {
        if (slide.dataset.poster === "1") slide.remove();
      });
      slides = Array.from(carousel.querySelectorAll("[data-slide]"));
    }

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let index = 0;
    let timer = null;

    // 懒加载：仅在幻灯片成为当前或下一张时设置背景图
    const loadSlide = (slide) => {
      if (slide && slide.dataset.bg) {
        slide.style.backgroundImage = "url('" + slide.dataset.bg + "')";
        delete slide.dataset.bg;
      }
    };

    const render = (i) => {
      index = (i + slides.length) % slides.length;
      loadSlide(slides[index]);
      loadSlide(slides[(index + 1) % slides.length]);
      slides.forEach((slide, n) => slide.classList.toggle("is-active", n === index));
      carousel.classList.toggle("is-poster", slides[index].dataset.poster === "1");
    };

    const restart = () => {
      if (timer) window.clearInterval(timer);
      if (reduceMotion || slides.length < 2) return;
      timer = window.setInterval(() => {
        if (!document.hidden) render(index + 1);
      }, 2000);
    };

    render(0);
    restart();
  }
})();
