"""新版大屏 /screen 路由层：页面服务端渲染 + JSON API。

设计文档：OUTPUT/设计文档.md；实施计划：OUTPUT/实施计划.md。
原则：复用 auth/history/app 推理层，旧界面（/ 入口）零改动。
"""
import os

from fastapi import APIRouter, Request
from fastapi.responses import (HTMLResponse, RedirectResponse, JSONResponse,
                               Response)

import auth
from parser import IncompleteReportError
from formatter import risk_alert

router = APIRouter(prefix="/screen")
account_router = APIRouter(prefix="/screen")

SCREEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "screen")

# 迭代期静态资源不缓存（皮肤迭代教训：浏览器缓存造成"改了没生效"假象）
_NO_CACHE = {"Cache-Control": "no-cache"}


def _page(html: str) -> HTMLResponse:
    return HTMLResponse(html, headers=_NO_CACHE)


def _current_user(request: Request):
    """当前会话用户（复用 wd_session Cookie，与旧入口通用）。"""
    return auth.user_for_request(request)


# ─── 登录 / 注册 ─────────────────────────────────────────────
_LOGIN_ERR = {
    "auth_username_invalid": "账号格式不正确",
    "auth_pw_len": "密码长度不足（至少 8 位）",
    "auth_pw_letter": "密码需包含字母",
    "auth_pw_digit": "密码需包含数字",
    "dup": "该账号已被注册",
    "confirm": "两次输入的密码不一致",
}


def _login_page_html(error: str = "", mode: str = "login") -> str:
    """大屏登录/注册页。mode: "login" | "register"（错误回显时保持所在 Tab）。"""
    err = f'<div class="sc-form-error">{error}</div>' if error else ""
    reg_active = " active" if mode == "register" else ""
    log_active = " active" if mode != "register" else ""
    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>登录 · 基于多模态大模型的风电塔灾损测算平台</title>'
        '<link rel="stylesheet" href="/screen-assets/screen.css">'
        '<link rel="stylesheet" href="/screen-assets/hud-theme.css">'
        '<style>'
        '.sc-tabs{display:flex;gap:6px;margin:14px 0 4px;background:rgba(7,20,40,.55);'
        'border-radius:8px;padding:4px}'
        '.sc-tab{flex:1;height:34px;border:0;border-radius:6px;cursor:pointer;'
        'background:transparent;color:#7E9CBE;font-size:14px;letter-spacing:2px}'
        '.sc-tab.active{background:var(--hud-active);color:#fff}'
        '.sc-login-box form.sc-mode{display:none}'
        '.sc-login-box form.sc-mode.active{display:flex;flex-direction:column;gap:16px}'
        '.pw-wrap{position:relative;display:block}'
        '.pw-wrap input{width:100%;box-sizing:border-box;padding-right:42px}'
        '.pw-eye{position:absolute;right:4px;top:50%;transform:translateY(-50%);'
        'width:34px;height:34px;border:0;background:transparent;cursor:pointer;'
        'color:#7E9CBE;font-size:17px;line-height:1}'
        '.pw-eye.on{color:#22D3EE}'
        '.sc-login-box label.sc-remember{display:flex;flex-direction:row;align-items:center;gap:8px}'
        '.sc-login-box label.sc-remember input{width:15px;height:15px;min-height:0;padding:0;'
        'border:0;background:transparent;accent-color:#22D3EE;box-shadow:none;flex:none}'
        '.sc-form-hint{font-size:12px;color:#7E9CBE;margin:-6px 0 4px}'
        '</style></head>'
        '<body class="sc-page sc-login mountain-hud">'
        '<div class="sc-login-box sc-panel">'
        '<div class="sc-login-title">基于多模态大模型的风电塔灾损测算平台</div>'
        '<div class="sc-login-sub">WIND TURBINE TOWER DAMAGE ASSESSMENT</div>'
        '<div class="sc-tabs">'
        f'<button type="button" class="sc-tab{log_active}" data-mode="login">登 录</button>'
        f'<button type="button" class="sc-tab{reg_active}" data-mode="register">注 册</button>'
        '</div>'
        + err +
        '<form method="post" action="/screen/login" class="sc-mode sc-mode-login' + log_active + '">'
        '<label>账号<input name="username" id="li-user" autocomplete="username" required></label>'
        '<label>密码<span class="pw-wrap">'
        '<input name="password" id="li-pw" type="password"'
        ' autocomplete="current-password" required>'
        '<button type="button" class="pw-eye" data-target="li-pw" title="显示/隐藏密码">👁</button>'
        '</span></label>'
        '<label class="sc-remember"><input type="checkbox" name="remember" id="li-remember">'
        '记住密码（30 天免登录）</label>'
        '<button class="sc-btn primary" type="submit">登 录</button>'
        '</form>'
        '<form method="post" action="/screen/register" class="sc-mode sc-mode-register' + reg_active + '"'
        ' id="rg-form">'
        '<label>账号<input name="username" id="rg-user" autocomplete="username" required></label>'
        '<label>密码<span class="pw-wrap">'
        '<input name="password" id="rg-pw" type="password"'
        ' autocomplete="new-password" required>'
        '<button type="button" class="pw-eye" data-target="rg-pw" title="显示/隐藏密码">👁</button>'
        '</span></label>'
        '<label>确认密码<span class="pw-wrap">'
        '<input name="confirm" id="rg-pw2" type="password"'
        ' autocomplete="new-password" required>'
        '<button type="button" class="pw-eye" data-target="rg-pw2" title="显示/隐藏密码">👁</button>'
        '</span></label>'
        '<div class="sc-form-hint">密码至少 8 位，需包含字母和数字；新账号为巡检员角色</div>'
        '<button class="sc-btn primary" type="submit">注册并登录</button>'
        '</form>'
        '</div>'
        '<script src="/screen-assets/login.js"></script>'
        '</body></html>')


@account_router.get("/login", response_class=HTMLResponse)
async def login_page(error: str = ""):
    return _page(_login_page_html("账号或密码错误" if error else ""))


@account_router.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    status, payload = auth.authenticate(str(form.get("username") or ""),
                                        str(form.get("password") or ""))
    if status == "ok":
        remember = str(form.get("remember") or "").lower() in ("on", "1", "true")
        days = 30 if remember else None
        resp = RedirectResponse("/screen", status_code=302)
        resp.set_cookie(
            auth.SESSION_COOKIE, auth.create_session(payload["id"], days=days),
            httponly=True, samesite="lax",
            max_age=30 * 86400 if days else auth.SESSION_TTL_HOURS * 3600, path="/")
        return resp
    if status == "locked":
        return _page(_login_page_html(f"尝试过多，已锁定，请 {payload} 分钟后重试"))
    return _page(_login_page_html("账号或密码错误"))


@account_router.post("/register", response_class=HTMLResponse)
async def register_submit(request: Request):
    """开放注册：创建巡检员账号并自动登录。"""
    form = await request.form()
    username = str(form.get("username") or "")
    password = str(form.get("password") or "")
    confirm = str(form.get("confirm") or "")

    def fail(code):
        return _page(_login_page_html(_LOGIN_ERR.get(code, "注册失败"), mode="register"))

    if password != confirm:
        return fail("confirm")
    uissue = auth.username_issue(username)
    if uissue:
        return fail(uissue)
    issues = auth.password_issues(password)
    if issues:
        return fail(issues[0])
    try:
        uid = auth.create_user(username, password, role="user")
    except auth.UsernameExists:
        return fail("dup")
    except ValueError as exc:
        return fail(str(exc))
    resp = RedirectResponse("/screen", status_code=302)
    resp.set_cookie(
        auth.SESSION_COOKIE, auth.create_session(uid),
        httponly=True, samesite="lax",
        max_age=auth.SESSION_TTL_HOURS * 3600, path="/")
    return resp


# ─── 页面（骨架占位；Task 4-7 逐页充实） ──────────────────────
@router.get("", response_class=HTMLResponse)
async def home_page(request: Request):
    with open(os.path.join(SCREEN_DIR, "home.html"), encoding="utf-8") as f:
        html = f.read()
    if getattr(request.state, "local_user", None) is not None:
        html = html.replace("<body ", "<body data-local ", 1)
    return _page(html)


@router.get("/batch", response_class=HTMLResponse)
async def batch_page(request: Request):
    with open(os.path.join(SCREEN_DIR, "batch.html"), encoding="utf-8") as f:
        return _page(f.read())


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    with open(os.path.join(SCREEN_DIR, "history.html"), encoding="utf-8") as f:
        return _page(f.read())


# ─── 账户 / 用户管理 / 导出 ──────────────────────────────────
@account_router.post("/api/change-password")
async def api_change_password(request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    body = await request.json()
    token = auth.parse_cookie(request.headers.get("cookie"))
    ok, err = auth.change_password(user["id"], str(body.get("old_password") or ""),
                                   str(body.get("new_password") or ""),
                                   current_token=token)
    if not ok:
        return JSONResponse({"detail": err or "change failed"}, status_code=400)
    return JSONResponse({"ok": True})


def _user_public(u):
    return {k: u.get(k) for k in ("id", "username", "role", "is_active",
                                  "created_at", "last_login")}


@account_router.get("/api/users")
async def api_users(request: Request):
    user = _current_user(request)
    if not user or user.get("role") != "admin":
        return JSONResponse({"detail": "admin only"}, status_code=403)
    return JSONResponse({"users": [_user_public(u) for u in auth.list_users()]})


@account_router.post("/api/users/{target_id}/action")
async def api_user_action(request: Request, target_id: int):
    user = _current_user(request)
    if not user or user.get("role") != "admin":
        return JSONResponse({"detail": "admin only"}, status_code=403)
    body = await request.json()
    action = str(body.get("action") or "")
    value = body.get("value")
    if target_id == user["id"] and action in ("deactivate", "set_role"):
        return JSONResponse({"detail": "cannot modify own account this way"}, status_code=400)
    if action == "activate":
        auth.set_user_active(target_id, True)
    elif action == "deactivate":
        auth.set_user_active(target_id, False)
    elif action == "unlock":
        auth.unlock_user(target_id)
    elif action == "set_role":
        if value not in ("admin", "user"):
            return JSONResponse({"detail": "bad role"}, status_code=400)
        auth.set_user_role(target_id, value)
    elif action == "reset_password":
        err = auth.reset_password(target_id, str(value or ""))
        if err:
            return JSONResponse({"detail": err}, status_code=400)
    else:
        return JSONResponse({"detail": "unknown action"}, status_code=400)
    return JSONResponse({"ok": True})


@router.get("/api/export/{record_id}")
async def api_export(request: Request, record_id: int, format: str = "md"):
    """从本次评估的归档内容生成报告下载。旧链接默认返回 Markdown。"""
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    rec = history.get_record(record_id)
    if not rec:
        return JSONResponse({"detail": "not found"}, status_code=404)
    if not history.can_access(rec, user["id"], user.get("role") == "admin"):
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    media_types = {"pdf": "application/pdf", "md": "text/markdown", "csv": "text/csv"}
    if format not in media_types:
        return JSONResponse({"detail": "unsupported report format"}, status_code=400)
    from report_export import record_download
    from starlette.concurrency import run_in_threadpool
    report = rec.get("json_report")
    if isinstance(report, str):
        try:
            report = _json.loads(report)
        except ValueError:
            return JSONResponse({"detail": "invalid archived JSON"}, status_code=422)
    if not isinstance(report, dict):
        return JSONResponse({"detail": "invalid archived report"}, status_code=422)
    data = await run_in_threadpool(record_download, report, rec, format)
    return Response(content=data, media_type=media_types[format],
                    headers={"Content-Disposition": f'attachment; filename="report_{record_id}.{format}"',
                             "Cache-Control": "private, no-store"})


@account_router.get("/account", response_class=HTMLResponse)
async def account_page(request: Request):
    with open(os.path.join(SCREEN_DIR, "account.html"), encoding="utf-8") as f:
        return _page(f.read())


# ─── JSON API ─────────────────────────────────────────────────
import json as _json
import shutil as _shutil
import tempfile as _tempfile
import time as _time
from datetime import date as _date, timedelta as _timedelta

import history
from wind_farm import TURBINE_IDS, farm_payload, observed_parts


@router.get("/api/me")
async def api_me(request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"username": None, "role": None})
    return JSONResponse({"username": user["username"], "role": user.get("role")})


def _scope(user):
    """(owner_scope, is_admin)：admin 见全量，普通用户仅本人。"""
    if not user:
        return 0, False
    return (None, True) if user.get("role") == "admin" else (user["id"], False)


def _row_item(row):
    """history 行 → 大屏历史/快查 JSON。"""
    return {
        "id": row["id"], "timestamp": row["timestamp"], "image_name": row["image_name"],
        "high_risk": bool(row["high_risk"]), "has_damage": row["has_damage"],
        "damage_type": row["damage_type"], "component": row["component"],
        "priority": row["priority"], "confidence": row["confidence"],
        "infer_time": row["infer_time"], "note": row.get("note", ""),
        "turbine_id": row.get("turbine_id"), "image_file_id": row.get("image_file_id"),
    }


def _overview_payload(owner_scope, week, recheck):
    stats = history.get_stats(owner_scope)
    total = stats["total"]
    completion = round(100 * min(total, 120) / 120) if total else 0
    return {"total": total, "week": week, "high_risk": stats["high_risk"],
            "recheck": recheck, "completion": completion}


def _report_payload(parsed, record_id, infer_time, image_info, recent, turbine_id=None):
    """模型报告 → 大屏右列完整报告 JSON（设计文档 §5）。"""
    from app import _damage_locator_payload, format_summary
    from config import MODEL_PATH
    from parser import get_field
    import i18n
    level = get_field(parsed, i18n.SECTION_CONCLUSION, "巡检优先级")
    dtype = get_field(parsed, i18n.SECTION_DAMAGE, "损伤类型")
    conf = get_field(parsed, i18n.SECTION_CONCLUSION, "本次判断的置信度")
    return {
        "record_id": record_id,
        "turbine_id": turbine_id,
        "json_report": parsed,
        "summary": format_summary(parsed),
        "risk": {"level": level.strip(), "type": dtype, "confidence": conf, "alert": risk_alert(parsed)},
        "kv": {
            "component": get_field(parsed, i18n.SECTION_COMPONENT, "构件名称"),
            "location": get_field(parsed, i18n.SECTION_DAMAGE, "损伤分布位置与范围"),
            "size": (get_field(parsed, i18n.SECTION_DAMAGE, "损伤程度")
                     or get_field(parsed, i18n.SECTION_DAMAGE, "损伤尺寸")),
            "advice": get_field(parsed, i18n.SECTION_OM, "短期处置建议"),
            "model": os.path.basename(os.path.normpath(MODEL_PATH)),
            "time": _time.strftime("%Y-%m-%d %H:%M:%S"),
            "report_no": f"RPT-{_time.strftime('%Y%m%d')}-{record_id:04d}",
        },
        "locator": _damage_locator_payload(parsed),
        "image_info": image_info,
        "recent": recent,
    }


def _week_count(owner_scope):
    monday = (_date.today() - _timedelta(days=_date.today().weekday())).strftime("%Y-%m-%d")
    _, total = history.query_records(limit=1, offset=0, owner_user_id=owner_scope,
                                     date_from=monday)
    return total


@router.get("/api/overview")
async def api_overview(request: Request):
    user = _current_user(request)
    scope, _is_admin = _scope(user)
    return JSONResponse(_overview_payload(scope, _week_count(scope),
                                          history.get_stats(scope)["high_risk"]))


@router.get("/api/farm")
async def api_farm(request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    scope, _ = _scope(user)
    return JSONResponse(farm_payload(history.latest_turbine_observations(scope)),
                        headers={"Cache-Control": "no-store"})


@router.get("/api/damage-stats")
def api_damage_stats(request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    scope, _ = _scope(user)
    return JSONResponse(history.damage_type_stats(scope), headers={"Cache-Control": "no-store"})


def _upload_turbines(form, count):
    ids = form.getlist("turbine_id")
    if not ids:  # Requests from older inspection clients have no turbine attribution.
        return [None] * count
    if len(ids) not in (1, count):
        raise ValueError("机组编号数量与图片数量不符")
    if any(unit not in TURBINE_IDS for unit in ids):
        raise ValueError("未知机组编号")
    return ids * count if len(ids) == 1 else ids


@router.post("/api/analyze")
async def api_analyze(request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    form = await request.form()
    up = form.get("file")
    if up is None or not getattr(up, "filename", ""):
        return JSONResponse({"detail": "no file"}, status_code=400)
    try:
        turbine_id, = _upload_turbines(form, 1)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    from app import _do_inference, get_image_info
    tmpd = _tempfile.mkdtemp(prefix="sc_")
    path = os.path.join(tmpd, os.path.basename(up.filename))
    with open(path, "wb") as f:
        f.write(await up.read())
    try:
        parsed, raw, infer_time = _do_inference(path)
        if parsed is None:
            return JSONResponse({"detail": "模型输出未能解析为 JSON 报告，请重新评估。", "raw": str(raw)[:500]},
                                status_code=422)
        owner_scope, _ = _scope(user)
        rid = history.save_record(os.path.basename(up.filename), parsed, infer_time,
                                  path, source="screen", persist_image=True,
                                  owner_user_id=user["id"],
                                  created_by=user["username"], turbine_id=turbine_id)
        rows, _total = history.query_records(limit=6, offset=0, owner_user_id=owner_scope)
        image_info = {"filename": os.path.basename(up.filename),
                      "meta": get_image_info(path) or ""}
        payload = _report_payload(parsed, rid, infer_time, image_info,
                                  [_row_item(r) for r in rows], turbine_id)
        return JSONResponse(payload)
    except IncompleteReportError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=422)
    finally:
        _shutil.rmtree(tmpd, ignore_errors=True)


@router.get("/api/records")
async def api_records(request: Request, page: int = 1, page_size: int = 15,
                      search: str = "", risk: str = "", date_from: str = "",
                      date_to: str = "", sort: str = "time_desc", turbine_id: str = ""):
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    scope, _is_admin = _scope(user)
    rows, total = history.query_records(
        limit=page_size, offset=max(0, (page - 1) * page_size),
        owner_user_id=scope, search=search.strip(),
        risk={"high": "high", "normal": "normal"}.get(risk.strip(), ""),
        date_from=date_from.strip(), date_to=date_to.strip(), sort=sort.strip(),
        turbine_id=turbine_id.strip())
    return JSONResponse({"rows": [_row_item(r) for r in rows], "total": total,
                         "stats": history.get_stats(scope)})


@router.post("/api/batch")
async def api_batch(request: Request):
    """批量分析：逐张推理+入库（失败不中断），返回逐行结果与汇总。

    有存储配额时归档原图；配额已满时仍保存报告。
    """
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    form = await request.form()
    uploads = [u for u in form.getlist("files") if getattr(u, "filename", "")]
    if not uploads:
        return JSONResponse({"detail": "no files"}, status_code=400)
    try:
        turbine_ids = _upload_turbines(form, len(uploads))
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    from app import _do_inference
    from parser import get_field
    import i18n
    results, high = [], 0
    tmpd = _tempfile.mkdtemp(prefix="scb_")
    try:
        for up, turbine_id in zip(uploads, turbine_ids):
            name = os.path.basename(up.filename)
            path = os.path.join(tmpd, name)
            with open(path, "wb") as f:
                f.write(await up.read())
            try:
                parsed, raw, infer_time = _do_inference(path)
                if parsed is None:
                    raise ValueError("模型输出未能解析为 JSON 报告，请重新评估。")
                rid = history.save_record(name, parsed, infer_time, path,
                                          source="screen", persist_image=True,
                                          owner_user_id=user["id"],
                                          created_by=user["username"], turbine_id=turbine_id)
                alert = risk_alert(parsed)
                is_high = alert is not None
                high += 1 if is_high else 0
                row = {
                    "ok": True, "filename": name, "record_id": rid, "turbine_id": turbine_id,
                    "component": get_field(parsed, i18n.SECTION_COMPONENT, "构件名称"),
                    "damage_type": get_field(parsed, i18n.SECTION_DAMAGE, "损伤类型"),
                    "priority": get_field(parsed, i18n.SECTION_CONCLUSION, "巡检优先级"),
                    "high_risk": is_high, "alert": alert, "infer_time": infer_time,
                }
                if form.get("include_report") == "1":
                    record = history.get_record(rid)
                    row["detail"] = {"json_report": parsed, "timestamp": record["timestamp"],
                                     "confidence": record["confidence"]}
                results.append(row)
            except Exception as exc:                       # 单张失败不影响整批
                results.append({"ok": False, "filename": name,
                                "record_id": None, "turbine_id": turbine_id, "error": str(exc)[:300]})
    finally:
        _shutil.rmtree(tmpd, ignore_errors=True)
    return JSONResponse({"results": results, "total": len(results),
                         "ok_count": sum(1 for r in results if r["ok"]),
                         "high_risk": high})


@router.get("/api/records/{record_id}")
async def api_record_detail(request: Request, record_id: int):
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    rec = history.get_record(record_id)
    if not rec:
        return JSONResponse({"detail": "not found"}, status_code=404)
    if not history.can_access(rec, user["id"], user.get("role") == "admin"):
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    import json as _j
    detail = dict(rec)
    try:
        detail["json_report"] = (_j.loads(rec["json_report"])
                                 if isinstance(rec.get("json_report"), str)
                                 else rec.get("json_report"))
    except (ValueError, TypeError):
        pass
    detail["alert"] = risk_alert(detail["json_report"], rec.get("priority"))
    detail["observed_parts"] = [
        {"part": part, "status": status} for part, status in observed_parts(detail["json_report"])
    ]
    return JSONResponse(detail)


@router.post("/api/records/{record_id}/note")
async def api_record_note(request: Request, record_id: int):
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    rec = history.get_record(record_id)
    if not rec:
        return JSONResponse({"detail": "not found"}, status_code=404)
    if not history.can_access(rec, user["id"], user.get("role") == "admin"):
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    body = await request.json()
    history.update_note(record_id, str(body.get("note") or ""))
    return JSONResponse({"ok": True})


@router.delete("/api/records/{record_id}")
async def api_record_delete(request: Request, record_id: int):
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    scope, _ = _scope(user)
    try:
        count = history.delete_records([record_id], scope)
    except PermissionError:
        return JSONResponse({"detail": "forbidden"}, status_code=403)
    if not count:
        return JSONResponse({"detail": "not found"}, status_code=404)
    return JSONResponse({"ok": True})


@router.delete("/api/records")
async def api_records_delete(request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"detail": "not authenticated"}, status_code=401)
    try:
        data = await request.json()
    except (ValueError, UnicodeError):
        return JSONResponse({"detail": "请提交记录编号列表"}, status_code=400)
    ids = data.get("ids") if isinstance(data, dict) else None
    if not isinstance(ids, list) or not ids or any(
        type(rid) is not int or not 0 < rid < 2**63 for rid in ids
    ):
        return JSONResponse({"detail": "请选择有效的记录编号"}, status_code=400)
    scope, _ = _scope(user)
    try:
        count = history.delete_records(ids, scope)
    except PermissionError:
        return JSONResponse({"detail": "无权删除所选记录"}, status_code=403)
    return JSONResponse({"deleted": count})
