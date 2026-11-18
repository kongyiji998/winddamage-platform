#!/usr/bin/env python3
"""
风电塔灾损测算软件 — 本机巡检大屏与多用户 Web 服务

默认本机模式直接打开 /screen，使用本地模型，巡检记录归属本机工作区。
多用户模式（--setup，DEVELOPMENT_PLAN.md §10 / §13）：
  - 组装 FastAPI 应用：认证中间件 + 登录/注册/首次设置/改密/用户管理路由
    + 独立详情页 /history/{id} + Gradio 主应用挂载
  - 会话：HttpOnly SameSite=Lax Cookie（wd_session）→ sessions 表校验
  - 中间件：未登录访问页面 → /login；未登录调用 /gradio_api/* → 401；
    users 表为空 → 强制 /setup 创建首个管理员（并回填迁移数据归属）
  - POST 请求校验 Origin（与 Host 一致），配合 SameSite=Lax 做 CSRF 基线防护

启动：python server.py（端口 GRADIO_SERVER_PORT，默认 7860）
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import i18n
from i18n import t as tr
import ui_components as uc
import auth
import screen_api
from history import get_record, can_access

# app.py 顶部会依据 --lang/UI_LANG 设置语言；导入其构建函数
import app as app_module


# ══════════════════════════════════════════════════════════
#  页面 HTML 构建（复用 ui_components 设计令牌与认证样式）
# ══════════════════════════════════════════════════════════

def _banner_html(msg: str, tone: str = "warn") -> str:
    if not msg:
        return ""
    return f'<div class="wd-auth-banner wd-banner-{tone}">{uc.esc(msg)}</div>'


def _field_error(msg: str) -> str:
    if not msg:
        return ""
    return f'<div class="wd-form-error">{uc.esc(msg)}</div>'


def _auth_page(title: str, body: str):
    from fastapi.responses import HTMLResponse
    return HTMLResponse(uc.page_shell(title, body))


def _form_open(action: str, extra_hidden: str = "") -> str:
    return (f'<form method="post" action="{action}" '
            f'class="wd-auth-form" style="display:flex;flex-direction:column;gap:14px;">'
            f"{extra_hidden}")


def _pw_input(name: str, label: str, placeholder: str = "", autocap: str = "") -> str:
    auto = f' autocomplete="{autocap}"' if autocap else ""
    return (f'<div class="wd-field"><label>{uc.esc(label)}</label>'
            f'<input type="password" name="{name}" required{auto} '
            f'placeholder="{uc.esc(placeholder)}"/></div>')


def _login_page(error: str = "", banner: str = "", username: str = ""):
    body = f"""
<div class="wd-auth-wrap">
  <div class="wd-auth-card">
    <h1 style="font-size:22px;margin:0 0 6px;">{uc.esc(tr("login_title"))}</h1>
    <div class="wd-auth-sub">{uc.esc(tr("login_subtitle"))}</div>
    {_banner_html(banner, "warn")}
    {_form_open("/login")}
      {_field_error(error)}
      <div class="wd-field">
        <label>{uc.esc(tr("login_username"))}</label>
        <input type="text" name="username" required maxlength="40"
               value="{uc.esc(username)}" autocomplete="username"/>
      </div>
      {_pw_input("password", tr("login_password"), autocap="current-password")}
      <button type="submit" class="wd-btn-primary-block">{uc.esc(tr("btn_login"))}</button>
    </form>
    <div class="wd-auth-alt">
      <a href="/register">{uc.esc(tr("link_register"))}</a>
    </div>
  </div>
</div>"""
    return _auth_page(tr("login_title"), body)


def _password_rules_html() -> str:
    rules = "".join(f'<li data-rule="{k}">{uc.esc(tr(k))}</li>'
                    for k in ("auth_rule_len", "auth_rule_letter", "auth_rule_digit"))
    return f'<ul class="wd-pw-rules">{rules}</ul>'


def _password_strength_html() -> str:
    """密码强度实时提示条（F5）：0-3 分对应 弱/中/强，JS 随输入刷新。"""
    return ('<div class="wd-pw-meter" aria-live="polite">'
            '<div class="wd-pw-meter-bar"><span></span></div>'
            '<span class="wd-pw-meter-label"></span></div>')


_PW_RULES_JS = """
(function () {
  var LEVELS = ['wd-pw-weak', 'wd-pw-medium', 'wd-pw-strong'];
  var LABELS = ['%(weak)s', '%(medium)s', '%(strong)s'];
  function bind(inputId, listSel) {
    var input = document.getElementById(inputId);
    if (!input) return;
    var list = listSel ? document.querySelector(listSel) : null;
    var meter = input.parentNode.querySelector('.wd-pw-meter');
    input.addEventListener('input', function () {
      var v = input.value;
      var checks = [v.length >= 8, /[A-Za-z]/.test(v), /\\d/.test(v)];
      if (list) {
        var items = list.querySelectorAll('li');
        for (var i = 0; i < items.length; i++) {
          items[i].classList.toggle('wd-rule-ok', checks[i]);
        }
      }
      if (meter) {
        var score = checks.filter(Boolean).length;
        var level = score <= 1 ? 0 : (score === 2 ? 1 : 2);
        meter.className = 'wd-pw-meter ' + (v ? LEVELS[level] : '');
        meter.querySelector('.wd-pw-meter-bar span').style.width =
          v ? Math.round(score / 3 * 100) + '%%' : '0';
        meter.querySelector('.wd-pw-meter-label').textContent = v ? LABELS[level] : '';
      }
    });
  }
  bind('wd-reg-pw', '.wd-pw-rules');
  var pw = document.getElementById('wd-reg-pw');
  var cf = document.getElementById('wd-reg-pw2');
  var err = document.getElementById('wd-pw2-err');
  if (pw && cf && err) {
    cf.addEventListener('input', function () {
      err.textContent = (cf.value && cf.value !== pw.value)
        ? '%(mismatch)s' : '';
    });
  }
})();
"""


def _register_page(error: str = "", banner: str = "", username: str = ""):
    js = _PW_RULES_JS % {"mismatch": tr("auth_pw_mismatch"),
                                "weak": tr("pw_strength_weak"),
                                "medium": tr("pw_strength_medium"),
                                "strong": tr("pw_strength_strong")}
    body = f"""
<div class="wd-auth-wrap">
  <div class="wd-auth-card">
    <h1 style="font-size:22px;margin:0 0 6px;">{uc.esc(tr("register_title"))}</h1>
    <div class="wd-auth-sub">{uc.esc(tr("register_subtitle"))}</div>
    {_banner_html(banner, "warn")}
    {_form_open("/register")}
      {_field_error(error)}
      <div class="wd-field">
        <label>{uc.esc(tr("register_username"))}</label>
        <input type="text" id="wd-reg-username" name="username" required maxlength="40"
               value="{uc.esc(username)}" autocomplete="username"/>
        <div class="wd-form-error" id="wd-username-err" style="display:none;"></div>
      </div>
      <div class="wd-field">
        <label>{uc.esc(tr("register_password"))}</label>
        <input type="password" id="wd-reg-pw" name="password" required
               autocomplete="new-password"/>
        {_password_rules_html()}
        {_password_strength_html()}
      </div>
      <div class="wd-field">
        <label>{uc.esc(tr("register_password2"))}</label>
        <input type="password" id="wd-reg-pw2" name="password2" required
               autocomplete="new-password"/>
        <div class="wd-form-error" id="wd-pw2-err"></div>
      </div>
      <button type="submit" class="wd-btn-primary-block">{uc.esc(tr("register_btn"))}</button>
    </form>
    <div class="wd-auth-alt">
      <a href="/login">{uc.esc(tr("link_login"))}</a>
    </div>
  </div>
</div>
<script>{js}</script>"""
    return _auth_page(tr("register_title"), body)


def _setup_page(error: str = "", username: str = ""):
    body = f"""
<div class="wd-auth-wrap">
  <div class="wd-auth-card">
    <h1 style="font-size:22px;margin:0 0 6px;">{uc.esc(tr("setup_title"))}</h1>
    <div class="wd-auth-sub">{uc.esc(tr("setup_subtitle"))}</div>
    {_form_open("/setup")}
      {_field_error(error)}
      <div class="wd-field">
        <label>{uc.esc(tr("setup_username"))}</label>
        <input type="text" name="username" required maxlength="40"
               value="{uc.esc(username)}" autocomplete="username"/>
      </div>
      <div class="wd-field">
        <label>{uc.esc(tr("setup_password"))}</label>
        <input type="password" id="wd-reg-pw" name="password" required
               autocomplete="new-password"/>
        {_password_rules_html()}
        {_password_strength_html()}
      </div>
      <div class="wd-field">
        <label>{uc.esc(tr("register_password2"))}</label>
        <input type="password" id="wd-reg-pw2" name="password2" required
               autocomplete="new-password"/>
        <div class="wd-form-error" id="wd-pw2-err"></div>
      </div>
      <button type="submit" class="wd-btn-primary-block">{uc.esc(tr("setup_btn"))}</button>
    </form>
  </div>
</div>
<script>{_PW_RULES_JS % {"mismatch": tr("auth_pw_mismatch"),
                                "weak": tr("pw_strength_weak"),
                                "medium": tr("pw_strength_medium"),
                                "strong": tr("pw_strength_strong")}}</script>"""
    return _auth_page(tr("setup_title"), body)


def _change_pw_page(error: str = "", banner: str = ""):
    body = f"""
<div class="wd-auth-wrap">
  <div class="wd-auth-card">
    <h1 style="font-size:22px;margin:0 0 6px;">{uc.esc(tr("change_pw_title"))}</h1>
    {_banner_html(banner, "warn")}
    {_form_open("/change-password")}
      {_field_error(error)}
      {_pw_input("old_password", tr("pw_label_old"), autocap="current-password")}
      <div class="wd-field">
        <label>{uc.esc(tr("pw_label_new"))}</label>
        <input type="password" id="wd-reg-pw" name="new_password" required
               autocomplete="new-password"/>
        {_password_rules_html()}
        {_password_strength_html()}
      </div>
      <div class="wd-field">
        <label>{uc.esc(tr("pw_label_confirm"))}</label>
        <input type="password" id="wd-reg-pw2" name="password2" required
               autocomplete="new-password"/>
        <div class="wd-form-error" id="wd-pw2-err"></div>
      </div>
      <button type="submit" class="wd-btn-primary-block">{uc.esc(tr("btn_change_pw"))}</button>
    </form>
    <div class="wd-auth-alt"><a href="/">← {uc.esc(tr("app_title"))}</a></div>
  </div>
</div>
<script>{_PW_RULES_JS % {"mismatch": tr("auth_pw_mismatch"),
                                "weak": tr("pw_strength_weak"),
                                "medium": tr("pw_strength_medium"),
                                "strong": tr("pw_strength_strong")}}</script>"""
    return _auth_page(tr("change_pw_title"), body)


def _users_page(me: dict, banner: str = ""):
    """用户管理（简版）：列表 + 启停/解锁/角色/重置密码（§10）。"""
    rows = []
    for u in auth.list_users():
        if u["locked_until"]:
            remain = auth._lock_remaining_minutes(u["locked_until"])
            status = (f'<span class="wd-badge wd-badge-danger">'
                      f'{uc.esc(tr("users_status_locked"))} {remain}min</span>')
        elif not u["is_active"]:
            status = f'<span class="wd-badge wd-badge-muted">{uc.esc(tr("users_status_disabled"))}</span>'
        else:
            status = f'<span class="wd-badge wd-badge-success">{uc.esc(tr("users_status_active"))}</span>'

        role = (f'<span class="wd-badge wd-badge-{"info" if u["role"] == "admin" else "muted"}">'
                f'{uc.esc(tr("users_role_admin") if u["role"] == "admin" else tr("users_role_user"))}</span>')

        actions = []
        is_self = u["id"] == me["id"]
        # 停用/启用（不能操作自己）；危险操作带 confirm 二次确认（F4）
        if not is_self:
            if u["is_active"]:
                actions.append(_user_action(
                    u["id"], "disable", tr("users_btn_disable"), danger=True,
                    confirm=tr("users_confirm_disable", name=u["username"])))
            else:
                actions.append(_user_action(u["id"], "enable", tr("users_btn_enable")))
        if u["locked_until"]:
            actions.append(_user_action(u["id"], "unlock", tr("users_btn_unlock")))
        # 角色（不能改自己，保证至少逻辑上不自降）
        if not is_self:
            new_role = "user" if u["role"] == "admin" else "admin"
            actions.append(_user_action(u["id"], "role", tr("users_btn_role", role=(
                tr("users_role_user") if new_role == "user" else tr("users_role_admin"))),
                extra=f'<input type="hidden" name="role" value="{new_role}"/>',
                confirm=tr("users_confirm_role", name=u["username"],
                           role=(tr("users_role_user") if new_role == "user"
                                 else tr("users_role_admin")))))
        # 重置密码（不能重置自己——自己走 /change-password）
        if not is_self:
            actions.append(
                f'<form method="post" action="/users/action" '
                f'onsubmit="return confirm({uc.esc_js(tr("users_confirm_resetpw", name=u["username"]))})">'
                f'<input type="hidden" name="action" value="resetpw"/>'
                f'<input type="hidden" name="user_id" value="{u["id"]}"/>'
                f'<input type="password" name="new_password" required '
                f'placeholder="{uc.esc(tr("users_resetpw_ph"))}"/>'
                f'<button type="submit" class="wd-u-danger">{uc.esc(tr("users_btn_resetpw"))}</button>'
                f'</form>')

        self_tag = (f' <span class="wd-badge wd-badge-muted">'
                    f'{uc.esc(tr("users_self"))}</span>' if is_self else "")
        name_html = uc.esc(u["username"]) + self_tag
        rows.append(
            "<tr>"
            f'<td class="wd-num">{u["id"]}</td>'
            f"<td>{name_html}</td>"
            f"<td>{role}</td>"
            f"<td>{status}</td>"
            f"<td class='wd-num'>{uc.esc(u['created_at'] or '—')}</td>"
            f"<td class='wd-num'>{uc.esc(u['last_login_at'] or '—')}</td>"
            f'<td><div class="wd-users-actions">{"".join(actions) or "—"}</div></td>'
            "</tr>")

    header = [tr("hdr_id"), tr("users_col_user"), tr("users_col_role"),
              tr("users_col_status"), tr("users_col_created"),
              tr("users_col_last_login"), tr("users_col_actions")]
    table = uc.data_table(header, "".join(rows))

    body = f"""
<div class="wd-users-wrap">
  <div class="wd-page-head" style="display:flex;justify-content:space-between;align-items:center;">
    <a class="wd-backlink" href="/">← {uc.esc(tr("app_title"))}</a>
    <span class="wd-user-badge" style="display:flex;gap:12px;align-items:center;font-size:13px;">
      <span class="wd-ub-name">{uc.esc(me["username"])}</span>
      <a href="/change-password">{uc.esc(tr("pw_link"))}</a>
      <a href="/logout">{uc.esc(tr("btn_logout"))}</a>
    </span>
  </div>
  <h1 style="font-size:20px;margin:8px 0 12px;">{uc.esc(tr("users_title"))}</h1>
  {_banner_html(banner, "warn")}
  {table}
</div>"""
    return _auth_page(tr("users_title"), body)


def _user_action(user_id: int, action: str, label: str, danger: bool = False,
                 extra: str = "", confirm: str = "") -> str:
    cls = ' class="wd-u-danger"' if danger else ""
    onsubmit = (f' onsubmit="return confirm({uc.esc_js(confirm)})"' if confirm else "")
    return (f'<form method="post" action="/users/action"{onsubmit}>'
            f'<input type="hidden" name="action" value="{action}"/>'
            f'<input type="hidden" name="user_id" value="{user_id}"/>{extra}'
            f'<button type="submit"{cls}>{uc.esc(label)}</button></form>')


def _error_page(msg: str, status_code: int):
    from fastapi.responses import HTMLResponse
    body = uc.page_shell(tr("app_title"),
                         f'<div class="wd-page-head">{uc.empty_state(msg, "")}</div>')
    return HTMLResponse(body, status_code=status_code)


# ══════════════════════════════════════════════════════════
#  认证中间件
# ══════════════════════════════════════════════════════════

# 静态资源前缀：不要求登录（Gradio 前端资源，无业务数据）
_ASSET_PREFIXES = ("/assets/", "/gradio_api/queue/join", "/_next/")

_PROTECTED_EXACT = {"/", "/users", "/change-password"}


def _cookie_set(response, token: str):
    response.set_cookie(
        auth.SESSION_COOKIE, token, httponly=True, samesite="lax",
        max_age=auth.SESSION_TTL_HOURS * 3600, path="/")


def _configure_local_workspace(fastapp):
    from fastapi import Request
    from fastapi.responses import PlainTextResponse, RedirectResponse
    from fastapi.staticfiles import StaticFiles

    @fastapp.middleware("http")
    async def local_requests(request: Request, call_next):
        if not request.client or request.client.host not in ("127.0.0.1", "::1"):
            return PlainTextResponse("Local access only", status_code=403)
        if request.url.hostname not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
            return PlainTextResponse("Invalid host", status_code=403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            if ((origin and origin != str(request.base_url).rstrip("/"))
                    or request.headers.get("sec-fetch-site") == "cross-site"):
                return PlainTextResponse("Forbidden (origin)", status_code=403)
        if request.url.hostname == "0.0.0.0":
            return RedirectResponse(str(request.url.replace(hostname="127.0.0.1")), status_code=307)
        # Positive IDs belong to registered accounts; NULL belongs to unclaimed imports.
        request.state.local_user = {"id": -1, "username": "本机巡检", "role": "local"}
        return await call_next(request)

    def open_screen():
        return RedirectResponse("/screen", status_code=303)

    for path in ("/", "/setup", "/login", "/logout", "/register", "/change-password",
                 "/users", "/screen/login", "/screen/register", "/screen/account"):
        fastapp.add_api_route(path, open_screen, methods=["GET", "POST"])

    vendor_dir = os.path.join(os.path.dirname(screen_api.SCREEN_DIR), "vendor")
    fastapp.mount("/wd-assets/vendor", StaticFiles(directory=vendor_dir), name="vendor")


def create_app(*, local_workspace=False):
    from fastapi import FastAPI, Request
    from fastapi.responses import (HTMLResponse, RedirectResponse,
                                   JSONResponse, PlainTextResponse)
    from fastapi.staticfiles import StaticFiles
    from history import init_db

    init_db()
    fastapp = FastAPI(title=tr("app_title"), docs_url=None, redoc_url=None)
    fastapp.include_router(screen_api.router)
    fastapp.mount("/screen-assets", StaticFiles(directory=screen_api.SCREEN_DIR), name="screen-assets")

    # ─── 记录持久化图像 /history/{id}/image（权限与详情页一致）──
    @fastapp.get("/history/{record_id}/image")
    async def history_record_image(record_id: int, request: Request):
        from fastapi.responses import FileResponse
        import image_store
        user_id, is_admin = app_module._current_scope(request)
        record = get_record(record_id)
        if not record:
            return _error_page(tr("msg_record_not_found", id=record_id), 404)
        if not can_access(record, user_id, is_admin):
            return _error_page(tr("msg_record_no_access"), 403)
        if not record["image_file_id"]:
            return _error_page(tr("msg_image_missing"), 404)
        path = image_store.get_image_path(record["image_file_id"])
        if not path or not os.path.exists(path):
            return _error_page(tr("msg_image_missing"), 404)
        return FileResponse(path)

    if local_workspace:
        _configure_local_workspace(fastapp)
        return fastapp

    async def _finish(request: Request, call_next):
        """统一补缓存头：HTML 页面禁缓存（防止浏览器拿旧样式渲染新页面导致白屏），
        /wd-assets 背景图允许 1 小时缓存。"""
        response = await call_next(request)
        ctype = response.headers.get("content-type", "")
        if ctype.startswith("text/html"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/wd-assets/"):
            response.headers.setdefault("Cache-Control", "public, max-age=3600")
        return response

    # ─── 中间件：会话守卫 + Origin 校验 ─────────────────────
    @fastapp.middleware("http")
    async def auth_guard(request: Request, call_next):
        path = request.url.path
        method = request.method

        # POST/PUT/DELETE：Origin 与 Host 一致性校验（CSRF 基线）
        if method in ("POST", "PUT", "DELETE"):
            origin = request.headers.get("origin")
            if origin:
                host = request.headers.get("host", "")
                from urllib.parse import urlparse
                o_host = urlparse(origin).netloc
                if o_host and o_host != host:
                    return PlainTextResponse("Forbidden (origin)", status_code=403)

        token = auth.parse_cookie(request.headers.get("cookie"))
        user = auth.get_session_user(token)

        # 未初始化（无用户）：仅放行 /setup 与静态资源，其余全部导向 /setup
        if auth.count_users() == 0:
            if path == "/setup" or path.startswith("/wd-assets/") or \
                    path.startswith("/gradio_api/theme.css") or path == "/favicon.ico":
                return await _finish(request, call_next)
            if path.startswith("/gradio_api/"):
                return JSONResponse({"detail": "setup required"}, status_code=401)
            return RedirectResponse("/setup", status_code=302)

        # 已初始化后，/setup 不再可用
        if path == "/setup":
            return RedirectResponse("/" if user else "/login", status_code=302)

        # 已登录访问登录/注册页 → 回首页
        if path in ("/login", "/register") and user:
            return RedirectResponse("/", status_code=302)
        # 已登录访问大屏登录页 → 回大屏
        if path == "/screen/login" and user:
            return RedirectResponse("/screen", status_code=302)

        if user:
            # admin-only 页面
            if path == "/users" and user["role"] != "admin":
                return _error_page(tr("auth_need_admin"), 403)
            return await _finish(request, call_next)

        # 未登录：
        if path.startswith("/gradio_api/"):
            return JSONResponse({"detail": "not authenticated"}, status_code=401)
        if path == "/api/me":
            return JSONResponse({"username": None, "role": None})
        # 大屏入口：API 未登录一律 401 JSON（供前端 fetch 判定），页面跳大屏登录页
        if path.startswith("/screen/api/"):
            return JSONResponse({"detail": "not authenticated"}, status_code=401)
        if path.startswith("/screen-assets"):
            return await _finish(request, call_next)   # 静态资源放行（登录页样式依赖）
        if path.startswith("/screen"):
            if path in ("/screen/login", "/screen/register"):
                return await _finish(request, call_next)   # 登录/注册页放行（防重定向环）
            next_url = "/screen/login?expired=1" if token else "/screen/login"
            return RedirectResponse(next_url, status_code=302)
        if path in _PROTECTED_EXACT or path.startswith("/history/"):
            # 有过期 Cookie 的带提示跳转（§10.3 过期告知）
            if token:
                next_url = "/login?expired=1"
                if request.url.query:
                    next_url += f"&{request.url.query}"
            else:
                next_url = "/login"
            return RedirectResponse(next_url, status_code=302)
        return await _finish(request, call_next)

    # ─── 登录 ──────────────────────────────────────────────
    @fastapp.get("/login")
    async def login_page(request: Request, expired: int = 0):
        banner = tr("msg_session_expired") if expired else ""
        return _login_page(banner=banner)

    @fastapp.post("/login")
    async def login_submit(request: Request):
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        status, payload = auth.authenticate(username, password)
        if status == "ok":
            resp = RedirectResponse("/", status_code=302)
            _cookie_set(resp, auth.create_session(payload["id"]))
            return resp
        if status == "locked":
            return _login_page(error=tr("msg_locked", minutes=payload), username=username)
        return _login_page(error=tr("msg_login_failed"), username=username)

    # ─── 注册 ──────────────────────────────────────────────
    @fastapp.get("/register")
    async def register_page():
        return _register_page()

    @fastapp.post("/register")
    async def register_submit(request: Request):
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        password2 = str(form.get("password2") or "")
        if password != password2:
            return _register_page(error=tr("auth_pw_mismatch"), username=username)
        issue = auth.username_issue(username)
        if issue:
            return _register_page(error=tr(issue), username=username)
        issues = auth.password_issues(password)
        if issues:
            return _register_page(error=tr(issues[0]), username=username)
        try:
            auth.create_user(username, password, role="user")
        except auth.UsernameExists:
            return _register_page(error=tr("auth_username_taken"), username=username)
        user = auth.get_user_by_name(username)
        resp = RedirectResponse("/", status_code=302)
        _cookie_set(resp, auth.create_session(user["id"]))
        return resp

    @fastapp.get("/api/check_username")
    async def check_username(q: str = ""):
        user = auth.get_user_by_name(q)
        return JSONResponse({"taken": bool(user),
                             "valid": auth.username_issue(q) is None})

    # ─── 首次设置（创建首个管理员 + 回填迁移数据归属）─────
    @fastapp.get("/setup")
    async def setup_page():
        if auth.count_users() > 0:
            return RedirectResponse("/login", status_code=302)
        return _setup_page()

    @fastapp.post("/setup")
    async def setup_submit(request: Request):
        if auth.count_users() > 0:
            return RedirectResponse("/login", status_code=302)
        form = await request.form()
        username = str(form.get("username") or "")
        password = str(form.get("password") or "")
        password2 = str(form.get("password2") or "")
        if password != password2:
            return _setup_page(error=tr("auth_pw_mismatch"), username=username)
        issue = auth.username_issue(username)
        if issue:
            return _setup_page(error=tr(issue), username=username)
        issues = auth.password_issues(password)
        if issues:
            return _setup_page(error=tr(issues[0]), username=username)
        admin_id = auth.create_user(username, password, role="admin")
        # §13.1：迁移数据归属回填——按用户名查询 admin id，不假设 id==1
        n = auth.backfill_migration_owner(username)
        print(f"[setup] 管理员已创建 (id={admin_id})，迁移数据回填 {n} 条 → {username}")
        resp = RedirectResponse("/", status_code=302)
        _cookie_set(resp, auth.create_session(admin_id))
        return resp

    # ─── 登出 ──────────────────────────────────────────────
    @fastapp.get("/logout")
    async def logout(request: Request):
        auth.revoke_session(auth.parse_cookie(request.headers.get("cookie")))
        resp = RedirectResponse("/login", status_code=302)
        resp.delete_cookie(auth.SESSION_COOKIE, path="/")
        return resp

    # ─── 修改密码 ──────────────────────────────────────────
    @fastapp.get("/change-password")
    async def change_pw_page(request: Request, done: int = 0):
        user = auth.user_for_request(request)
        if not user:
            return RedirectResponse("/login", status_code=302)
        banner = tr("msg_pw_changed") if done else ""
        return _change_pw_page(banner=banner)

    @fastapp.post("/change-password")
    async def change_pw_submit(request: Request):
        user = auth.user_for_request(request)
        if not user:
            return RedirectResponse("/login", status_code=302)
        form = await request.form()
        old = str(form.get("old_password") or "")
        new = str(form.get("new_password") or "")
        new2 = str(form.get("password2") or "")
        if new != new2:
            return _change_pw_page(error=tr("auth_pw_mismatch"))
        ok, err = auth.change_password(
            user["id"], old, new,
            current_token=auth.parse_cookie(request.headers.get("cookie")))
        if ok:
            return RedirectResponse("/change-password?done=1", status_code=302)
        return _change_pw_page(error=tr(err or "msg_error"))

    # ─── 用户管理（admin 简版）─────────────────────────────
    @fastapp.get("/users")
    async def users_page(request: Request, done: int = 0):
        user = auth.user_for_request(request)
        if not user or user["role"] != "admin":
            return _error_page(tr("auth_need_admin"), 403)
        banner = tr("users_msg_done") if done else ""
        return _users_page(user, banner=banner)

    @fastapp.post("/users/action")
    async def users_action(request: Request):
        me = auth.user_for_request(request)
        if not me or me["role"] != "admin":
            return _error_page(tr("auth_need_admin"), 403)
        form = await request.form()
        action = str(form.get("action") or "")
        try:
            target_id = int(str(form.get("user_id") or ""))
        except ValueError:
            return RedirectResponse("/users", status_code=302)
        target = auth.get_user(target_id)
        if not target:
            return RedirectResponse("/users", status_code=302)

        is_self = target_id == me["id"]
        if action == "disable" and not is_self:
            auth.set_user_active(target_id, False)
        elif action == "enable":
            auth.set_user_active(target_id, True)
        elif action == "unlock":
            auth.unlock_user(target_id)
        elif action == "role" and not is_self:
            role = str(form.get("role") or "")
            if role in ("user", "admin"):
                auth.set_user_role(target_id, role)
        elif action == "resetpw" and not is_self:
            auth.reset_password(target_id, str(form.get("new_password") or ""))
        return RedirectResponse("/users?done=1", status_code=302)

    # ─── 当前用户 API（Gradio 页内徽章用）──────────────────
    @fastapp.get("/api/me")
    async def api_me(request: Request):
        user = auth.user_for_request(request)
        if not user:
            return JSONResponse({"username": None, "role": None})
        return JSONResponse({"username": user["username"], "role": user["role"]})

    # ─── 独立详情页 /history/{id}（§9.2）────────────────────
    @fastapp.get("/history/{record_id}")
    async def history_detail_page(record_id: int, request: Request):
        # 权限：登录用户仅本人记录；admin 全量
        user_id, is_admin = app_module._current_scope(request)
        record = get_record(record_id)
        if not record:
            return _error_page(tr("msg_record_not_found", id=record_id), 404)
        if not can_access(record, user_id, is_admin):
            return _error_page(tr("msg_record_no_access"), 403)

        import json as _json
        report = _json.loads(record["json_report"])
        detail_html, _formatted = app_module._build_result_html(report, meta={
            "record_id": record["id"],
            "timestamp": record["timestamp"],
            "infer_time": record["infer_time"] or 0,
        })

        back = (f'<div class="wd-page-head">'
                f'<a class="wd-backlink" href="/">← {tr("tab_history")} / {tr("app_title")}</a>'
                f"</div>")
        body = f"{back}{app_module._record_image_html(record)}{detail_html}"
        return HTMLResponse(uc.page_shell(f'#{record_id} · {tr("app_title")}', body))

    # ─── Gradio 主应用挂载 ──────────────────────────────────
    # 静态资源：页面背景照片（BASE_CSS 引用 /wd-assets/bg_photo.jpg）。
    # 注意：路径必须是 /wd-assets 而不是 /assets —— Gradio 自身的前端
    # 样式/脚本就发布在 /assets 下（如 index-*.css），若占用同名路径会把
    # Gradio 静态资源全部 404，导致主页面白屏。
    # 仍须在 Gradio 挂载到 "/" 之前注册，否则会被 "/" 通配路由吞掉。
    from fastapi.responses import Response
    assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

    # 全局样式：以真实 CSS 文件形式提供（主页面经 head <link> 引用）。
    # 必须注册在 /wd-assets 静态目录挂载之前——Mount 会匹配整个前缀，
    # 后注册的精确路由会被它遮住。
    @fastapp.get("/wd-assets/base.css")
    async def wd_base_css():
        # no-cache：样式随代码更新必须立刻生效（内容极小，重新验证成本可忽略）。
        # 曾用 max-age=3600，用户浏览器在样式更新后最长 1 小时内仍是旧主题。
        return Response(uc.BASE_CSS, media_type="text/css",
                        headers={"Cache-Control": "no-cache"})

    if os.path.isdir(assets_dir):
        fastapp.mount("/wd-assets", StaticFiles(directory=assets_dir), name="wd-assets")

    fastapp.include_router(screen_api.account_router)

    import gradio as gr
    demo = app_module.build_ui()
    # 全局样式经 head 以 <style> 内联注入（Gradio 运行时用 DOMParser 重建
    # head 参数里的元素并原样拷贝 textContent，<style> 内容保持顶层作用域）。
    # 不能用 css= 参数：Gradio 会给 css= 的每条规则加
    # ".gradio-container… .contain" 前缀，html/body/:root 顶层规则被前缀化后
    # 在主页面全部失效（背景照片/字体/透明度全丢）——此前白底问题的根因之一。
    # 也不用 <link>：实测 head 里的 <link> 在主页面不生效（渲染探针证实），
    # 内联 <style> 同步生效、无加载时序问题。
    gr.mount_gradio_app(
        fastapp, demo, path="/",
        theme=gr.themes.Soft(primary_hue="blue"),
        head="<style>" + uc.BASE_CSS + "</style>",
        js=getattr(demo, "_wd_badge_js", None),
        show_error=True,
        # 页脚保留 settings：仅作为 Gradio 面板自身的入口兜底；右上角"设置"
        # 链接打开的是自定义中文显示设置弹层（见 app._SETTINGS_POPOVER_JS）。
        # 页脚视觉由 CSS 隐藏（见 ui_components BASE_CSS 尾部）。
        footer_links=["settings"],
    )
    return fastapp


def main():
    import uvicorn
    from config import MODEL_PATH

    local_workspace = "--setup" not in sys.argv
    if local_workspace and not os.path.isfile(os.path.join(MODEL_PATH, "config.json")):
        from preview_ui import run_preview
        run_preview()
        return

    port = int(os.environ.get("GRADIO_SERVER_PORT", "7860"))
    host = "127.0.0.1" if local_workspace else "0.0.0.0"
    print(f"  {tr('app_title')}  http://127.0.0.1:{port}/screen", flush=True)
    uvicorn.run(create_app(local_workspace=local_workspace), host=host, port=port,
                proxy_headers=not local_workspace, log_level="info")


if __name__ == "__main__":
    main()
