"""
风电塔灾损测算软件 — 数据库增量迁移脚本

版本化增量迁移（v2 归属与图片元数据 / v3 认证 / v4 导出任务 / v5 机组与构件），
特性：
  - 幂等：重复执行不报错、不重复改数据（schema_migrations 记录版本）
  - 自动备份：每次实际迁移前先 .bak（带版本号与时间戳）
  - 可回滚：restore_backup() 用最近一次 .bak 还原
  - 无 admin ID 硬编码假设：v2 旧记录 owner_user_id 置 NULL，
    v3 之后由应用层按用户名查询 admin 再回填（见 auth.backfill_migrated_records）

用法：
    python migrate.py            # 迁移到最新版本
    python migrate.py --status   # 查看当前版本
"""

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import history  # 提供 DB_PATH


def get_db_path():
    """允许测试通过环境变量指向临时库。"""
    return os.environ.get("WD_DB_PATH", history.DB_PATH)


def get_conn(db_path=None):
    conn = sqlite3.connect(db_path or get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# ─── 版本记录 ─────────────────────────────────────────────

def _ensure_schema_migrations(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        )
    """)


def current_version(conn) -> int:
    _ensure_schema_migrations(conn)
    row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
    return row["v"] or 1  # v1 = 原始 detections 表


def _column_exists(conn, table, column) -> bool:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r["name"] == column for r in rows)


def _table_exists(conn, table) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# ─── 备份 / 回滚 ──────────────────────────────────────────

def _backup(db_path: str, version: int) -> str:
    bak = f"{db_path}.bak_v{version}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, bak)
    return bak


def latest_backup(db_path=None):
    """返回最近一次迁移备份文件路径（无则 None）。"""
    import glob
    db_path = db_path or get_db_path()
    baks = sorted(glob.glob(f"{db_path}.bak_v*"))
    return baks[-1] if baks else None


def restore_backup(db_path=None) -> str:
    """用最近一次 .bak 还原数据库（迁移回滚路径）。"""
    db_path = db_path or get_db_path()
    bak = latest_backup(db_path)
    if not bak:
        raise FileNotFoundError("没有可用的迁移备份（.bak_v*）")
    shutil.copy2(bak, db_path)
    return bak


# ─── v2：归属 + 备注 + 图片元数据 ─────────────────────────

def migrate_v2(conn):
    """detections 增加 note/owner_user_id/created_by/source/image_file_id；
    新建 image_files 表与 persisted_images/ 目录；建查询索引。

    旧记录：source='migration'（列默认值），owner_user_id=NULL（待 v3 后回填）。
    """
    # detections 新列
    alters = [
        ("note", "TEXT"),
        ("owner_user_id", "INTEGER"),
        ("created_by", "TEXT"),
        # 默认值 migration：仅作用于迁移时刻已存在的旧行；
        # 应用层写入时始终显式指定 source（'ui'/'batch'）
        ("source", "TEXT DEFAULT 'migration'"),
        ("image_file_id", "INTEGER"),
    ]
    for col, decl in alters:
        if not _column_exists(conn, "detections", col):
            conn.execute(f"ALTER TABLE detections ADD COLUMN {col} {decl}")

    # 图片元数据表（§13.2）
    if not _table_exists(conn, "image_files"):
        conn.execute("""
            CREATE TABLE image_files (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                stored_name  TEXT UNIQUE NOT NULL,
                original_name TEXT NOT NULL,
                mime         TEXT,
                size         INTEGER,
                sha256       TEXT,
                created_at   TEXT,
                refcount     INTEGER NOT NULL DEFAULT 0
            )
        """)

    # 图片持久化目录
    store_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persisted_images")
    os.makedirs(store_dir, exist_ok=True)

    # 查询索引（历史筛选/排序/归属隔离）
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_det_timestamp ON detections(timestamp)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_det_high_risk ON detections(high_risk)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_det_owner ON detections(owner_user_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_img_sha256 ON image_files(sha256)"
    )


# ─── v3：认证（用户 / 会话） ──────────────────────────────

def migrate_v3(conn):
    """users / sessions 表（认证阶段建表，逻辑见 auth.py）。"""
    if not _table_exists(conn, "users"):
        conn.execute("""
            CREATE TABLE users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT UNIQUE NOT NULL,   -- 存储小写
                display_name  TEXT,
                role          TEXT NOT NULL DEFAULT 'user',  -- user / admin
                pw_hash       TEXT NOT NULL,          -- PBKDF2-SHA256
                pw_salt       TEXT NOT NULL,
                failed_count  INTEGER NOT NULL DEFAULT 0,
                locked_until  TEXT,
                created_at    TEXT NOT NULL,
                last_login_at TEXT,
                is_active     INTEGER NOT NULL DEFAULT 1
            )
        """)
    if not _table_exists(conn, "sessions"):
        conn.execute("""
            CREATE TABLE sessions (
                token      TEXT PRIMARY KEY,          -- 随机 256bit hex
                user_id    INTEGER NOT NULL REFERENCES users(id),
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked    INTEGER NOT NULL DEFAULT 0
            )
        """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sess_user ON sessions(user_id)")


# ─── v4：导出任务 ─────────────────────────────────────────

def migrate_v4(conn):
    """export_tasks 表（异步导出任务中心）。"""
    if not _table_exists(conn, "export_tasks"):
        conn.execute("""
            CREATE TABLE export_tasks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER REFERENCES users(id),
                record_id    INTEGER,
                fmt          TEXT NOT NULL,            -- pdf / docx / xlsx / csv
                preset       TEXT NOT NULL DEFAULT 'standard',
                status       TEXT NOT NULL DEFAULT 'pending',  -- pending/running/done/failed/expired
                file_path    TEXT,
                error        TEXT,
                created_at   TEXT NOT NULL,
                finished_at  TEXT,
                expires_at   TEXT
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_task_user ON export_tasks(user_id)"
        )


def migrate_v5(conn):
    """历史照片没有机组信息，保留原记录及空机组归属。"""
    if not _column_exists(conn, "detections", "turbine_id"):
        conn.execute("ALTER TABLE detections ADD COLUMN turbine_id TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS detection_parts (
            record_id INTEGER NOT NULL REFERENCES detections(id) ON DELETE CASCADE,
            part      TEXT NOT NULL,
            status    TEXT NOT NULL,
            PRIMARY KEY (record_id, part)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_det_turbine_owner
        ON detections(turbine_id, owner_user_id) WHERE turbine_id IS NOT NULL
    """)


def migrate_v6(conn):
    """按当前判据重算告警，以便旧记录和新记录使用相同的筛选和统计口径。"""
    from formatter import risk_alert

    for row in conn.execute("SELECT id, json_report, priority, high_risk FROM detections"):
        try:
            report = json.loads(row["json_report"])
        except (TypeError, ValueError):
            report = {}
        high_risk = int(risk_alert(report, row["priority"]) is not None)
        if row["high_risk"] != high_risk:
            conn.execute("UPDATE detections SET high_risk = ? WHERE id = ?", (high_risk, row["id"]))


def migrate_v7(conn):
    """从已关联机组的原始报告刷新部件索引，保留档案内容与记录编号。"""
    from wind_farm import observed_parts

    for row in conn.execute("SELECT id, json_report FROM detections WHERE turbine_id IS NOT NULL"):
        try:
            report = json.loads(row["json_report"])
        except (TypeError, ValueError):
            report = {}
        expected = observed_parts(report)
        existing = conn.execute("SELECT part, status FROM detection_parts WHERE record_id=? ORDER BY part",
                                (row["id"],))
        if expected == [tuple(entry) for entry in existing]:
            continue
        conn.execute("DELETE FROM detection_parts WHERE record_id=?", (row["id"],))
        conn.executemany("INSERT INTO detection_parts(record_id, part, status) VALUES (?, ?, ?)",
                         [(row["id"], part, status) for part, status in expected])


# ─── 迁移注册表（顺序执行） ───────────────────────────────

MIGRATIONS = [
    (2, "归属与图片元数据", migrate_v2),
    (3, "认证（用户/会话）", migrate_v3),
    (4, "导出任务", migrate_v4),
    (5, "巡检机组与构件", migrate_v5),
    (6, "按结构化报告校正历史高风险标记", migrate_v6),
    (7, "校正同一报告中各部件的病害与健康状态", migrate_v7),
]


def migrate(target=None, db_path=None):
    """迁移到 target 版本（默认最新）。返回实际执行的版本列表。"""
    db_path = db_path or get_db_path()
    conn = get_conn(db_path)
    applied = []
    try:
        v0 = current_version(conn)
        for version, name, fn in MIGRATIONS:
            if target is not None and version > target:
                break
            if version <= v0:
                continue
            bak = _backup(db_path, version)
            print(f"[migrate] v{version} {name} ... (backup: {os.path.basename(bak)})")
            fn(conn)
            conn.execute(
                "INSERT OR REPLACE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                (version, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
            )
            conn.commit()
            applied.append(version)
        if not applied:
            print(f"[migrate] 已是最新版本 v{v0}，无需迁移")
    finally:
        conn.close()
    return applied


if __name__ == "__main__":
    if "--status" in sys.argv:
        conn = get_conn()
        print(f"当前数据库版本: v{current_version(conn)}")
        conn.close()
    else:
        migrate()
