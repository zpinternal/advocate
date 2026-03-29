#!/usr/bin/env python3
"""Bootstrap Advocate in ephemeral environments.

Milestone 1 requirements:
1) install required dependencies if missing,
2) validate env-based auth credentials,
3) start the ASGI server.
"""

import importlib.util
import os
import subprocess
import sys


PYTHON_MIN = (3, 11)
REQUIRED_IMPORTS = {
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "multipart": "python-multipart",
    "jinja2": "jinja2",
}


def ensure_python_version() -> None:
    if sys.version_info < PYTHON_MIN:
        version = ".".join(str(part) for part in PYTHON_MIN)
        raise SystemExit(
            f"Python {version}+ is required. Current: {sys.version.split()[0]}"
        )


def missing_packages() -> list[str]:
    return [
        pip_name
        for module_name, pip_name in REQUIRED_IMPORTS.items()
        if importlib.util.find_spec(module_name) is None
    ]


def install_if_needed() -> None:
    missing = missing_packages()
    if not missing:
        print("All required dependencies are already installed.")
        return

    print(f"Installing missing dependencies: {', '.join(missing)}")
    req_file = "requirements.txt"
    if os.path.exists(req_file):
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", req_file])
    else:
        subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])


def ensure_auth_env() -> None:
    user = os.getenv("ADVOCATE_USER")
    password = os.getenv("ADVOCATE_PASSWORD")
    if not user or not password:
        raise SystemExit(
            "Missing auth environment vars. Set ADVOCATE_USER and ADVOCATE_PASSWORD before starting the server."
        )


def start_server() -> None:
    host = os.getenv("ADVOCATE_HOST", "0.0.0.0")
    port = os.getenv("ADVOCATE_PORT", "8000")
    print(f"Starting server on {host}:{port}")
    subprocess.check_call(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ]
    )


if __name__ == "__main__":
    ensure_python_version()
    install_if_needed()
    ensure_auth_env()
    start_server()
