/* 账户中心大屏页：修改密码 + admin 用户管理 */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function msg(cls, text) {
    var el = $("pw-msg");
    el.className = "sc-msg " + cls;
    el.textContent = text;
  }

  /* ── 修改密码 ── */
  $("pw-form").addEventListener("submit", function (e) {
    e.preventDefault();
    if ($("pw-new").value !== $("pw-new2").value) {
      msg("err", "两次输入的新密码不一致");
      return;
    }
    fetch("/screen/api/change-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ old_password: $("pw-old").value, new_password: $("pw-new").value }),
    }).then(function (r) {
      if (r.ok) {
        msg("ok", "密码已修改，其他会话已注销，请牢记新密码");
        $("pw-form").reset();
      } else {
        return r.json().then(function (d) {
          var map = {
            auth_old_pw_wrong: "当前密码错误",
            auth_pw_len: "新密码长度不足（至少 8 位）",
            auth_pw_letter: "新密码需包含字母",
            auth_pw_digit: "新密码需包含数字",
            auth_user_missing: "用户不存在"
          };
          msg("err", map[d.detail] || "修改失败：" + (d.detail || "未知错误"));
        });
      }
    }).catch(function () { msg("err", "网络错误，请重试"); });
  });

  /* ── 用户管理（admin） ── */
  var me = null;
  fetch("/screen/api/me").then(function (r) { return r.json(); }).then(function (u) {
    me = u;
    if (u.role === "admin") { $("users-panel").hidden = false; loadUsers(); }
  }).catch(function () {});

  function loadUsers() {
    fetch("/screen/api/users").then(function (r) { return r.json(); })
      .then(function (d) { renderUsers(d.users || []); }).catch(function () {});
  }

  function renderUsers(users) {
    var h = "";
    users.forEach(function (u) {
      var isMe = me && u.id === me.id;
      var acts = "";
      if (u.is_active) {
        if (!isMe) acts += '<span class="sc-act danger" data-act="deactivate" data-id="' + u.id + '">停用</span>';
      } else {
        acts += '<span class="sc-act" data-act="activate" data-id="' + u.id + '">启用</span>';
        acts += '<span class="sc-act" data-act="unlock" data-id="' + u.id + '">解锁</span>';
      }
      acts += '<span class="sc-act" data-act="reset_password" data-id="' + u.id + '">重置密码</span>';
      if (!isMe) {
        acts += '<select class="sc-rolesel" data-role-id="' + u.id + '">' +
          '<option value="user"' + (u.role === "user" ? " selected" : "") + '>巡检员</option>' +
          '<option value="admin"' + (u.role === "admin" ? " selected" : "") + '>管理员</option></select>';
      }
      h += "<tr><td>" + u.id + "</td><td>" + esc(u.username) + (isMe ? "（我）" : "") +
        "</td><td>" + (u.role === "admin" ? "管理员" : "巡检员") + "</td><td>" +
        (u.is_active ? '<span class="sc-badge ok">正常</span>' : '<span class="sc-badge hi">停用</span>') +
        "</td><td>" + acts + "</td></tr>";
    });
    $("user-rows").innerHTML = h || '<tr><td colspan="5"><div class="sc-empty">无用户</div></td></tr>';
  }

  $("user-rows").addEventListener("click", function (e) {
    var t = e.target;
    if (!t.dataset || !t.dataset.act) return;
    var id = parseInt(t.dataset.id, 10);
    var act = t.dataset.act;
    var body = { action: act };
    if (act === "reset_password") {
      var pw = prompt("输入新密码（≥8 位，含大小写字母/数字/特殊字符）：");
      if (!pw) return;
      body.value = pw;
    }
    actOnUser(id, body);
  });

  $("user-rows").addEventListener("change", function (e) {
    var t = e.target;
    if (!t.dataset || !t.dataset.roleId) return;
    actOnUser(parseInt(t.dataset.roleId, 10), { action: "set_role", value: t.value });
  });

  function actOnUser(id, body) {
    fetch("/screen/api/users/" + id + "/action", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(function (r) {
      if (!r.ok) return r.json().then(function (d) { alert("操作失败：" + (d.detail || r.status)); });
      loadUsers();
    }).catch(function () { alert("网络错误"); });
  }
})();
