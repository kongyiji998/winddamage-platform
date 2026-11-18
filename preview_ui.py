"""本机大屏外观预览，复用正式页面和静态资源。"""

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles


ASSETS = Path(__file__).resolve().parent / "assets"
SCREEN = ASSETS / "screen"
PAGES = {
    "/screen": "home.html",
    "/screen/batch": "batch.html",
    "/screen/history": "history.html",
}


def create_preview_app():
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.mount("/screen-assets", StaticFiles(directory=SCREEN))
    app.mount("/wd-assets/vendor", StaticFiles(directory=ASSETS / "vendor"))

    def open_home():
        return RedirectResponse("/screen", status_code=303)

    for path in ("/", "/setup", "/login", "/register", "/logout", "/screen/login",
                 "/screen/register", "/screen/account"):
        app.add_api_route(path, open_home, methods=["GET", "POST"])

    def screen_page(request: Request):
        html = (SCREEN / PAGES[request.url.path]).read_text(encoding="utf-8")
        return HTMLResponse(html.replace("<body ", "<body data-preview ", 1),
                            headers={"Cache-Control": "no-store"})

    for path in PAGES:
        app.add_api_route(path, screen_page)

    @app.get("/screen/api/me")
    def preview_user():
        return {"username": "界面预览", "role": "preview"}

    @app.get("/screen/api/overview")
    def overview():
        return dict.fromkeys(("total", "week", "high_risk", "recheck", "completion"), 0)

    @app.get("/screen/api/farm")
    def farm():
        from wind_farm import farm_payload
        return farm_payload()

    @app.get("/screen/api/damage-stats")
    def damage_stats():
        from wind_farm import damage_stats_payload
        return damage_stats_payload()

    @app.get("/screen/api/records")
    def records():
        return {"rows": [], "total": 0}

    @app.api_route("/screen/api/{operation:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    def unavailable():
        raise HTTPException(403, "外观预览仅支持浏览界面")

    return app


def run_preview():
    import uvicorn

    port = int(os.environ.get("GRADIO_SERVER_PORT", "7860"))
    print(f"界面预览：http://127.0.0.1:{port}/screen", flush=True)
    uvicorn.run(create_preview_app(), host="127.0.0.1", port=port)


if __name__ == "__main__":
    run_preview()
