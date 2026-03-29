# BACKLOG

- Add authentication exemptions for docs pages while keeping API routes protected.
- Add deduplication/upsert logic for `/zlink/metrics/usage` to avoid repeated inserts.
- Persist latest release metadata in database instead of returning generic `cached` version.
- Add comprehensive tests with mocked GitHub API responses.
- Add task queue/caching layer for release refresh to avoid concurrent downloads.
- Replace process-wide `CURRENT_DIR` with per-user session working directories.
- Add task cancellation support and bounded queue visibility for archive/compress operations.
- Add chunked upload support for large files in File Explorer.
- Replace terminal `shell=True` execution with safer command parsing/allowlists.
- Upgrade WebSocket terminal from command-per-message to full PTY streaming for richer shell parity.
- Add recursive FTP directory upload/download and remote directory creation handling.
- Move FTP session storage to encrypted persistence with TTL cleanup.
