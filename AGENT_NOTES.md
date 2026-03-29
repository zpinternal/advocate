# AGENT_NOTES

- 2026-03-29: Implemented Milestone 2 (ZLink ingestion, dashboard, latest release fetch/download).
- 2026-03-29: Could not run dependency installation from PyPI because outbound package index access is blocked by proxy restrictions in this environment.
- 2026-03-29: Playwright is not installed in the environment (`No module named playwright`), so browser UI automation could not be executed here.
- 2026-03-29: Implemented Milestone 3 file explorer + task framework using an in-memory TaskManager and threaded archive/compress jobs.
- 2026-03-29: Attempted `pip install -r requirements.txt` for milestone 3 setup; package installation is still blocked by proxy/index restrictions in this environment.
- 2026-03-29: Implemented Milestone 4 terminal endpoints (`/terminal/exec` and `/terminal/ws`) and wired module into app.
- 2026-03-29: Re-attempted `pip install -r requirements.txt`; installation remains blocked by proxy/index restrictions.
- 2026-03-29: Playwright still unavailable (`No module named playwright`), so UI automation for milestone 4 could not run.
- 2026-03-29: Implemented Milestone 5 FTP viewer module with login, browse, transfer, archive/compress/extract, and combined endpoints.
- 2026-03-29: Re-attempted dependency/tool setup for milestone 5; `pip install -r requirements.txt` still blocked by proxy restrictions and Playwright remains unavailable.
- 2026-03-29: Implemented Milestone 6 Gemini foundations (conversation/message persistence, sync endpoint, chat send, translation).
- 2026-03-29: Fixed middleware auth exception handling so missing Authorization now returns 401 JSON instead of 500 on deployment.
- 2026-03-29: Could not run FastAPI TestClient runtime check in this container because `fastapi` package is not installed locally.
- 2026-03-29: Migrated authentication from HTTP Basic to cookie-backed session login pages (`/login`) and introduced shared dashboard/navigation templates.
- 2026-03-29: Attempted UI automation check with `python -m playwright --version`; Playwright is still unavailable in this environment (`No module named playwright`).
- 2026-03-29: FastAPI runtime smoke test via `fastapi.testclient` could not run because `fastapi` is not installed in the active Python interpreter.
- 2026-03-29: Migrated app from FastAPI to Flask and added milestone UI pages for Files, Terminal, FTP, and Gemini modules.

- 2026-03-29: Vendored xterm.js assets locally under `static/vendors/xterm` to keep terminal UI functional without network access at runtime.
- 2026-03-29: Implemented FTP credential/session restoration using Flask session storage (`ftp_saved_sessions`) and fallback reconstruction on API calls.
