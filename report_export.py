"""
风电塔灾损测算软件 — 四格式报告导出（DEVELOPMENT_PLAN.md §11）

格式：PDF（reportlab，中文走内置 CID 字体 STSong-Light）
     Word（python-docx）· Excel（openpyxl）· CSV（stdlib，UTF-8 BOM）
内容预设（§11.1）：
  standard  标准报告：基本信息 + 检测结果 + 风险分析 + 处置建议
  brief     简版报告：摘要卡内容 + 结论
  full      完整技术报告：全部字段 + 原始 JSON + 备注
语言：报告语言与界面语言可分开（§12）。
"""

import os
import csv
import json
import io
from datetime import datetime
from typing import BinaryIO, Dict, List, Optional, Union

import i18n
from i18n import t as tr, tr_value, section_title, field_label

EXPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
TASK_EXPIRE_DAYS = 30

# 预设 → 包含的区块 key（i18n.SECTION_* 原始中文键）
PRESET_SECTIONS = {
    "standard": [
        i18n.SECTION_CAPTION, i18n.SECTION_COMPONENT, i18n.SECTION_DAMAGE,
        i18n.SECTION_RISK, i18n.SECTION_OM,
    ],
    "brief": [
        i18n.SECTION_COMPONENT, i18n.SECTION_DAMAGE, i18n.SECTION_CONCLUSION,
    ],
    "full": [],  # 空 = 全部区块
}
PRESETS = ("standard", "brief", "full")
FORMATS = ("pdf", "docx", "xlsx", "csv")


# ─── 内容组装 ─────────────────────────────────────────────

def build_content(report: dict, record: Optional[dict] = None,
                  preset: str = "standard", lang: str = None) -> Dict:
    """把检测报告按预设组装为统一内容结构，供四格式渲染。

    返回 {meta: [(label, value)...], sections: [(title, [(label, value)...])...],
          note: str, raw_json: str}
    """
    lang_key = lang or i18n.LANG
    report = report or {}
    record = record or {}
    if preset not in PRESETS:
        preset = "standard"
    section_keys = PRESET_SECTIONS[preset] or report.keys()

    def L(key: str) -> str:
        return i18n.UI.get(lang_key, {}).get(key, key)

    meta = [
        (L("export_time"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        (L("export_image_name"), str(record.get("image_name") or "")),
        (L("export_record_no"), f"#{record['id']}" if record.get("id") else "—"),
        (L("export_time_detect"), str(record.get("timestamp") or "—")),
        (L("export_infer_time"), f"{record.get('infer_time') or 0:.1f}s"),
    ]
    if record.get("source") == "migration":
        meta.append((L("badge_migrated"), "✓"))
    if record.get("turbine_id"):
        meta.append((L("export_turbine"), str(record["turbine_id"])))

    sections = []
    for sk in section_keys:
        if sk not in report:
            continue
        fields = []
        section = report[sk]
        items = section.items() if isinstance(section, dict) else [(L("export_content"), section)]
        for fk, value in items:
            label = field_label(sk, fk, lang=lang_key)
            display = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            fields.append((label, tr_value(display, lang=lang_key)))
        title = section_title(sk, lang=lang_key)
        sections.append((title, fields))

    return {
        "title": L("export_title"),
        "preset_label": L(f"preset_{preset}"),
        "meta": meta,
        "sections": sections,
        "note": str(record.get("note") or ""),
        "raw_json": json.dumps(report, ensure_ascii=False, indent=2)
        if preset == "full" else "",
    }


def _flat_rows(content: Dict) -> List[List[str]]:
    """展平为 [类别, 项, 值] 行（Excel / CSV 用）。"""
    rows = []
    for label, value in content["meta"]:
        rows.append([content["preset_label"], label, str(value)])
    for title, fields in content["sections"]:
        for label, value in fields:
            rows.append([title, label, str(value)])
    if content["note"]:
        rows.append([content["title"], tr("note_label"), content["note"]])
    if content["raw_json"]:
        rows.append([content["title"], tr("json_raw_label"), content["raw_json"]])
    return rows


def _safe_basename(name: str) -> str:
    keep = "".join(c if (c.isalnum() or c in "._-") else "_" for c in (name or "export"))
    return keep[:60] or "export"


def _write_csv(content, stream):
    writer = csv.writer(stream)
    writer.writerow([tr("export_csv_section"), tr("export_csv_item"), tr("export_csv_value")])
    writer.writerows(_flat_rows(content))


def export_csv(content: Dict, record: Optional[dict], path: str) -> str:
    """CSV（UTF-8 BOM，Excel 直接打开不乱码）。"""
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        _write_csv(content, f)
    return path


def export_xlsx(content: Dict, record: Optional[dict], path: str) -> str:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = _safe_basename((record or {}).get("image_name") or "report")[:28]

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="125191")
    for col, text in enumerate(
            [tr("export_csv_section"), tr("export_csv_item"),
             tr("export_csv_value")], start=1):
        c = ws.cell(row=1, column=col, value=text)
        c.font = header_font
        c.fill = header_fill

    for r, row in enumerate(_flat_rows(content), start=2):
        for c, v in enumerate(row, start=1):
            cell = ws.cell(row=r, column=c, value=v)
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["C"].width = 60
    ws.freeze_panes = "A2"
    wb.save(path)
    return path


def export_docx(content: Dict, record: Optional[dict], path: str) -> str:
    from docx import Document
    from docx.shared import Pt, RGBColor

    doc = Document()
    doc.add_heading(content["title"], level=0)
    doc.add_paragraph(content["preset_label"])

    table = doc.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for label, value in content["meta"]:
        cells = table.add_row().cells
        cells[0].text = str(label)
        cells[1].text = str(value)

    for title, fields in content["sections"]:
        doc.add_heading(str(title), level=1)
        t = doc.add_table(rows=0, cols=2)
        t.style = "Light Grid Accent 1"
        for label, value in fields:
            cells = t.add_row().cells
            cells[0].text = str(label)
            cells[1].text = str(value)

    if content["note"]:
        doc.add_heading(tr("note_label"), level=1)
        doc.add_paragraph(content["note"])

    if content["raw_json"]:
        doc.add_heading(tr("json_raw_label"), level=1)
        p = doc.add_paragraph()
        run = p.add_run(content["raw_json"])
        run.font.name = "Consolas"
        run.font.size = Pt(8)

    doc.save(path)
    return path


def export_pdf(content: Dict, record: Optional[dict], path: Union[str, BinaryIO]) -> Union[str, BinaryIO]:
    from xml.sax.saxutils import escape
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                    Table, TableStyle)
    from reportlab.lib.styles import ParagraphStyle

    # 中文：reportlab 内置 Adobe CID 字体（无需携带字体文件）
    if "STSong-Light" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    title_style = ParagraphStyle("t", fontName="STSong-Light", fontSize=18,
                                 spaceAfter=6, textColor=colors.HexColor("#125191"))
    sub_style = ParagraphStyle("s", fontName="STSong-Light", fontSize=10,
                               textColor=colors.HexColor("#5D6D7E"), spaceAfter=10)
    head_style = ParagraphStyle("h", fontName="STSong-Light", fontSize=13,
                                spaceBefore=12, spaceAfter=4,
                                textColor=colors.HexColor("#125191"))
    cell_style = ParagraphStyle("c", fontName="STSong-Light", fontSize=9.5, leading=13, wordWrap="CJK")
    json_style = ParagraphStyle("j", fontName="STSong-Light", fontSize=8, leading=11, wordWrap="CJK")

    def P(text):
        return Paragraph(escape(str(text)).replace("\n", "<br/>"), cell_style)

    story = [Paragraph(content["title"], title_style),
             Paragraph(content["preset_label"], sub_style)]

    def add_table(rows):
        if not rows:
            return
        data = [[P(a), P(b)] for a, b in rows]
        t = Table(data, colWidths=[55 * mm, 105 * mm], splitInRow=1)
        t.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DBE1")),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F4F6F8")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t)

    add_table(content["meta"])
    for title, fields in content["sections"]:
        story.append(Paragraph(escape(str(title)), head_style))
        add_table(fields)

    if content["note"]:
        story.append(Paragraph(tr("note_label"), head_style))
        story.append(P(content["note"]))

    if content["raw_json"]:
        story.append(Paragraph(tr("json_raw_label"), head_style))
        for line in content["raw_json"].splitlines():
            story.append(Paragraph(escape(line), json_style))

    doc = SimpleDocTemplate(path, pagesize=A4,
                            leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=content["title"])
    doc.build(story)
    return path


def record_download(report: dict, record: dict, fmt: str) -> bytes:
    """Render one archived assessment with its complete fields, entirely in memory."""
    content = build_content(report, record, preset="full")
    if fmt == "pdf":
        stream = io.BytesIO()
        export_pdf(content, record, stream)
        return stream.getvalue()
    if fmt == "csv":
        stream = io.StringIO(newline="")
        _write_csv(content, stream)
        return stream.getvalue().encode("utf-8-sig")
    if fmt == "md":
        from exporter import markdown_content
        return markdown_content(content).encode("utf-8")
    raise ValueError(f"Unsupported download format: {fmt}")


# ─── 统一入口 ─────────────────────────────────────────────

_GENERATORS = {"csv": export_csv, "xlsx": export_xlsx,
               "docx": export_docx, "pdf": export_pdf}


def generate_export(fmt: str, report: dict, record: Optional[dict] = None,
                    preset: str = "standard", lang: str = None,
                    out_dir: str = None) -> str:
    """生成导出文件，返回文件绝对路径。fmt ∈ pdf/docx/xlsx/csv。"""
    if fmt not in _GENERATORS:
        raise ValueError(f"bad format: {fmt}")
    out_dir = out_dir or EXPORTS_DIR
    os.makedirs(out_dir, exist_ok=True)
    content = build_content(report, record, preset=preset, lang=lang)
    base = _safe_basename(os.path.splitext((record or {}).get("image_name") or "export")[0])
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(out_dir, f"export_{base}_{preset}_{ts}.{fmt}")
    return _GENERATORS[fmt](content, record, path)


# ─── 过期清理（§11.2：文件 30 天过期）────────────────────

def cleanup_expired(now: Optional[datetime] = None, out_dir: str = None) -> int:
    """删除 exports/ 中超过保留期的文件，返回删除数。"""
    import time as _time
    out_dir = out_dir or EXPORTS_DIR
    if not os.path.isdir(out_dir):
        return 0
    now = now or datetime.now()
    n = 0
    for name in os.listdir(out_dir):
        p = os.path.join(out_dir, name)
        if not os.path.isfile(p):
            continue
        age_days = (now.timestamp() - os.path.getmtime(p)) / 86400
        if age_days > TASK_EXPIRE_DAYS:
            try:
                os.remove(p)
                n += 1
            except OSError:
                pass
    return n
