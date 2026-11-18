"""Simulated wind farm inventory and component-level observations from inspection reports."""

import json
import re
from collections import Counter
from datetime import date, timedelta

from parser import get_field


TURBINE_IDS = ("FT01", "FT02", "FT03", "FT04", "FT05")

_PART_NAMES = {
    "blade": r"叶片|风叶|桨叶|叶尖|叶根|\bblades?\b",
    "hub": r"轮毂|整流罩|导流罩|\bhub\b|\bnose cone\b",
    "nacelle": r"机舱|\bnacelle\b",
    "tower": r"塔筒|塔身|塔架|筒体|\btower\b",
    "foundation": r"基础|基座|承台|\bfoundation\b",
}
_YES = {"是", "yes", "true"}
_NO = {"否", "no", "false"}
_NO_DAMAGE_TYPE = {"", "无", "无损伤", "未见损伤", "无病害", "未知", "不确定", "无法判定", "无法判断",
                   "不可判定", "图像证据不足", "不适用", "—", "-", "none", "null", "unknown", "no damage", "n/a"}
_CLEAR = re.compile(r"(?:无|没有|未见|未发现)(?:明显|可见)?(?:异常|损伤|病害|缺陷)|"
                    r"(?<!不)(?<!非)完好(?:无损)?$|未受损$")
_PART = "(?:" + "|".join(_PART_NAMES.values()) + ")"
_NORMAL = re.compile(_PART + r"(?:外观|表面|结构|状态)?(?:均|整体)?正常$", re.I)
_CLAUSE_BREAK = re.compile(r"、|但是|但|而|(?:并且|同时|以及|且|和|与|及)(?=" + _PART + ")", re.I)
_UNCERTAIN = re.compile(r"疑似|可能|不确定|无法(?:判断|判定|观察|看清)|不可见|"
                        r"不能排除|未(?:检查|评估|拍摄|覆盖)|未见全貌|未拍到|遮挡")
_DEFECT = re.compile(r"裂纹|裂缝|开裂|断裂|折断|破损|脱落|腐蚀|锈蚀|变形|损伤|撞击|病害")
_NEGATED_DEFECT = re.compile(r"(?:无|未见|未发现)(?:明显)?(?:" + _DEFECT.pattern + ")")


def _named_parts(text):
    return {part for part, names in _PART_NAMES.items() if re.search(names, text, re.I)}


def _location_clauses(location):
    # Keep a shared predicate ("叶片、轮毂均正常"), separate independent findings
    # ("叶片断裂、塔筒完好"). A bare list of locations can refer to the same defect.
    for sentence in re.split(r"[，,；;。\n]", location):
        group = []
        for fragment in _CLAUSE_BREAK.split(sentence):
            group.append(fragment)
            if (_DEFECT.search(fragment) or _CLEAR.search(fragment) or
                    _UNCERTAIN.search(fragment) or "正常" in fragment):
                yield "、".join(group)
                group = []
        if group:
            yield "、".join(group)


def _located_observations(location, components, decision):
    damaged, clear, uncertain = set(), set(), set()
    for phrase in _location_clauses(location):
        # References such as “叶片根部靠近轮毂” use a neighbouring part as a landmark.
        target = re.split(r"靠近|临近|邻近", phrase, maxsplit=1)[0]
        parts = _named_parts(target)
        if len(components) == 1 and parts & components and "连接处" in target:
            parts = components
        if _UNCERTAIN.search(target):
            uncertain.update(parts)
        elif _CLEAR.search(target) or _NORMAL.search(target.strip()):
            clear.update(parts)
        elif _NEGATED_DEFECT.search(target) or "正常" in target:
            # Absence of a particular defect or normal operation alone is inconclusive.
            uncertain.update(parts)
        elif decision == "damaged":
            damaged.update(parts)
    if decision == "clear":
        clear.update(components)
    elif not damaged:
        conflicting = _UNCERTAIN.search(location) or _CLEAR.search(location) or _NEGATED_DEFECT.search(location)
        if len(components) == 1 and not _named_parts(location) and not conflicting:
            damaged.update(components)
        else:
            damaged.add("unknown")
    observations = dict.fromkeys(clear, "clear")
    observations.update(dict.fromkeys(uncertain, "uncertain"))
    observations.update(dict.fromkeys(damaged, "damaged"))
    return sorted(observations.items()) or [("unknown", decision)]


def observed_parts(report):
    """Return (part, status) pairs; the location describes damage, the component describes the image."""
    damage = "2. 损伤判定"
    decision = get_field(report, damage, "是否存在损伤").lower()
    assessable = get_field(report, damage, "是否可判定").lower()
    status = "uncertain"
    if not assessable or assessable in _YES:
        if decision in _YES:
            status = "damaged"
        elif decision in _NO:
            status = "clear"

    component = get_field(report, "1. 构件识别", "构件名称")
    components = _named_parts(component)
    if re.search(r"疑似|不确定|可能是", component) or (
        len(components) > 1 and re.search(r"或|\bor\b", component, re.I)
    ):
        components.clear()
    if status == "uncertain":
        return [(part, status) for part in sorted(components or {"unknown"})]
    location = get_field(report, damage, "损伤分布位置与范围")
    return _located_observations(location, components, status)


def farm_payload(observations=()):
    units = {unit: {"id": unit, "parts": []} for unit in TURBINE_IDS}
    for row in observations:
        unit = units[row["turbine_id"]]
        unit["parts"].append({key: value for key, value in row.items() if key != "turbine_id"})
    return {"turbines": list(units.values())}


def damage_stats_payload(records=(), assessment_groups=(), today=None):
    """Count each confirmed type once per report. Unassigned records contribute to the farm only."""
    counts = {scope: Counter() for scope in ("all", *TURBINE_IDS)}
    for record in records:
        # Legacy records can have only the indexed summary fields.
        try:
            report = json.loads(record["json_report"])
        except (ValueError, TypeError):
            report = {}
        assessable = get_field(report, "2. 损伤判定", "是否可判定").lower()
        if assessable and assessable not in _YES:
            continue
        assessment = report.get("2. 损伤判定") if isinstance(report, dict) else None
        raw = record["damage_type"]
        if isinstance(assessment, dict):
            raw = assessment.get("损伤类型", raw)
        values = raw if isinstance(raw, list) else [raw]
        types = set()
        for value in values:
            if isinstance(value, str):
                labels = re.split(r"[、，,；;／/\n]+", re.sub(r"\bn/a\b", "", value, flags=re.I))
                types.update(label.strip() for label in labels if label.strip().lower() not in _NO_DAMAGE_TYPE)
        counts["all"].update(types)
        if record["turbine_id"] in TURBINE_IDS:
            counts[record["turbine_id"]].update(types)

    payload = {"scopes": {
        scope: [{"type": name, "count": count} for name, count in
                sorted(counter.items(), key=lambda item: (-item[1], item[0]))]
        for scope, counter in counts.items()
    }}
    today = today or date.today()
    monday = today - timedelta(days=today.weekday())
    days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    weeks = [(monday - timedelta(weeks=i)).isoformat() for i in range(7, -1, -1)]
    day_index = {day: i for i, day in enumerate(days)}
    week_index = {
        (date.fromisoformat(start) + timedelta(days=offset)).isoformat(): i
        for i, start in enumerate(weeks) for offset in range(7)
    }
    payload["periods"] = {"daily": days, "weekly": weeks, "through": today.isoformat()}
    scopes = {}
    for scope in counts:
        scopes[scope] = {
            "priority": dict.fromkeys(("高", "中", "低", "未判定"), 0),
            "daily": [{"total": 0, "high_risk": 0} for _ in days],
            "weekly": [{"total": 0, "high_risk": 0} for _ in weeks],
        }
    priorities = {"高": "高", "中": "中", "低": "低", "high": "高", "medium": "中", "low": "低"}
    for row in assessment_groups:
        priority = priorities.get((row["priority"] or "").strip().lower(), "未判定")
        unit = row["turbine_id"]
        for key in (("all", unit) if unit in TURBINE_IDS else ("all",)):
            scoped = scopes[key]
            scoped["priority"][priority] += row["total"]
            day = row["day"]
            if day in week_index and day <= days[-1]:
                week = scoped["weekly"][week_index[day]]
                week["total"] += row["total"]
                week["high_risk"] += row["high_risk"]
            if day in day_index:
                entry = scoped["daily"][day_index[day]]
                entry["total"] += row["total"]
                entry["high_risk"] += row["high_risk"]
    payload["assessments"] = scopes
    return payload
