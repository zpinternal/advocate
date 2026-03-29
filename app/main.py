import hmac
import os
import secrets
from pathlib import Path

from fastapi import FastAPI, Form, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.files import router as files_router
from app.gemini import init_db as init_gemini_db
from app.gemini import router as gemini_router
from app.ftp import router as ftp_router
from app.task_routes import router as task_router
from app.terminal import router as terminal_router
from app.zlink import init_db, router as zlink_router


APP_VERSION = "0.7.0"
app = FastAPI(title="Advocate", version=APP_VERSION)
templates = Jinja2Templates(directory="templates")

PUBLIC_PATH_PREFIXES = ("/health", "/login", "/static")


class AuthConfigError(RuntimeError):
    pass


def get_expected_credentials() -> tuple[str, str]:
    user = os.getenv("ADVOCATE_USER")
    password = os.getenv("ADVOCATE_PASSWORD")
    if not user or not password:
        raise AuthConfigError(
            "ADVOCATE_USER and ADVOCATE_PASSWORD must both be set before starting the server."
        )
    return user, password


def _wants_html(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/html" in accept.lower()


def _is_public_path(path: str) -> bool:
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in PUBLIC_PATH_PREFIXES
    )


@app.middleware("http")
async def session_auth_guard(request: Request, call_next):
    path = request.url.path
    if _is_public_path(path):
        return await call_next(request)

    try:
        get_expected_credentials()
    except AuthConfigError as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "ok": False,
                "error": {"code": "AUTH_CONFIG_ERROR", "message": str(exc)},
            },
        )

    if request.session.get("authenticated"):
        return await call_next(request)

    if _wants_html(request):
        login_redirect = f"/login?next={path}"
        return RedirectResponse(
            url=login_redirect, status_code=status.HTTP_303_SEE_OTHER
        )

    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={
            "ok": False,
            "error": {
                "code": "UNAUTHORIZED",
                "message": "Login required. Use /login for session authentication.",
            },
        },
    )


@app.on_event("startup")
def startup() -> None:
    init_db()
    init_gemini_db()
    Path("static").mkdir(parents=True, exist_ok=True)
    Path("templates").mkdir(parents=True, exist_ok=True)


session_secret = os.getenv("ADVOCATE_SESSION_SECRET") or secrets.token_hex(32)
app.add_middleware(
    SessionMiddleware,
    secret_key=session_secret,
    same_site="lax",
    https_only=False,
    max_age=60 * 60 * 8,
)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(zlink_router)
app.include_router(files_router)
app.include_router(ftp_router)
app.include_router(task_router)
app.include_router(terminal_router)
app.include_router(gemini_router)


@app.get("/health")
def health():
    return {"ok": True, "status": "healthy"}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", include_in_schema=False)
def login_page(request: Request, next: str = "/dashboard"):
    if request.session.get("authenticated"):
        return RedirectResponse(url=next, status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        "core/login.html",
        {
            "request": request,
            "title": "Login",
            "next_path": next,
            "error": None,
        },
    )


@app.post("/login", include_in_schema=False)
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/dashboard"),
):
    expected_user, expected_password = get_expected_credentials()
    user_ok = hmac.compare_digest(username, expected_user)
    pass_ok = hmac.compare_digest(password, expected_password)

    if not (user_ok and pass_ok):
        return templates.TemplateResponse(
            "core/login.html",
            {
                "request": request,
                "title": "Login",
                "next_path": next,
                "error": "Invalid username or password.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    request.session.update({"authenticated": True, "username": username})
    return RedirectResponse(
        url=next or "/dashboard", status_code=status.HTTP_303_SEE_OTHER
    )


@app.post("/logout", include_in_schema=False)
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/dashboard", include_in_schema=False)
def dashboard(request: Request):
    return templates.TemplateResponse(
        "core/dashboard.html",
        {
            "request": request,
            "title": "Dashboard",
            "username": request.session.get("username", "user"),
        },
    )


@app.get("/api/me")
def me(request: Request):
    return {
        "ok": True,
        "data": {
            "module": "core",
            "auth": "session",
            "version": APP_VERSION,
            "user": request.session.get("username"),
        },
    }
