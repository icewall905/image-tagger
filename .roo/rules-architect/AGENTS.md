# Architect Mode Rules (Non-Obvious Only)

- The [`ScheduleChecker`](image-webui/backend/tasks.py:141) is the central orchestrator for batch AI processing. Any architectural change to processing flow must integrate with its window-based gating.
- [`globals.py`](image-webui/backend/globals.py) holds mutable state shared across threads without synchronization — this is a known architectural constraint. New state added here must follow the same polling pattern (check flags in loops).
- The two config systems (INI for Web UI, YAML for tagger core) are intentionally separate. Do not attempt to unify them without a migration plan — the INI config writes to `data/config.ini` to survive container rebuilds.
- DB sessions are NOT thread-safe. The architecture relies on each thread/worker creating its own `SessionLocal()` instance. Connection pooling is not used (SQLite).
- The "soft rollback" pattern in [`_soft_rollback_images()`](image-webui/backend/tasks.py:842) is the architectural answer to mid-window cancellation — images are reset to `pending` rather than left in a broken state.
- The [`image_tagger/core.py`](image-webui/backend/image_tagger/core.py) monolithic design (~1320 lines) is a known technical debt area. Any refactoring should maintain the wildcard export pattern in [`__init__.py`](image-webui/backend/image_tagger/__init__.py:2).
- Folder watchers (watchdog) are initialized in a daemon thread to prevent startup blocking on large file trees — this async initialization pattern must be preserved.
- The app serves images from `/images` volume path (Docker) via a catch-all route in [`app.py`](image-webui/backend/app.py:268), not via static mount — this is intentional for Docker compatibility.
