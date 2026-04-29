# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Project Layout
- All application code lives under [`image-webui/`](image-webui/). The repo root contains only install scripts and docs.
- The app runs from within `image-webui/` — all relative paths (e.g., `data/`, `backend/`) resolve from there.

## Build/Run Commands
```bash
cd image-webui
./run.sh                          # creates venv, installs deps, runs on :8491
uvicorn backend.app:app --reload  # manual start (venv must be active)
```

## Two Independent Config Systems
- **Web UI**: INI format via [`Config`](image-webui/backend/config.py:153) class (configparser). Resolution order: `/etc/image-tagger/config.ini` → `data/config.ini` → root `config.ini`. Writes go to `data/config.ini` to survive container rebuilds.
- **CLI/tagger core**: YAML format via [`load_config()`](image-webui/backend/image_tagger/core.py:47) in `core.py`. These two config systems are completely separate.

## Database
- SQLite via SQLAlchemy 2.0, stored at `data/image_tagger.db`.
- [`models.py`](image-webui/backend/models.py) is the canonical DB module. [`database.py`](image-webui/backend/database.py) is a legacy duplicate — prefer `models.py` for `SessionLocal`, `get_db`, `Base`.
- Alembic migrations in [`migrations/`](image-webui/migrations/), triggered by [`setup_db.sh`](image-webui/setup_db.sh).

## Schedule-Based Processing (Critical)
- The [`ScheduleChecker`](image-webui/backend/tasks.py:141) background thread auto-triggers batch AI processing during configured time windows.
- Outside the window, new images are queued as `processing_status='pending'` and processed later.
- When the window closes mid-scan, a "soft rollback" via [`_soft_rollback_images()`](image-webui/backend/tasks.py:842) resets in-flight images to pending.
- Always check [`is_within_schedule_window()`](image-webui/backend/tasks.py:117) before triggering AI processing in new code paths.

## Global State
- [`globals.py`](image-webui/backend/globals.py) holds mutable [`AppState`](image-webui/backend/globals.py:4) shared across threads (scan progress, pause/cancel flags). Thread-safe access is NOT guaranteed — use the existing patterns (checking `cancel_requested` in loops).

## AI Backend
- Supports both Ollama-native and OpenAI-compatible APIs, controlled by `ollama.api_type` config key.
- The core processing logic is in [`image_tagger/core.py`](image-webui/backend/image_tagger/core.py) (~1320 lines, monolithic). It does `from .core import *` in [`__init__.py`](image-webui/backend/image_tagger/__init__.py:2).

## Type Checking
- pyright configured in [`pyrightconfig.json`](image-webui/pyrightconfig.json) with nearly all strict checks disabled. Custom stubs in [`stubs/`](image-webui/stubs/) provide minimal type hints for fastapi, sqlalchemy, uvicorn, watchdog.

## Testing
- No test framework (no pytest/unittest). Ad-hoc scripts: [`test_api.py`](image-webui/test_api.py), [`test_imports.py`](image-webui/test_imports.py), [`test_comprehensive.py`](image-webui/test_comprehensive.py).
- Run them directly: `cd image-webui && python test_imports.py`

## HEIC Support
- Requires `pillow-heif` Python package AND `libheif-dev` system library (installed in Dockerfile).
