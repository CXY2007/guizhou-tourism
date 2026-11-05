/* Detail page extras: weather card, AMap map, rating charts. All degrade silently. */
(function () {
  "use strict";

  var COLORS = {
    ink: "#0E2A24",
    teal: "#1F4E5A",
    cinnabar: "#B83A2D",
    gold: "#C9A227",
    mist: "#8FA6A0",
  };

  function esc(v) {
    var d = document.createElement("div");
    d.textContent = v == null ? "" : String(v);
    return d.innerHTML;
  }

  function getJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (r) {
      if (!r.ok) throw new Error("http " + r.status);
      return r.json();
    });
  }

  /* ---------- Weather ---------- */
  function initWeather() {
    var box = document.querySelector("[data-weather]");
    if (!box) return;
    var id = box.getAttribute("data-attraction-id");

    function fail() {
      box.innerHTML = '<p class="weather-loading">' + T("天气暂不可用") + "</p>";
    }

    getJSON("/api/weather/" + encodeURIComponent(id))
      .then(function (res) {
        var d = res && res.ok && res.data;
        if (!d || !d.live) return fail();
        var live = d.live;
        var isEn = document.documentElement.lang === "en";
        var wind = isEn
          ? esc(T(live.winddirection)) + " " + esc(live.windpower)
          : esc(live.winddirection) + " " + esc(live.windpower) + " 级";
        var html = '<div class="weather-head"><div>' +
          '<p class="side-label">' + T("天气") + " · " + esc(d.city) + "</p>" +
          '<p class="weather-now"><span class="weather-temp">' + esc(live.temperature) + "°</span> " +
          '<span class="weather-desc">' + esc(T(live.weather)) + "</span></p>" +
          "</div>" +
          '<p class="weather-meta">' + T("湿度") + " " + esc(live.humidity) + "% · " +
          wind + "</p></div>";
        var fc = d.forecast || [];
        if (fc.length) {
          html += '<ul class="weather-forecast">';
          fc.slice(0, 3).forEach(function (f) {
            html += "<li><span class=\"wf-date\">" + esc(String(f.date || "").slice(5)) +
              (f.week ? " " + esc(f.week) : "") + "</span>" +
              '<span class="wf-weather">' + esc(T(f.dayweather)) + " / " + esc(T(f.nightweather)) + "</span>" +
              '<span class="wf-temp">' + esc(f.nighttemp) + "~" + esc(f.daytemp) + "°</span></li>";
          });
          html += "</ul>";
        }
        if (d.advice) html += '<p class="weather-advice">' + esc(d.advice) + "</p>";
        box.innerHTML = html;
      })
      .catch(fail);
  }

  /* ---------- Map ---------- */
  function initMap() {
    var el = document.getElementById("detail-map");
    if (!el) return;
    var key = el.getAttribute("data-amap-key");
    var sec = el.getAttribute("data-amap-security");
    var lng = parseFloat(el.getAttribute("data-lng"));
    var lat = parseFloat(el.getAttribute("data-lat"));

    function fail() {
      el.innerHTML = '<p class="map-fallback">地图暂不可用</p>';
    }
    if (!key || isNaN(lng) || isNaN(lat)) return fail();

    function draw() {
      try {
        el.innerHTML = "";
        var map = new window.AMap.Map(el, { zoom: 13, center: [lng, lat] });
        var marker = new window.AMap.Marker({
          position: [lng, lat],
          title: el.getAttribute("data-name") || "",
        });
        map.add(marker);
      } catch (e) {
        fail();
      }
    }

    if (window.AMap && window.AMap.Map) return draw();
    if (sec) window._AMapSecurityConfig = { securityJsCode: sec };
    var s = document.createElement("script");
    s.src = "https://webapi.amap.com/maps?v=2.0&key=" + encodeURIComponent(key);
    s.async = true;
    s.onload = draw;
    s.onerror = fail;
    document.head.appendChild(s);
  }

  /* ---------- Charts ---------- */
  function initCharts() {
    var wrap = document.querySelector("[data-rating-charts]");
    if (!wrap) return;
    var id = wrap.getAttribute("data-attraction-id");
    var pieEl = wrap.querySelector('[data-chart="pie"]');
    var lineEl = wrap.querySelector('[data-chart="line"]');

    function empty(el) {
      el.innerHTML = '<p class="chart-empty">暂无评分数据</p>';
    }
    function emptyAll() {
      empty(pieEl);
      empty(lineEl);
    }

    if (!window.echarts) return emptyAll();

    var charts = [];

    function render(d) {
        // 重绘前先销毁旧实例，否则 echarts 会叠加在同一个容器上
        charts.forEach(function (c) { try { c.dispose(); } catch (e) { /* 忽略 */ } });
        charts = [];
        if (!d) return emptyAll();

        var pie = (d.pie || []).filter(function (p) { return p.count > 0; });
        if (!pie.length || !d.total) {
          empty(pieEl);
        } else {
          var pc = echarts.init(pieEl);
          pc.setOption({
            color: [COLORS.cinnabar, COLORS.gold, COLORS.mist, COLORS.teal, COLORS.ink],
            tooltip: { trigger: "item", formatter: "{b}: {c} ({d}%)" },
            legend: { bottom: 0, textStyle: { color: COLORS.ink, fontSize: 11 }, itemWidth: 10, itemHeight: 10 },
            series: [{
              type: "pie",
              radius: ["42%", "68%"],
              center: ["50%", "44%"],
              label: { show: false },
              data: pie.map(function (p) { return { name: p.rating + "★", value: p.count }; }),
            }],
          });
          charts.push(pc);
        }

        var weeks = d.weeks || [];
        var avgs = d.averages || [];
        var hasLine = avgs.some(function (v) { return v != null && v > 0; });
        if (!weeks.length || !hasLine) {
          empty(lineEl);
        } else {
          var lc = echarts.init(lineEl);
          lc.setOption({
            color: [COLORS.teal],
            grid: { left: 32, right: 16, top: 16, bottom: 28 },
            tooltip: { trigger: "axis" },
            xAxis: {
              type: "category",
              data: weeks,
              axisLine: { lineStyle: { color: COLORS.mist } },
              axisLabel: { color: COLORS.ink, fontSize: 10 },
            },
            yAxis: {
              type: "value",
              min: 0,
              max: 5,
              interval: 1,
              axisLabel: { color: COLORS.ink, fontSize: 10 },
              splitLine: { lineStyle: { color: "rgba(14,42,36,0.08)" } },
            },
            series: [{
              type: "line",
              data: avgs,
              smooth: true,
              connectNulls: true,
              symbolSize: 6,
              lineStyle: { width: 2 },
              areaStyle: { color: "rgba(31,78,90,0.12)" },
            }],
          });
          charts.push(lc);
        }

    }

    function load() {
      return getJSON("/api/attractions/" + encodeURIComponent(id) + "/stats")
        .then(function (res) { render(res && res.ok && res.data); })
        .catch(function () { render(null); });
    }

    window.addEventListener("resize", function () {
      charts.forEach(function (c) { c.resize(); });
    });

    // 打分后由 interactions.js 调用，立刻重画扇形图与折线图
    window.refreshRatingCharts = load;

    load();
  }

  function init() {
    initWeather();
    initMap();
    initCharts();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
