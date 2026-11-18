/* 历史记录大屏页：筛选/分页/详情抽屉/备注/删除 */
(function () {
  "use strict";
  var $ = function (id) { return document.getElementById(id); };
  var page = 1, pageSize = 15, total = 0, lastDetail = null;

  let listRequest = null, deleting = false;
  let pendingIds = [];
  const selected = new Set();

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  function showFeedback(text) {
    $("delete-feedback").textContent = text;
    $("delete-feedback").hidden = !text;
  }

  function updateSelection() {
    const boxes = $("rows").querySelectorAll("input[data-select]");
    const busy = Boolean(listRequest) || deleting;
    for (const box of boxes) {
      box.checked = selected.has(Number(box.value));
      box.disabled = busy;
    }
    $("select-page").checked = boxes.length > 0 && selected.size === boxes.length;
    $("select-page").indeterminate = selected.size > 0 && selected.size < boxes.length;
    $("select-page").disabled = busy || !boxes.length;
    $("delete-selected").disabled = busy || !selected.size;
    $("selection-count").textContent = selected.size ? "已选 " + selected.size + " 条" : "";
  }

  async function load() {
    listRequest?.abort();
    const request = new AbortController();
    listRequest = request;
    selected.clear();
    updateSelection();
    $("pg-prev").disabled = $("pg-next").disabled = true;
    $("rows").setAttribute("aria-busy", "true");
    var q = new URLSearchParams({
      page: page, page_size: pageSize,
      search: $("f-search").value.trim(),
      risk: $("f-risk").value,
      date_from: $("f-from").value, date_to: $("f-to").value,
      sort: $("f-sort").value,
    });
    try {
      const response = await fetch("/screen/api/records?" + q, {signal:request.signal, cache:"no-store"});
      if (!response.ok) throw new Error(String(response.status));
      const data = await response.json();
      if (request.signal.aborted) return;
      total = data.total;
      const pages = Math.max(1, Math.ceil(total / pageSize));
      if (page > pages) {
        page = pages;
        return load();
      }
      $("f-total").textContent = "共 " + total + " 条";
      $("pg-info").textContent = page + " / " + pages;
      $("pg-prev").disabled = page <= 1;
      $("pg-next").disabled = page >= pages;
      renderRows(data.rows);
    } catch (error) {
      if (!request.signal.aborted) {
        $("f-total").textContent = "";
        $("pg-info").textContent = "—";
        $("rows").innerHTML = '<tr><td colspan="12"><div class="sc-empty">记录加载失败，请重新查询。</div></td></tr>';
      }
    } finally {
      if (listRequest === request) {
        listRequest = null;
        $("rows").removeAttribute("aria-busy");
        updateSelection();
      }
    }
  }

  function renderRows(rows) {
    if (!rows.length) {
      $("rows").innerHTML = '<tr><td colspan="12"><div class="sc-empty">无匹配记录</div></td></tr>';
      return;
    }
    var h = "";
    rows.forEach(function (r) {
      h += '<tr><td class="select-row"><label class="selection-cell"><input type="checkbox" data-select value="' + r.id +
        '" aria-label="选择记录 #' + r.id + ' ' + esc(r.image_name) + '"></label></td><td>' + r.id + "</td><td>" + esc(r.timestamp) + "</td><td>" + esc(r.turbine_id || "未关联") + "</td><td>" + esc(r.image_name) +
        "</td><td>" + esc(r.component || "—") + "</td><td>" + esc(r.damage_type || "无") +
        '</td><td>' + esc(r.priority || "—") + "</td><td>" +
        (r.high_risk ? '<span class="sc-badge hi">高风险</span>' : '<span class="sc-badge ok">未触发告警</span>') +
        "</td><td>" + (r.infer_time != null ? Number(r.infer_time).toFixed(1) + "s" : "—") +
        "</td><td>" + esc(r.note || "") +
        '</td><td><button class="sc-link" data-act="detail" data-id="' + r.id + '">详情</button>' +
        '<button class="sc-link danger" data-act="del" data-id="' + r.id + '">删除</button></td></tr>';
    });
    $("rows").innerHTML = h;
  }

  $("rows").addEventListener("change", function (event) {
    if (!event.target.matches("input[data-select]")) return;
    const id = Number(event.target.value);
    if (event.target.checked) selected.add(id);
    else selected.delete(id);
    updateSelection();
  });

  $("select-page").addEventListener("change", function () {
    selected.clear();
    if (this.checked) {
      for (const box of $("rows").querySelectorAll("input[data-select]")) selected.add(Number(box.value));
    }
    updateSelection();
  });

  function confirmDeletion(ids) {
    if (!ids.length || deleting || listRequest) return;
    pendingIds = ids;
    const target = ids.length === 1 ? "记录 #" + ids[0] : "选中的 " + ids.length + " 条评估记录";
    $("delete-message").textContent = "确认删除" + target + "？删除后无法恢复。";
    $("delete-dialog").showModal();
  }

  $("delete-selected").addEventListener("click", () => confirmDeletion([...selected]));
  $("delete-cancel").addEventListener("click", () => $("delete-dialog").close());
  $("delete-confirm").addEventListener("click", async function () {
    if (deleting || !pendingIds.length) return;
    const ids = pendingIds;
    pendingIds = [];
    deleting = true;
    $("delete-dialog").close();
    updateSelection();
    showFeedback("正在删除…");
    try {
      const response = await fetch("/screen/api/records", {
        method:"DELETE", headers:{"Content-Type":"application/json"}, body:JSON.stringify({ids})
      });
      if (!response.ok) throw new Error(response.status === 403 ? "无权删除所选记录" : "请重新查询后重试");
      const data = await response.json();
      showFeedback(data.deleted ? "已删除 " + data.deleted + " 条记录。" : "所选记录已被删除。");
      await load();
    } catch (error) {
      showFeedback("删除未完成，" + error.message + "。");
    } finally {
      deleting = false;
      updateSelection();
    }
  });

  $("rows").addEventListener("click", function (e) {
    const t = e.target;
    if (!t.dataset.act || listRequest || deleting) return;
    const id = Number(t.dataset.id);
    if (t.dataset.act === "detail") openDetail(id);
    if (t.dataset.act === "del") confirmDeletion([id]);
  });

  /* ── 详情抽屉 ── */
  function openDetail(id) {
    fetch("/screen/api/records/" + id).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    }).then(function (d) {
      lastDetail = d;
      $("drawer-title").textContent = ["#" + d.id, d.turbine_id, d.image_name].filter(Boolean).join(" · ");
      $("note-input").value = d.note || "";
      var rep = d.json_report || {};
      var h = "";
      if (d.image_file_id) {
        h += '<img src="/history/' + d.id + '/image" alt="" style="max-width:100%;max-height:300px;border-radius:6px;margin-bottom:14px;border:1px solid rgba(103,232,249,.3)">';
      }
      Object.keys(rep).forEach(function (sec) {
        h += '<div class="sc-sec"><div class="t">' + esc(sec) + "</div>";
        var obj = rep[sec] || {};
        h += '<div class="sc-kv">' + Object.keys(obj).map(function (k) {
          return '<span class="k">' + esc(k) + '</span><span class="v">' + esc(obj[k]) + "</span>";
        }).join("") + "</div></div>";
      });
      $("drawer-body").innerHTML = h || '<div class="sc-empty">无报告内容</div>';
      const reportTools = document.createElement("div");
      renderReportTools(reportTools, d.json_report, d.id);
      $("drawer-body").prepend(reportTools);
      const riskPanel = createInspectionAlert(d.alert);
      if (riskPanel) $("drawer-body").prepend(riskPanel);
      $("drawer").showModal();
    }).catch(function (e) { alert("加载详情失败：" + e.message); });
  }

  $("drawer").addEventListener("click", function (e) {
    if (e.target !== this) return;
    var bounds = this.getBoundingClientRect();
    if (e.clientX < bounds.left || e.clientX > bounds.right ||
        e.clientY < bounds.top || e.clientY > bounds.bottom) closeDrawer();
  });
  $("drawer-close").addEventListener("click", closeDrawer);
  function closeDrawer() { $("drawer").close(); }

  $("note-save").addEventListener("click", function () {
    if (!lastDetail) return;
    fetch("/screen/api/records/" + lastDetail.id + "/note", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: $("note-input").value }),
    }).then(function (r) {
      if (!r.ok) throw 0;
      closeDrawer(); load();
    });
  });

  /* ── 筛选/分页 ── */
  $("filters").addEventListener("submit", function (e) {
    e.preventDefault();
    page = 1;
    load();
  });
  $("pg-prev").addEventListener("click", function () { if (page > 1) { page--; load(); } });
  $("pg-next").addEventListener("click", function () { page++; load(); });

  load();
  const record = new URLSearchParams(location.search).get("record");
  if (record && /^\d+$/.test(record)) openDetail(Number(record));
})();
