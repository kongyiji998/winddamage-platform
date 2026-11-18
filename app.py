#!/usr/bin/env python3
"""
风电塔灾损测算软件 — Gradio 前端

功能：
  - 单图/批量图片上传 → 模型推理 → 结构化报告展示
  - 高风险自动告警（浅底色条横幅，文字+颜色双通道）
  - 结论摘要卡 + 折叠式分组报告 + 完整 JSON 折叠查看
  - 报告导出（Markdown / JSON）
  - 检测历史记录（SQLite 存储，下拉选择回看，删除需确认）
  - 统计面板
  - 中 / 英双语界面（--lang en 或 UI_LANG=en 切换英文）

启动: python app.py            （中文界面）
      python app.py --lang en  （英文界面）
访问: http://localhost:7860
"""

import os
import sys
import time
import json
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import MODEL_PATH, IMAGE_DIR
import i18n
if "--lang" in sys.argv or os.environ.get("UI_LANG"):
    i18n.set_lang(i18n.detect_lang())  # 需在导入展示模块前确定语言
# 未显式指定语言时保持 i18n 已有设置（便于外部 import app 前预设语言）

import gradio as gr
from inference import WindDamageModel
from parser import IncompleteReportError, validate_report, get_field
from formatter import format_report, format_summary, get_risk_badge, is_high_risk
from history import (init_db, save_record, query_records, get_record, clear_all,
                     clear_user_records, get_stats, can_access, update_note,
                     delete_record)
from auth import user_for_request
import export_tasks as xt
from exporter import save_export
from charts import charts_html
from i18n import t as tr, tr_value
import ui_components as uc

# ─── 全局模型实例 ─────────────────────────────────────────
_model = None

# ─── 空状态图标 ───────────────────────────────────────────
_UPLOAD_ICON_SVG = (
    "<svg width='52' height='52' viewBox='0 0 24 24' fill='none' stroke='#9AA5B1' "
    "stroke-width='1.4' stroke-linecap='round' stroke-linejoin='round'>"
    "<path d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'/>"
    "<polyline points='17 8 12 3 7 8'/>"
    "<line x1='12' y1='3' x2='12' y2='15'/>"
    "</svg>"
)


def _empty_result_html():
    """结果区空状态：图标 + 标题 + 格式说明。"""
    return uc.empty_state(tr("empty_upload"), tr("empty_format"), _UPLOAD_ICON_SVG)


EMPTY_RESULT_HTML = _empty_result_html()


def get_model():
    global _model
    if _model is None:
        _model = WindDamageModel()
        _model.load()
    return _model


# ══════════════════════════════════════════════════════════
#  核心推理函数
# ══════════════════════════════════════════════════════════

def get_image_info(image_path):
    """提取图片元信息（尺寸、大小、格式）。"""
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            w, h = im.size
            fmt = im.format or ""
        size_kb = os.path.getsize(image_path) / 1024
        return f"{w} × {h} px | {fmt} | {size_kb:.0f} KB"
    except Exception:
        return ""


def _do_inference(image_path):
    """对单张图片执行推理，返回 (parsed, raw, infer_time) 或 raise。"""
    model = get_model()
    parsed, raw, infer_time = model.infer(image_path)
    if parsed is not None:
        validation = validate_report(parsed)
        if not validation["valid"]:
            raise IncompleteReportError(validation["message"])
    return parsed, raw, infer_time


def _damage_locator_payload(parsed):
    """将模型报告压缩为三维风机可视化所需的安全定位数据。"""
    has_damage = get_field(parsed, i18n.SECTION_DAMAGE, "是否存在损伤")
    return {
        "hasDamage": has_damage.strip() in ("是", "Yes", "yes", "true", "True"),
        "part": get_field(parsed, i18n.SECTION_COMPONENT, "构件名称"),
        "type": get_field(parsed, i18n.SECTION_DAMAGE, "损伤类型"),
        "location": get_field(parsed, i18n.SECTION_DAMAGE, "损伤分布位置与范围"),
    }


def _viewer_bridge_html(parsed=None):
    """返回 Three.js 风机 iframe，通过查询参数传入报告的损伤定位数据。"""
    payload = _damage_locator_payload(parsed) if parsed else {
        "hasDamage": False, "part": "", "type": "", "location": ""
    }
    encoded = quote(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), safe="")
    return (
        '<div class="wd-turbine-frame">'
        '<iframe title="风机三维损伤定位" '
        f'src="/wd-assets/wind_turbine_viewer.html?v=10&amp;damage={encoded}"></iframe></div>'
    )


def _summary_card_html(parsed, meta=None):
    """结果页第一层：结论摘要卡（风险等级/损伤类型/优先级 + 元信息）。"""
    meta = meta or {}
    priority_raw = get_field(parsed, i18n.SECTION_CONCLUSION, "巡检优先级") or "—"
    damage_raw = get_field(parsed, i18n.SECTION_DAMAGE, "损伤类型") or "—"
    has_damage_raw = get_field(parsed, i18n.SECTION_DAMAGE, "是否存在损伤")
    high = is_high_risk(parsed)
    if high:
        tone = "danger"
    else:
        tone = "success" if (has_damage_raw or "").strip() != "是" else "warn"
    risk_disp = uc.risk_badge(tr("badge_high_risk") if high else tr("badge_normal"), tone)

    items = [
        (tr("card_risk"), risk_disp),
        (tr("card_damage"), uc.risk_badge(tr_value(damage_raw))),
        (tr("card_priority"), esc_risk(tr_value(priority_raw))),
    ]
    if meta.get("timestamp"):
        items.append((tr("card_time"), uc.esc(meta["timestamp"])))
    if meta.get("infer_time") is not None:
        items.append((tr("card_cost"), f"{meta['infer_time']:.1f}s"))
    if meta.get("record_id"):
        items.append((tr("card_no"), f"#{meta['record_id']}"))
    return uc.summary_card(items, tone=tone)


def esc_risk(text) -> str:
    """风险值着色徽章（无法映射时原样转义）。"""
    from ui_components import tone_for_value
    text = str(text or "—")
    return uc.risk_badge(text, tone_for_value(text))


def _build_result_html(parsed, meta=None):
    """将解析后的 JSON 构建为四层结构的 HTML 展示。

    第一层：结论摘要卡；高风险横幅（浅底色条）；
    第二~三层：折叠式分组报告板块（损伤判定与结论默认展开）；
    （JSON 技术信息由外层 Accordion 承载。）
    """
    formatted = format_report(parsed)
    html_parts = []

    # 第一层：结论摘要卡
    html_parts.append(_summary_card_html(parsed, meta))

    # 高风险横幅：浅底 + 左色条 + 图标 + 明确文字
    if formatted["high_risk"]:
        notice = tr("msg_high_risk_banner")
        advice = get_field(parsed, i18n.SECTION_OM, "短期处置建议")
        if advice:
            notice += " · " + i18n.field_label(i18n.SECTION_OM, "短期处置建议") + " · " + tr_value(advice)
        html_parts.append(uc.risk_banner(notice))

    # 折叠板块：损伤判定、风险判断、结论建议默认展开
    open_keys = {i18n.SECTION_DAMAGE, i18n.SECTION_RISK, i18n.SECTION_CONCLUSION}
    for sec in formatted["sections"]:
        fields = []
        for f in sec["fields"]:
            value_html = uc.esc(f["value"])
            if f["is_risk"] and f["value"] in get_risk_badge_values():
                value_html = get_risk_badge(f["value"], f["raw_field"])
            fields.append((f["label"], value_html, f["is_risk"]))
        body = uc.kv_rows(fields)
        open_ = sec["title"] in open_keys or any(
            k in str(sec["title"]) for k in ("损伤", "Damage", "风险", "Risk", "结论", "Conclusion")
        )
        html_parts.append(uc.sec_details(sec["icon"], sec["title"], body, open_))

    return "".join(html_parts), formatted


def get_risk_badge_values():
    """当前语言下需要渲染成彩色 badge 的取值集合。"""
    if i18n.LANG == "en":
        return ("Yes", "No", "None", "High", "Medium", "Low")
    return ("是", "高", "中", "否", "低", "无")


# ══════════════════════════════════════════════════════════
#  Tab 1: 单图检测
# ══════════════════════════════════════════════════════════

def analyze_single(image, request: gr.Request = None):
    """单图分析（生成器）。

    先立即 yield 一条带旋转 spinner 的"分析中"状态条（等待动效），
    推理完成后再 yield 最终结果。返回值结构为：
    (summary, detail_html, json_out, status, img_info, md_path, json_path, viewer_html)。
    """
    if image is None:
        yield (tr("msg_please_upload"), _empty_result_html(), "",
               tr("msg_upload_first"), "", None, None, _viewer_bridge_html())
        return

    image_path = image if isinstance(image, str) else getattr(image, 'name', str(image))

    if not os.path.exists(image_path):
        yield (
            tr("msg_file_not_exist"),
            uc.status_banner(f'{uc.esc(tr("msg_file_not_exist"))}: {uc.esc(image_path)}', "error"),
            "", tr("msg_file_not_exist"), "", None, None, _viewer_bridge_html(),
        )
        return

    img_info = get_image_info(image_path)

    # 等待动效：立即给出"分析中"状态（spinner），清空旧结果避免误读
    yield ("", uc.working_banner(tr("msg_working")), "", "", img_info, None, None,
           _viewer_bridge_html())

    try:
        t0 = time.time()
        parsed, raw, infer_time = _do_inference(image_path)
        total_time = time.time() - t0

        if parsed is None:
            yield (
                tr("msg_parse_fail"),
                uc.status_banner(tr("msg_infer_parse_fail", t=infer_time), "error")
                + f"<pre style='overflow-x:auto;background:#F0F3F7;padding:12px;border-radius:8px;font-size:12px;'>{uc.esc(raw[:2000])}</pre>",
                raw, tr("msg_infer_parse_fail", t=infer_time), img_info, None, None,
                _viewer_bridge_html(),
            )
            return

        # 保存历史记录（先拿到记录 ID，用于摘要卡报告编号；归属当前登录用户）
        owner_id, created_by = _scope_owner(request)
        record_id = save_record(os.path.basename(image_path), parsed, infer_time,
                                image_path, source="ui", persist_image=True,
                                owner_user_id=owner_id, created_by=created_by)

        detail_html, formatted = _build_result_html(parsed, meta={
            "record_id": record_id,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "infer_time": infer_time,
        })
        summary = format_summary(parsed)
        json_str = formatted["json_str"]
        val = formatted["validation"]
        image_name = os.path.basename(image_path)
        comp = "✅" if val["valid"] else f"⚠️ {val['message']}"
        status = (f'✅ {tr("msg_infer_done", t=infer_time)} | '
                  f'{tr("msg_json_ok")} | '
                  f'{tr("msg_completeness")}: {comp}')

        # 导出文件
        md_path = save_export(parsed, image_name, infer_time, fmt="md")
        json_path = save_export(parsed, image_name, infer_time, fmt="json")

        yield (summary, detail_html, json_str, status, img_info, md_path, json_path,
               _viewer_bridge_html(parsed))

    except Exception as e:
        import traceback
        traceback.print_exc()
        yield (
            tr("msg_infer_fail"),
            uc.status_banner(f'{uc.esc(tr("msg_error", e=e))}', "error")
            + f"<pre style='overflow-x:auto;background:#F0F3F7;padding:12px;border-radius:8px;font-size:12px;'>{uc.esc(traceback.format_exc()[:1500])}</pre>",
            "", tr("msg_error", e=e), img_info, None, None, _viewer_bridge_html(),
        )


# ══════════════════════════════════════════════════════════
#  Tab 2: 批量检测（生成器：边分析边刷新进度）
# ══════════════════════════════════════════════════════════

def _batch_progress_html(banner_html: str, log_lines) -> str:
    """批量进度：状态横幅 + 可滚动日志（column-reverse 保证最新行可见）。"""
    log = uc.esc("\n".join(log_lines)) if log_lines else "—"
    return (f'{banner_html}'
            f'<div class="wd-progress-box"><pre class="wd-progress-log">{log}</pre></div>')


# 最近一次批量检测的可导出数据（进程内缓存；批量完成时由 analyze_batch 写入）
_LAST_BATCH = {"rows": [], "header": [], "summary": ""}


def export_batch_summary(fmt: str = "csv"):
    """批量汇总导出按钮回调：返回 (文件, 状态文本)。"""
    if not _LAST_BATCH["rows"]:
        return None, tr("batch_export_none")
    from exporter import save_batch_export
    path = save_batch_export(_LAST_BATCH["rows"], _LAST_BATCH["header"],
                             _LAST_BATCH["summary"], fmt=fmt)
    return path, tr("msg_infer_done", t=0) if False else f"✅ {os.path.basename(path)}"


def analyze_batch(files, request: gr.Request = None):
    """批量分析多张图片。生成器逐张产出 (summary, table_html, progress_html)，实时刷新进度。"""
    if not files:
        yield "", _empty_result_html(), _batch_progress_html("", [])
        return

    owner_id, created_by = _scope_owner(request)

    results = []
    high_flags = []  # 与 results 行一一对应，用于整行风险着色
    export_rows = []  # 纯文本行（无 HTML 标签），供批量汇总导出
    status_parts = []
    total = len(files)
    ok_count = 0
    fail_count = 0

    header = [tr("hdr_image"), tr("hdr_risk"), tr("hdr_damage"), tr("hdr_damage_type"),
              tr("hdr_component"), tr("hdr_priority"), tr("hdr_time_cost")]

    def render_table(collapsed: bool = False):
        """已完成的行 → 可折叠的样式化表格（点表头收起/展开）。"""
        rows = []
        for idx, row in enumerate(results):
            row_cls = ' class="wd-row-danger"' if high_flags[idx] else ""
            tds = "".join(
                f'<td class="wd-num">{c}</td>' if j == 6 else f'<td>{c}</td>'
                for j, c in enumerate(row)
            )
            rows.append(f"<tr{row_cls}>{tds}</tr>")
        table = uc.data_table(header, "".join(rows))
        open_attr = "" if collapsed else " open"
        return (f'<details class="wd-sec"{open_attr}>'
                f'<summary><span>📋</span><span>{uc.esc(tr("batch_detail_title"))}'
                f'（{ok_count + fail_count}/{total}）</span></summary>'
                f'<div class="wd-sec-body">{table}</div></details>')

    banner0 = uc.working_banner(tr("msg_progress", i=0, total=total, name="…"))
    yield "", "", _batch_progress_html(banner0, status_parts)

    for i, f in enumerate(files):
        image_path = f if isinstance(f, str) else f.name
        image_name = os.path.basename(image_path)

        banner = uc.working_banner(
            tr("msg_progress", i=i + 1, total=total, name=uc.esc(image_name)))
        yield "", render_table(), _batch_progress_html(banner, status_parts)

        try:
            parsed, raw, infer_time = _do_inference(image_path)

            if parsed is None:
                fail_count += 1
                results.append([uc.esc(image_name), "❌", "—", "—", "—", "—", f"{infer_time:.1f}s"])
                high_flags.append(False)
                export_rows.append([image_name, tr("msg_parse_fail"),
                                    "—", "—", "—", "—", f"{infer_time:.1f}s"])
                status_parts.append(f'[{i+1}/{total}] {image_name}: ❌ {tr("msg_parse_fail")}')
                yield tr("batch_partial", ok=ok_count, total=total, failed=fail_count), \
                      render_table(), _batch_progress_html(banner, status_parts)
                continue

            ok_count += 1
            has_damage = tr_value(get_field(parsed, i18n.SECTION_DAMAGE, "是否存在损伤"))
            damage_type = tr_value(get_field(parsed, i18n.SECTION_DAMAGE, "损伤类型"))
            component = tr_value(get_field(parsed, i18n.SECTION_COMPONENT, "构件名称"))
            priority = tr_value(get_field(parsed, i18n.SECTION_CONCLUSION, "巡检优先级"))

            high = is_high_risk(parsed)
            risk_cell = f'<span class="wd-badge wd-badge-{"danger" if high else "success"}">' \
                        f'{tr("badge_high_risk") if high else tr("badge_normal")}</span>'
            results.append([
                uc.esc(image_name), risk_cell,
                uc.risk_badge(has_damage) if has_damage else "—",
                uc.esc(damage_type) if damage_type else "—",
                uc.esc(component) if component else "—",
                uc.risk_badge(priority) if priority else "—",
                f"{infer_time:.1f}s",
            ])
            high_flags.append(high)
            export_rows.append([
                image_name,
                tr("badge_high_risk") if high else tr("badge_normal"),
                has_damage or "—", damage_type or "—",
                component or "—", priority or "—",
                f"{infer_time:.1f}s",
            ])

            # 保存历史（归属当前登录用户）
            save_record(image_name, parsed, infer_time, image_path,
                        source="batch", persist_image=True,
                        owner_user_id=owner_id, created_by=created_by)

            status_parts.append(f"[{i+1}/{total}] {image_name}: ✅ {damage_type} | {priority}")

        except Exception as e:
            fail_count += 1
            results.append([uc.esc(image_name), "❌", "—", "—", "—", "—", uc.esc(str(e)[:50])])
            high_flags.append(False)
            export_rows.append([image_name, f"{tr('msg_infer_fail')}: {str(e)[:40]}",
                                "—", "—", "—", "—", "—"])
            status_parts.append(f"[{i+1}/{total}] {image_name}: ❌ {e}")

        done_summary = tr("batch_partial", ok=ok_count, total=total, failed=fail_count) if fail_count \
            else tr("batch_done", ok=ok_count, total=total)
        yield done_summary, render_table(), _batch_progress_html(banner, status_parts)

    final_summary = tr("batch_partial", ok=ok_count, total=total, failed=fail_count) if fail_count \
        else tr("batch_done", ok=ok_count, total=total)
    final_banner = uc.status_banner(final_summary, "warn" if fail_count else "success")
    # 记录最终导出数据（生成器结束时写入模块级"最近一次批量结果"，
    # 导出按钮点击时读取 —— gradio 事件间传递用）
    _LAST_BATCH["rows"] = export_rows
    _LAST_BATCH["header"] = header
    _LAST_BATCH["summary"] = final_summary
    yield final_summary, render_table(), _batch_progress_html(final_banner, status_parts)


# ══════════════════════════════════════════════════════════
#  Tab 3: 历史记录（筛选 / 排序 / 分页 / 分级删除 / 移动卡片）
# ══════════════════════════════════════════════════════════

def _current_scope(request=None):
    """当前会话的数据范围 (user_id, is_admin)。

    - request 带 gr.Request 注解时由 gradio 注入真实请求 → 从会话 Cookie 解析用户；
    - request=None（单元测试 / 直接函数调用）：保持 (None, True) 兼容旧离线行为，
      生产路由全部经过登录中间件，不会出现 None 请求。
    """
    if request is None:
        return None, True
    user = user_for_request(request)
    if not user:
        return None, False
    return user["id"], user.get("role") == "admin"


def _scope_owner(request=None):
    """(owner_user_id, username)：用于 save_record 归属。"""
    if request is None:
        return None, None
    user = user_for_request(request)
    if not user:
        return None, None
    return user["id"], user.get("username")


def _valid_date(s: str) -> bool:
    try:
        time.strptime(s.strip(), "%Y-%m-%d")
        return True
    except (ValueError, AttributeError):
        return False


def _risk_badge_cell(high_risk) -> str:
    cls = "danger" if high_risk else "success"
    txt = tr("badge_high_risk") if high_risk else tr("badge_normal")
    return f'<span class="wd-badge wd-badge-{cls}">{txt}</span>'


def _record_image_html(record) -> str:
    """巡检图像卡：有持久化图像时返回 <img>（走 /history/{id}/image 权限路由）。"""
    if not record or not record.get("image_file_id"):
        return ""
    rid = record["id"]
    name = uc.esc(record["image_name"] or f"#{rid}")
    return (f'<div class="wd-img-card">'
            f'<div class="wd-img-title">🖼 {uc.esc(tr("img_section"))} · {name}</div>'
            f'<img src="/history/{rid}/image" alt="{name}" loading="lazy"/></div>')


# 抽屉交互脚本：页面加载时注入一次，用 document 级事件委托——
# 历史列表每次刷新重建 DOM，委托监听不受影响。预览内容走 /history/{id}
# 独立页（服务端会话鉴权），iframe 内不承载任何额外权限。
_DRAWER_JS = """
() => {
  var lastRid = null;
  function drawerEls() {
    return {
      mask: document.getElementById("wd-drawer-mask"),
      drawer: document.getElementById("wd-drawer"),
      frame: document.getElementById("wd-drawer-frame"),
      openLink: document.getElementById("wd-drawer-open"),
      titleEl: document.getElementById("wd-drawer-title")
    };
  }
  function show(rid, name) {
    var el = drawerEls();
    if (!el.drawer) return;
    lastRid = rid;
    el.frame.src = "/history/" + rid;
    el.openLink.href = "/history/" + rid;
    el.titleEl.textContent = "#" + rid + (name ? " · " + name : "");
    el.mask.classList.add("wd-open");
    el.drawer.classList.add("wd-open");
  }
  function hide() {
    var el = drawerEls();
    if (!el.drawer) return;
    el.mask.classList.remove("wd-open");
    el.drawer.classList.remove("wd-open");
    setTimeout(function() { el.frame.src = "about:blank"; }, 240);
  }
  document.addEventListener("click", function(e) {
    var p = e.target.closest ? e.target.closest(".wd-preview-link") : null;
    if (p) {
      e.preventDefault();
      show(p.getAttribute("data-rid"), p.getAttribute("data-name"));
      return;
    }
    if (e.target.id === "wd-drawer-mask" ||
        (e.target.closest && e.target.closest("#wd-drawer-close"))) {
      hide();
    }
  });
  document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") hide();
  });
}
"""


def _drawer_shell_html() -> str:
    """抽屉骨架（含当前语言标签）。静态组件，构建时渲染一次，不随后续刷新重建。"""
    return (
        '<div class="wd-drawer-mask" id="wd-drawer-mask"></div>'
        '<div class="wd-drawer" id="wd-drawer" role="dialog" aria-modal="true">'
        '<div class="wd-drawer-head">'
        f'<span class="wd-drawer-title" id="wd-drawer-title">{uc.esc(tr("drawer_title"))}</span>'
        f'<a id="wd-drawer-open" href="#" target="_blank" rel="noopener">{uc.esc(tr("drawer_open_page"))}</a>'
        f'<button type="button" id="wd-drawer-close">{uc.esc(tr("drawer_close"))}</button>'
        '</div>'
        '<div class="wd-drawer-body"><iframe id="wd-drawer-frame" title="preview"></iframe></div>'
        '</div>'
    )


def _history_list_html(records, total, filtered):
    """历史列表：桌面表格 + 移动卡片双渲染（CSS 切换）。"""
    if not records:
        if filtered:
            empty = uc.empty_state(tr("empty_filtered"), tr("empty_filtered_desc"))
        else:
            empty = (uc.empty_state(tr("empty_no_data"), tr("empty_no_data_desc"),
                                    _UPLOAD_ICON_SVG))
        return empty

    header = [tr("hdr_id"), tr("hdr_timestamp"), tr("hdr_image"), tr("hdr_risk"),
              tr("hdr_damage"), tr("hdr_damage_type"), tr("hdr_component"),
              tr("hdr_priority"), tr("hdr_confidence"), tr("hdr_infer_time")]
    preview_label = uc.esc(tr("preview_btn"))
    rows, cards = [], []
    for r in records:
        rid = r["id"]
        high = bool(r["high_risk"])
        row_cls = ' class="wd-row-danger"' if high else ""
        src_tag = (f' <span class="wd-badge wd-badge-muted">{tr("badge_migrated")}</span>'
                   if r.get("source") == "migration" else "")
        preview = (f'<span class="wd-preview-link" data-rid="{rid}" '
                   f'data-name="{uc.esc(r["image_name"])}">🔍 {preview_label}</span>')
        cells = [
            f'<td class="wd-num">{rid}</td>',
            f'<td class="wd-num">{uc.esc(r["timestamp"])}</td>',
            f"<td>{uc.esc(r['image_name'])}{src_tag}{preview}</td>",
            f"<td>{_risk_badge_cell(high)}</td>",
            f"<td>{uc.risk_badge(tr_value(r['has_damage'])) if r['has_damage'] else '—'}</td>",
            f"<td>{uc.esc(tr_value(r['damage_type'])) if r['damage_type'] else '—'}</td>",
            f"<td>{uc.esc(tr_value(r['component'])) if r['component'] else '—'}</td>",
            f"<td>{uc.risk_badge(tr_value(r['priority'])) if r['priority'] else '—'}</td>",
            f"<td>{uc.esc(tr_value(r['confidence'])) if r['confidence'] else '—'}</td>",
            f'<td class="wd-num">{r["infer_time"] or "—"}s</td>',
        ]
        rows.append(f"<tr{row_cls}>{''.join(cells)}</tr>")

        meta = (f'{tr("card_time")}: {uc.esc(r["timestamp"])} · '
                f'{tr("summary_priority")}: {uc.esc(tr_value(r["priority"]) or "—")} · '
                f'{r["infer_time"] or "—"}s')
        cards.append(uc.mobile_history_card(
            _risk_badge_cell(high), r["image_name"], meta,
            f"/history/{rid}", tr("btn_view_detail"), danger=high,
            preview_html=(f'<a class="wd-preview-link" data-rid="{rid}" '
                          f'data-name="{uc.esc(r["image_name"])}" href="#">'
                          f'🔍 {preview_label}</a>')))

    return (
        f'<div class="wd-total-count" style="margin:0 0 10px;">'
        f'{tr("filter_total", n=total)}</div>'
        f'<div class="wd-desktop-only">{uc.data_table(header, "".join(rows))}</div>'
        f'<div class="wd-mobile-only">{"".join(cards)}</div>'
    )


def query_history(search, risk, date_from, date_to, sort, page_size, page,
                  request: gr.Request = None):
    """按筛选/排序/分页查询历史。返回 (stats_html, list_html, page_info, dd_update, status)。"""
    search = (search or "").strip()
    date_from = (date_from or "").strip()
    date_to = (date_to or "").strip()
    if (date_from and not _valid_date(date_from)) or (date_to and not _valid_date(date_to)):
        return "", tr("msg_invalid_date"), tr("page_info", page=1, pages=1, total=0), gr.update(), ""

    user_id, is_admin = _current_scope(request)
    if user_id is None and not is_admin:
        # 未登录：绝不返回全量数据（scope=None 会被当作 admin 视角）
        return "", uc.empty_state(tr("auth_need_login"), ""), \
               tr("page_info", page=1, pages=1, total=0), gr.update(), ""
    scope = None if is_admin else user_id
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = 20
    page = max(1, int(page or 1))

    rows, total = query_records(
        limit=page_size, offset=(page - 1) * page_size, owner_user_id=scope,
        search=search, risk=risk or "", date_from=date_from, date_to=date_to,
        sort=sort or "time_desc")
    pages = max(1, -(-total // page_size))
    if page > pages:
        page = pages
        rows, total = query_records(
            limit=page_size, offset=(page - 1) * page_size, owner_user_id=scope,
            search=search, risk=risk or "", date_from=date_from, date_to=date_to,
            sort=sort or "time_desc")

    stats = get_stats(scope)
    stats_html = (
        '<div class="wd-stats">'
        + uc.stat_card(stats["total"], tr("stat_total"))
        + uc.stat_card(stats["high_risk"], tr("stat_high_risk"), tone="danger")
        + uc.stat_card(stats["damaged"], tr("stat_damaged"), tone="warn")
        + uc.stat_card(stats["normal"], tr("stat_normal"), tone="success")
        + "</div>"
    )
    filtered = bool(search or risk or date_from or date_to)
    list_html = _history_list_html(rows, total, filtered)
    page_info = tr("page_info", page=page, pages=pages, total=total)

    choices = []
    for r in rows:
        prio = tr_value(r["priority"]) if r["priority"] else "—"
        label = f'#{r["id"]} | {r["image_name"]} | {tr("badge_high_risk") if r["high_risk"] else tr("badge_normal")} | {prio}'
        choices.append((label, str(r["id"])))
    dd_update = gr.update(choices=choices, value=None)

    return stats_html, list_html, page_info, dd_update, ""


def _quick_range(days):
    """快捷日期范围 → (from, to)。"""
    today = time.strftime("%Y-%m-%d")
    if days <= 0:
        return today, today
    d = time.strftime("%Y-%m-%d", time.localtime(time.time() - days * 86400))
    return d, today


def refresh_history():
    """刷新（保持与旧接口兼容的包装）：全量第一页。"""
    stats_html, list_html, page_info, dd, _ = query_history("", "", "", "", "time_desc", 20, 1)
    chart_html = charts_html()
    return stats_html, list_html, page_info, dd, chart_html


def view_history_detail(record_id_str, request: gr.Request = None):
    """查看单条历史记录详情（含独立页链接、备注回填）。"""
    empty_json = ""
    if not record_id_str or not str(record_id_str).strip().isdigit():
        return uc.status_banner(tr("msg_invalid_id"), "warn"), empty_json, ""

    user_id, is_admin = _current_scope(request)
    record = get_record(int(str(record_id_str).strip()))
    if not record:
        return uc.status_banner(tr("msg_record_not_found", id=record_id_str), "error"), empty_json, ""
    if not can_access(record, user_id, is_admin):
        return uc.status_banner(tr("msg_record_no_access"), "error"), empty_json, ""

    report = json.loads(record["json_report"])
    detail_html, formatted = _build_result_html(report, meta={
        "record_id": record["id"],
        "timestamp": record["timestamp"],
        "infer_time": record["infer_time"] or 0,
    })
    link = (f'<div style="margin-bottom:10px;">'
            f'<a class="wd-backlink" href="/history/{record["id"]}" target="_blank">'
            f'{tr("open_full_page")}</a></div>')
    return _record_image_html(record) + link + detail_html, \
        formatted["json_str"], record.get("note") or ""


def save_note(record_id_str, note, request: gr.Request = None):
    """保存所选记录的备注（校验归属权限）。"""
    if not record_id_str or not str(record_id_str).strip().isdigit():
        return tr("msg_invalid_id")
    user_id, is_admin = _current_scope(request)
    record = get_record(int(str(record_id_str).strip()))
    if not record or not can_access(record, user_id, is_admin):
        return tr("msg_record_no_access")
    update_note(record["id"], note or "")
    return tr("msg_note_saved")


def copy_json(json_str):
    """复制 JSON 到剪贴板（返回提示文字）。"""
    if json_str:
        return tr("msg_copied")
    return tr("msg_no_json")


def ask_delete_record(record_id_str, request: gr.Request = None):
    """单条删除第一步：显示确认条（分级确认：单条不需勾选，但需二次点击）。"""
    if not record_id_str or not str(record_id_str).strip().isdigit():
        return tr("msg_invalid_id"), gr.update(visible=False)
    rid = int(str(record_id_str).strip())
    rec = get_record(rid)
    user_id, is_admin = _current_scope(request)
    if not rec or not can_access(rec, user_id, is_admin):
        return tr("msg_record_no_access"), gr.update(visible=False)
    name = rec["image_name"]
    msg = f"⚠️ {tr('msg_delete_confirm_one', id=rid, name=uc.esc(name))}"
    return (f'<div class="wd-banner" style="margin-bottom:0;">'
            f'<span class="wd-banner-text">{msg}</span></div>'), gr.update(visible=True)


def do_delete_record(record_id_str, request: gr.Request = None):
    """单条删除第二步：确认后执行删除并刷新。"""
    if record_id_str and str(record_id_str).strip().isdigit():
        rid = int(str(record_id_str).strip())
        user_id, is_admin = _current_scope(request)
        rec = get_record(rid)
        if rec and can_access(rec, user_id, is_admin):
            delete_record(rid)
            status = tr("msg_deleted_one", id=rid)
        else:
            status = tr("msg_record_no_access")
    else:
        status = tr("msg_invalid_id")
    stats_html, list_html, page_info, dd, _ = query_history(
        "", "", "", "", "time_desc", 20, 1, request=request)
    return stats_html, list_html, page_info, dd, gr.update(visible=False), status


def do_clear_history(typed, request: gr.Request = None):
    """清空记录第一步：校验确认文字，弹出二次确认条（不执行删除）。

    权限模型：admin 清空全库；普通用户只清空自己的记录。
    返回 (confirm_row_update, confirm_banner_html, filter_status)。
    """
    typed = (typed or "").strip()
    user_id, is_admin = _current_scope(request)
    if user_id is None and not is_admin:
        return gr.update(visible=False), "", tr("auth_need_login")
    scope = None if is_admin else user_id
    total = get_stats(scope)["total"]
    if total == 0:
        return gr.update(visible=False), "", tr("msg_confirm_first")
    if typed != tr("clear_typed_word"):
        return gr.update(visible=False), "", tr("msg_clear_typed_wrong")
    banner = ('<div class="wd-banner" style="margin-bottom:8px;">'
              '<span class="wd-banner-text" style="color:var(--danger-deep);">'
              f'{uc.esc(tr("clear_confirm_banner"))}</span></div>')
    return gr.update(visible=True), banner, tr("msg_clear_need_confirm")


def do_clear_confirm(request: gr.Request = None):
    """清空记录第二步：二次确认后执行删除。"""
    user_id, is_admin = _current_scope(request)
    if user_id is None and not is_admin:
        return "", "", "", gr.update(), "", gr.update(visible=False), tr("auth_need_login")
    n = get_stats(None if is_admin else user_id)["total"]
    if is_admin:
        clear_all()
    else:
        clear_user_records(user_id)
    stats_html, list_html, page_info, dd, _ = query_history(
        "", "", "", "", "time_desc", 20, 1, request=request)
    return (stats_html, list_html, page_info, dd, "",
            gr.update(visible=False), tr("msg_deleted_n", n=n))


# ══════════════════════════════════════════════════════════
#  Tab 3: 报告导出（四格式 + 内容预设 + 任务中心，§11）
# ══════════════════════════════════════════════════════════

_TASK_BADGES = {
    "pending": ("muted", "task_status_pending"),
    "running": ("muted", "task_status_running"),
    "done": ("success", "task_status_done"),
    "failed": ("danger", "task_status_failed"),
    "expired": ("warn", "task_status_expired"),
}


def _tasks_list_html(tasks):
    """导出任务表：文件 · 格式 · 创建时间 · 状态 · 过期时间。"""
    if not tasks:
        return uc.empty_state(tr("tasks_none"), "")
    rows = []
    for t in tasks:
        tone, status_key = _TASK_BADGES.get(t["status"], ("muted", t["status"]))
        status = f'<span class="wd-badge wd-badge-{tone}">{tr(status_key)}</span>'
        if t["status"] == "failed" and t["error"]:
            status += f'<div style="font-size:12px;color:#C0392B;">{uc.esc(t["error"])}</div>'
        expires = (tr("task_expires_note", date=(t["expires_at"] or "")[:16])
                   if t["expires_at"] else "—")
        fname = os.path.basename(t["file_path"] or f"task-{t['id']}")
        rows.append(
            "<tr>"
            f"<td>{uc.esc(fname)}</td>"
            f'<td>{t["fmt"].upper()}</td>'
            f"<td class='wd-num'>{uc.esc(t['created_at'] or '—')}</td>"
            f"<td>{status}</td>"
            f"<td class='wd-num'>{uc.esc(expires)}</td>"
            "</tr>")
    header = [tr("tasks_col_file"), tr("tasks_col_fmt"), tr("tasks_col_created"),
              tr("tasks_col_status"), tr("tasks_col_expires")]
    return uc.data_table(header, "".join(rows))


def _task_dd_update(tasks):
    choices = []
    for t in tasks:
        label = (f'#{t["id"]} | {os.path.basename(t["file_path"] or "")} | '
                 f'{tr(_TASK_BADGES.get(t["status"], ("", t["status"]))[1])}')
        choices.append((label, str(t["id"])))
    return gr.update(choices=choices, value=None)


def _resolve_request_scope(request=None):
    user_id, is_admin = _current_scope(request)
    return user_id, is_admin


def _lang_code(sel: str):
    """报告语言选择 → i18n 语言码；auto=跟随界面。"""
    return None if sel == "auto" else sel


def start_export_task(fmt, preset, lang_sel, record_id_str, request: gr.Request = None):
    """开始导出：校验记录权限 → 建任务 → 同步执行 → 刷新任务列表。"""
    user_id, is_admin = _resolve_request_scope(request)
    if user_id is None and not is_admin:
        return tr("auth_need_login"), "", gr.update(), ""
    if not record_id_str or not str(record_id_str).strip().isdigit():
        return tr("export_msg_need_record"), "", gr.update(), ""

    rid = int(str(record_id_str).strip())
    record = get_record(rid)
    if not record or not can_access(record, user_id, is_admin):
        return tr("export_msg_no_access"), "", gr.update(), ""

    fmt = (fmt or "pdf").split(" ")[0].lower()
    if fmt not in xt.FORMATS:
        fmt = "pdf"
    preset = preset or "standard"
    tid = xt.create_task(user_id, rid, fmt, preset)
    task = xt.run_task(tid, user_id, is_admin)
    if task["status"] == "failed":
        err = task["error"] or ""
        msg = tr("export_msg_failed", error=tr(err) if err in i18n.UI[i18n.LANG] else err)
    else:
        msg = tr("export_msg_done")
    tasks = xt.list_tasks(None if is_admin else user_id)
    return msg, _tasks_list_html(tasks), _task_dd_update(tasks), ""


def refresh_tasks(request: gr.Request = None):
    """刷新导出任务列表。"""
    user_id, is_admin = _resolve_request_scope(request)
    tasks = xt.list_tasks(None if is_admin else user_id)
    return _tasks_list_html(tasks), _task_dd_update(tasks), ""


def download_task(task_id_str, request: gr.Request = None):
    """下载任务文件（过期/丢失文件给明确提示，不给死链）。"""
    user_id, is_admin = _resolve_request_scope(request)
    if not task_id_str or not str(task_id_str).strip().isdigit():
        return None, tr("msg_task_need_select")
    task = xt.get_task(int(str(task_id_str).strip()))
    if not task or (not is_admin and task["user_id"] != user_id):
        return None, tr("msg_task_forbidden")
    if task["status"] == "expired" or not task["file_path"] \
            or not os.path.exists(task["file_path"]):
        return None, tr("task_status_expired") + "：" + tr("btn_task_retry")
    return task["file_path"], tr("msg_task_download_done")


def retry_export_task(task_id_str, request: gr.Request = None):
    """重新生成失败/过期任务。"""
    user_id, is_admin = _resolve_request_scope(request)
    if not task_id_str or not str(task_id_str).strip().isdigit():
        return tr("msg_task_need_select"), "", gr.update()
    tid = int(str(task_id_str).strip())
    task = xt.get_task(tid)
    if not task or (not is_admin and task["user_id"] != user_id):
        return tr("msg_task_forbidden"), "", gr.update()
    xt.retry_task(tid, user_id, is_admin)
    tasks = xt.list_tasks(None if is_admin else user_id)
    return tr("users_msg_done"), _tasks_list_html(tasks), _task_dd_update(tasks)


def delete_export_task(task_id_str, request: gr.Request = None):
    """删除任务记录（user 仅限本人任务）。返回 (状态, 任务列表, 下拉更新, 确认行隐藏)。"""
    user_id, is_admin = _resolve_request_scope(request)
    if not task_id_str or not str(task_id_str).strip().isdigit():
        return tr("msg_task_need_select"), "", gr.update(), gr.update(visible=False)
    tid = int(str(task_id_str).strip())
    if not xt.delete_task(tid, user_id, is_admin):
        return tr("msg_task_forbidden"), "", gr.update(), gr.update(visible=False)
    tasks = xt.list_tasks(None if is_admin else user_id)
    return tr("msg_task_deleted"), _tasks_list_html(tasks), _task_dd_update(tasks), gr.update(visible=False)


def show_delete_task_confirm(task_id_str):
    """删除任务两步确认第一步：显示确认行（F4，与历史删除同模式）。"""
    if not task_id_str or not str(task_id_str).strip().isdigit():
        return tr("msg_task_need_select"), gr.update(visible=False)
    return (f"⚠️ {tr('task_delete_confirm', id=str(task_id_str).strip())}",
            gr.update(visible=True))


# ══════════════════════════════════════════════════════════
#  Gradio 界面
# ══════════════════════════════════════════════════════════

# 顶栏用户徽章：页面加载后从 /api/me 拉取当前会话用户（server.py 提供）。
# ⚠ 不能写成"fetch 一次然后 getElementById"：Gradio 的自定义 js 在 SPA 引导早期
#   注入执行，fetch 回调常常先于 #wd-user-badge 渲染完成 —— el 为 null 直接
#   return，徽章（用户管理/修改密码/退出登录入口）就永远空白（线上实拍复现）。
#   必须带重试：等元素出现再填，填上即停。
_BADGE_JS = """
() => {
  let done = false;
  let tries = 0;
  const fill = (u) => {
    const el = document.getElementById('wd-user-badge');
    if (!el) return false;
    const role = u.role === 'admin' ? '__ROLE_ADMIN__' : '__ROLE_USER__';
    // 小图标：内联 SVG（Feather 风格描边），尺寸/颜色由 CSS 控制
    const ic = (p) => '<svg class="wd-ub-ic" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + p + '</svg>';
    const IC_USER = ic('<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>');
    const IC_SHIELD = ic('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>');
    const IC_USERS = ic('<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>');
    const IC_KEY = ic('<path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4"/>');
    const IC_OUT = ic('<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/>');
    const IC_GEAR = ic('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>');
    el.innerHTML =
      '<span class="wd-ub-chip">' + IC_USER
      + '<span class="wd-ub-name" title="' + u.username + '">' + u.username + '</span></span>'
      + '<span class="wd-badge wd-badge-muted">' + IC_SHIELD + role + '</span>'
      + (u.role === 'admin' ? '<a class="wd-ub-link" href="/users">' + IC_USERS + '__USERS_LINK__</a>' : '')
      + '<a class="wd-ub-link" href="/change-password">' + IC_KEY + '__PW_LINK__</a>'
      + '<a class="wd-ub-link" href="/logout">' + IC_OUT + '__LOGOUT_LINK__</a>'
      + '<a class="wd-ub-link" href="javascript:void(0)" id="wd-settings-link">' + IC_GEAR + '__SETTINGS_LINK__</a>';
    // "设置"：打开自定义中文显示设置弹层（深浅模式/字号缩放，localStorage 持久化）。
    // 不再使用 Gradio 英文设置面板（其开关是页脚按钮的私有组件状态，无公开路由）。
    const sl = document.getElementById('wd-settings-link');
    if (sl) sl.addEventListener('click', (ev) => {
      ev.preventDefault();
      if (window.__wdToggleSettings) window.__wdToggleSettings();
    });
    return true;
  };
  fetch('/api/me').then(r => r.ok ? r.json() : null).then(u => {
    if (!u || !u.username) return;
    if (fill(u)) { done = true; return; }
    const t = setInterval(() => {
      tries += 1;
      if (fill(u)) { clearInterval(t); done = true; }
      else if (tries > 100) { clearInterval(t); }
    }, 100);
  }).catch(() => {});

  // 等待动效的实时已用时计时：每秒刷新页面上所有 .wd-elapsed（working_banner）。
  // 首次见到某元素时写入 data-start 作为计时起点；元素随生成器换页被重建，
  // data-start 不存在则重新起点，天然支持多次分析。
  if (!window.__wdElapsedTimer) {
    window.__wdElapsedTimer = setInterval(() => {
      const els = document.querySelectorAll('.wd-elapsed');
      for (let i = 0; i < els.length; i++) {
        const el = els[i];
        let st = Number(el.getAttribute('data-start'));
        if (!st) { el.setAttribute('data-start', String(Date.now())); continue; }
        el.textContent = Math.floor((Date.now() - st) / 1000);
      }
      // F3 日期控件：历史筛选的两个文本框升级为原生 date 控件。
      // Gradio 更新值时可能重建输入框，放进每秒心跳里兜底重升级。
      ['wd-date-from', 'wd-date-to'].forEach((id) => {
        const w = document.getElementById(id);
        if (!w) return;
        const inp = w.querySelector('input');
        if (inp && inp.type !== 'date') inp.type = 'date';
      });
    }, 1000);
  }
}
"""


# 显示设置弹层（右上角"设置"打开）：深浅模式 + 字号缩放。
# 不用 Gradio 自带英文设置面板——其开关是页脚按钮的私有 Svelte store 状态，
# 无公开路由、无法从自定义代码稳定编程打开。此弹层纯前端生效：
#   - 深浅模式：Gradio 主题由启动时 ?__theme=dark 一次性决定，运行时改 class
#     不可靠 → 用带参跳转切换，选择存 localStorage('wd_theme')，进入时自动带上；
#   - 字号缩放：调 :root 上的 --wd-fs（BASE_CSS 的 --text-* 均为 calc(px*var(--wd-fs))），
#     存 localStorage('wd_font_scale')，无需刷新即时生效。
def _settings_popover_html() -> str:
    return (
        '<div id="wd-settings-mask" class="wd-settings-mask"></div>\n'
        '<div id="wd-settings-popover" class="wd-settings-popover" '
        f'role="dialog" aria-label="{uc.esc(tr("settings_title"))}">\n'
        '  <div class="wd-sp-head">\n'
        f'    <span class="wd-sp-title">{uc.esc(tr("settings_title"))}</span>\n'
        f'    <button type="button" id="wd-sp-close">{uc.esc(tr("settings_close"))}</button>\n'
        '  </div>\n'
        '  <div class="wd-sp-row">\n'
        f'    <span class="wd-sp-label">{uc.esc(tr("settings_theme"))}</span>\n'
        '    <div class="wd-sp-seg" id="wd-sp-theme">\n'
        f'      <button type="button" data-wd-theme="light">{uc.esc(tr("settings_theme_light"))}</button>\n'
        f'      <button type="button" data-wd-theme="dark">{uc.esc(tr("settings_theme_dark"))}</button>\n'
        '    </div>\n'
        '  </div>\n'
        '  <div class="wd-sp-row">\n'
        f'    <span class="wd-sp-label">{uc.esc(tr("settings_skin"))}</span>\n'
        '    <div class="wd-sp-seg wd-sp-skin" id="wd-sp-skin">\n'
        f'      <button type="button" data-wd-skin="clear">{uc.esc(tr("skin_clear"))}</button>\n'
        f'      <button type="button" data-wd-skin="night">{uc.esc(tr("skin_night"))}</button>\n'
        f'      <button type="button" data-wd-skin="glass">{uc.esc(tr("skin_glass"))}</button>\n'
        f'      <button type="button" data-wd-skin="bento">{uc.esc(tr("skin_bento"))}</button>\n'
        f'      <button type="button" data-wd-skin="hmi">{uc.esc(tr("skin_hmi"))}</button>\n'
        f'      <button type="button" data-wd-skin="hud">{uc.esc(tr("skin_hud"))}</button>\n'
        '    </div>\n'
        '  </div>\n'
        '  <div class="wd-sp-row">\n'
        f'    <label class="wd-sp-label" for="wd-sp-font">{uc.esc(tr("settings_font"))}</label>\n'
        '    <div class="wd-sp-font">\n'
        '      <input type="range" id="wd-sp-font" min="85" max="135" step="5" value="115"/>\n'
        '      <span id="wd-sp-font-val">115%</span>\n'
        f'      <button type="button" id="wd-sp-font-reset">{uc.esc(tr("settings_reset"))}</button>\n'
        '    </div>\n'
        '  </div>\n'
        '</div>'
    )


# 弹层逻辑（与徽章脚本同批注入 head，IIFE 组合见 build_ui 尾部）：
#   - 启动时先应用持久化偏好（字号即时、深浅模式按需带参跳转）；
#   - 弹层元素由 gr.HTML 渲染，时机不确定 → 绑定带重试（同徽章做法）。
_SETTINGS_POPOVER_JS = """
() => {
  var store = null;
  try { store = window.localStorage; } catch (e) { store = null; }
  function get(k) { try { return store ? store.getItem(k) : null; } catch (e) { return null; } }
  function set(k, v) {
    try {
      if (!store) return;
      if (v === null) store.removeItem(k); else store.setItem(k, v);
    } catch (e) {}
  }

  // ── 字号缩放：设 --wd-fs 即时生效 ──
  function applyFont(v) {
    document.documentElement.style.setProperty('--wd-fs', String(v));
  }
  var fs = parseFloat(get('wd_font_scale'));
  if (!isFinite(fs) || fs < 0.85 || fs > 1.35) fs = 1.15;
  applyFont(fs);

  // ── 深浅模式：Gradio 主题由 ?__theme= 启动时决定 → 不一致就带参跳转一次 ──
  var hasDark = new URLSearchParams(location.search).get('__theme') === 'dark';
  var savedTheme = get('wd_theme');
  if ((savedTheme === 'dark') !== hasDark) {
    var u0 = new URL(location.href);
    if (savedTheme === 'dark') u0.searchParams.set('__theme', 'dark');
    else u0.searchParams.delete('__theme');
    location.replace(u0.toString());
    return; // 跳转中，后续初始化在新页面继续
  }
  var curDark = hasDark;

  // ── 界面风格（五主题皮肤）：html[data-wd-theme] 即时切换，localStorage 持久化 ──
  var SKINS = ['clear', 'night', 'glass', 'bento', 'hmi', 'hud'];
  // 把主题广播给 3D 风机 viewer（iframe 内换天空/草地/HUD 配色）。
  // viewer iframe 可能晚于本脚本加载，故除即时发送外再延迟重发两次。
  function postTheme(name) {
    var frames = document.querySelectorAll('.wd-turbine-frame iframe, #wd-bg-viewer');
    Array.prototype.forEach.call(frames, function (f) {
      try { f.contentWindow.postMessage({wdTheme: name}, '*'); } catch (err) {}
    });
  }
  function applySkin(name) {
    if (SKINS.indexOf(name) < 0) name = 'clear';
    if (name === 'clear') {
      document.documentElement.removeAttribute('data-wd-theme');
    } else {
      document.documentElement.setAttribute('data-wd-theme', name);
    }
    postTheme(name);
    moveViewerForSkin(name);
    setTimeout(function () { postTheme(name); }, 1500);
    setTimeout(function () { postTheme(name); }, 5000);
  }
  // ── HUD 全屏背景：viewer（含风机模型与复位按钮等自带界面）留在
  //    中栏槽位，布局即最初的左中右三栏；另建一个纯风景 iframe 固定
  //    在页面最底层当背景（?bg=1：隐藏主风机与自带 HUD，只渲染天空/
  //    草地/远景风机）。模型 iframe 从不移动 DOM——彻底避免移动触发
  //    的重载与滚动坐标同步问题。切到其他皮肤时移除背景层。──
  var BG_ID = 'wd-bg-viewer';
  function removeBgViewer() {
    var f = document.getElementById(BG_ID);
    if (f) f.parentNode.removeChild(f);
  }
  function ensureBgViewer() {
    if (document.getElementById(BG_ID)) return true;
    if (!document.body) return false;
    var f = document.createElement('iframe');
    f.id = BG_ID;
    f.src = '/wd-assets/wind_turbine_viewer.html?bg=1';
    f.title = '背景';
    document.body.appendChild(f);
    return true;
  }
  window.addEventListener('message', function (ev) {
    // 背景层加载完成后补发主题（加载前 postMessage 会丢）
    if (ev.data && ev.data.wdViewerReady) postTheme(nameSafe());
  });
  function nameSafe() {
    return document.documentElement.getAttribute('data-wd-theme') || 'hud';
  }
  function moveViewerForSkin(name) {
    if (name !== 'hud') { removeBgViewer(); return; }
    var n = 0;
    var t = setInterval(function () {
      if (ensureBgViewer() || ++n >= 40) clearInterval(t);
    }, 501);
  }
  function refreshSkinBtns() {
    var box = document.getElementById('wd-sp-skin');
    if (!box) return;
    var cur = document.documentElement.getAttribute('data-wd-theme') || 'clear';
    Array.prototype.forEach.call(box.querySelectorAll('button'), function (b) {
      b.classList.toggle('wd-active', b.getAttribute('data-wd-skin') === cur);
    });
  }
  applySkin(get('wd_skin') || 'hud');
  refreshSkinBtns();

  // ── 弹层开合与控件绑定（元素渲染完成前重试） ──
  var tries = 0;
  function refreshThemeBtns() {
    var box = document.getElementById('wd-sp-theme');
    if (!box) return;
    Array.prototype.forEach.call(box.querySelectorAll('button'), function (b) {
      var isCur = (b.getAttribute('data-wd-theme') === 'dark') === curDark;
      b.classList.toggle('wd-active', isCur);
    });
  }
  function gotoTheme(dark) {
    if (dark === curDark) return;
    set('wd_theme', dark ? 'dark' : null);
    var u = new URL(location.href);
    if (dark) u.searchParams.set('__theme', 'dark');
    else u.searchParams.delete('__theme');
    location.replace(u.toString());
  }
  function bind() {
    var pop = document.getElementById('wd-settings-popover');
    var mask = document.getElementById('wd-settings-mask');
    if (!pop || !mask) return false;
    window.__wdToggleSettings = function () {
      var open = pop.classList.toggle('wd-open');
      mask.classList.toggle('wd-open', open);
      if (open) { refreshThemeBtns(); refreshSkinBtns(); }
    };
    mask.addEventListener('click', function () { window.__wdToggleSettings(); });
    var closeBtn = document.getElementById('wd-sp-close');
    if (closeBtn) closeBtn.addEventListener('click', function () { window.__wdToggleSettings(); });
    var themeBox = document.getElementById('wd-sp-theme');
    if (themeBox) themeBox.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('button[data-wd-theme]') : null;
      if (b) gotoTheme(b.getAttribute('data-wd-theme') === 'dark');
    });
    var skinBox = document.getElementById('wd-sp-skin');
    if (skinBox) skinBox.addEventListener('click', function (ev) {
      var b = ev.target.closest ? ev.target.closest('button[data-wd-skin]') : null;
      if (!b) return;
      var s = b.getAttribute('data-wd-skin') || 'clear';
      applySkin(s);
      set('wd_skin', s === 'clear' ? null : s);
      refreshSkinBtns();
    });
    var range = document.getElementById('wd-sp-font');
    var val = document.getElementById('wd-sp-font-val');
    if (range) {
      range.value = String(Math.round(fs * 100));
      if (val) val.textContent = Math.round(fs * 100) + '%';
      range.addEventListener('input', function () {
        var v = parseInt(range.value, 10) / 100;
        fs = v; applyFont(v);
        if (val) val.textContent = range.value + '%';
        set('wd_font_scale', v === 1.15 ? null : String(v));
      });
    }
    var reset = document.getElementById('wd-sp-font-reset');
    if (reset) reset.addEventListener('click', function () {
      fs = 1.15; applyFont(1.15); set('wd_font_scale', null);
      if (range) range.value = '115';
      if (val) val.textContent = '115%';
    });
    return true;
  }
  if (!bind()) {
    var t = setInterval(function () {
      tries += 1;
      if (bind() || tries > 100) clearInterval(t);
    }, 100);
  }
  refreshThemeBtns();
}
"""


def build_ui():
    badge_js = (_BADGE_JS
                .replace("__ROLE_ADMIN__", tr("users_role_admin"))
                .replace("__ROLE_USER__", tr("users_role_user"))
                .replace("__USERS_LINK__", tr("users_link"))
                .replace("__PW_LINK__", tr("pw_link"))
                .replace("__LOGOUT_LINK__", tr("btn_logout"))
                .replace("__SETTINGS_LINK__", tr("settings_link")))
    with gr.Blocks(title=tr("app_title")) as app:
        # 固定全屏动态风场：蓝天、云层、摆动草地与旋转的远景风机。
        # iframe 与主工作台隔离，避免 Three.js 动画影响 Gradio 组件重绘。
        gr.HTML(
            '<div class="wd-dynamic-bg-host" aria-hidden="true">'
            '<iframe src="/wd-assets/dynamic_wind_farm.html?v=2" tabindex="-1" '
            'title=""></iframe></div>'
        )
        # 顶栏用户徽章（内容由 _BADGE_JS 注入）
        gr.HTML('<div id="wd-user-badge" class="wd-user-badge"></div>')
        # 显示设置弹层（右上角"设置"打开；深浅模式 + 字号缩放，localStorage 持久化）
        gr.HTML(_settings_popover_html())
        # 标题（含 SVG 风电机组图标，居中）
        gr.Markdown(
            "<div class='main-title'>"
            "<h1><span class='title-icon'>"
            "<svg width='38' height='38' viewBox='0 0 64 64' xmlns='http://www.w3.org/2000/svg'>"
            "<circle cx='32' cy='32' r='30' fill='#EBF5FB' stroke='#125191' stroke-width='1.5'/>"
            "<rect x='29.5' y='36' width='5' height='22' fill='#7F8C8D'/>"
            "<rect x='23' y='30' width='18' height='8' rx='2' fill='#5DADE2'/>"
            "<circle cx='32' cy='28' r='3.5' fill='#34495E'/>"
            "<g fill='#F1F8FD' stroke='#5DADE2' stroke-width='0.8'>"
            "<path d='M32 28 L38 10 A5 5 0 0 1 44 8 L46 16 Z'/>"
            "<path d='M32 28 L14 18 A5 5 0 0 1 10 12 L20 9 Z'/>"
            "<path d='M32 28 L42 42 A5 5 0 0 1 41 48 L32 44 Z'/>"
            "</g>"
            "</svg></span>" + tr("app_title") + "</h1>"
            "</div>"
        )

        with gr.Tabs():
            # ─── Tab 1: 单图检测 ────────────────────────────
            with gr.TabItem(tr("tab_single")):
                with gr.Row(equal_height=False, elem_classes=["wd-workbench-grid"]):
                    # 左：检测图像输入与操作
                    with gr.Column(scale=20, min_width=300, elem_classes=["wd-workbench-col", "wd-input-col"]):
                        gr.Markdown("### 原始检测图片")
                        img_input = gr.Image(
                            label=tr("upload_label"),
                            type="filepath",
                            height=330,
                        )
                        img_info_text = gr.Textbox(
                            label=tr("img_info_label"), interactive=False,
                            value=tr("img_info_default")
                        )
                        with gr.Row():
                            btn_analyze = gr.Button(tr("btn_analyze"), variant="primary", size="lg")
                            btn_clear = gr.Button(tr("btn_clear"), size="lg")

                        gr.Markdown(tr("examples_section"))
                        examples = []
                        if os.path.exists(IMAGE_DIR):
                            for i in range(1, 21):
                                img = os.path.join(IMAGE_DIR, f"{i:06d}.jpg")
                                if os.path.exists(img):
                                    examples.append([img])
                        if examples:
                            gr.Examples(examples=examples, inputs=img_input, label=tr("examples_label") % len(examples),
                                        examples_per_page=10)

                        status_text = gr.HTML(value="")
                        with gr.Row(elem_classes=["wd-export-row"]):
                            btn_export_md = gr.Button(tr("btn_export_md"), elem_classes=["wd-export-btn"])
                            btn_export_json = gr.Button(tr("btn_export_json"), elem_classes=["wd-export-btn"])
                            btn_copy_json = gr.Button(tr("btn_copy_json"), elem_classes=["wd-export-btn"])
                        export_md_file = gr.File(label=tr("md_report_label"), interactive=False)
                        export_json_file = gr.File(label=tr("json_report_label"), interactive=False)

                    # 中：WTA 方案中的程序化 Three.js 风机与损伤定位
                    with gr.Column(scale=58, min_width=0, elem_classes=["wd-workbench-col", "wd-model-col"]):
                        gr.Markdown("### 风机三维损伤定位")
                        turbine_viewer = gr.HTML(
                            value=_viewer_bridge_html(),
                            elem_classes=["wd-turbine-viewer"],
                        )

                    # 右：模型检测报告
                    with gr.Column(scale=22, min_width=340, elem_classes=["wd-workbench-col", "wd-report-col"]):
                        gr.Markdown("### 模型检测报告")
                        summary_md = gr.Markdown(tr("waiting_summary"))
                        detail_html = gr.HTML(
                            value=EMPTY_RESULT_HTML,
                            elem_classes=["wd-report-output"],
                        )
                        with gr.Accordion(tr("json_accordion"), open=False):
                            json_out = gr.Code(language="json", label=tr("json_raw_label"), interactive=False)

            # ─── Tab 2: 批量检测 ────────────────────────────
            with gr.TabItem(tr("tab_batch")):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown(tr("batch_upload_section"))
                        batch_input = gr.Files(
                            label=tr("batch_label"),
                            file_count="multiple",
                        )
                        btn_batch = gr.Button(tr("btn_batch"), variant="primary", size="lg")
                        batch_status = gr.HTML(value="")

                    with gr.Column(scale=2):
                        batch_summary = gr.Markdown(tr("batch_waiting"))
                        batch_html = gr.HTML(value=EMPTY_RESULT_HTML)
                        with gr.Row():
                            btn_batch_export_csv = gr.Button(tr("btn_batch_export_csv"))
                            btn_batch_export_md = gr.Button(tr("btn_batch_export_md"))
                        batch_export_file = gr.File(label=tr("batch_file_label"), interactive=False)

            # ─── Tab 3: 历史记录 ────────────────────────────
            with gr.TabItem(tr("tab_history")):
                # 筛选区
                with gr.Row(equal_height=True):
                    search_tb = gr.Textbox(label=tr("filter_search_label"),
                                           placeholder=tr("filter_search_ph"), scale=2)
                    risk_dd = gr.Dropdown(
                        label=tr("filter_risk_label"), choices=[
                            (tr("filter_risk_all"), ""),
                            (tr("filter_risk_high"), "high"),
                            (tr("filter_risk_normal"), "normal"),
                        ], value="", scale=1)
                    sort_dd = gr.Dropdown(
                        label=tr("sort_label"), choices=[
                            (tr("sort_time_desc"), "time_desc"),
                            (tr("sort_time_asc"), "time_asc"),
                            (tr("sort_risk"), "risk_desc"),
                            (tr("sort_time_cost"), "infer_time_desc"),
                        ], value="time_desc", scale=1)
                    pagesize_dd = gr.Dropdown(
                        label=tr("pagesize_label"),
                        choices=[("20", "20"), ("50", "50")], value="20", scale=1)
                with gr.Row(equal_height=True):
                    # 日期筛选：elem_id 供前端心跳脚本把文本框升级为原生
                    # <input type="date"> 日期控件（F3），值格式不变（YYYY-MM-DD）
                    date_from_tb = gr.Textbox(label=tr("filter_date_from"),
                                              placeholder=tr("date_ph"), scale=1,
                                              elem_id="wd-date-from")
                    date_to_tb = gr.Textbox(label=tr("filter_date_to"),
                                            placeholder=tr("date_ph"), scale=1,
                                            elem_id="wd-date-to")
                    btn_quick_today = gr.Button(tr("quick_today"), size="sm")
                    btn_quick_7d = gr.Button(tr("quick_7d"), size="sm")
                    btn_quick_30d = gr.Button(tr("quick_30d"), size="sm")
                    btn_apply = gr.Button(tr("btn_apply_filter"), variant="primary")
                    btn_refresh = gr.Button(tr("btn_refresh"))
                    btn_reset_filter = gr.Button(tr("btn_reset_filter"))

                filter_status = gr.HTML(value="")
                history_stats = gr.HTML(value=tr("history_hint"))
                history_list = gr.HTML(value="")
                with gr.Row(equal_height=True):
                    btn_prev_page = gr.Button(tr("btn_prev_page"), size="sm")
                    page_info_html = gr.HTML(value="")
                    btn_next_page = gr.Button(tr("btn_next_page"), size="sm")
                history_charts = gr.HTML(value=tr("charts_hint"))
                page_state = gr.State(value=1)

                # 详情 / 删除
                gr.Markdown(tr("detail_section"))
                with gr.Row(equal_height=True):
                    history_record_dd = gr.Dropdown(
                        label=tr("history_select_label"),
                        choices=[], interactive=True,
                        info=tr("history_select_hint"), scale=3)
                    btn_view_detail = gr.Button(tr("btn_view_detail"), variant="primary", scale=1)
                    btn_delete_one = gr.Button(tr("btn_delete_one"),
                                               elem_classes=["wd-btn-danger"], scale=1)
                confirm_row = gr.Row(visible=False)
                with confirm_row:
                    confirm_md = gr.HTML(value="")
                    btn_delete_confirm = gr.Button(tr("btn_delete_confirm"),
                                                   variant="stop",
                                                   elem_classes=["wd-btn-danger"])
                    btn_delete_cancel = gr.Button(tr("btn_delete_cancel"))

                history_detail = gr.HTML(value=tr("detail_hint"))
                with gr.Accordion(tr("json_accordion2"), open=False):
                    history_json = gr.Code(language="json", interactive=False)

                # 抽屉快捷预览骨架（静态渲染一次；交互 JS 由页面加载脚本注入）
                gr.HTML(value=_drawer_shell_html())

                with gr.Row(equal_height=True):
                    note_tb = gr.Textbox(label=tr("note_label"), lines=2, scale=3)
                    btn_save_note = gr.Button(tr("btn_save_note"), scale=1)

                # ─── 报告导出（§11：分裂选择 + 内容预设 + 任务中心）───
                with gr.Accordion(tr("export_section"), open=False):
                    with gr.Row(equal_height=True):
                        export_fmt_dd = gr.Dropdown(
                            label=tr("export_fmt_label"), scale=2,
                            choices=[
                                (tr("fmt_pdf"), "pdf"),
                                (tr("fmt_docx"), "docx"),
                                (tr("fmt_xlsx"), "xlsx"),
                                (tr("fmt_csv"), "csv"),
                            ], value="pdf")
                        export_preset_dd = gr.Dropdown(
                            label=tr("export_preset_label"), scale=2,
                            choices=[
                                (tr("preset_standard_short"), "standard"),
                                (tr("preset_brief_short"), "brief"),
                                (tr("preset_full_short"), "full"),
                            ], value="standard")
                        export_lang_dd = gr.Dropdown(
                            label=tr("export_lang_label"), scale=1,
                            choices=[
                                (tr("export_lang_auto"), "auto"),
                                (tr("export_lang_zh"), "zh"),
                                (tr("export_lang_en"), "en"),
                            ], value="auto")
                        btn_export_report = gr.Button(
                            tr("btn_start_export"), variant="primary", scale=1)
                    export_status = gr.HTML(value="")

                    gr.Markdown(f"**{tr('export_center_title')}**")
                    tasks_list = gr.HTML(value=tr("tasks_none"))
                    with gr.Row(equal_height=True):
                        task_dd = gr.Dropdown(
                            label=tr("task_select_label"), choices=[],
                            interactive=True, scale=3)
                        btn_task_refresh = gr.Button(tr("btn_task_refresh"), scale=1)
                    with gr.Row(equal_height=True):
                        task_download_file = gr.File(
                            label=tr("btn_task_download"), interactive=False, scale=2)
                        btn_task_download = gr.Button(tr("btn_task_download"), scale=1)
                        btn_task_retry = gr.Button(tr("btn_task_retry"), scale=1)
                        btn_task_delete = gr.Button(
                            tr("btn_task_delete"), elem_classes=["wd-btn-danger"], scale=1)
                    # 删除任务两步确认（F4，与历史删除同模式）
                    task_confirm_row = gr.Row(visible=False)
                    with task_confirm_row:
                        task_confirm_md = gr.HTML(value="")
                        btn_task_del_confirm = gr.Button(
                            tr("btn_delete_confirm"), variant="stop",
                            elem_classes=["wd-btn-danger"])
                        btn_task_del_cancel = gr.Button(tr("btn_delete_cancel"))

                # 清空（分级删除最高档：输入确认文字 + 二次确认）
                with gr.Accordion(tr("btn_clear_history"), open=False):
                    gr.HTML(value=(
                        '<div class="wd-banner" style="margin-bottom:12px;">'
                        '<span class="wd-banner-text" '
                        'style="color:var(--danger-deep);">'
                        f'{uc.esc(tr("clear_warning"))}</span></div>'))
                    with gr.Row(equal_height=True):
                        clear_typed_tb = gr.Textbox(
                            label=tr("clear_typed_label"),
                            placeholder=tr("clear_typed_ph"), scale=1)
                        btn_clear_history = gr.Button(
                            tr("btn_clear_n", n=0), variant="stop",
                            elem_classes=["wd-btn-danger"], scale=1)
                    clear_confirm_row = gr.Row(visible=False)
                    with clear_confirm_row:
                        clear_confirm_html = gr.HTML(value="")
                        with gr.Row(equal_height=True):
                            btn_clear_confirm = gr.Button(
                                tr("btn_clear_confirm"), variant="stop",
                                elem_classes=["wd-btn-danger"], scale=1)
                            btn_clear_cancel = gr.Button(
                                tr("btn_clear_cancel"), scale=1)

        # ─── 事件绑定 ───
        # Tab 1
        btn_analyze.click(
            fn=analyze_single,
            inputs=[img_input],
            outputs=[summary_md, detail_html, json_out, status_text, img_info_text,
                     export_md_file, export_json_file, turbine_viewer],
        )
        btn_clear.click(
            fn=lambda: (None, EMPTY_RESULT_HTML, "", "", tr("img_info_default"),
                        None, None, _viewer_bridge_html()),
            outputs=[img_input, detail_html, json_out, status_text, img_info_text,
                     export_md_file, export_json_file, turbine_viewer],
        )
        # 导出按钮触发重新分析（因为导出文件已在分析时生成）
        btn_export_md.click(
            fn=lambda md: md,
            inputs=[export_md_file],
            outputs=[export_md_file],
        )
        btn_copy_json.click(
            fn=copy_json,
            inputs=[json_out],
            outputs=[status_text],
        )

        # Tab 2
        btn_batch.click(
            fn=analyze_batch,
            inputs=[batch_input],
            outputs=[batch_summary, batch_html, batch_status],
        )
        btn_batch_export_csv.click(
            fn=lambda: export_batch_summary("csv"),
            inputs=[], outputs=[batch_export_file, batch_status],
        )
        btn_batch_export_md.click(
            fn=lambda: export_batch_summary("md"),
            inputs=[], outputs=[batch_export_file, batch_status],
        )

        # Tab 3 — 查询（任何筛选变化 → 回第一页）
        QUERY_INPUTS = [search_tb, risk_dd, date_from_tb, date_to_tb,
                        sort_dd, pagesize_dd, page_state]
        QUERY_OUTPUTS = [history_stats, history_list, page_info_html,
                         history_record_dd, filter_status]

        def _run_query(search, risk, df, dt, sort, psize, page,
                       request: gr.Request = None):
            return query_history(search, risk, df, dt, sort, psize, page,
                                 request=request)

        btn_apply.click(fn=_run_query, inputs=QUERY_INPUTS, outputs=QUERY_OUTPUTS)
        search_tb.submit(fn=_run_query, inputs=QUERY_INPUTS, outputs=QUERY_OUTPUTS)
        for comp in (risk_dd, sort_dd, pagesize_dd):
            comp.change(fn=lambda: 1, outputs=page_state).then(
                fn=_run_query, inputs=QUERY_INPUTS, outputs=QUERY_OUTPUTS)

        # 快捷日期范围（设置日期后回第一页查询）
        def _set_range(days):
            return (*_quick_range(days), 1)
        for btn, days in ((btn_quick_today, 0), (btn_quick_7d, 7), (btn_quick_30d, 30)):
            btn.click(fn=lambda d=days: _set_range(d),
                      inputs=[], outputs=[date_from_tb, date_to_tb, page_state]).then(
                fn=_run_query, inputs=QUERY_INPUTS, outputs=QUERY_OUTPUTS)

        btn_reset_filter.click(
            fn=lambda: ("", "", "", "", "time_desc", "20", 1),
            inputs=[], outputs=[search_tb, risk_dd, date_from_tb, date_to_tb,
                                sort_dd, pagesize_dd, page_state]).then(
            fn=_run_query, inputs=QUERY_INPUTS, outputs=QUERY_OUTPUTS)

        # 分页
        btn_prev_page.click(fn=lambda p: max(1, int(p) - 1),
                            inputs=[page_state], outputs=page_state).then(
            fn=_run_query, inputs=QUERY_INPUTS, outputs=QUERY_OUTPUTS)
        btn_next_page.click(fn=lambda p: int(p) + 1,
                            inputs=[page_state], outputs=page_state).then(
            fn=_run_query, inputs=QUERY_INPUTS, outputs=QUERY_OUTPUTS)

        # 首次加载 / 手动刷新（图表同样按当前用户范围）
        def _charts_for(request: gr.Request = None):
            user_id, is_admin = _current_scope(request)
            scope = None if is_admin else user_id
            return charts_html(owner_user_id=scope)

        btn_refresh.click(fn=_run_query, inputs=QUERY_INPUTS, outputs=QUERY_OUTPUTS).then(
            fn=_charts_for, inputs=[], outputs=[history_charts])
        app.load(fn=_run_query, inputs=QUERY_INPUTS, outputs=QUERY_OUTPUTS).then(
            fn=_charts_for, inputs=[], outputs=[history_charts])

        # 详情
        btn_view_detail.click(
            fn=view_history_detail,
            inputs=[history_record_dd],
            outputs=[history_detail, history_json, note_tb],
        )
        btn_save_note.click(
            fn=save_note,
            inputs=[history_record_dd, note_tb],
            outputs=[filter_status],
        )

        # 单条删除（确认条两步）
        btn_delete_one.click(
            fn=ask_delete_record,
            inputs=[history_record_dd],
            outputs=[confirm_md, confirm_row],
        )
        btn_delete_cancel.click(
            fn=lambda: gr.update(visible=False),
            inputs=[], outputs=[confirm_row],
        )
        btn_delete_confirm.click(
            fn=do_delete_record,
            inputs=[history_record_dd],
            outputs=[history_stats, history_list, page_info_html,
                     history_record_dd, confirm_row, filter_status],
        )

        # 清空（第一步：输入确认文字 → 弹二次确认；第二步：确认执行）
        btn_clear_history.click(
            fn=do_clear_history,
            inputs=[clear_typed_tb],
            outputs=[clear_confirm_row, clear_confirm_html, filter_status],
        )
        btn_clear_confirm.click(
            fn=do_clear_confirm,
            inputs=[],
            outputs=[history_stats, history_list, page_info_html,
                     history_record_dd, clear_typed_tb, clear_confirm_row,
                     filter_status],
        )
        btn_clear_cancel.click(
            fn=lambda: gr.update(visible=False),
            inputs=[], outputs=[clear_confirm_row],
        )

        # ─── 报告导出（§11）───
        btn_export_report.click(
            fn=start_export_task,
            inputs=[export_fmt_dd, export_preset_dd, export_lang_dd, history_record_dd],
            outputs=[export_status, tasks_list, task_dd, filter_status],
        )
        btn_task_refresh.click(
            fn=refresh_tasks,
            inputs=[],
            outputs=[tasks_list, task_dd, filter_status],
        )
        btn_task_download.click(
            fn=download_task,
            inputs=[task_dd],
            outputs=[task_download_file, export_status],
        )
        btn_task_retry.click(
            fn=retry_export_task,
            inputs=[task_dd],
            outputs=[export_status, tasks_list, task_dd],
        )
        # 删除任务两步确认（F4）
        btn_task_delete.click(
            fn=show_delete_task_confirm,
            inputs=[task_dd],
            outputs=[export_status, task_confirm_row],
        )
        btn_task_del_cancel.click(
            fn=lambda: gr.update(visible=False),
            inputs=[], outputs=[task_confirm_row],
        )
        btn_task_del_confirm.click(
            fn=delete_export_task,
            inputs=[task_dd],
            outputs=[export_status, tasks_list, task_dd, task_confirm_row],
        )

    # 页脚 — 放在 Tabs 外层，全宽居中
    gr.HTML(
        "<div class='footer-note'>"
        + tr("footer") +
        "</div>"
    )

    # gradio 6：js 参数在 launch()/mount_gradio_app() 上传入
    # （页面加载后注入用户徽章 + 抽屉快捷预览的事件委托）
    # ⚠ gradio 6.26 对 js 参数的实现是把它原样塞进 <script> 标签：
    #   e.textContent = config.js; document.head.appendChild(script)
    #   <script>() => {...}</script> 是一条"函数表达式语句"，永远不会被调用。
    #   旧写法 (badge_js) 为 "() => {...}"、07fcf9e 改成 "() => { a(); b(); }"
    #   都因此从未执行过 → 顶栏用户徽章（用户管理/修改密码/退出登录）一直为空。
    #   修复：包一层 IIFE 立即自调用。
    drawer_js = _DRAWER_JS
    settings_js = _SETTINGS_POPOVER_JS
    app._wd_badge_js = (f"(() => {{ ({badge_js})(); ({drawer_js})(); "
                        f"({settings_js})(); }})();")
    return app


if __name__ == "__main__":
    from server import main
    main()
