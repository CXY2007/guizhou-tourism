/* 后台流量页：近 N 天浏览趋势折线（ECharts 本地 vendor）。 */
(function () {
  "use strict";

  var host = document.getElementById("traffic-chart");
  if (!host || !window.echarts) return;

  var series = [];
  try {
    series = JSON.parse(host.getAttribute("data-series") || "[]");
  } catch (e) {
    series = [];
  }
  if (!series.length) {
    host.innerHTML = '<p class="chart-empty">暂无流量数据</p>';
    return;
  }

  var chart = window.echarts.init(host);
  chart.setOption({
    color: ["#1F4E5A", "#C9A227"],
    grid: { left: 44, right: 20, top: 30, bottom: 40 },
    tooltip: { trigger: "axis" },
    legend: { top: 0, right: 0, textStyle: { color: "#0E2A24", fontSize: 11 }, itemWidth: 12, itemHeight: 8 },
    xAxis: {
      type: "category",
      data: series.map(function (item) { return item.date.slice(5); }),
      axisLine: { lineStyle: { color: "#8FA6A0" } },
      axisLabel: { color: "#0E2A24", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: "#0E2A24", fontSize: 10 },
      splitLine: { lineStyle: { color: "rgba(14,42,36,0.08)" } },
    },
    series: [
      {
        name: "浏览",
        type: "line",
        smooth: true,
        symbolSize: 4,
        data: series.map(function (item) { return item.views; }),
        areaStyle: { color: "rgba(31,78,90,0.12)" },
      },
      {
        name: "访客",
        type: "line",
        smooth: true,
        symbolSize: 4,
        data: series.map(function (item) { return item.visitors; }),
        lineStyle: { width: 1.5, type: "dashed" },
      },
    ],
  });

  window.addEventListener("resize", function () { chart.resize(); });
})();
