# Code Mode Rules (Non-Obvious Only)

- Always create fresh DB sessions per operation — never reuse sessions across threads. Use `SessionLocal()` from [`models.py`](image-webui/backend/models.py:70), not [`database.py`](image-webui/backend/database.py).
- Before calling AI processing in any new code path, check [`is_within_schedule_window()`](image-webui/backend/tasks.py:117). Outside the window, set `processing_status='pending'` instead.
- The Web UI config (INI via [`Config`](image-webui/backend/config.py:153)) and tagger core config (YAML via [`load_config()`](image-webui/backend/image_tagger/core.py:47)) are completely separate — don't mix them.
- When adding new config keys, add them to both [`DEFAULT_CONFIG`](image-webui/backend/config.py:41) dict and [`ENV_MAPPINGS`](image-webui/backend/config.py:105) dict for env var overrides.
- Check `globals.app_state.cancel_requested` in all processing loops. The [`ScheduleChecker`](image-webui/backend/tasks.py:141) sets this flag when the window closes.
- Thumbnail generation has three duplicate implementations: [`ImageEventHandler._process_image()`](image-webui/backend/tasks.py:374), [`_make_thumbnail()`](image-webui/backend/tasks.py:534), and [`get_thumbnail()`](image-webui/backend/api/thumbnails.py:113). Prefer the thumbnails API version for new code.
- The `image_tagger` package uses wildcard imports (`from .core import *`) — any public function added to `core.py` is automatically exported.
