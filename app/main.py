import hmac
import os
import secrets
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, session

from app.files import bp as files_bp
from app.gemini import bp as gemini_bp
from app.gemini import init_db as init_gemini_db
from app.ftp import bp as ftp_bp
from app.task_routes import bp as task_bp
from app.terminal import bp as terminal_bp
from app.zlink import bp as zlink_bp
from app.zlink import init_db as init_zlink_db

APP_VERSION = "0.8.0"
PUBLIC_PATH_PREFIXES = ("/health", "/login", "/static")


def create_app() -> Flask:
    app = Flask(__name__, static_folder="../static", template_folder="../templates")
    app.config["SECRET_KEY"] = os.getenv(
        "ADVOCATE_SESSION_SECRET"
    ) or secrets.token_hex(32)

    Path("static").mkdir(parents=True, exist_ok=True)
    Path("templates").mkdir(parents=True, exist_ok=True)
    init_zlink_db()
    init_gemini_db()

    app.register_blueprint(zlink_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(ftp_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(terminal_bp)
    app.register_blueprint(gemini_bp)

    @app.before_request
    def session_auth_guard():
        path = request.path
        is_public = any(
            path == p or path.startswith(f"{p}/") for p in PUBLIC_PATH_PREFIXES
        )
        if is_public:
            return None

        if not os.getenv("ADVOCATE_USER") or not os.getenv("ADVOCATE_PASSWORD"):
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": {
                            "code": "AUTH_CONFIG_ERROR",
                            "message": "ADVOCATE_USER and ADVOCATE_PASSWORD must both be set before starting the server.",
                        },
                    }
                ),
                500,
            )

        if session.get("authenticated"):
            return None

        accepts_html = "text/html" in request.headers.get("accept", "").lower()
        if accepts_html:
            return redirect(f"/login?next={path}", code=303)
        return (
            jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "UNAUTHORIZED",
                        "message": "Login required. Use /login for session authentication.",
                    },
                }
            ),
            401,
        )

    @app.get("/health")
    def health():
        return jsonify({"ok": True, "status": "healthy"})

    @app.get("/")
    def root():
        return redirect("/dashboard", code=303)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "GET":
            next_path = request.args.get("next", "/dashboard")
            if session.get("authenticated"):
                return redirect(next_path, code=303)
            return render_template(
                "core/login.html", title="Login", next_path=next_path, error=None
            )

        username = request.form.get("username", "")
        password = request.form.get("password", "")
        next_path = request.form.get("next", "/dashboard")
        expected_user = os.getenv("ADVOCATE_USER", "")
        expected_password = os.getenv("ADVOCATE_PASSWORD", "")
        if not (
            hmac.compare_digest(username, expected_user)
            and hmac.compare_digest(password, expected_password)
        ):
            return (
                render_template(
                    "core/login.html",
                    title="Login",
                    next_path=next_path,
                    error="Invalid username or password.",
                ),
                401,
            )

        session["authenticated"] = True
        session["username"] = username
        return redirect(next_path or "/dashboard", code=303)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect("/login", code=303)

    @app.get("/dashboard")
    def dashboard():
        return render_template(
            "core/dashboard.html",
            title="Dashboard",
            username=session.get("username", "user"),
        )

    @app.get("/api/me")
    def me():
        return jsonify(
            {
                "ok": True,
                "data": {
                    "module": "core",
                    "auth": "session",
                    "version": APP_VERSION,
                    "user": session.get("username"),
                },
            }
        )

    return app


app = create_app()
