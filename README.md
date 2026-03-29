# Advocate

Advocate is an ephemeral operations web app with authenticated tooling and integrations.

## Quick Start

```bash
export ADVOCATE_USER=admin
export ADVOCATE_PASSWORD=secret
# Optional for ZLink latest release integration
export ZLINK_REPO=owner/repo
python run.py
```

## Dependencies
Runtime dependencies are listed in `requirements.txt` and are auto-installed by `run.py` when missing.

## Implemented Milestones
- Milestone 1: bootstrap runner + session-based login auth.
- Milestone 2: ZLink metrics ingestion, dashboard, and latest release fetch/download link.
- Milestone 3: File Explorer AJAX APIs and async task framework for archive/compress.
- Milestone 4: Terminal APIs via AJAX and WebSocket plus xterm.js-based GUI terminal.
- Milestone 5: FTP viewer APIs with GUI workflow and session-persisted credential restoration.
- Milestone 6: Gemini module foundations (conversation/message persistence, sync by message ID, Gemini chat send, translation endpoint).

## Key Endpoints
- `GET /health`
- `POST /zlink/metrics/usage`
- `GET /zlink/metrics/usage`
- `GET /zlink/dashboard`
- `POST /zlink/latest/refresh`
- `GET /zlink/latest`
- `GET /files/cwd`
- `POST /files/chdir`
- `GET /files/list`
- `POST /files/create`
- `POST /files/rename`
- `POST /files/upload`
- `GET /files/download`
- `POST /files/archive`
- `POST /files/compress`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /terminal/exec`
- `WS /terminal/ws`
- `POST /ftp/login`
- `GET /ftp/session`
- `GET /ftp/browse`
- `POST /ftp/upload`
- `GET /ftp/download`
- `POST /ftp/archive`
- `POST /ftp/compress`
- `POST /ftp/extract`
- `POST /ftp/upload-extract`
- `POST /ftp/archive-download`
- `POST /gemini/conversations`
- `GET /gemini/conversations`
- `POST /gemini/conversations/{conversation_id}/messages`
- `GET /gemini/conversations/{conversation_id}/messages`
- `GET /gemini/sync`
- `POST /gemini/chat/send`
- `POST /gemini/translate`

## Version
Current version: `0.9.0`.


## UI Routes
- `GET /login`
- `POST /login`
- `POST /logout`
- `GET /dashboard`


## Flask-based UI
- `/dashboard` central UX hub for milestones 2-6.
- `/files/ui`, `/terminal/ui`, `/ftp/ui`, `/gemini/ui` module pages.
