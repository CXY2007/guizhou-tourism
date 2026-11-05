(() => {
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const page = document.body.dataset.page || "";
  const toast = (message) => {
    if (window.showToast) window.showToast(message);
    else console.log(message);
  };

  async function api(path, options = {}) {
    const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
    if (csrfToken) headers["X-CSRFToken"] = csrfToken;
    const response = await fetch(path, { ...options, headers });
    let body = null;
    try {
      body = await response.json();
    } catch (error) {
      body = null;
    }
    if (!response.ok || !body || body.ok === false) {
      const message = (body && body.error && body.error.message) || "操作失败";
      throw new Error(message);
    }
    return body.data;
  }

  function goLogin() {
    const next = encodeURIComponent(window.location.pathname + window.location.search);
    window.location.href = `/auth/login?next=${next}`;
  }

  // ---------------- 详情页 ----------------
  function initDetail() {
    const root = document.querySelector("[data-detail]");
    if (!root) return;
    const attractionId = Number(root.dataset.attractionId);
    const loggedIn = root.dataset.loggedIn === "1";

    const favoriteBtn = document.querySelector("[data-favorite]");
    const avgEl = document.querySelector("[data-avg]");
    const countEl = document.querySelector("[data-count]");
    const stars = Array.from(document.querySelectorAll("[data-stars] .star"));
    const hint = document.querySelector("[data-rating-hint]");
    let currentRating = 0;

    const paintStars = (value) => {
      stars.forEach((star) => {
        star.classList.toggle("is-active", Number(star.dataset.value) <= value);
      });
    };

    if (favoriteBtn && loggedIn) {
      api(`/api/favorites/${attractionId}/status`)
        .then((data) => {
          favoriteBtn.dataset.favorited = data.favorited ? "1" : "0";
          favoriteBtn.textContent = data.favorited ? "已收藏" : "收藏";
          favoriteBtn.classList.toggle("is-active", data.favorited);
        })
        .catch(() => {});
    }

    if (favoriteBtn) {
      favoriteBtn.addEventListener("click", async () => {
        if (!loggedIn) return goLogin();
        try {
          const data = await api(`/api/favorites/${attractionId}`, { method: "POST" });
          favoriteBtn.dataset.favorited = data.favorited ? "1" : "0";
          favoriteBtn.textContent = data.favorited ? "已收藏" : "收藏";
          favoriteBtn.classList.toggle("is-active", data.favorited);
          toast(data.favorited ? "已加入收藏" : "已取消收藏");
        } catch (error) {
          toast(error.message);
        }
      });
    }

    api(`/api/ratings/${attractionId}`)
      .then((data) => {
        currentRating = data.user_rating || 0;
        paintStars(currentRating);
        if (avgEl) avgEl.textContent = Number(data.avg_rating).toFixed(1);
        if (countEl) countEl.textContent = data.rating_count;
        if (hint && currentRating) hint.textContent = `你已打 ${currentRating} 星，可重新选择`;
      })
      .catch(() => {});

    stars.forEach((star) => {
      star.addEventListener("mouseenter", () => paintStars(Number(star.dataset.value)));
      star.addEventListener("mouseleave", () => paintStars(currentRating));
      star.addEventListener("click", async () => {
        if (!loggedIn) return goLogin();
        const value = Number(star.dataset.value);
        try {
          const data = await api("/api/ratings", {
            method: "POST",
            body: JSON.stringify({ attraction_id: attractionId, rating: value }),
          });
          currentRating = value;
          paintStars(value);
          if (avgEl) avgEl.textContent = Number(data.avg_rating).toFixed(1);
          if (countEl) countEl.textContent = data.rating_count;
          if (hint) hint.textContent = `你已打 ${value} 星`;
          if (typeof window.refreshRatingCharts === "function") window.refreshRatingCharts();
          toast(`已评分 ${value} 星`);
        } catch (error) {
          toast(error.message);
        }
      });
    });

    const list = document.querySelector("[data-comment-list]");
    const form = document.querySelector("[data-comment-form]");
    const input = document.querySelector("[data-comment-input]");
    const commentHint = document.querySelector("[data-comment-hint]");
    const fileInput = document.querySelector("[data-comment-file]");
    const mediaBox = document.querySelector("[data-comment-media]");
    const preview = document.querySelector("[data-comment-preview]");
    const clearBtn = document.querySelector("[data-comment-clear]");
    let pendingImage = "";

    const renderComments = (items) => {
      if (!list) return;
      if (!items.length) {
        list.innerHTML = '<p class="comment-empty">还没有评论，来写第一条。</p>';
        return;
      }
      list.innerHTML = "";
      let previousUser = null;

      const buildRow = (item, options) => {
        const opts = options || {};
        const row = document.createElement("div");
        row.className = "comment-item" + (opts.sameUser ? " is-continuation" : "") + (opts.isReply ? " is-reply" : "");
        const avatar = document.createElement("div");
        avatar.className = "comment-avatar" + (opts.sameUser ? " is-ghost" : "") + (opts.isReply ? " is-small" : "");
        if (item.avatar_url) {
          const img = document.createElement("img");
          img.src = item.avatar_url;
          img.alt = item.user || "";
          img.loading = "lazy";
          avatar.appendChild(img);
        } else {
          avatar.textContent = (item.user || "?").slice(0, 1);
        }
        const body = document.createElement("div");
        body.className = "comment-body";
        const text = document.createElement("p");
        text.className = "comment-text";
        text.textContent = item.content;
        const meta = document.createElement("p");
        meta.className = "comment-meta";
        meta.textContent = `${item.user} · ${item.created_at}`;
        if (item.image_url) {
          const img = document.createElement("img");
          img.className = "comment-image zoomable";
          img.src = item.image_url;
          img.alt = T("评论配图");
          img.loading = "lazy";
          const figure = document.createElement("div");
          figure.className = "comment-image-wrap";
          figure.appendChild(img);
          body.appendChild(figure);
        }
        body.append(meta, text);
        row.append(avatar, body);
        // 评论区是"内容"不是"卡片"，直接可见，避免入场动画导致新插入的评论/回复短暂空白
        row.classList.add("is-visible");

        if (!opts.isReply) {
          const replyBtn = document.createElement("button");
          replyBtn.type = "button";
          replyBtn.className = "link-muted";
          replyBtn.textContent = T("回复");
          replyBtn.addEventListener("click", () => startReply(item));
          meta.appendChild(document.createTextNode(" · "));
          meta.appendChild(replyBtn);
        }
        return row;
      };

      items.forEach((item) => {
        const sameUser = previousUser !== null && previousUser === item.user_id;
        previousUser = item.user_id ?? null;
        const row = buildRow(item, { sameUser });
        const replies = item.replies || [];
        if (replies.length) {
          const wrap = document.createElement("div");
          wrap.className = "comment-replies";
          replies.forEach((reply) => wrap.appendChild(buildRow(reply, { isReply: true })));
          row.querySelector(".comment-body").appendChild(wrap);
        }
        list.appendChild(row);
      });
    };

    // 回复模式
    let replyTo = null;
    const replyChip = document.querySelector("[data-reply-chip]");
    const replyTarget = document.querySelector("[data-reply-target]");
    const replyCancel = document.querySelector("[data-reply-cancel]");
    const startReply = (item) => {
      replyTo = item;
      if (replyTarget) replyTarget.textContent = T("回复 @{name}", { name: item.user });
      if (replyChip) replyChip.hidden = false;
      if (input) input.focus();
    };
    const clearReply = () => {
      replyTo = null;
      if (replyChip) replyChip.hidden = true;
    };
    if (replyCancel) replyCancel.addEventListener("click", clearReply);

    const resetMedia = () => {
      pendingImage = "";
      if (fileInput) fileInput.value = "";
      if (preview) preview.removeAttribute("src");
      if (mediaBox) mediaBox.hidden = true;
    };

    if (fileInput) {
      fileInput.addEventListener("change", () => {
        const file = fileInput.files && fileInput.files[0];
        if (!file) return;
        if (file.size > 4 * 1024 * 1024) {
          if (commentHint) commentHint.textContent = "图片不能超过 4MB";
          fileInput.value = "";
          return;
        }
        if (commentHint) commentHint.textContent = "";
        const reader = new FileReader();
        reader.onload = () => {
          if (preview) preview.src = reader.result;
          if (mediaBox) mediaBox.hidden = false;
        };
        reader.readAsDataURL(file);
      });
    }

    if (clearBtn) clearBtn.addEventListener("click", resetMedia);

    const uploadImage = async () => {
      const file = fileInput && fileInput.files && fileInput.files[0];
      if (!file) return "";
      const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/comments/upload", {
        method: "POST",
        headers: { "X-CSRFToken": token },
        body,
      });
      const payload = await response.json().catch(() => null);
      if (!response.ok || !payload || payload.ok === false) {
        throw new Error((payload && payload.error && payload.error.message) || "图片上传失败");
      }
      return payload.data.url;
    };

    const loadComments = () => {
      api(`/api/comments?attraction_id=${attractionId}`)
        .then(renderComments)
        .catch(() => {});
    };
    loadComments();

    if (form) {
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const content = (input?.value || "").trim();
        const hasFile = Boolean(fileInput && fileInput.files && fileInput.files[0]);
        if ((!content && !hasFile) || content.length > 500) {
          if (commentHint) commentHint.textContent = "评论需为 1–500 字（或直接发表一张图片）";
          return;
        }
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) submitBtn.disabled = true;
        try {
          if (hasFile) {
            if (commentHint) commentHint.textContent = "图片上传中…";
            pendingImage = await uploadImage();
          }
          const created = await api("/api/comments", {
            method: "POST",
            body: JSON.stringify({
              attraction_id: attractionId,
              content,
              image_url: pendingImage || undefined,
              parent_id: replyTo ? replyTo.id : undefined,
            }),
          });
          if (input) input.value = "";
          resetMedia();
          clearReply();
          const autoPassed = Boolean(created && created.auto_passed);
          if (commentHint) {
            commentHint.textContent = autoPassed ? "AI 审核通过，评论已发布" : "已提交，等待管理员审核";
          }
          toast(autoPassed ? "评论已发布" : "评论已提交，等待审核");
          loadComments();
        } catch (error) {
          if (commentHint) commentHint.textContent = error.message;
        } finally {
          if (submitBtn) submitBtn.disabled = false;
        }
      });
    }
  }

  // ---------------- 个人中心 ----------------
  function initProfile() {
    const tabs = Array.from(document.querySelectorAll("[data-tab]"));
    const panes = Array.from(document.querySelectorAll("[data-pane]"));
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const key = tab.dataset.tab;
        tabs.forEach((item) => item.classList.toggle("is-active", item === tab));
        panes.forEach((pane) => {
          pane.hidden = pane.dataset.pane !== key;
        });
      });
    });

    document.querySelectorAll("[data-remove-fav]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.removeFav;
        try {
          await api(`/api/favorites/${id}`, { method: "POST" });
          document.querySelector(`[data-fav-item="${id}"]`)?.remove();
          toast("已取消收藏");
        } catch (error) {
          toast(error.message);
        }
      });
    });

    document.querySelectorAll("[data-delete-comment]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.deleteComment;
        try {
          await api(`/api/comments/${id}`, { method: "DELETE" });
          document.querySelector(`[data-comment-row="${id}"]`)?.remove();
          toast("评论已删除");
        } catch (error) {
          toast(error.message);
        }
      });
    });

    document.querySelectorAll("[data-delete-itinerary]").forEach((button) => {
      button.addEventListener("click", async (event) => {
        event.preventDefault();
        const id = button.dataset.deleteItinerary;
        if (!window.confirm(T("确定删除这条行程？"))) return;
        try {
          await api(`/api/itineraries/${id}`, { method: "DELETE" });
          const onSavedPage = /^\/itinerary\/\d+/.test(window.location.pathname);
          if (onSavedPage) {
            window.location.href = "/profile";
            return;
          }
          const row = document.querySelector(`[data-itinerary-row="${id}"]`);
          if (row) row.remove();
          toast("行程已删除");
          const list = document.querySelector(".itin-list");
          if (list && !list.querySelector("[data-itinerary-row]")) {
            list.outerHTML = '<p class="pane-empty">还没有保存的行程。<a href="/itinerary">去规划一条 →</a></p>';
          }
        } catch (error) {
          toast(error.message);
        }
      });
    });

    // ---------------- 头像上传 ----------------
    const avatarInput = document.querySelector("[data-avatar-input]");
    const avatarUpload = document.querySelector("[data-avatar-upload]");
    const avatarRemove = document.querySelector("[data-avatar-remove]");
    const avatarFeedback = document.querySelector("[data-avatar-feedback]");
    const avatarPreview = document.querySelector("[data-avatar-preview]");
    const headerAvatar = document.querySelector(".profile-head .profile-avatar");

    function renderAvatar(url, initial) {
      const targets = [avatarPreview, headerAvatar].filter(Boolean);
      targets.forEach((box) => {
        if (url) {
          box.innerHTML = `<img src="${url}" alt="头像">`;
        } else {
          box.textContent = initial || "";
        }
      });
    }

    if (avatarInput && avatarUpload) {
      avatarInput.addEventListener("change", () => {
        const file = avatarInput.files && avatarInput.files[0];
        avatarUpload.disabled = !file;
        if (avatarFeedback) avatarFeedback.textContent = "";
        if (file && avatarPreview) {
          const reader = new FileReader();
          reader.onload = () => {
            avatarPreview.innerHTML = `<img src="${reader.result}" alt="预览">`;
          };
          reader.readAsDataURL(file);
        }
      });

      avatarUpload.addEventListener("click", async () => {
        const file = avatarInput.files && avatarInput.files[0];
        if (!file) return;
        const token = document.querySelector('meta[name="csrf-token"]')?.content || "";
        const body = new FormData();
        body.append("file", file);
        avatarUpload.disabled = true;
        try {
          const response = await fetch("/api/profile/avatar", {
            method: "POST",
            headers: { "X-CSRFToken": token },
            body,
          });
          const payload = await response.json().catch(() => null);
          if (!response.ok || !payload || payload.ok === false) {
            throw new Error((payload && payload.error && payload.error.message) || "上传失败");
          }
          renderAvatar(payload.data.avatar_url);
          if (avatarFeedback) avatarFeedback.textContent = "头像已更新";
          toast("头像已更新");
          avatarInput.value = "";
        } catch (error) {
          if (avatarFeedback) avatarFeedback.textContent = error.message;
          avatarUpload.disabled = false;
        }
      });
    }

    if (avatarRemove) {
      avatarRemove.addEventListener("click", async () => {
        try {
          await fetch("/api/profile/avatar", {
            method: "DELETE",
            headers: { "X-CSRFToken": document.querySelector('meta[name="csrf-token"]')?.content || "" },
          });
          window.location.reload();
        } catch (error) {
          if (avatarFeedback) avatarFeedback.textContent = error.message;
        }
      });
    }

    const nicknameInput = document.querySelector("[data-nickname-input]");
    const nicknameBtn = document.querySelector("[data-save-nickname]");
    const nicknameFeedback = document.querySelector("[data-nickname-feedback]");
    if (nicknameBtn && nicknameInput) {
      nicknameBtn.addEventListener("click", async () => {
        const nickname = nicknameInput.value.trim();
        if (!nickname) {
          if (nicknameFeedback) nicknameFeedback.textContent = "显示名不能为空";
          return;
        }
        nicknameBtn.disabled = true;
        try {
          const data = await api("/api/profile", { method: "PUT", body: JSON.stringify({ nickname }) });
          if (nicknameFeedback) nicknameFeedback.textContent = "已保存";
          toast(T("显示名已更新"));
          const nameEl = document.querySelector(".profile-name");
          if (nameEl) nameEl.textContent = data.display_name || nickname;
        } catch (error) {
          if (nicknameFeedback) nicknameFeedback.textContent = error.message;
        } finally {
          nicknameBtn.disabled = false;
        }
      });
    }

    const passwordForm = document.querySelector("[data-password-form]");
    const passwordFeedback = document.querySelector("[data-password-feedback]");
    if (passwordForm) {
      passwordForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const oldPassword = passwordForm.querySelector('[name="old_password"]').value;
        const newPassword = passwordForm.querySelector('[name="new_password"]').value;
        const confirm = passwordForm.querySelector('[name="confirm_password"]').value;
        if (newPassword !== confirm) {
          if (passwordFeedback) passwordFeedback.textContent = "两次新密码不一致";
          return;
        }
        try {
          await api("/api/profile/password", {
            method: "POST",
            body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
          });
          passwordForm.reset();
          if (passwordFeedback) passwordFeedback.textContent = "密码已修改";
          toast("密码已修改");
        } catch (error) {
          if (passwordFeedback) passwordFeedback.textContent = error.message;
        }
      });
    }
  }

  // ---------------- 管理端评论审核 ----------------
  function initAdmin() {
    const list = document.querySelector("[data-admin-list]");
    const count = document.querySelector("[data-admin-count]");
    const filters = Array.from(document.querySelectorAll("[data-admin-filters] [data-status]"));
    if (!list) return;
    let status = "pending";

    const render = (items) => {
      if (count) count.textContent = `共 ${items.length} 条`;
      if (!items.length) {
        list.innerHTML = '<p class="pane-empty">这个状态下没有评论。</p>';
        return;
      }
      list.innerHTML = "";
      items.forEach((item) => {
        const card = document.createElement("article");
        card.className = "admin-item";
        const head = document.createElement("div");
        head.className = "admin-item-head";
        if (item.avatar_url) {
          const avatarImg = document.createElement("img");
          avatarImg.className = "admin-avatar";
          avatarImg.src = item.avatar_url;
          avatarImg.alt = item.user || "";
          avatarImg.loading = "lazy";
          head.appendChild(avatarImg);
        }
        const who = document.createElement("span");
        who.className = "admin-user";
        who.textContent = `${item.user} · ${item.attraction.name}`;
        const time = document.createElement("span");
        time.className = "admin-time";
        time.textContent = item.created_at;
        head.append(who, time);
        const reviewTag = document.createElement("span");
        reviewTag.className = "review-tag";
        if (item.status === "pending") {
          reviewTag.classList.add("is-flag");
          reviewTag.textContent = item.ai_reason ? `AI 存疑：${item.ai_reason}` : "待人工审核";
        } else if (item.review_by === "ai") {
          reviewTag.classList.add("is-ai");
          reviewTag.textContent = "AI 直通";
        } else if (item.review_by === "human") {
          reviewTag.classList.add("is-human");
          reviewTag.textContent = "人工审核";
        } else {
          reviewTag.classList.add("is-seed");
          reviewTag.textContent = "预置数据";
        }
        head.appendChild(reviewTag);

        const text = document.createElement("p");
        text.className = "admin-text";
        text.textContent = item.content;
        if (item.image_url) {
          const thumb = document.createElement("img");
          thumb.className = "admin-comment-image zoomable";
          thumb.src = item.image_url;
          thumb.alt = "评论配图";
          thumb.loading = "lazy";
          card.append(thumb);
        }
        const actions = document.createElement("div");
        actions.className = "admin-actions";

        const makeButton = (label, className, handler) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = className;
          button.textContent = label;
          button.addEventListener("click", handler);
          return button;
        };

        if (item.status === "pending") {
          actions.append(
            makeButton("通过", "btn btn-primary btn-sm", async () => {
              await api(`/api/admin/comments/${item.id}/approve`, {
                method: "POST",
                body: JSON.stringify({ action: "approve" }),
              });
              toast("已通过");
              load();
            }),
            makeButton("拒绝", "btn btn-outline btn-sm", async () => {
              await api(`/api/admin/comments/${item.id}/approve`, {
                method: "POST",
                body: JSON.stringify({ action: "reject" }),
              });
              toast("已拒绝");
              load();
            })
          );
        }
        actions.append(
          makeButton("删除", "link-danger", async () => {
            await api(`/api/admin/comments/${item.id}`, { method: "DELETE" });
            toast("已删除");
            load();
          })
        );

        card.append(head, text, actions);
        list.appendChild(card);
      });
    };

    const load = async () => {
      try {
        const items = await api(`/api/admin/comments?status=${status}`);
        render(items);
      } catch (error) {
        list.innerHTML = `<p class="pane-empty">${error.message}</p>`;
      }
    };

    filters.forEach((button) => {
      button.addEventListener("click", () => {
        status = button.dataset.status;
        filters.forEach((item) => item.classList.toggle("is-active", item === button));
        load();
      });
    });

    load();
  }

  if (page === "detail") initDetail();
  if (page === "profile") initProfile();
  if (page === "admin-comments") initAdmin();
})();
