/* 景点大图页：高德地图 + 景点标记 + 周边 POI + 卫星图切换。
 *
 * 设计要点：
 * - 全屏地图，失败时静默降级成一句占位文案，不白屏。
 * - 周边 POI 用高德类型码（050000 餐饮 / 100000 住宿 / 150900 停车场 / 200300 卫生间），
 *   不能传中文标签当 type；也不能带 city（会限制在市辖区，边界景点全部搜不到）。
 * - 卫星图与标准图来回切换，按钮文案跟着换。
 */
(function () {
  "use strict";

  var mount = document.getElementById("full-map");
  if (!mount) return;

  var key = mount.dataset.amapKey;
  var security = mount.dataset.amapSecurity;
  var lng = parseFloat(mount.dataset.lng);
  var lat = parseFloat(mount.dataset.lat);
  var name = mount.dataset.name || "";

  var map = null;
  var poiMarkers = [];
  var activeType = "";
  var isSatellite = false;

  var statusEl = document.querySelector(".map-poi-status");
  var poiButtons = [].slice.call(document.querySelectorAll("[data-poi-type]"));
  var satelliteBtn = document.querySelector("[data-map-satellite]");

  function setStatus(text) {
    if (!statusEl) return;
    statusEl.textContent = text || "";
    statusEl.hidden = !text;
  }

  function fallback() {
    mount.innerHTML = "<p class='map-fallback'>地图暂时不可用</p>";
  }

  function clearPoi() {
    if (map && poiMarkers.length) map.remove(poiMarkers);
    poiMarkers = [];
  }

  /* ---------- 周边 POI ---------- */

  function searchPoi(typeCode, label) {
    if (!map) return setStatus("周边服务暂时不可用");
    if (!window.AMap || !AMap.PlaceSearch) {
      if (window.AMap && typeof AMap.plugin === "function") {
        AMap.plugin(["AMap.PlaceSearch"], function () {
          searchPoi(typeCode, label);
        });
        return;
      }
      return setStatus("周边服务暂时不可用");
    }

    clearPoi();
    setStatus("正在搜索周边" + label + "…");

    try {
      var searcher = new AMap.PlaceSearch({ type: typeCode, pageSize: 20 });
      searcher.searchNearBy(label, [lng, lat], 2000, function (status, result) {
        var empty = status === "no_data" || !result || !result.poiList;
        if (empty) {
          return setStatus(status === "no_data" || !result ? "附近暂无" + label : "周边搜索暂时不可用");
        }
        if (status !== "complete") return setStatus("周边搜索暂时不可用");

        var pois = result.poiList.pois || [];
        if (!pois.length) return setStatus("附近暂无" + label);

        pois.forEach(function (poi) {
          if (!poi.location) return;
          var marker = new AMap.Marker({ position: poi.location, map: map, title: poi.name });
          marker.on("click", function () {
            new AMap.InfoWindow({
              content:
                "<div style='padding:6px'>" +
                (poi.name || label) +
                "<br>距景点 " +
                (poi.distance || "?") +
                " 米</div>",
            }).open(map, poi.location);
          });
          poiMarkers.push(marker);
        });
        activeType = typeCode;
        setStatus("已显示附近" + label + " " + poiMarkers.length + " 处");
      });
    } catch (error) {
      setStatus("周边搜索暂时不可用");
    }
  }

  function bindPoiButtons() {
    poiButtons.forEach(function (btn) {
      btn.onclick = function () {
        var code = btn.dataset.poiType;
        var label = btn.dataset.poiLabel || code;
        if (activeType === code) {
          clearPoi();
          activeType = "";
          setStatus("");
          poiButtons.forEach(function (other) {
            other.classList.remove("is-active");
          });
          return;
        }
        poiButtons.forEach(function (other) {
          other.classList.toggle("is-active", other === btn);
        });
        searchPoi(code, label);
      };
    });
  }

  /* ---------- 卫星图切换 ---------- */

  function toggleSatellite() {
    if (!map) return;
    if (!window.AMap || !AMap.TileLayer || !AMap.TileLayer.Satellite) {
      if (satelliteBtn) {
        satelliteBtn.disabled = true;
        satelliteBtn.textContent = fallbackLabel();
      }
      return;
    }

    isSatellite = !isSatellite;
    if (isSatellite) {
      map.setLayers([new AMap.TileLayer.Satellite()]);
    } else {
      map.setLayers([new AMap.TileLayer()]);
    }
    if (satelliteBtn) {
      satelliteBtn.textContent = isSatellite
        ? satelliteBtn.dataset.labelStd || "切换标准图"
        : satelliteBtn.dataset.labelSat || "切换卫星图";
    }
  }

  function fallbackLabel() {
    return (satelliteBtn && satelliteBtn.dataset.labelUnavailable) || "卫星图不可用";
  }

  /* ---------- 初始化 ---------- */

  function draw() {
    try {
      mount.innerHTML = "";
      map = new AMap.Map(mount, {
        zoom: 14,
        center: [lng, lat],
        viewMode: "2D",
        resizeEnable: true,
      });

      var pin = new AMap.Marker({ position: [lng, lat], title: name, map: map });
      pin.on("click", function () {
        new AMap.InfoWindow({
          content: "<div style='padding:6px'>" + name + "</div>",
        }).open(map, [lng, lat]);
      });

      if (AMap.Scale) map.addControl(new AMap.Scale());
      if (AMap.ToolBar) map.addControl(new AMap.ToolBar({ position: "RT" }));

      bindPoiButtons();
      if (satelliteBtn) satelliteBtn.addEventListener("click", toggleSatellite);
    } catch (error) {
      fallback();
    }
  }

  if (!key || isNaN(lng) || isNaN(lat)) return fallback();

  if (window.AMap && AMap.Map) return draw();

  if (security) window._AMapSecurityConfig = { securityJsCode: security };

  var script = document.createElement("script");
  script.src =
    "https://webapi.amap.com/maps?v=2.0&key=" +
    encodeURIComponent(key) +
    "&plugin=AMap.PlaceSearch,AMap.TileLayer.Satellite";
  script.onload = draw;
  script.onerror = fallback;
  document.head.appendChild(script);
})();
