(() => {
  const root = document.querySelector("[data-orders]");
  if (!root) return;

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const msgEl = root.querySelector("[data-msg]");

  root.querySelectorAll("[data-pay]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      if (msgEl) msgEl.textContent = "支付中…";
      try {
        const res = await fetch(`/api/bookings/${encodeURIComponent(btn.dataset.pay)}/pay`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        });
        let body = null;
        try {
          body = await res.json();
        } catch (e) {
          body = null;
        }
        if (!res.ok || !body || body.ok === false) {
          throw new Error((body && body.error && body.error.message) || "支付失败");
        }
        window.location.reload();
      } catch (e) {
        btn.disabled = false;
        if (msgEl) {
          msgEl.textContent = e.message;
          msgEl.classList.add("is-error");
        }
      }
    });
  });

  root.querySelectorAll("[data-cancel]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      if (msgEl) msgEl.textContent = "取消中…";
      try {
        const res = await fetch(`/api/bookings/${encodeURIComponent(btn.dataset.cancel)}/cancel`, {
          method: "POST",
          headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        });
        let body = null;
        try {
          body = await res.json();
        } catch (e) {
          body = null;
        }
        if (!res.ok || !body || body.ok === false) {
          throw new Error((body && body.error && body.error.message) || "取消失败");
        }
        window.location.reload();
      } catch (e) {
        btn.disabled = false;
        if (msgEl) {
          msgEl.textContent = e.message;
          msgEl.classList.add("is-error");
        }
      }
    });
  });
})();
