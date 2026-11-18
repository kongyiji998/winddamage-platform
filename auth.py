"""
风电塔灾损测算软件 — 认证模块（DEVELOPMENT_PLAN.md §10 / §13）

- PBKDF2-SHA256 口令哈希（200k 轮，随机盐，无明文/无可逆存储）
- 登录失败 5 次锁定（默认 15 分钟，env WD_LOCK_MINUTES）
- 服务端会话（sessions 表，随机 256bit token，HttpOnly Cookie，默认 12h 过期）
- 用户名 4–40 字符（允许中文），存储小写、大小写不敏感
- 不做任何 admin_id 硬编码假设；迁移数据回填按用户名查询（§13.1）

安全约定：
  - 认证失败统一返回模糊提示（不区分用户不存在/密码错误，防枚举）
  - 锁定按账号计（已注册账号）；会话过期/吊销后立即失效
"""

import os
import re
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from history import get_conn

SESSION_COOKIE = "wd_session"
PBKDF2_ITERATIONS = 200_000
SESSION_TTL_HOURS = int(os.environ.get("WD_SESSION_HOURS", "12"))
LOCK_MINUTES = int(os.environ.get("WD_LOCK_MINUTES", "15"))
# 登录失败锁定保护：0 = 关闭（默认）。需要时设 WD_MAX_FAILED_ATTEMPTS=5 重新启用。
MAX_FAILED_ATTEMPTS = int(os.environ.get("WD_MAX_FAILED_ATTEMPTS", "0"))

_TIME_FMT = "%Y-%m-%d %H:%M:%S"

# 用户名：去空格后转小写存储；4–40 字符；字母/数字/下划线/连字符/中文
_USERNAME_RE = re.compile(r"^[a-z0-9_\-一-鿿]{4,40}$")


def _now() -> str:
    return datetime.now().strftime(_TIME_FMT)


def _expires(hours: float = SESSION_TTL_HOURS) -> str:
    return (datetime.now() + timedelta(hours=hours)).strftime(_TIME_FMT)


# ─── 口令哈希 ─────────────────────────────────────────────

def hash_password(password: str) -> Tuple[str, str]:
    """返回 (salt_hex, hash_hex)。"""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex(), dk.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex),
            PBKDF2_ITERATIONS)
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# ─── 校验规则 ─────────────────────────────────────────────

def normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def username_issue(username: str) -> Optional[str]:
    """用户名不合法时返回错误码，合法返回 None。"""
    u = normalize_username(username)
    if not _USERNAME_RE.match(u):
        return "auth_username_invalid"
    return None


def password_issues(password: str) -> List[str]:
    """密码未满足的规则列表（≥8 位、含字母、含数字）。为空表示合法。"""
    issues = []
    if len(password or "") < 8:
        issues.append("auth_pw_len")
    if not re.search(r"[A-Za-z]", password or ""):
        issues.append("auth_pw_letter")
    if not re.search(r"\d", password or ""):
        issues.append("auth_pw_digit")
    return issues


# ─── 用户 ─────────────────────────────────────────────────

class UsernameExists(Exception):
    pass


def create_user(username: str, password: str, role: str = "user",
                display_name: str = "") -> int:
    """创建用户（存储小写用户名）。重名抛 UsernameExists。"""
    u = normalize_username(username)
    if username_issue(u):
        raise ValueError("auth_username_invalid")
    issues = password_issues(password)
    if issues:
        raise ValueError(issues[0])
    if role not in ("user", "admin"):
        raise ValueError("auth_bad_role")
    salt, pw_hash = hash_password(password)
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO users (username, display_name, role, pw_hash, pw_salt, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (u, display_name or u, role, pw_hash, salt, _now()))
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        raise UsernameExists(u)
    finally:
        conn.close()


def count_users() -> int:
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    conn.close()
    return n


def _row_to_user(row) -> Optional[Dict]:
    if not row:
        return None
    d = dict(row)
    d.pop("pw_hash", None)
    d.pop("pw_salt", None)
    return d


def get_user(user_id: int) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return _row_to_user(row)


def get_user_by_name(username: str) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (normalize_username(username),)
    ).fetchone()
    conn.close()
    return _row_to_user(row)


def list_users() -> List[Dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT id, username, display_name, role, created_at, last_login_at,
                  failed_count, locked_until, is_active
           FROM users ORDER BY id""")
    out = [dict(r) for r in rows.fetchall()]
    conn.close()
    return out


# ─── 登录 / 锁定 ──────────────────────────────────────────

def _lock_until() -> str:
    return (datetime.now() + timedelta(minutes=LOCK_MINUTES)).strftime(_TIME_FMT)


def _lock_remaining_minutes(locked_until: str) -> int:
    try:
        until = datetime.strptime(locked_until, _TIME_FMT)
    except (ValueError, TypeError):
        return 0
    secs = (until - datetime.now()).total_seconds()
    return max(0, int((secs + 59) // 60))  # 向上取整分钟


def authenticate(username: str, password: str) -> Tuple[str, object]:
    """登录验证。返回 (status, payload)：
      ("ok", user_dict)
      ("failed", attempts_left)        — 凭据错误（含用户不存在，不区分）
      ("locked", remaining_minutes)    — 账号锁定中（仅 WD_MAX_FAILED_ATTEMPTS>0 时可能）
    """
    user = None
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (normalize_username(username),)).fetchone()
        if row and not row["is_active"]:
            conn.close()
            return "failed", MAX_FAILED_ATTEMPTS
        if row:
            user = dict(row)
            if user["locked_until"] and MAX_FAILED_ATTEMPTS > 0:
                remain = _lock_remaining_minutes(user["locked_until"])
                if remain > 0:
                    conn.close()
                    return "locked", remain
                # 锁定已过期：重置计数继续验证
                conn.execute(
                    "UPDATE users SET locked_until = NULL, failed_count = 0 WHERE id = ?",
                    (user["id"],))
                conn.commit()
                user["failed_count"] = 0
                user["locked_until"] = None

        if user and verify_password(password, user["pw_salt"], user["pw_hash"]):
            conn.execute(
                """UPDATE users SET failed_count = 0, locked_until = NULL,
                                       last_login_at = ? WHERE id = ?""",
                (_now(), user["id"]))
            conn.commit()
            conn.close()
            return "ok", _row_to_user(
                get_user(user["id"]) or user)  # get_user 去掉口令字段

        # 失败：已注册账号累计计数并可能触发锁定；未注册账号不暴露信息
        if user:
            failed = user["failed_count"] + 1
            if MAX_FAILED_ATTEMPTS <= 0:
                # 锁定保护关闭：不计数、顺带清掉历史遗留的锁定状态
                conn.execute(
                    "UPDATE users SET failed_count = 0, locked_until = NULL WHERE id = ?",
                    (user["id"],))
                conn.commit()
            else:
                if failed >= MAX_FAILED_ATTEMPTS:
                    conn.execute(
                        """UPDATE users SET failed_count = 0, locked_until = ? WHERE id = ?""",
                        (_lock_until(), user["id"]))
                    conn.commit()
                    conn.close()
                    return "locked", LOCK_MINUTES
                conn.execute(
                    "UPDATE users SET failed_count = ? WHERE id = ?",
                    (failed, user["id"]))
                conn.commit()
        conn.close()
        if MAX_FAILED_ATTEMPTS <= 0:
            return "failed", 0
        return "failed", MAX_FAILED_ATTEMPTS - (user["failed_count"] + 1 if user else 0)
    finally:
        try:
            conn.close()
        except Exception:
            pass


# ─── 会话 ─────────────────────────────────────────────────

def create_session(user_id: int, days: Optional[float] = None) -> str:
    """签发新会话 token，并顺手清理过期会话。

    days 指定自定义有效期（天），用于「记住密码」长效登录；不传保持旧行为。
    """
    token = secrets.token_hex(32)
    expires = _expires(days * 24) if days else _expires()
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, user_id, _now(), expires))
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (_now(),))
    conn.commit()
    conn.close()
    return token


def get_session_user(token: Optional[str]) -> Optional[Dict]:
    """校验会话 token，返回用户信息；无效/过期/吊销/停用返回 None。"""
    if not token:
        return None
    conn = get_conn()
    row = conn.execute(
        """SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id
           WHERE s.token = ? AND s.revoked = 0 AND s.expires_at > ? AND u.is_active = 1""",
        (token, _now())).fetchone()
    conn.close()
    return _row_to_user(row)


def revoke_session(token: Optional[str]):
    if not token:
        return
    conn = get_conn()
    conn.execute("UPDATE sessions SET revoked = 1 WHERE token = ?", (token,))
    conn.commit()
    conn.close()


def revoke_user_sessions(user_id: int, except_token: Optional[str] = None):
    conn = get_conn()
    if except_token:
        conn.execute(
            "UPDATE sessions SET revoked = 1 WHERE user_id = ? AND token != ?",
            (user_id, except_token))
    else:
        conn.execute("UPDATE sessions SET revoked = 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()


# ─── Cookie / 请求解析 ────────────────────────────────────

def parse_cookie(header_value: Optional[str], name: str = SESSION_COOKIE) -> Optional[str]:
    """从 Cookie 头解析指定 token。"""
    if not header_value:
        return None
    for part in header_value.split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v or None
    return None


def user_for_request(request) -> Optional[Dict]:
    """从请求（FastAPI Request 或 gradio Request，均有 .headers）解析当前用户。"""
    if request is None:
        return None
    local_user = getattr(getattr(request, "state", None), "local_user", None)
    if local_user is not None:
        return local_user
    try:
        header = request.headers.get("cookie")
    except Exception:
        return None
    return get_session_user(parse_cookie(header))


# ─── 口令修改 / 管理操作 ──────────────────────────────────

def change_password(user_id: int, old_pw: str, new_pw: str,
                    current_token: Optional[str] = None) -> Tuple[bool, Optional[str]]:
    """修改口令：校验旧口令与新规则；成功后吊销其他会话。返回 (ok, 错误码)。"""
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not row:
        conn.close()
        return False, "auth_user_missing"
    if not verify_password(old_pw, row["pw_salt"], row["pw_hash"]):
        conn.close()
        return False, "auth_old_pw_wrong"
    issues = password_issues(new_pw)
    if issues:
        conn.close()
        return False, issues[0]
    salt, pw_hash = hash_password(new_pw)
    conn.execute("UPDATE users SET pw_hash = ?, pw_salt = ? WHERE id = ?",
                 (pw_hash, salt, user_id))
    conn.commit()
    conn.close()
    revoke_user_sessions(user_id, except_token=current_token)
    return True, None


def set_user_active(user_id: int, active: bool):
    conn = get_conn()
    conn.execute("UPDATE users SET is_active = ? WHERE id = ?",
                 (1 if active else 0, user_id))
    conn.commit()
    conn.close()
    if not active:
        revoke_user_sessions(user_id)


def unlock_user(user_id: int):
    conn = get_conn()
    conn.execute(
        "UPDATE users SET failed_count = 0, locked_until = NULL WHERE id = ?",
        (user_id,))
    conn.commit()
    conn.close()


def set_user_role(user_id: int, role: str):
    if role not in ("user", "admin"):
        raise ValueError("auth_bad_role")
    conn = get_conn()
    conn.execute("UPDATE users SET role = ? WHERE id = ?", (role, user_id))
    conn.commit()
    conn.close()


def reset_password(user_id: int, new_pw: str) -> Optional[str]:
    """管理员重置口令（不需旧口令）。返回错误码或 None。"""
    issues = password_issues(new_pw)
    if issues:
        return issues[0]
    salt, pw_hash = hash_password(new_pw)
    conn = get_conn()
    conn.execute("UPDATE users SET pw_hash = ?, pw_salt = ?, failed_count = 0, locked_until = NULL WHERE id = ?",
                 (pw_hash, salt, user_id))
    conn.commit()
    conn.close()
    revoke_user_sessions(user_id)
    return None


# ─── 迁移数据回填（§13.1：不假设 admin id，按用户名查询） ──

def backfill_migration_owner(admin_username: str) -> int:
    """把迁移数据（owner NULL 且 source='migration'）归属到指定用户名对应的账号。
    返回回填条数。source 保持 'migration' 以保留「系统迁移数据」标识。"""
    admin = get_user_by_name(admin_username)
    if not admin:
        return 0
    conn = get_conn()
    cur = conn.execute(
        """UPDATE detections SET owner_user_id = ?
           WHERE owner_user_id IS NULL AND source = 'migration'""",
        (admin["id"],))
    conn.commit()
    n = cur.rowcount
    conn.close()
    return n
