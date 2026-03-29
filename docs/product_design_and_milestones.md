# Advocate — Product Design, Architecture, and Milestones

## 1) Vision and Goals

Build an **ephemeral, browser-accessed ops + productivity platform** that can:
- run as a self-bootstrapping server (`run.py`),
- expose core system tools (file explorer, terminal, FTP/Git/GitHub wrappers),
- provide integrations (Reddit, Twitter, Gmail, GDrive), and
- offer AI-powered workflows (Gemini chat, translation, TTS, image generation).

Primary design constraints:
- **Ephemeral server lifecycle** (stateless bootstrap, environment-driven auth).
- **Safe async operations** for long-running tasks (archive/compress/upload).
- **Incremental delivery**: core + foundations first, then modules.

---

## 2) Product Scope (from ordered feature list)

### Core
- `run.py` checks/install dependencies, then launches a uv server.

### Auth module
- Username/password from `ADVOCATE_USER` and `ADVOCATE_PASSWORD` env vars.

### ZLink module
- `POST /zlink/metrics/usage` for usage payload ingestion.
- dashboard with time-series graphs.
- fetch latest release from configurable GitHub repo (`ZLINK_REPO`) and expose download link.

### File Explorer (AJAX API)
- CWD-based browsing, chdir, upload/download, rename, create.
- archive/compress as background jobs with task IDs and status polling.

### Terminal
- AJAX API execution.
- WebSocket interactive terminal.

### FTP viewer
- login (optional SSL), browse/upload/download/extract/archive/compress.
- upload+extract and archive+download workflows.

### Gemini API chat interface
- Conversations + messages persisted locally.
- sync messages via `id > last_saved_message_id`.
- Image generation previews + full download.
- Translation via Gemini 3.x Flash models.
- Audio generation via 2.5 TTS Flash and conversion to 16kbps opus mono.

### GitHub Wrapper
- create repo, approve PR, set repo private/public.

### Git Features
- clone/upload/commit/pull/archive+download/patch generation.

### Reddit Interface
- browse/view/comment/vote/search.
- bulk voting actions.
- Gemini-generated replies.

### Twitter Feed
- single tweet, tweet from JSON, Gemini tweet generation.

### GDrive
- upload/download/list.

### Gmail
- fetch/download EML/compose/AI reply/AI summary.

### Stable Uploader
- resumable chunked upload with recovery from last byte.
- MD5 part verification before append.
- optional GDrive destination and folder upload.

---

## 3) High-Level Architecture

## 3.1 Runtime components
1. **Bootstrap Layer** (`run.py`)
   - environment validation,
   - dependency installation,
   - server start (uvicorn/uv-based runtime).

2. **Web API Server**
   - REST endpoints (AJAX module APIs),
   - WebSocket endpoints (interactive terminal/live updates),
   - auth middleware (env-based credentials),
   - background worker manager for long jobs.

3. **Data Layer**
   - local DB (SQLite recommended initially) for:
     - chat conversations/messages,
     - async task records,
     - sync cursors,
     - audit logs.

4. **Job/Task Execution Layer**
   - thread pool for archive/compress/upload jobs,
   - optional process pool for CPU-heavy compression,
   - task status registry (`queued/running/succeeded/failed/cancelled`).

5. **Integration Adapters**
   - GitHub, Reddit, Twitter, Gmail, GDrive, Gemini, FTP,
   - isolated service interfaces for easier replacement/testing.

6. **UI Layer**
   - modular pages for each feature,
   - shared task/status center,
   - charting for ZLink usage metrics.

## 3.2 Recommended backend stack
- **Python 3.11+**
- **FastAPI** for REST + WebSockets
- **Uvicorn** server
- **SQLAlchemy + SQLite**
- **APScheduler/Celery-lite pattern** (initially in-process task manager)
- **httpx** for APIs
- **plot/chart via frontend** (Chart.js/ECharts)

## 3.3 API conventions
- Prefix module APIs (`/api/file/*`, `/api/git/*`, `/api/zlink/*` etc).
- Consistent response envelope:
  - `{"ok": true, "data": ...}`
  - `{"ok": false, "error": {"code": "...", "message": "..."}}`
- Long-running operations return:
  - `task_id`, `status_url`, and optional ETA.

---

## 4) Data Model (initial)

## 4.1 Auth/session
- Minimal in-memory session/cookie with server-side token map.
- Credentials sourced only from env vars.

## 4.2 Chat
- `conversations(id, title, created_at, updated_at)`
- `messages(id, conv_id, sha1, message, type, created_at)`
- `sync_state(module, last_saved_message_id, updated_at)`

## 4.3 Async tasks
- `tasks(id, module, op, status, progress, payload_json, result_json, error_json, created_at, updated_at)`

## 4.4 ZLink usage
- `zlink_usage(id, server, ts_hour, bytes, created_at)`
- materialized aggregation query for dashboard plots.

---

## 5) Key Module Designs

## 5.1 Core + Auth
- `run.py`
  1. verify Python version,
  2. install missing deps (idempotent),
  3. validate env vars (`ADVOCATE_USER`, `ADVOCATE_PASSWORD`),
  4. start server.
- add startup checks with clear failure messages.

## 5.2 ZLink
- **Ingestion endpoint**: validate array payload, normalize timestamps to UTC hour.
- **Dashboard**:
  - total bytes per server over time,
  - stacked/global usage trends,
  - selectable server filter.
- **Latest release fetcher**:
  - poll GitHub Releases API from `ZLINK_REPO`,
  - cache metadata with TTL,
  - expose `latest-version` + download route.

## 5.3 File Explorer
- root constraint: start in CWD; configurable jail mode optional.
- safe path resolution (`realpath`, traversal prevention).
- upload/download streaming for large files.
- archive/compress jobs are async tasks with polling endpoint.

## 5.4 Terminal
- AJAX: non-interactive command execution endpoint.
- WebSocket: PTY-backed interactive shell session.
- enforce command timeouts and output caps in AJAX mode.

## 5.5 FTP Viewer
- connector abstraction with SSL toggle.
- remote fs operations mirror local explorer concepts.
- workflows (upload+extract, archive+download) implemented as orchestrated tasks.

## 5.6 Gemini module
- chats persisted locally.
- sync protocol: client sends `last_saved_message_id`; server returns incremental messages.
- image gen pipeline:
  - generate low-res previews (1/16, 1/8),
  - optimized preview,
  - full-size artifact storage + download.
- TTS pipeline: Gemini output -> ffmpeg transcode to opus 16kbps mono.

## 5.7 Git/GitHub
- Git operations via subprocess wrapper with sanitized args.
- GitHub wrapper via OAuth/App token.
- repository privacy change and PR approval guarded by explicit permissions.

## 5.8 Reddit/Twitter/Gmail/GDrive
- each integration has:
  - credential config,
  - adapter service,
  - rate-limit handling,
  - retry/backoff,
  - audit/error logs.
- AI operations are optional overlays, never blocking core read/write features.

## 5.9 Stable Uploader
- chunking strategy (dynamic chunk size based on observed throughput).
- server tracks upload offsets + md5 hash per part.
- resume by querying last valid byte.
- optional post-complete actions (save to GDrive, folder support).

---

## 6) Non-Functional Requirements

- **Security**: path traversal prevention, auth required for all non-health endpoints, secret redaction in logs.
- **Reliability**: retry network operations, resume-capable uploads, task recovery after restart where feasible.
- **Performance**: streaming I/O for files, pagination for listings, async HTTP clients.
- **Observability**: structured logs, per-module error counters, task metrics.
- **Extensibility**: adapter interfaces per external provider.

---

## 7) Milestones (ordered plan)

## Milestone 0 — Project foundation (Week 1)
- repository structure (`app/`, `modules/`, `ui/`, `db/`, `tasks/`).
- config management + env loading.
- health endpoint and logging baseline.

**Exit criteria**
- app boots locally with a health check and basic auth guard scaffold.

## Milestone 1 — Core bootstrap + auth (Week 1–2)
- implement `run.py` dependency check/install and server startup.
- enforce env-based auth using `ADVOCATE_USER` / `ADVOCATE_PASSWORD`.

**Exit criteria**
- fresh environment can run one command and get authenticated access.

## Milestone 2 — ZLink module MVP (Week 2)
- `/zlink/metrics/usage` ingestion endpoint.
- persistence for usage metrics.
- dashboard with server/time charts.
- release fetch from `ZLINK_REPO` + download link endpoint.

**Exit criteria**
- sample JSON payload appears in dashboard and latest version metadata is retrievable.

## Milestone 3 — File Explorer + Task framework (Week 3)
- CRUD-like file ops (browse/chdir/upload/download/rename/create).
- async task engine + task status APIs.
- archive/compress async operations.

**Exit criteria**
- large archive/compress operations run in background with progress polling.

## Milestone 4 — Terminal (Week 4)
- AJAX command execution endpoint.
- WebSocket interactive terminal with PTY.

**Exit criteria**
- both non-interactive and interactive terminal modes stable under auth.

## Milestone 5 — FTP viewer (Week 5)
- login (SSL optional), browse/upload/download.
- extract/archive/compress and compound workflows.

**Exit criteria**
- end-to-end remote file workflows complete via UI.

## Milestone 6 — Gemini chat platform (Week 6–7)
- conversation/message models + local DB persistence.
- incremental sync protocol.
- chat UI + message history.
- translation + TTS (opus conversion).
- image generation preview pipeline + full download.

**Exit criteria**
- user can chat, sync, translate, generate audio/image outputs from UI.

## Milestone 7 — Git + GitHub wrappers (Week 8)
- git operations (clone/upload/commit/pull/archive/patch).
- GitHub repo create, PR approve, visibility toggle.

**Exit criteria**
- authenticated user can execute safe git workflows and selected GitHub actions.

## Milestone 8 — Social and productivity integrations (Week 9–10)
- Reddit interface incl. bulk actions + Gemini replies.
- Twitter interface (single/JSON/generated tweets).
- GDrive upload/download/list.
- Gmail fetch/EML/compose/AI reply/summary.

**Exit criteria**
- each integration supports at least one full user flow from login to action completion.

## Milestone 9 — Stable uploader + hardening (Week 11)
- resumable dynamic chunk uploads.
- md5 part validation.
- optional GDrive and folder upload modes.
- system-wide resilience, rate-limit and timeout tuning.

**Exit criteria**
- interrupted uploads reliably resume and pass integrity checks.

## Milestone 10 — Release readiness (Week 12)
- QA pass, security pass, docs, packaging.
- final performance and reliability fixes.

**Exit criteria**
- release candidate with setup guide and operational playbook.

---

## 8) Risk Register and Mitigations

1. **API provider instability/rate limits**
   - mitigation: retries with jitter, circuit-breaker behavior, cached fallbacks.
2. **Long-running task contention**
   - mitigation: bounded worker pools, cancellation support, priority queues.
3. **Ephemeral environment data loss**
   - mitigation: optional persistent volume + export/import backups.
4. **Security risks from shell/file operations**
   - mitigation: strict auth, command sanitization, path guards, audit logs.
5. **Complexity creep across many modules**
   - mitigation: strict module interfaces and milestone gating.

---

## 9) Suggested Repository Layout

```text
advocate/
  run.py
  app/
    main.py
    auth/
    core/
    modules/
      zlink/
      files/
      terminal/
      ftp/
      gemini/
      git/
      github/
      reddit/
      twitter/
      gdrive/
      gmail/
      uploader/
    tasks/
    db/
    schemas/
  ui/
  docs/
    product_design_and_milestones.md
```

---

## 10) Definition of Done (cross-module)

A feature is done when:
- API contract documented and implemented.
- Auth enforced.
- Input validation + error handling complete.
- Tests for critical path included.
- Logs/metrics added.
- UI flow functional (if applicable).
- Security checklist passed.

