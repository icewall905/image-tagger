# Image Tagger Backend Optimization Plan

## Problem Summary

User visits the page from another machine and sees **zero images**, despite having scanned folders and seen results from another machine. The root cause is a combination of architectural issues that make the backend unreliable for multi-machine access.

---

## Root Cause Analysis

### 🔴 Critical: Gallery Hides Non-AI-Processed Images

[`images.py:73`](image-webui/backend/api/images.py:73) — The default query filters to only images where `description IS NOT NULL AND description != ''`. This means:

- Images scanned but not yet AI-processed (pending) are invisible
- If Ollama is unreachable or schedule window is closed, ALL images are hidden
- User sees "No images found" even though the DB has records

**Fix**: Change default to show all images, add a `status` filter for users who want only completed ones.

### 🔴 Critical: Dashboard Stats Completely Broken

[`index.html:183-185`](image-webui/frontend/templates/index.html:183) reads `data.folders`, `data.images`, `data.tags` from `/api/settings/status`, but [`settings.py:654`](image-webui/backend/api/settings.py:654) returns `{status, database, ollama, storage, timestamp}` — no counts at all. Dashboard always shows `-` for all stats.

**Fix**: Either add counts to the status endpoint, or have the dashboard call `/api/settings/stats` instead.

### 🔴 Critical: Image Serving Hardcoded to Docker Path

[`app.py:274`](image-webui/backend/app.py:274) — The `/images/{path}` route uses `Path("/images")` which only exists inside Docker containers. When running via `run.sh` outside Docker, no images can be served.

**Fix**: Make the image root configurable, defaulting to `/` (filesystem root) when not in Docker, or serve images through a proper API endpoint that resolves paths from the DB.

### 🟡 Major: Duplicate Database Modules

Two separate database modules exist:
- [`models.py`](image-webui/backend/models.py) — canonical, used by `app.py` for initialization
- [`database.py`](image-webui/backend/database.py) — legacy duplicate, creates its own engine and `SessionLocal`

Both create separate engines. Code that imports from `database.py` gets a different `SessionLocal` than code importing from `models.py`. This is a source of subtle bugs.

**Fix**: Remove `database.py`, consolidate everything into `models.py`.

### 🟡 Major: Frontend Uses Filesystem Paths as URLs

[`gallery.html:226`](image-webui/frontend/templates/gallery.html:226) uses `image.path` (absolute filesystem path like `/home/user/photos/img.jpg`) directly in `<a href>` and lightbox. From a remote browser, these are meaningless.

**Fix**: Use `/api/images/{id}/file` or `/images/{relative_path}` endpoints instead.

### 🟡 Major: No Config File Exists

No `config.ini` exists in the repo. The app creates one on first run with defaults, but:
- Default host is `0.0.0.0` in config but `127.0.0.1` in `__main__` block
- Schedule is disabled by default (good), but the ScheduleChecker still runs
- `scan_on_startup` defaults to `false`

**Fix**: Ship a sensible default `config.ini` with the repo.

---

## Optimization Plan

### Phase 1: Make It Work (Critical Fixes)

#### 1. Fix Gallery API — Show All Images

**File**: [`image-webui/backend/api/images.py`](image-webui/backend/api/images.py)

Change the default query from filtering to `description IS NOT NULL` to showing all images. Add a `status` query parameter for filtering:

```python
@router.get("/images", response_model=List[ImageListResponse])
def list_images(
    q: Optional[str] = None,
    tag: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, description="Filter: completed, pending, failed, skipped, processing, or 'all'"),
    db: Session = Depends(get_db)
):
    query = db.query(Image)
    if status and status != "all":
        query = query.filter(Image.processing_status == status)
    # ... rest of filtering
```

Also add `processing_status` to `ImageListResponse` so the frontend can show status badges.

#### 2. Fix Dashboard Stats

**File**: [`image-webui/frontend/templates/index.html`](image-webui/frontend/templates/index.html)

Change the dashboard JS to call `/api/settings/stats` instead of `/api/settings/status`:

```javascript
$.ajax({
    url: '/api/settings/stats',
    method: 'GET',
    success: function(data) {
        $('#dash-folder-count').text(data.folder_count);
        $('#dash-image-count').text(data.image_count);
        $('#dash-tag-count').text(data.tag_count);
        // ...
    }
});
```

#### 3. Fix Image Serving for Non-Docker Environments

**File**: [`image-webui/backend/app.py`](image-webui/backend/app.py)

Replace the hardcoded `/images` path with configurable resolution:

```python
IMAGE_ROOT = os.environ.get("IMAGE_ROOT", "/")

@app.get("/images/{path:path}")
async def serve_image(path: str):
    image_path = Path(IMAGE_ROOT) / path
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(image_path)
```

Also add a proper API endpoint for serving images by DB ID:

```python
@app.get("/api/images/{image_id}/file")
async def serve_image_by_id(image_id: int, db: Session = Depends(get_db)):
    image = db.query(Image).filter(Image.id == image_id).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    image_path = Path(image.path)
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")
    return FileResponse(image_path)
```

#### 4. Fix Frontend Image URLs

**File**: [`image-webui/frontend/templates/gallery.html`](image-webui/frontend/templates/gallery.html)

Change all direct path references to API endpoints:
- Thumbnails: already using `/api/thumbnails/{id}` ✓
- Full image: change from `image.path` to `/api/images/{id}/file`
- Download link: change to `/api/images/{id}/file?download=true`

### Phase 2: Simplify & Harden

#### 5. Consolidate Database Modules

- Remove [`image-webui/backend/database.py`](image-webui/backend/database.py)
- Update all imports to use `models.py` only
- Ensure `models.py` has `check_same_thread=False` for SQLite (currently missing)

#### 6. Simplify Configuration

**File**: [`image-webui/backend/config.py`](image-webui/backend/config.py)

- Remove the `get_config()` backwards-compatibility function (the `ConfigObj` class)
- Ship a default `config.ini` in the repo root
- Remove the `tracking` section (unused tracking DB)
- Ensure `host` defaults to `0.0.0.0` everywhere (currently `127.0.0.1` in `__main__`)

#### 7. Add Health Check Endpoint

Add a simple `/api/health` endpoint that returns `{"status": "ok", "db": "connected"}` for monitoring.

#### 8. Remove Dead Code

- Remove `tracking` config section and any tracking DB references
- Remove the `ConfigObj` backwards-compatibility class in `config.py`
- Remove `scan_folders_for_images()` in `tasks.py` (duplicate of `process_existing_images()`)
- Remove the duplicate `generate_thumbnail()` method in `ImageEventHandler`

#### 9. Harden CORS and Host Binding

- Ensure `run.sh` uses `--host 0.0.0.0` (already does via env var)
- Ensure CORS allows all origins by default for LAN access
- Add a warning on startup if binding to `127.0.0.1` (only local access)

### Phase 3: Reliability Improvements

#### 10. Add Startup Validation

At startup, validate:
- Database file is writable
- Thumbnail directory is writable
- At least one folder is configured (warn if not)
- Print clear startup message with bound address

#### 11. Improve Error Handling in Frontend

- Show meaningful error messages when API calls fail
- Add retry logic for transient failures
- Show image status (pending/processing/completed/failed) in gallery cards

#### 12. Simplify Schedule System

The schedule system adds significant complexity. Consider:
- Making it opt-in with a clear warning
- Simplifying the ScheduleChecker to only trigger, not cancel
- Removing the soft-rollback pattern (confusing behavior)

---

## Architecture Diagram

```mermaid
flowchart TD
    A[Browser - Remote Machine] -->|HTTP :8491| B[FastAPI App]
    B --> C[API Routes]
    C --> D[images.py - Gallery API]
    C --> E[settings.py - Stats/Status]
    C --> F[folders.py - Folder Management]
    C --> G[thumbnails.py - Thumbnail Serving]
    
    D --> H[(SQLite DB - models.py)]
    E --> H
    F --> H
    
    B --> I[/images/{path} - File Serving]
    I --> J[Filesystem - IMAGE_ROOT]
    
    B --> K[/api/images/{id}/file - File by ID]
    K --> H
    K --> J
    
    style A fill:#4a9eff,color:#fff
    style B fill:#2d2d2d,color:#fff
    style H fill:#f5a623,color:#000
    style J fill:#7ed321,color:#000
```

---

## Files to Modify

| File | Change | Priority |
|------|--------|----------|
| [`images.py`](image-webui/backend/api/images.py) | Show all images by default, add status filter | 🔴 Critical |
| [`index.html`](image-webui/frontend/templates/index.html) | Fix dashboard to call /stats endpoint | 🔴 Critical |
| [`app.py`](image-webui/backend/app.py) | Configurable IMAGE_ROOT, add /api/images/{id}/file | 🔴 Critical |
| [`gallery.html`](image-webui/frontend/templates/gallery.html) | Use API URLs instead of filesystem paths | 🔴 Critical |
| [`models.py`](image-webui/backend/models.py) | Add check_same_thread=False, consolidate | 🟡 Major |
| [`database.py`](image-webui/backend/database.py) | DELETE - consolidate into models.py | 🟡 Major |
| [`config.py`](image-webui/backend/config.py) | Remove ConfigObj, simplify, ship default config.ini | 🟡 Major |
| [`tasks.py`](image-webui/backend/tasks.py) | Remove dead code, simplify | 🟢 Minor |
| New: `config.ini` | Ship sensible defaults | 🟡 Major |
| New: health endpoint in `app.py` | Add /api/health | 🟢 Minor |

---

## What NOT to Change

- The two config systems (INI for Web UI, YAML for tagger core) — keep separate as documented
- The watchdog-based folder monitoring — it works correctly
- The `image_tagger/core.py` monolithic design — out of scope for this optimization
- The `globals.py` mutable state pattern — works for current threading model
- The schedule window concept — simplify but don't remove (users may rely on it)
