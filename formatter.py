"""
风电结构损伤检测平台 — 格式化模块

将模型输出的 JSON 报告转换为前端展示用的结构化数据。
负责字段分类、风险标记、颜色编码。
展示文本跟随 i18n.LANG（zh/en）；内部键始终使用中文。
"""

import json
from typing import Optional, Dict, Any, List
from parser import get_field, validate_report
import i18n
from i18n import tr_value, section_title, field_label


# ─── 风险等级映射 ─────────────────────────────────────────
# 中文键与英文展示值都映射到同一颜色
RISK_COLORS = {
    "高": "#E74C3C", "High": "#E74C3C",     # 红色
    "中": "#F39C12", "Medium": "#F39C12",   # 橙色
    "低": "#27AE60", "Low": "#27AE60",      # 绿色
    "无": "#27AE60", "None": "#27AE60",     # 绿色
    "是": "#E74C3C", "Yes": "#E74C3C",      # 红色（危险）
    "否": "#27AE60", "No": "#27AE60",       # 绿色（安全）
}

RISK_FIELDS = {
    "损伤类型": True,       # 需检查是否含损伤
    "对结构安全性的影响程度": True,
    "巡检优先级": True,
    "是否存在损伤": True,
    "是否建议停机、限功率运行或重点监测": True,
}


def risk_alert(report: Dict, archived_priority: str = "") -> Optional[Dict]:
    """从结构化报告提取告警依据和模型建议。合并的停机/限功率/监测字段不能区分严重程度。"""
    reasons = []
    priority = get_field(report, i18n.SECTION_CONCLUSION, "巡检优先级") or archived_priority
    if priority == "高":
        reasons.append("巡检优先级为高")
    impact = get_field(report, i18n.SECTION_RISK, "对结构安全性的影响程度")
    if impact in ("高", "严重", "重度"):
        reasons.append(f"对结构安全性的影响程度为{impact}")
    damage = get_field(report, i18n.SECTION_DAMAGE, "损伤程度")
    if damage in ("严重", "重度"):
        reasons.append(f"损伤程度为{damage}")
    if reasons:
        return {"reasons": reasons, "advice": get_field(report, i18n.SECTION_OM, "短期处置建议")}
    return None


def is_high_risk(report: Dict) -> bool:
    return risk_alert(report) is not None


def get_risk_badge(value: str, field_name: str = "") -> str:
    """生成风险徽章（胶囊形：浅色语义底 + 深色文字，文字+颜色双通道）。

    value 应为展示语言；语义映射与 RISK_COLORS 一致，不改变数据含义。
    """
    if not value:
        return value
    from ui_components import risk_badge, tone_for_value
    return risk_badge(value, tone_for_value(value))


def format_report(report: Optional[Dict]) -> Dict[str, Any]:
    """将 JSON 报告转换为前端展示结构（展示文本跟随当前语言）。

    Returns:
        {
            "high_risk": bool,
            "sections": [
                {
                    "title": "1. 构件识别",
                    "icon": "🔧",
                    "fields": [{"label": "构件名称", "value": "...", "is_risk": False}, ...]
                },
                ...
            ],
            "json_str": "pretty JSON string",
            "validation": {...}
        }
    """
    if report is None:
        return {
            "high_risk": False,
            "sections": [],
            "json_str": "",
            "validation": {"valid": False, "message": "报告为空"},
        }

    high_risk = is_high_risk(report)
    validation = validate_report(report)

    # 按展示顺序定义区块：(section_key, field_key, 中文短标签)
    section_defs = [
        {
            "section": i18n.SECTION_CAPTION,
            "icon": "🖼️",
            "fields": [
                (i18n.SECTION_CAPTION, "简要", "简要"),
                (i18n.SECTION_CAPTION, "图像质量评价", "图像质量"),
            ],
        },
        {
            "section": i18n.SECTION_COMPONENT,
            "icon": "🔧",
            "fields": [
                (i18n.SECTION_COMPONENT, "构件名称", "构件名称"),
                (i18n.SECTION_COMPONENT, "构件所属系统", "所属系统"),
            ],
        },
        {
            "section": i18n.SECTION_DAMAGE,
            "icon": "⚠️",
            "fields": [
                (i18n.SECTION_DAMAGE, "是否可判定", "是否可判定"),
                (i18n.SECTION_DAMAGE, "是否存在损伤", "是否存在损伤"),
                (i18n.SECTION_DAMAGE, "损伤类型", "损伤类型"),
                (i18n.SECTION_DAMAGE, "损伤发展趋势", "发展趋势"),
                (i18n.SECTION_DAMAGE, "损伤分布位置与范围", "位置与范围"),
                (i18n.SECTION_DAMAGE, "关键视觉证据描述", "视觉证据"),
                (i18n.SECTION_DAMAGE, "可能的成因推测", "成因推测"),
                (i18n.SECTION_DAMAGE, "不可判定原因", "不可判定原因"),
            ],
        },
        {
            "section": i18n.SECTION_RISK,
            "icon": "🔴",
            "fields": [
                (i18n.SECTION_RISK, "对结构安全性的影响程度", "对结构安全影响"),
                (i18n.SECTION_RISK, "是否对机组运行可靠性影响", "对运行可靠性影响"),
                (i18n.SECTION_RISK, "是否对长期服役寿命的影响", "对长期寿命影响"),
            ],
        },
        {
            "section": i18n.SECTION_OM,
            "icon": "🛠️",
            "fields": [
                (i18n.SECTION_OM, "是否建议停机、限功率运行或重点监测", "建议停机、限功率或重点监测"),
                (i18n.SECTION_OM, "短期处置建议", "短期处置"),
                (i18n.SECTION_OM, "中长期修复或改进建议", "中长期修复"),
                (i18n.SECTION_OM, "后续巡检建议关注的问题", "后续巡检关注"),
            ],
        },
        {
            "section": i18n.SECTION_UNCERTAINTY,
            "icon": "❓",
            "fields": [
                (i18n.SECTION_UNCERTAINTY, "是否建议补充获取更高分辨率或多角度图像", "建议补充图像"),
                (i18n.SECTION_UNCERTAINTY, "是否建议结合现场巡检或历史运维数据进行综合判断", "建议结合巡检历史"),
                (i18n.SECTION_UNCERTAINTY, "当前是否建议仅基于该图像做出维修或停机决策", "仅基于图像决策"),
            ],
        },
        {
            "section": i18n.SECTION_CONCLUSION,
            "icon": "📋",
            "fields": [
                (i18n.SECTION_CONCLUSION, "本次判断的置信度", "置信度"),
                (i18n.SECTION_CONCLUSION, "巡检优先级", "巡检优先级"),
            ],
        },
    ]

    sections = []
    for sec_def in section_defs:
        section_key = sec_def["section"]
        fields = []
        for section_key, field_key, display_label in sec_def["fields"]:
            value = get_field(report, section_key, field_key)
            is_risk = field_key in RISK_FIELDS
            display_value = tr_value(value) if value else "—"
            fields.append({
                "label": field_label(section_key, field_key),
                "value": display_value,
                "is_risk": is_risk,
                "raw_field": field_key,
            })
        sections.append({
            "title": section_title(section_key),
            "icon": sec_def["icon"],
            "fields": fields,
        })

    json_str = json.dumps(report, ensure_ascii=False, indent=2)

    return {
        "high_risk": high_risk,
        "sections": sections,
        "json_str": json_str,
        "validation": validation,
    }


def format_summary(report: Dict) -> str:
    """生成一句话摘要（用于 Gradio 标题栏，跟随当前语言）。"""
    component = tr_value(get_field(report, i18n.SECTION_COMPONENT, "构件名称"))
    damage_type = tr_value(get_field(report, i18n.SECTION_DAMAGE, "损伤类型"))
    priority = tr_value(get_field(report, i18n.SECTION_CONCLUSION, "巡检优先级"))
    has_damage = get_field(report, i18n.SECTION_DAMAGE, "是否存在损伤")
    prio_label = i18n.t("summary_priority")

    if has_damage == "是":
        return f"⚠️ {component} — {damage_type} — {prio_label}: {priority}"
    else:
        return f"✅ {component} — {i18n.t('summary_no_damage')} — {prio_label}: {priority}"
