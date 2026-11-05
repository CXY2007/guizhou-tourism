/* AI 助手语音输入：识别结果只写入输入框，不自动发送。 */
(function () {
  "use strict";
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return; // 不支持：不创建按钮

  function init() {
    var form = document.querySelector("[data-ai-form]");
    if (!form || form.querySelector("[data-ai-voice]")) return;
    var input = form.querySelector("[data-ai-input]") || form.querySelector("input");
    var send = form.querySelector('button[type="submit"]');
    if (!input) return;

    var en = (document.documentElement.lang || "").toLowerCase().indexOf("en") === 0;
    var T = en ? {
      start: "Voice input", stop: "Stop listening", listening: "Listening… speak now",
      denied: "Microphone access was denied. Allow it in your browser and try again.",
      fail: "Voice input failed. Please try again or type instead.",
      nospeech: "Didn't catch that. Please try again."
    } : {
      start: "语音输入", stop: "停止录音", listening: "正在听…请说话",
      denied: "麦克风权限被拒绝，请在浏览器中允许后重试。",
      fail: "语音输入失败，请重试或直接打字。",
      nospeech: "没听清，请再说一次。"
    };

    var style = document.createElement("style");
    style.textContent =
      ".ai-input .ai-voice{display:inline-flex;align-items:center;justify-content:center;width:38px;height:38px;flex:none;padding:0;border:0;border-radius:999px;background:rgba(14,42,36,.08);color:#1f4e5a;cursor:pointer;transition:background .2s,color .2s}" +
      ".ai-input .ai-voice:hover{background:rgba(14,42,36,.16)}" +
      ".ai-input .ai-voice.is-listening{background:#b83a2d;color:#fff;animation:ai-voice-pulse 1.2s ease-out infinite}" +
      "@keyframes ai-voice-pulse{0%{box-shadow:0 0 0 0 rgba(184,58,45,.55)}100%{box-shadow:0 0 0 12px rgba(184,58,45,0)}}" +
      ".ai-voice-hint{margin:0 12px 6px;padding:0 6px;font-size:.75rem;color:#1f2937;font-weight:500}" +
      ".ai-voice-hint.is-error{color:#b83a2d}" +
      "@media (prefers-reduced-motion:reduce){.ai-input .ai-voice.is-listening{animation:none}}";
    document.head.appendChild(style);

    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "ai-voice";
    btn.setAttribute("data-ai-voice", "");
    btn.setAttribute("aria-pressed", "false");
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3"></rect><path d="M5 11a7 7 0 0 0 14 0"></path><path d="M12 18v3"></path></svg>';
    form.insertBefore(btn, send || null);

    var hint = document.createElement("p");
    hint.className = "ai-voice-hint";
    hint.setAttribute("role", "status");
    hint.setAttribute("aria-live", "polite");
    hint.hidden = true;
    form.parentNode.insertBefore(hint, form);

    var rec = null, listening = false, hintTimer = null;

    function showHint(text, isError, sticky) {
      clearTimeout(hintTimer);
      hint.textContent = text;
      hint.classList.toggle("is-error", !!isError);
      hint.hidden = false;
      if (!sticky) hintTimer = setTimeout(function () { hint.hidden = true; }, 5000);
    }
    function hideHint() { clearTimeout(hintTimer); hint.hidden = true; }
    function setState(on) {
      listening = on;
      btn.classList.toggle("is-listening", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
      var label = on ? T.stop : T.start;
      btn.setAttribute("aria-label", label);
      btn.title = label;
    }
    setState(false);

    function start() {
      var r;
      try { r = new SR(); } catch (e) { showHint(T.fail, true); return; }
      rec = r;
      r.lang = en ? "en-US" : "zh-CN";
      r.interimResults = true;
      r.continuous = false;
      r.maxAlternatives = 1;
      var base = input.value ? input.value.replace(/\s+$/, "") + (en ? " " : "") : "";
      var errored = false, gotText = false;

      r.onresult = function (ev) {
        var text = "";
        for (var i = 0; i < ev.results.length; i++) text += ev.results[i][0].transcript;
        text = text.trim();
        if (!text) return;
        gotText = true;
        input.value = (base + text).slice(0, input.maxLength > 0 ? input.maxLength : 500);
        input.dispatchEvent(new Event("input", { bubbles: true }));
      };
      r.onerror = function (ev) {
        errored = true;
        var code = ev && ev.error;
        if (code === "aborted") { return; }
        if (code === "no-speech") showHint(T.nospeech, false);
        else if (code === "not-allowed" || code === "service-not-allowed") showHint(T.denied, true);
        else showHint(T.fail, true);
      };
      r.onend = function () {
        if (rec === r) rec = null;
        setState(false);
        if (!errored) hideHint();
        if (gotText) input.focus();
      };
      try {
        r.start();
        setState(true);
        showHint(T.listening, false, true);
      } catch (e) {
        rec = null;
        setState(false);
        showHint(T.fail, true);
      }
    }

    btn.addEventListener("click", function () {
      if (listening && rec) { try { rec.stop(); } catch (e) {} return; }
      start();
    });
    form.addEventListener("submit", function () {
      if (rec) { try { rec.abort(); } catch (e) {} }
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
  else init();
})();
