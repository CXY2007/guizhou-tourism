/* 图片灯箱：点景点大图 / 图集缩略图放大，支持左右切换、Esc 关闭、滚轮缩放不误触。 */
(function () {
  "use strict";

  var SELECTOR = "img.zoomable";
  var overlay = null;
  var imageEl = null;
  var captionEl = null;
  var counterEl = null;
  var group = [];
  var index = 0;

  function collect() {
    // 封面图和图集第一张常常是同一张，按地址去重，避免点下一张原地不动
    var seen = {};
    group = Array.prototype.slice.call(document.querySelectorAll(SELECTOR)).filter(function (img) {
      var key = img.getAttribute("src") || "";
      if (!key || seen[key]) return false;
      seen[key] = true;
      return true;
    });
  }

  function build() {
    overlay = document.createElement("div");
    overlay.className = "lightbox";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.hidden = true;

    var close = document.createElement("button");
    close.className = "lightbox-close";
    close.type = "button";
    close.setAttribute("aria-label", "关闭");
    close.innerHTML = "&times;";
    close.addEventListener("click", hide);

    var prev = document.createElement("button");
    prev.className = "lightbox-nav lightbox-prev";
    prev.type = "button";
    prev.setAttribute("aria-label", "上一张");
    prev.innerHTML = "&#10094;";
    prev.addEventListener("click", function (event) {
      event.stopPropagation();
      step(-1);
    });

    var next = document.createElement("button");
    next.className = "lightbox-nav lightbox-next";
    next.type = "button";
    next.setAttribute("aria-label", "下一张");
    next.innerHTML = "&#10095;";
    next.addEventListener("click", function (event) {
      event.stopPropagation();
      step(1);
    });

    var figure = document.createElement("figure");
    figure.className = "lightbox-figure";
    imageEl = document.createElement("img");
    imageEl.className = "lightbox-image";
    imageEl.alt = "";
    captionEl = document.createElement("figcaption");
    captionEl.className = "lightbox-caption";
    counterEl = document.createElement("span");
    counterEl.className = "lightbox-counter";
    figure.appendChild(imageEl);
    figure.appendChild(captionEl);
    figure.appendChild(counterEl);

    overlay.appendChild(close);
    overlay.appendChild(prev);
    overlay.appendChild(next);
    overlay.appendChild(figure);
    overlay.addEventListener("click", function (event) {
      if (event.target === overlay) hide();
    });

    document.body.appendChild(overlay);
  }

  function render() {
    var source = group[index];
    if (!source) return;
    imageEl.src = source.currentSrc || source.src;
    imageEl.alt = source.alt || "";
    captionEl.textContent = source.alt || "";
    counterEl.textContent = group.length > 1 ? index + 1 + " / " + group.length : "";
    overlay.querySelector(".lightbox-prev").hidden = group.length < 2;
    overlay.querySelector(".lightbox-next").hidden = group.length < 2;
  }

  function step(delta) {
    if (group.length < 2) return;
    index = (index + delta + group.length) % group.length;
    render();
  }

  function show(target) {
    collect();
    index = group.indexOf(target);
    if (index < 0) {
      // 点的是被去重掉的那张（封面与图集首图重复），按地址找回同一张
      var key = target.getAttribute("src") || "";
      index = group.findIndex(function (img) {
        return img.getAttribute("src") === key;
      });
    }
    if (index < 0) return;
    if (!overlay) build();
    render();
    overlay.hidden = false;
    document.body.classList.add("lightbox-open");
  }

  function hide() {
    if (!overlay) return;
    overlay.hidden = true;
    document.body.classList.remove("lightbox-open");
    imageEl.src = "";
  }

  document.addEventListener("click", function (event) {
    var target = event.target;
    if (!(target instanceof HTMLImageElement) || !target.matches(SELECTOR)) return;
    event.preventDefault();
    show(target);
  });

  document.addEventListener("keydown", function (event) {
    if (!overlay || overlay.hidden) return;
    if (event.key === "Escape") hide();
    else if (event.key === "ArrowLeft") step(-1);
    else if (event.key === "ArrowRight") step(1);
  });
})();
