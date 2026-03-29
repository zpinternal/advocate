# CHANGELOG

## 0.5.0 - 2026-03-29 11:32:15 GMT+3
- Implemented Milestone 5 FTP Viewer module:
  - Added FTP/FTPS login session management (`POST /ftp/login`).
  - Added browse/upload/download endpoints (`GET /ftp/browse`, `POST /ftp/upload`, `GET /ftp/download`).
  - Added extract/archive/compress operations (`POST /ftp/extract`, `POST /ftp/archive`, `POST /ftp/compress`).
  - Added combined workflows (`POST /ftp/upload-extract`, `POST /ftp/archive-download`).
- Wired FTP router into the main FastAPI app.
- Bumped version from `0.4.0` to `0.5.0`.

## 0.4.0 - 2026-03-29 11:21:29 GMT+3
- Implemented Milestone 4 Terminal module:
  - Added `POST /terminal/exec` AJAX API for command execution with timeout, stdout/stderr capture, and base-dir cwd protection.
  - Added `WS /terminal/ws` WebSocket command interface with connect/result/error/closing events.
- Wired terminal router into the main FastAPI app.
- Bumped version from `0.3.0` to `0.4.0` (minor version for new feature milestone).

## 0.3.0 - 2026-03-29 11:17:24 GMT+3
- Implemented Milestone 3 File Explorer module with AJAX APIs:
  - Added CWD/base directory introspection, chdir, list, create, rename, upload, and download endpoints.
  - Added async archive (`.tar`) and compress (`.zip`) operations using background thread tasks.
  - Added task status APIs with unique task IDs and polling endpoints (`/tasks`, `/tasks/{task_id}`).
- Added reusable in-process task manager with progress/status/error/result tracking.
- Wired file/task routers into the FastAPI app and bumped application version to `0.3.0`.
- Added `requirements.txt` and updated bootstrap dependency installation logic.

## 0.2.0 - 2026-03-29 11:11:54 GMT+3
- Implemented Milestone 2 ZLink module:
  - Added `/zlink/metrics/usage` ingestion endpoint with payload validation and SQLite persistence.
  - Added `/zlink/metrics/usage` retrieval endpoint for aggregated timeseries data.
  - Added `/zlink/dashboard` with built-in SVG graph rendering (no external CDN assets).
  - Added `ZLINK_REPO` driven release refresh endpoint and local static download support.
- Integrated ZLink router and static file serving into the main FastAPI app.
- Bumped app version from 0.1.0 to 0.2.0 (minor increase for new feature set).
- Added required project governance files: AGENTS.md, AGENT_NOTES.md, BACKLOG.md, DESIGN.md, README.md.
