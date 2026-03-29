import hmac
import os
from base64 import b64decode
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.files import router as files_router
from app.gemini import init_db as init_gemini_db
from app.gemini import router as gemini_router
from app.ftp import router as ftp_router
from app.task_routes import router as task_router
from app.terminal import router as terminal_router
from app.zlink import init_db, router as zlink_router


app = FastAPI(title="Advocate", version="0.6.1")


PUBLIC_PATHS = {"/health"}


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


def parse_basic_auth(authorization_header: Optional[str]) -> tuple[str, str]:
    if not authorization_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        scheme, encoded = authorization_header.split(" ", 1)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed Authorization header",
            headers={"WWW-Authenticate": "Basic"},
        ) from exc

    if scheme.lower() != "basic":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsupported auth scheme",
            headers={"WWW-Authenticate": "Basic"},
        )

    try:
        decoded = b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Basic auth credentials",
            headers={"WWW-Authenticate": "Basic"},
        ) from exc

    return username, password


@app.middleware("http")
async def basic_auth_guard(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)

    try:
        expected_user, expected_password = get_expected_credentials()
        username, password = parse_basic_auth(request.headers.get("Authorization"))
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "ok": False,
                "error": {"code": "UNAUTHORIZED", "message": str(exc.detail)},
            },
            headers={"WWW-Authenticate": "Basic"},
        )

    except AuthConfigError as exc:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "ok": False,
                "error": {"code": "AUTH_CONFIG_ERROR", "message": str(exc)},
            },
        )

    user_ok = hmac.compare_digest(username, expected_user)
    pass_ok = hmac.compare_digest(password, expected_password)

    if not (user_ok and pass_ok):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "ok": False,
                "error": {"code": "UNAUTHORIZED", "message": "Invalid credentials"},
            },
            headers={"WWW-Authenticate": "Basic"},
        )

    return await call_next(request)


@app.on_event("startup")
def startup() -> None:
    init_db()
    init_gemini_db()
    Path("static").mkdir(parents=True, exist_ok=True)


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


@app.get("/api/me")
def me():
    return {
        "ok": True,
        "data": {"module": "core", "auth": "enabled", "version": "0.6.1"},
    }
