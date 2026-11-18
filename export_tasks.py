"""
风电塔灾损测算软件 — 导出任务中心（DEVELOPMENT_PLAN.md §11.2 / 迁移 v4 export_tasks）

状态流转：pending → running → done / failed；done 且文件超期 → expired（可 retry 重开）。
文件保留 30 天（report_export.TASK_EXPIRE_DAYS），过期文件由 cleanup 删除。
"""

import os
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from history import get_conn, get_record, can_access
from report_export import generate_export, EXPORTS_DIR, TASK_EXPIRE_DAYS, PRESETS, FORMATS

_TIME_FMT = "%Y-%m-%d %H:%M:%S"

_FMT_EXT_LABELS = {"pdf": "PDF", "docx": "Word", "xlsx": "Excel", "csv": "CSV"}


def _now() -> str:
    return datetime.now().strftime(_TIME_FMT)


def _expires(days: int = TASK_EXPIRE_DAYS) -> str:
    return (datetime.now() + timedelta(days=days)).strftime(_TIME_FMT)


# ─── 任务 CRUD ────────────────────────────────────────────

def create_task(user_id: int, record_id: int, fmt: str,
                preset: str = "standard") -> int:
    assert fmt in FORMATS, f"bad fmt {fmt}"
    assert preset in PRESETS, f"bad preset {preset}"
    conn = get_conn()
    cur = conn.execute(
        """INSERT INTO export_tasks (user_id, record_id, fmt, preset, status, created_at)
           VALUES (?, ?, ?, ?, 'pending', ?)""",
        (user_id, record_id, fmt, preset, _now()))
    conn.commit()
    tid = cur.lastrowid
    conn.close()
    return tid


def get_task(task_id: int) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM export_tasks WHERE id = ?",
                       (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_tasks(owner_user_id: Optional[int] = None,
               limit: int = 30) -> List[Dict]:
    """任务列表（owner_user_id=None 查全部 = admin）。旧的先清理再列出。"""
    cleanup_expired_tasks()
    cond, params = "", ()
    if owner_user_id is not None:
        cond = " WHERE user_id = ?"
        params = (owner_user_id,)
    conn = get_conn()
    rows = conn.execute(
        f"""SELECT * FROM export_tasks{cond}
            ORDER BY id DESC LIMIT ?""", params + (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _set_status(task_id: int, status: str, error: str = None,
                file_path: str = None, expire: bool = False):
    sets = ["status = ?"]
    params: list = [status]
    if error is not None:
        sets.append("error = ?")
        params.append(error)
    if file_path is not None:
        sets.append("file_path = ?")
        params.append(file_path)
    if status in ("done", "failed", "expired"):
        sets.append("finished_at = ?")
        params.append(_now())
    if expire:
        sets.append("expires_at = ?")
        params.append(_expires())
    params.append(task_id)
    conn = get_conn()
    conn.execute(f"UPDATE export_tasks SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    conn.close()


# ─── 执行 / 重试 / 过期 ───────────────────────────────────

def run_task(task_id: int, user_id: Optional[int], is_admin: bool) -> Dict:
    """执行导出任务（同步生成；生成耗时秒级）。

    权限：user 仅能导出本人记录；admin 全量（越权导出被拒，任务标 failed）。
    返回更新后的任务行。
    """
    task = get_task(task_id)
    if not task:
        raise ValueError("task not found")
    _set_status(task_id, "running", error=None)

    try:
        record = get_record(task["record_id"]) if task["record_id"] else None
        if not record:
            raise RuntimeError("record missing")
        if not can_access(record, user_id, is_admin):
            raise PermissionError("no access")

        report = json.loads(record["json_report"])
        path = generate_export(task["fmt"], report, record,
                               preset=task["preset"] or "standard")
        _set_status(task_id, "done", file_path=path, expire=True)
    except PermissionError:
        _set_status(task_id, "failed", error="msg_record_no_access")
    except Exception as e:  # 生成失败：任务标 failed，留原因
        _set_status(task_id, "failed", error=str(e)[:200])
    return get_task(task_id)


def retry_task(task_id: int, user_id: Optional[int], is_admin: bool) -> Dict:
    """重试失败/过期任务：回到 pending 再执行。"""
    task = get_task(task_id)
    if not task:
        raise ValueError("task not found")
    if task["status"] not in ("failed", "expired"):
        return task
    conn = get_conn()
    conn.execute("UPDATE export_tasks SET status = 'pending', error = NULL WHERE id = ?",
                 (task_id,))
    conn.commit()
    conn.close()
    return run_task(task_id, user_id, is_admin)


def mark_expired_tasks() -> int:
    """done 且文件不存在或超期的任务 → expired。返回标记数。"""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, file_path, expires_at FROM export_tasks WHERE status = 'done'"
    ).fetchall()
    n = 0
    now = datetime.now()
    for r in rows:
        expired = False
        if r["expires_at"]:
            try:
                expired = datetime.strptime(r["expires_at"], _TIME_FMT) < now
            except ValueError:
                expired = False
        if not expired and r["file_path"] and not os.path.exists(r["file_path"]):
            expired = True  # 文件被清理/丢失
        if expired:
            conn.execute("UPDATE export_tasks SET status = 'expired' WHERE id = ?",
                         (r["id"],))
            n += 1
    conn.commit()
    conn.close()
    return n


def cleanup_expired_tasks() -> int:
    """删除已过期任务的历史行（文件本体由 report_export.cleanup_expired 清理）。"""
    mark_expired_tasks()
    conn = get_conn()
    cur = conn.execute(
        """DELETE FROM export_tasks WHERE status = 'expired'
           AND expires_at IS NOT NULL AND expires_at < ?""", (_now(),))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n


def delete_task(task_id: int, user_id: Optional[int], is_admin: bool) -> bool:
    """删除任务记录（文件保留给清理器统一处理）。user 只能删自己的。"""
    task = get_task(task_id)
    if not task:
        return False
    if not is_admin and task["user_id"] != user_id:
        return False
    conn = get_conn()
    conn.execute("DELETE FROM export_tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return True
