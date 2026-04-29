# Ask Mode Rules (Non-Obvious Only)

- The repo root contains only install scripts and docs. All application code is under [`image-webui/`](image-webui/). Paths like `data/` and `backend/` resolve from within `image-webui/`.
- There are two completely independent config systems: INI (Web UI, configparser) and YAML (CLI/tagger core). They do not share values.
- [`models.py`](image-webui/backend/models.py) is the canonical DB module. [`database.py`](image-webui/backend/database.py) exists but is a legacy duplicate — always reference `models.py` for schema questions.
- The [`image_tagger/core.py`](image-webui/backend/image_tagger/core.py) file is ~1320 lines and monolithic — it contains the AI processing pipeline, EXIF metadata handling, and image format detection all in one file.
- The app supports both Ollama-native and OpenAI-compatible APIs for AI inference, controlled by the `ollama.api_type` config key.
- There is no test framework (no pytest/unittest). Test scripts are ad-hoc Python files run directly.
- HEIC support requires both the `pillow-heif` Python package and the `libheif-dev` system library.
