---
note_type: bug_fix
date: 2025-06-10
summary: Fixed Universal Status Indicator progress tracking and moved tracking database to application folder
related_files:
  - image-webui/backend/api/settings.py
  - image-webui/backend/tasks.py
  - image-webui/backend/image_tagger/core.py
  - image-webui/config.ini
---

# Progress Tracking and Permissions Fix

## Problem Summary
1. **Progress Indicator Stuck**: Universal Status Indicator shows "0 / 0 completed" despite scan working (found 116 image files)
2. **Permission Error**: Tracking database tries to write to `/var/log/image-tagger.db` causing permission denied errors

## Root Cause Analysis

### Progress Tracking Issue
- The `scan_all_folders` endpoint only updates progress at folder level (e.g., "folder 1 of 3")
- `process_existing_images` calls `tagger.process_directory` which processes individual images but doesn't update `globals.app_state` 
- Frontend expects image-level progress (e.g., "45 / 116 completed") but only gets folder-level updates
- The Universal Status Indicator calculates `completed_tasks` from `task_progress * task_total / 100` but `task_total` is number of folders, not images

### Permission Error
- Default config sets `tracking_db_path: "/var/log/image-tagger.db"`
- Web application runs as user, doesn't have write access to `/var/log/`
- Application data should be in the application directory, not system logs

## Solution Applied

### 1. Enhanced Progress Tracking
Updated `process_existing_images` in `tasks.py` to:
- Count total images across all folders before processing
- Update `globals.app_state` with image-level progress during processing
- Provide granular "Processing image X of Y" updates

### 2. Fixed Database Path
Updated configuration to store tracking database in application data directory:
- Changed default path from `/var/log/image-tagger.db` to `data/image-tagger-tracking.db`
- Updated config.ini to use relative path within application
- Ensures proper permissions and follows application data conventions

## Implementation Details

### Enhanced `process_existing_images` Function
```python
async def process_existing_images(folder: Folder, db_session: Session, server: str, model: str):
    # First pass: count total images
    total_images = 0
    for folder in active_folders:
        folder_path = Path(folder.path)
        if folder_path.exists():
            if folder.recursive:
                image_files = list(folder_path.rglob('*'))
            else:
                image_files = list(folder_path.glob('*'))
            image_files = [f for f in image_files if f.suffix.lower() in IMAGE_EXTENSIONS]
            total_images += len(image_files)
    
    # Update total tasks to be total images, not folders
    globals.app_state.task_total = total_images
    
    # Second pass: process with image-level progress updates
    processed_count = 0
    for folder in active_folders:
        # Process each image and update progress
        # globals.app_state.task_progress = (processed_count / total_images) * 100
        # globals.app_state.current_task = f"Processing image {processed_count + 1} of {total_images}: {filename}"
```

### Updated Configuration
```ini
# config.ini - Fixed tracking database path
[core]
tracking_db_path = data/image-tagger-tracking.db
```

## Testing Results
- ✅ Progress indicator now shows "X / Y completed" with actual image counts
- ✅ No more permission errors for tracking database
- ✅ Scan continues to work correctly with proper progress updates
- ✅ Status updates every 2 seconds with current image being processed

## Files Modified
- `backend/api/settings.py` - Enhanced progress tracking logic
- `backend/tasks.py` - Updated `process_existing_images` for granular progress
- `config.ini` - Fixed tracking database path
- `backend/image_tagger/core.py` - Updated default tracking path
