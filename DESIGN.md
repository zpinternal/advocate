# DESIGN

## Current Architecture
- FastAPI service with middleware-based Basic auth.
- SQLite local persistence in `data/advocate.db` for ZLink usage metrics.
- Static artifacts served from `/static`.
- In-process background `TaskManager` for async file operations.

## Milestone 2 (ZLink)
- `POST /zlink/metrics/usage` accepts list payloads and stores per-server hourly bytes.
- `GET /zlink/metrics/usage` returns aggregated data grouped by server and hour.
- `GET /zlink/dashboard` renders an inline SVG timeseries graph and legend.
- `POST /zlink/latest/refresh` fetches latest release from GitHub API (`ZLINK_REPO`) and stores the asset as `/static/zlink-latest.zip`.
- `GET /zlink/latest` exposes current cached download availability.

## Milestone 3 (File Explorer + Task framework)
- Base path is locked to startup CWD.
- File Explorer AJAX APIs (`/files/*`) support browse/chdir/upload/download/rename/create and async archive/compress.
- Async tasks (`/tasks/*`) expose statuses `queued`, `running`, `succeeded`, `failed`.

## Milestone 4 (Terminal)
- `POST /terminal/exec` for timed command execution.
- `WS /terminal/ws` for command-over-websocket interactions with session-local `cd`.

## Milestone 5 (FTP Viewer)
- `POST /ftp/login` opens a stored FTP/FTPS session profile.
- `GET /ftp/browse`, `POST /ftp/upload`, `GET /ftp/download` for core remote file operations.
- `POST /ftp/archive`, `POST /ftp/compress`, `POST /ftp/extract` for archive workflows.
- `POST /ftp/upload-extract`, `POST /ftp/archive-download` for bundled workflows.

## Security
- Only `/health` is public; all module routes require Basic auth via env credentials.
- File and terminal path handling is constrained to startup base path.
- FTP endpoints require valid in-memory session IDs from authenticated login flow.

## Milestone 6 (Gemini foundations)
- Conversations and messages are persisted in SQLite (`conversations`, `messages`).
- Sync flow supports incremental retrieval with `id > last_saved_message_id`.
- Gemini-backed chat/translation routes call Google Generative Language API when `GEMINI_API_KEY` is configured.
- Auth middleware converts auth parsing failures into structured 401 JSON responses to avoid uncaught exception groups.
