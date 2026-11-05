(() => {
  const root = document.querySelector("[data-booking]");
  if (!root) return;

  const csrf = document.querySelector('meta[name="csrf-token"]')?.content || "";
  const form = root.querySelector("[data-form]");
  const dateInput = root.querySelector("[data-date]");
  const qtyInput = root.querySelector("[data-qty]");
  const totalEl = root.querySelector("[data-total]");
  const submitBtn = root.querySelector("[data-submit]");
  const msgEl = root.querySelector("[data-msg]");
  const price = Number(root.dataset.price) || 0;

  const pad = (n) => String(n).padStart(2, "0");
  const now = new Date();
  dateInput.min = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;

  const quantity = () => Math.min(10, Math.max(1, parseInt(qtyInput.value, 10) || 1));

  function updateTotal() {
    if (price <= 0) {
      totalEl.textContent = "免费";
      return;
    }
    const total = price * quantity();
    totalEl.textContent = `¥${Number.isInteger(total) ? total : total.toFixed(2)}`;
  }
  qtyInput.addEventListener("input", updateTotal);
  updateTotal();

  const setMsg = (text, isError) => {
    msgEl.textContent = text || "";
    msgEl.classList.toggle("is-error", Boolean(isError));
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!dateInput.value) {
      setMsg("请选择游玩日期", true);
      return;
    }
    if (dateInput.value < dateInput.min) {
      setMsg("游玩日期不能早于今天", true);
      return;
    }
    submitBtn.disabled = true;
    setMsg("提交中…");
    try {
      const res = await fetch("/api/bookings", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
        body: JSON.stringify({
          attraction_id: Number(root.dataset.attractionId),
          visit_date: dateInput.value,
          quantity: quantity(),
        }),
      });
      let body = null;
      try {
        body = await res.json();
      } catch (e) {
        body = null;
      }
      if (!res.ok || !body || body.ok === false) {
        throw new Error((body && body.error && body.error.message) || "预订失败，请稍后再试");
      }
      window.location.href = "/orders";
    } catch (e) {
      setMsg(e.message, true);
      submitBtn.disabled = false;
    }
  });
})();
