"""
风电塔灾损测算软件 — 图片持久化存储

检测图片持久化到 persisted_images/（UUID 文件名），元数据入 image_files 表：
  - sha256 去重：同图多条记录复用同一物理文件（refcount 计数）
  - 删除记录时 refcount-1，归零才物理删除（§13.2 生命周期规则）
"""

import os
import uuid
import hashlib
import shutil
import sqlite3
from datetime import datetime

import history  # 复用 DB_PATH / get_conn

STORE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "persisted_images")

# 磁盘限额（可配）：persisted_images/ 超过 5GB 拒绝新分析
QUOTA_BYTES = int(os.environ.get("WD_IMAGE_QUOTA_GB", "5")) * 1024 ** 3


def _ensure_dir():
    os.makedirs(STORE_DIR, exist_ok=True)


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def store_dir_size() -> int:
    total = 0
    if os.path.isdir(STORE_DIR):
        for name in os.listdir(STORE_DIR):
            p = os.path.join(STORE_DIR, name)
            if os.path.isfile(p):
                total += os.path.getsize(p)
    return total


def check_quota() -> bool:
    """是否还有写入空间。"""
    return store_dir_size() < QUOTA_BYTES


def store_image(image_path: str) -> int:
    """持久化图片，返回 image_file_id。sha256 相同则复用并 refcount+1。"""
    _ensure_dir()
    conn = history.get_conn()
    try:
        digest = _sha256(image_path)
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id FROM image_files WHERE sha256 = ?", (digest,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE image_files SET refcount = refcount + 1 WHERE id = ?",
                (row["id"],),
            )
            conn.commit()
            return row["id"]

        ext = os.path.splitext(image_path)[1].lower() or ".jpg"
        stored_name = f"{uuid.uuid4().hex}{ext}"
        dest = os.path.join(STORE_DIR, stored_name)
        shutil.copy2(image_path, dest)
        mime = _guess_mime(ext)
        cur = conn.execute(
            """INSERT INTO image_files
               (stored_name, original_name, mime, size, sha256, created_at, refcount)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (stored_name, os.path.basename(image_path), mime,
             os.path.getsize(dest), digest,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def _guess_mime(ext: str) -> str:
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".gif": "image/gif", ".bmp": "image/bmp",
    }.get(ext, "application/octet-stream")


def get_image_path(image_file_id: int):
    """返回物理文件路径；不存在（已删除）返回 None。"""
    conn = history.get_conn()
    try:
        row = conn.execute(
            "SELECT stored_name FROM image_files WHERE id = ?", (image_file_id,)
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    path = os.path.join(STORE_DIR, row["stored_name"])
    return path if os.path.exists(path) else None


def release_reference(conn, image_file_id):
    """释放一个图片引用，返回事务提交后需要移除的文件名。"""
    row = conn.execute(
        "SELECT stored_name, refcount FROM image_files WHERE id = ?", (image_file_id,),
    ).fetchone()
    if not row:
        return None
    if row["refcount"] > 1:
        conn.execute("UPDATE image_files SET refcount = refcount - 1 WHERE id = ?", (image_file_id,))
        return None
    conn.execute("DELETE FROM image_files WHERE id = ?", (image_file_id,))
    return row["stored_name"]


def remove_stored_file(filename):
    try:
        os.remove(os.path.join(STORE_DIR, filename))
    except OSError:
        pass  # 文件占用等：purge_orphans 可回收孤儿文件。


def release_image(image_file_id):
    """记录删除时调用：refcount-1，归零则删除行与磁盘文件。"""
    if not image_file_id:
        return
    conn = history.get_conn()
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            filename = release_reference(conn, image_file_id)
    finally:
        conn.close()
    if filename:
        remove_stored_file(filename)


def purge_orphans():
    """清理磁盘上没有对应元数据行的孤儿文件（维护用）。"""
    _ensure_dir()
    conn = history.get_conn()
    try:
        known = {r["stored_name"] for r in
                 conn.execute("SELECT stored_name FROM image_files").fetchall()}
    finally:
        conn.close()
    removed = 0
    for name in os.listdir(STORE_DIR):
        if name not in known:
            try:
                os.remove(os.path.join(STORE_DIR, name))
                removed += 1
            except OSError:
                pass
    return removed
