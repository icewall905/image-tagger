# Debug Mode Rules (Non-Obvious Only)

- Logs go to `data/image-tagger.log` by default, with a separate `data/image-tagger.error.log` for errors only. Structured JSON logging is available via `general.enable_structured_logging=true`.
- The [`ScheduleChecker`](image-webui/backend/tasks.py:141) ticks every 60 seconds — schedule changes take up to 60s to apply without restart.
- Processing status is exposed at `GET /api/settings/processing-status` — check `queue_depth` and `failed_count` for backlog diagnostics.
- Folder watchers start in a background thread to avoid blocking startup on large directories. If watchers fail silently, check `DISABLE_FOLDER_WATCHERS=1` env var.
- The [`_soft_rollback_images()`](image-webui/backend/tasks.py:842) function resets images to `pending` when the schedule window closes mid-scan — this is intentional, not a bug.
- DB is at `data/image_tagger.db` (SQLite). Direct inspection: `sqlite3 data/image_tagger.db`.
- The `ollama.api_type` config key switches between `ollama` (native) and `openai` (OpenAI-compatible) API modes. Connection test endpoint: `POST /api/settings/test-ollama`.
- Rate limiting is bypassed for private/local IPs (RFC1918/loopback) — see [`SecurityMiddleware.__call__()`](image-webui/backend/security.py:124).
