"""
风电塔灾损测算软件 — 历史记录模块

SQLite 存储，支持保存检测记录、查询历史（筛选/排序/分页/归属隔离）、回看详情、
备注、分级删除（单条/批量/按用户清空）。

归属模型（DEVELOPMENT_PLAN.md §13.1）：
  - owner_user_id = 记录归属；NULL = 待认领（系统迁移数据）
  - user 只能读写自己的记录（owner_user_id 过滤）；admin 可查全量（角色授权）
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple

_DEFAULT_DB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "history.db")


def _db_path() -> str:
    """动态解析库路径（测试可通过 WD_DB_PATH 指向临时库）。"""
    return os.environ.get("WD_DB_PATH") or _DEFAULT_DB


# 兼容保留：模块导入时的默认路径
DB_PATH = _db_path()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """初始化基础表，并执行增量迁移到最新版本。"""
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS detections (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT    NOT NULL,
            image_name  TEXT    NOT NULL,
            image_path  TEXT,
            high_risk   INTEGER DEFAULT 0,
            has_damage  TEXT,
            damage_type TEXT,
            component   TEXT,
            priority    TEXT,
            confidence  TEXT,
            json_report TEXT    NOT NULL,
            infer_time  REAL
        )
    """)
    conn.commit()
    conn.close()
    # 增量迁移（幂等）
    import migrate
    migrate.migrate()


# ─── 写入 ─────────────────────────────────────────────────

def save_record(image_name: str, json_report: dict, infer_time: float = 0,
                image_path: str = "", source: str = "ui",
                owner_user_id: Optional[int] = None,
                created_by: Optional[str] = None,
                persist_image: bool = False, turbine_id: Optional[str] = None) -> int:
    """保存一条检测记录，返回记录 ID。

    persist_image=True 时把图片持久化到 image_files（引用计数复用）。
    """
    from formatter import is_high_risk
    from parser import get_field
    from wind_farm import TURBINE_IDS, observed_parts

    if turbine_id is not None and turbine_id not in TURBINE_IDS:
        raise ValueError("未知机组编号")

    report = json_report or {}
    high_risk = 1 if is_high_risk(report) else 0
    has_damage = get_field(report, "2. 损伤判定", "是否存在损伤")
    damage_type = get_field(report, "2. 损伤判定", "损伤类型")
    component = get_field(report, "1. 构件识别", "构件名称")
    priority = get_field(report, "6. 结论建议", "巡检优先级")
    confidence = get_field(report, "6. 结论建议", "本次判断的置信度")

    image_file_id = None
    if persist_image and image_path and os.path.exists(image_path):
        import image_store
        if image_store.check_quota():
            image_file_id = image_store.store_image(image_path)

    conn = get_conn()
    try:
        with conn:
            cur = conn.execute("""
                INSERT INTO detections
                    (timestamp, image_name, image_path, high_risk, has_damage,
                     damage_type, component, priority, confidence, json_report, infer_time,
                     owner_user_id, created_by, source, image_file_id, turbine_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                image_name, image_path, high_risk, has_damage,
                damage_type, component, priority, confidence,
                json.dumps(report, ensure_ascii=False), round(infer_time, 1),
                owner_user_id, created_by, source, image_file_id, turbine_id,
            ))
            rid = cur.lastrowid
            if turbine_id is not None:
                conn.executemany(
                    "INSERT INTO detection_parts(record_id, part, status) VALUES (?, ?, ?)",
                    [(rid, part, status) for part, status in observed_parts(report)],
                )
        return rid
    finally:
        conn.close()


def update_note(record_id: int, note: str) -> bool:
    """更新记录备注。返回是否存在该记录。"""
    conn = get_conn()
    cur = conn.execute("UPDATE detections SET note = ? WHERE id = ?", (note, record_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


# ─── 查询 ─────────────────────────────────────────────────

# 排序白名单（防注入；KEY 为 SQL 片段）
_SORTS = {
    "time_desc": "id DESC",
    "time_asc": "id ASC",
    "risk_desc": "high_risk DESC, id DESC",
    "infer_time_desc": "infer_time DESC, id DESC",
}


def list_records(limit: int = 50,
                 owner_user_id: Optional[int] = None,
                 search: str = "",
                 risk: str = "",          # '' | 'high' | 'normal'
                 damage: str = "",        # '' | 'yes' | 'no'
                 date_from: str = "",
                 date_to: str = "",
                 sort: str = "time_desc") -> List[Dict]:
    """查询记录（摘要字段，不含完整 JSON）。owner_user_id=None 查全部（admin）。"""
    rows, _ = query_records(limit=limit, offset=0, owner_user_id=owner_user_id,
                            search=search, risk=risk, damage=damage,
                            date_from=date_from, date_to=date_to, sort=sort)
    return rows


def query_records(limit: int = 20, offset: int = 0,
                  owner_user_id: Optional[int] = None,
                  search: str = "", risk: str = "", damage: str = "",
                  date_from: str = "", date_to: str = "",
                  sort: str = "time_desc", turbine_id: str = "") -> Tuple[List[Dict], int]:
    """分页 + 筛选查询。返回 (rows, total)。所有值化参数，排序走白名单。"""
    where, params = [], []
    if owner_user_id is not None:
        where.append("owner_user_id = ?")
        params.append(owner_user_id)
    if turbine_id == "unassigned":
        where.append("turbine_id IS NULL")
    elif turbine_id:
        where.append("turbine_id = ?")
        params.append(turbine_id)
    if search:
        where.append("(image_name LIKE ? OR damage_type LIKE ? OR component LIKE ?)")
        like = f"%{search}%"
        params.extend([like, like, like])
    if risk == "high":
        where.append("high_risk = 1")
    elif risk == "normal":
        where.append("high_risk = 0")
    if damage == "yes":
        where.append("has_damage = '是'")
    elif damage == "no":
        where.append("has_damage = '否'")
    if date_from:
        where.append("date(timestamp) >= date(?)")
        params.append(date_from)
    if date_to:
        where.append("date(timestamp) <= date(?)")
        params.append(date_to)
    where_sql = (" WHERE " + " AND ".join(where)) if where else ""
    order_sql = _SORTS.get(sort, _SORTS["time_desc"])

    conn = get_conn()
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM detections{where_sql}", params
        ).fetchone()[0]
        rows = conn.execute(
            f"""SELECT id, timestamp, image_name, high_risk, has_damage,
                       damage_type, component, priority, confidence, infer_time,
                       note, owner_user_id, source, turbine_id, image_file_id
                FROM detections{where_sql}
                ORDER BY {order_sql}
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        return [dict(r) for r in rows], total
    finally:
        conn.close()


def get_record(record_id: int) -> Optional[Dict]:
    """根据 ID 查询单条记录详情（含完整 JSON）。"""
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM detections WHERE id = ?", (record_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def latest_turbine_observations(owner_user_id: Optional[int]) -> List[Dict]:
    """Show the latest visible damage for each part, falling back to its latest observation."""
    scope = "AND d.owner_user_id = ?" if owner_user_id is not None else ""
    params = (owner_user_id,) if owner_user_id is not None else ()
    conn = get_conn()
    try:
        rows = conn.execute(f"""
            WITH ranked AS (
                SELECT d.turbine_id, p.part, p.status, d.component, d.damage_type,
                       d.priority, d.id AS record_id, d.timestamp, d.image_name,
                       ROW_NUMBER() OVER (
                           PARTITION BY d.turbine_id, p.part
                           ORDER BY (p.status = 'damaged') DESC, d.id DESC
                       ) AS position
                FROM detections d JOIN detection_parts p ON p.record_id = d.id
                WHERE d.turbine_id IS NOT NULL {scope}
            )
            SELECT turbine_id, part, status, component, damage_type, priority, record_id,
                   timestamp, image_name FROM ranked WHERE position = 1
            ORDER BY turbine_id, record_id DESC, part
        """, params)
        return [dict(row) for row in rows]
    finally:
        conn.close()


def damage_type_stats(owner_user_id: Optional[int]) -> Dict:
    """Aggregate disease types, inspection priorities and trends from a single snapshot."""
    from wind_farm import damage_stats_payload
    scope = "AND owner_user_id = ?" if owner_user_id is not None else ""
    params = (owner_user_id,) if owner_user_id is not None else ()
    conn = get_conn()
    try:
        today = datetime.now().date()
        # Older rows contribute to all-time priorities, without a separate group per day.
        cutoff = (today - timedelta(weeks=7, days=today.weekday())).isoformat()
        conn.execute("BEGIN")
        rows = conn.execute(f"""
            SELECT turbine_id, damage_type, json_report FROM detections
            WHERE lower(trim(has_damage)) IN ('是', 'yes', 'true') {scope}
        """, params)
        groups = conn.execute(f"""
            SELECT turbine_id, priority, CASE WHEN timestamp >= ? THEN substr(timestamp, 1, 10) END AS day,
                   COUNT(*) AS total, SUM(CASE WHEN high_risk = 1 THEN 1 ELSE 0 END) AS high_risk
            FROM detections WHERE 1=1 {scope}
            GROUP BY turbine_id, priority, day
        """, (cutoff, *params))
        return damage_stats_payload(rows, groups, today)
    finally:
        conn.close()


def can_access(record: Dict, user_id: Optional[int], is_admin: bool) -> bool:
    """记录访问权限：admin 全量；user 仅本人；迁移数据（owner NULL）仅 admin。"""
    if is_admin:
        return True
    if user_id is None:
        return False
    return record.get("owner_user_id") == user_id


def get_stats(owner_user_id: Optional[int] = None) -> Dict:
    """返回统计摘要（可按归属过滤）。"""
    cond = " WHERE owner_user_id = ?" if owner_user_id is not None else ""
    params = (owner_user_id,) if owner_user_id is not None else ()
    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) FROM detections{cond}", params).fetchone()[0]
    high = conn.execute(
        f"SELECT COUNT(*) FROM detections{cond}{' AND' if cond else ' WHERE'} high_risk=1",
        params).fetchone()[0]
    damaged = conn.execute(
        f"SELECT COUNT(*) FROM detections{cond}{' AND' if cond else ' WHERE'} has_damage='是'",
        params).fetchone()[0]
    avg_time = conn.execute(
        f"SELECT AVG(infer_time) FROM detections{cond}{' AND' if cond else ' WHERE'} infer_time > 0",
        params).fetchone()[0]
    conn.close()
    return {
        "total": total,
        "high_risk": high,
        "damaged": damaged,
        "normal": total - damaged,
        "avg_time": round(avg_time, 1) if avg_time else 0,
    }


# ─── 删除（分级） ─────────────────────────────────────────

def delete_record(record_id: int) -> bool:
    """删除单条记录，同时释放其持久化图片。"""
    return bool(delete_records([record_id]))


def delete_records(record_ids: List[int], owner_user_id: Optional[int] = None) -> int:
    """在同一事务中校验归属、删除记录并释放图片引用。已删除的记录可安全重试。"""
    import image_store
    conn = get_conn()
    unused_files = []
    count = 0
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            for rid in dict.fromkeys(record_ids):
                row = conn.execute(
                    "SELECT owner_user_id, image_file_id FROM detections WHERE id = ?", (rid,)
                ).fetchone()
                if row is None:
                    continue
                if owner_user_id is not None and row["owner_user_id"] != owner_user_id:
                    raise PermissionError("无权删除所选记录")
                conn.execute("DELETE FROM detections WHERE id = ?", (rid,))
                if row["image_file_id"]:
                    filename = image_store.release_reference(conn, row["image_file_id"])
                    if filename:
                        unused_files.append(filename)
                count += 1
    finally:
        conn.close()
    for filename in unused_files:
        image_store.remove_stored_file(filename)
    return count


def clear_user_records(owner_user_id: int) -> int:
    """清空指定用户的记录，并在删除事务中再次核对归属。"""
    conn = get_conn()
    ids = [r["id"] for r in conn.execute(
        "SELECT id FROM detections WHERE owner_user_id = ?", (owner_user_id,)
    ).fetchall()]
    conn.close()
    return delete_records(ids, owner_user_id)


def clear_all():
    """清空所有历史记录（兼容保留；图片同步释放）。"""
    conn = get_conn()
    ids = [r["id"] for r in conn.execute("SELECT id FROM detections").fetchall()]
    conn.close()
    delete_records(ids)


def count_expired_retention(days: int = 0) -> int:
    """统计超过保留天数的记录数（预留：数据保留策略）。"""
    if days <= 0:
        return 0
    conn = get_conn()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    n = conn.execute(
        "SELECT COUNT(*) FROM detections WHERE date(timestamp) < date(?)", (cutoff,)
    ).fetchone()[0]
    conn.close()
    return n
