/* 大屏登录/注册页：Tab 切换、记住密码（localStorage 混淆存）、注册前端校验 */
(function () {
  "use strict";
  var $ = function (sel) { return document.querySelector(sel); };
  var KEY = "wd_screen_remember";   // localStorage 键
  var REMEMBER_DAYS = 30;

  /* ── Tab 切换 ── */
  var tabs = document.querySelectorAll(".sc-tab");
  tabs.forEach(function (t) {
    t.addEventListener("click", function () {
      tabs.forEach(function (x) { x.classList.remove("active"); });
      t.classList.add("active");
      document.querySelectorAll(".sc-mode").forEach(function (f) { f.classList.remove("active"); });
      var form = document.querySelector(".sc-mode-" + t.dataset.mode);
      if (form) form.classList.add("active");
    });
  });

  /* ── 记住密码：混淆存储（base64，便捷换安全的本地记忆） ── */
  function ob(s) { try { return btoa(unescape(encodeURIComponent(s))); } catch (e) { return ""; } }
  function de(s) { try { return decodeURIComponent(escape(atob(s))); } catch (e) { return ""; } }

  function loadRemember() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return;
      var d = JSON.parse(raw);
      if (d.exp && Date.now() > d.exp) { localStorage.removeItem(KEY); return; }
      $("#li-user").value = de(d.u || "");
      $("#li-pw").value = de(d.p || "");
      $("#li-remember").checked = true;
    } catch (e) {}
  }

  function saveRemember(u, p) {
    try {
      localStorage.setItem(KEY, JSON.stringify({
        u: ob(u), p: ob(p),
        exp: Date.now() + REMEMBER_DAYS * 86400000,
      }));
    } catch (e) {}
  }

  function clearRemember() {
    try { localStorage.removeItem(KEY); } catch (e) {}
  }

  loadRemember();
  $(".sc-mode-login").addEventListener("submit", function () {
    if ($("#li-remember").checked) {
      saveRemember($("#li-user").value, $("#li-pw").value);
    } else {
      clearRemember();
    }
  });

  /* ── 密码显隐小眼睛 ── */
  document.querySelectorAll(".pw-eye").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var input = document.getElementById(btn.dataset.target);
      if (!input) return;
      var show = input.type === "password";
      input.type = show ? "text" : "password";
      btn.classList.toggle("on", show);
      btn.textContent = show ? "🙈" : "👁";
    });
  });

  /* ── 注册前端校验（服务端仍会完整复检） ── */
  $("#rg-form").addEventListener("submit", function (e) {
    var pw = $("#rg-pw").value, pw2 = $("#rg-pw2").value;
    var problems = [];
    if (pw !== pw2) problems.push("两次输入的密码不一致");
    if (pw.length < 8) problems.push("密码长度至少 8 位");
    if (!/[A-Za-z]/.test(pw)) problems.push("密码需包含字母");
    if (!/\d/.test(pw)) problems.push("密码需包含数字");
    if (problems.length) {
      e.preventDefault();
      var box = $(".sc-form-error");
      if (!box) {
        box = document.createElement("div");
        box.className = "sc-form-error";
        $(".sc-tabs").after(box);
      }
      box.textContent = problems[0];
    }
  });
})();
