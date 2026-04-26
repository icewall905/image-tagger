import os
import time
import logging
import threading
import datetime
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from sqlalchemy.orm import Session
from typing import Optional
import random
from PIL import Image as PILImage

try:
    from zoneinfo import ZoneInfo
    HAS_ZONEINFO = True
except ImportError:
    HAS_ZONEINFO = False

from .models import Folder, Image, Tag, SessionLocal
from .image_tagger import core as tagger
from .utils import log_error_with_context, log_performance_metric
from . import globals
from .api.thumbnails import get_thumbnail_path

# Configure logging for this module
logger = logging.getLogger(__name__)

_low_priority_lock = threading.Lock()
_low_priority_applied = False


def _get_processing_limits():
    """Load processing limits from config with safe fallbacks."""
    from .config import Config
    return {
        "max_workers": max(1, Config.getint("processing", "max_workers", fallback=1)),
        "llm_inter_image_delay_seconds": max(0.0, Config.getfloat("processing", "llm_inter_image_delay_seconds", fallback=1.5)),
        "scan_pause_every_n_files": max(0, Config.getint("processing", "scan_pause_every_n_files", fallback=200)),
        "scan_pause_seconds": max(0.0, Config.getfloat("processing", "scan_pause_seconds", fallback=0.05)),
        "low_priority_enabled": Config.getboolean("processing", "low_priority_enabled", fallback=True),
        "low_priority_nice": max(0, Config.getint("processing", "low_priority_nice", fallback=10)),
        "low_priority_ionice_class": max(1, min(3, Config.getint("processing", "low_priority_ionice_class", fallback=3))),
    }


def _apply_low_priority_settings():
    """Best-effort process priority reduction for safe background scanning."""
    global _low_priority_applied
    with _low_priority_lock:
        if _low_priority_applied:
            return
        limits = _get_processing_limits()
        if not limits["low_priority_enabled"]:
            _low_priority_applied = True
            return

        try:
            os.nice(limits["low_priority_nice"])
            logger.info(f"Applied process niceness: +{limits['low_priority_nice']}")
        except Exception as e:
            logger.warning(f"Could not apply niceness: {e}")

        try:
            subprocess.run(
                ["ionice", "-c", str(limits["low_priority_ionice_class"]), "-p", str(os.getpid())],
                check=False,
                capture_output=True,
                text=True,
            )
            logger.info(f"Applied ionice class: {limits['low_priority_ionice_class']}")
        except Exception as e:
            logger.warning(f"Could not apply ionice class: {e}")

        _low_priority_applied = True


def _iter_image_files(folder_path: Path, recursive: bool):
    """Yield image files lazily to avoid materializing huge libraries in memory."""
    iterator = folder_path.rglob("*") if recursive else folder_path.glob("*")
    for entry in iterator:
        if entry.is_file() and entry.suffix.lower() in IMAGE_EXTENSIONS:
            yield entry


def _add_tags_to_image(db: Session, image: Image, tag_names):
    for tag_name in tag_names:
        tag = db.query(Tag).filter_by(name=tag_name).first()
        if not tag:
            tag = Tag(name=tag_name)
            db.add(tag)
        image.tags.append(tag)


def is_schedule_enabled() -> bool:
    """Returns True if the processing schedule is enabled."""
    from .config import Config
    return Config.getboolean('schedule', 'enabled', fallback=False)


def _get_schedule_now():
    """Get the current time in the configured schedule timezone.
    Falls back to system local time if zoneinfo is not available or no timezone is configured."""
    from .config import Config
    tz_name = Config.get('schedule', 'timezone', fallback=None)
    if tz_name and HAS_ZONEINFO:
        try:
            tz = ZoneInfo(tz_name)
            return datetime.datetime.now(tz)
        except Exception:
            pass
    return datetime.datetime.now()


def is_within_schedule_window() -> bool:
    """Returns True if the current time is within the configured schedule window,
    or if the schedule is disabled (processing is always allowed).

    Uses the configured schedule timezone (defaulting to the system local time)
    so that the start/end hours match the user's clock."""
    from .config import Config
    if not is_schedule_enabled():
        return True
    start_hour = Config.getint('schedule', 'start_hour', fallback=1)
    end_hour = Config.getint('schedule', 'end_hour', fallback=5)
    now = _get_schedule_now()
    current_hour = now.hour
    if start_hour == end_hour:
        return True  # degenerate window — treat as always open
    if start_hour < end_hour:
        return start_hour <= current_hour < end_hour
    else:  # overnight window: e.g. 22–6
        return current_hour >= start_hour or current_hour < end_hour


_schedule_stop_event = threading.Event()


class ScheduleChecker:
    """Background thread that auto-triggers batch processing at window open
    and cancels at window close. Reads config each tick so live changes apply
    within 60 seconds without a restart."""

    def __init__(self, server: str, model: str, stop_event: threading.Event):
        self.server = server
        self.model = model
        self.stop_event = stop_event
        self._was_in_window = False
        self._triggered_this_window = False
        self._thread = threading.Thread(
            target=self._run, name="ScheduleChecker", daemon=True
        )

    def start(self):
        self._thread.start()
        logger.info("Schedule checker thread started")

    def stop(self):
        self.stop_event.set()
        self._thread.join(timeout=70)
        logger.info("Schedule checker thread stopped")

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self._tick()
            except Exception as e:
                logger.error(f"Schedule checker error: {e}")
            # Sleep in 1-second increments so shutdown is responsive
            for _ in range(60):
                if self.stop_event.is_set():
                    break
                self.stop_event.wait(timeout=1.0)

    def _tick(self):
        # Do nothing if schedule is disabled — don't auto-trigger or cancel anything
        if not is_schedule_enabled():
            self._was_in_window = False
            self._triggered_this_window = False
            return

        in_window = is_within_schedule_window()

        if in_window and not self._was_in_window:
            logger.info("Schedule: Entered processing window")
            self._triggered_this_window = False

        if not in_window:
            if self._was_in_window:
                logger.info("Schedule: Left processing window — signalling cancel for in-flight work")
                globals.app_state.cancel_requested = True
            # Per-image schedule checks in process_existing_images handle gating
            # automatically, so no bulk cancel is needed here.
            self._triggered_this_window = False

        if in_window and not self._triggered_this_window:
            self._triggered_this_window = True
            if globals.app_state.is_scanning:
                logger.info("Schedule: Window active, scan already running — skipping auto-trigger")
            else:
                logger.info("Schedule: Triggering scheduled batch processing")
                globals.app_state.cancel_requested = False
                self._trigger_batch_processing()

        self._was_in_window = in_window

    def _trigger_batch_processing(self):
        """Start a background thread that processes all active folders.

        Two passes:
        1. Scan filesystem for files not yet in the DB and process them with AI.
        2. Process images already in the DB but without a description (queued
           during off-hours by the file watcher).
        """
        def run_all_folders():
            _apply_low_priority_settings()
            from .models import SessionLocal, Folder as FolderModel, Image as ImageModel
            db = SessionLocal()
            try:
                folder_list = db.query(FolderModel).filter_by(active=True).all()
                folder_data = [(f.path, f.id) for f in folder_list]
            finally:
                db.close()

            globals.app_state.is_scanning = True
            globals.app_state.current_task = "Scheduled processing"
            globals.app_state.task_progress = 0
            globals.app_state.completed_tasks = 0
            total = 0
            processed_ids = []

            # Pass 1: files on disk not yet in the DB
            for folder_path, folder_id in folder_data:
                if globals.app_state.cancel_requested:
                    logger.info("Schedule: Cancelled mid-run")
                    break
                if is_schedule_enabled() and not is_within_schedule_window():
                    logger.info("Schedule: Left processing window — stopping folder scan")
                    globals.app_state.cancel_requested = True
                    break
                try:
                    db2 = SessionLocal()
                    try:
                        folder_obj = db2.query(FolderModel).get(folder_id)
                        if folder_obj:
                            count = process_existing_images(
                                folder_obj, self.server, self.model,
                                global_progress_offset=total, total_global_images=0
                            )
                            total += count
                            # Collect IDs of images processed in this run
                            processed_in_folder = db2.query(ImageModel).filter(
                                ImageModel.processing_status == 'completed',
                                ImageModel.path.startswith(folder_path)
                            ).all()
                            processed_ids.extend([img.id for img in processed_in_folder])
                    finally:
                        db2.close()
                except Exception as e:
                    logger.error(f"Schedule: Error processing folder {folder_path}: {e}")

            # Pass 2: images in DB queued as pending (detected outside window)
            if not globals.app_state.cancel_requested:
                db3 = SessionLocal()
                try:
                    pending = db3.query(ImageModel).filter(
                        (ImageModel.description == None) | (ImageModel.description == ''),
                        ImageModel.processing_status == 'pending'
                    ).all()
                    pending_paths = [img.path for img in pending]
                finally:
                    db3.close()

                if pending_paths:
                    logger.info(f"Schedule: Processing {len(pending_paths)} pending images")
                for image_path in pending_paths:
                    if globals.app_state.cancel_requested:
                        break
                    # Stop if we've left the schedule window
                    if is_schedule_enabled() and not is_within_schedule_window():
                        logger.info("Schedule: Left processing window — stopping pending image processing")
                        globals.app_state.cancel_requested = True
                        break
                    try:
                        tagger.process_image(
                            Path(image_path), self.server, self.model,
                            quiet=True, return_data=False
                        )
                        total += 1
                        # Track ID for potential rollback
                        try:
                            db4 = SessionLocal()
                            try:
                                img = db4.query(ImageModel).filter_by(path=image_path).first()
                                if img:
                                    processed_ids.append(img.id)
                            finally:
                                db4.close()
                        except Exception:
                            pass
                    except Exception as e:
                        logger.error(f"Schedule: Error processing pending image {image_path}: {e}")

            # Soft rollback if cancelled due to schedule
            schedule_cancelled = globals.app_state.cancel_requested and is_schedule_enabled() and not is_within_schedule_window()
            if schedule_cancelled and processed_ids:
                logger.info(f"Schedule: Soft-rolling back {len(processed_ids)} images to pending")
                _soft_rollback_images(processed_ids)

            globals.app_state.is_scanning = False
            globals.app_state.task_progress = 100
            globals.app_state.current_task = None
            logger.info(f"Schedule: Batch complete, {total} images processed")

        threading.Thread(target=run_all_folders, name="ScheduledBatch", daemon=True).start()


# Image file extensions we'll monitor for changes
IMAGE_EXTENSIONS = (
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.heic', '.heif', '.tif', '.tiff', '.webp', '.avif'
)

class ImageEventHandler(FileSystemEventHandler):
    """Handle file system events for images, process new or modified images"""
    
    def __init__(self, server: str, model: str):
        # Don't store db_session - create fresh session for each event
        self.server = server
        self.model = model
        
    def on_created(self, event):
        """Handle new file creation events"""
        if event.is_directory:
            return
            
        path = Path(event.src_path)
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            self._process_image(path)
            
    def on_modified(self, event):
        """Handle file modification events"""
        if event.is_directory:
            return
            
        path = Path(event.src_path)
        if path.suffix.lower() in IMAGE_EXTENSIONS:
            self._process_image(path)
    
    def _process_image(self, image_path: Path):
        """Process a single image file"""
        start_time = time.time()

        try:
            # Create fresh database session for this event
            db = SessionLocal()

            try:
                # Check if image already exists in database
                existing_image = db.query(Image).filter_by(path=str(image_path)).first()
                if existing_image:
                    logger.debug(f"Image already in database: {image_path}")
                    return

                # Outside schedule window: add image as pending so the scheduler
                # picks it up during the next processing window, but skip Ollama now.
                if not is_within_schedule_window():
                    logger.debug(f"Schedule: queuing image for later AI processing: {image_path}")
                    new_image = Image(path=str(image_path), processing_status='pending')
                    db.add(new_image)
                    db.commit()
                    db.refresh(new_image)
                    self._generate_thumbnail(image_path, new_image.id)
                    return

                # Process the image with AI (pass database session for deduplication)
                logger.info(f"Processing new image: {image_path}")
                result = tagger.process_image(
                    image_path, 
                    self.server, 
                    self.model, 
                    quiet=True,
                    return_data=True,
                    db_session=db  # Pass database session for deduplication
                )
                
                if result[0] and result[0] != "skipped" and result[0] is not False:
                    description, tags = result[0], result[1]
                    
                    # Add to database
                    new_image = Image(
                        path=str(image_path),
                        description=description
                    )
                    db.add(new_image)
                    
                    # Add tags
                    _add_tags_to_image(db, new_image, tags)
                    
                    db.commit()
                    logger.info(f"Processed image from watcher: {image_path.name}")
                    
                    # Generate thumbnail for the newly added image
                    try:
                        # Get the image ID that was just added
                        db.refresh(new_image)
                        thumbnail_path = get_thumbnail_path(new_image.id, 200)
                        
                        # Generate thumbnail using PIL
                        with PILImage.open(image_path) as img:
                            # Convert RGBA to RGB if needed
                            if img.mode in ('RGBA', 'LA'):
                                background = PILImage.new('RGB', img.size, (255, 255, 255))
                                if img.mode == 'RGBA':
                                    background.paste(img, mask=img.split()[-1])
                                else:
                                    background.paste(img, mask=img.split()[-1])
                                img = background
                            elif img.mode == 'P':
                                img = img.convert('RGB')
                            elif img.mode not in ('RGB', 'L'):
                                img = img.convert('RGB')
                            
                            # Calculate new dimensions while preserving aspect ratio
                            width, height = img.size
                            if width > height:
                                new_width = 200
                                new_height = int(height * (200 / width))
                            else:
                                new_height = 200
                                new_width = int(width * (200 / height))
                            
                            # Create thumbnail
                            img.thumbnail((new_width, new_height), PILImage.Resampling.LANCZOS)
                            
                            # Save thumbnail
                            img.save(thumbnail_path, "JPEG", quality=85, optimize=True)
                            logger.debug(f"Generated thumbnail: {thumbnail_path}")
                            
                    except Exception as e:
                        logger.error(f"Error generating thumbnail for {image_path}: {e}")
                    
                elif result[0] == "skipped":
                    skipped_image = Image(path=str(image_path), processing_status="skipped")
                    db.add(skipped_image)
                    db.commit()
                    logger.debug(f"Image skipped (already processed): {image_path}")
                else:
                    logger.error(f"Failed to process image: {image_path}")
                    
            except Exception as e:
                db.rollback()
                log_error_with_context(e, {"image_path": str(image_path), "event": "file_processing"})
                logger.error(f"Error processing image {image_path}: {e}")
            finally:
                db.close()
                
        except Exception as e:
            log_error_with_context(e, {"image_path": str(image_path), "event": "file_event"})
            logger.error(f"Fatal error in file event handler for {image_path}: {e}")
        
        finally:
            duration = time.time() - start_time
            log_performance_metric("file_event_processing", duration, success=True, 
                                 extra_data={"image_path": str(image_path)})

    def _generate_thumbnail(self, image_path: Path, image_id: int):
        """Generate and save a thumbnail for an image given its DB id."""
        try:
            thumbnail_path = get_thumbnail_path(image_id, 200)
            with PILImage.open(image_path) as img:
                if img.mode in ('RGBA', 'LA'):
                    background = PILImage.new('RGB', img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif img.mode == 'P':
                    img = img.convert('RGB')
                elif img.mode not in ('RGB', 'L'):
                    img = img.convert('RGB')
                width, height = img.size
                if width > height:
                    new_width = 200
                    new_height = int(height * (200 / width))
                else:
                    new_height = 200
                    new_width = int(width * (200 / height))
                img.thumbnail((new_width, new_height), PILImage.Resampling.LANCZOS)
                img.save(thumbnail_path, "JPEG", quality=85, optimize=True)
                logger.debug(f"Generated thumbnail: {thumbnail_path}")
        except Exception as e:
            logger.error(f"Error generating thumbnail for {image_path}: {e}")

    def generate_thumbnail(self, image_path: Path, image_id: int):
        """Generate a thumbnail for the processed image"""
        try:
            # Open the image
            with PILImage.open(image_path) as img:
                # Resize the image to fit within the thumbnail size
                img.thumbnail((200, 200))
                
                # Save the thumbnail
                thumbnail_path = get_thumbnail_path(image_id, 200)
                img.save(thumbnail_path)
                
                logger.info(f"Thumbnail generated and saved: {thumbnail_path}")
        except Exception as e:
            log_error_with_context(e, {"image_path": str(image_path), "event": "thumbnail_generation"})
            logger.error(f"Error generating thumbnail for {image_path}: {e}")

def _make_thumbnail(image_path: Path, image_id: int):
    """Generate and save a thumbnail for an image by its DB id."""
    try:
        thumbnail_path = get_thumbnail_path(image_id, 200)
        with PILImage.open(image_path) as img:
            if img.mode in ('RGBA', 'LA'):
                bg = PILImage.new('RGB', img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1])
                img = bg
            elif img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            w, h = img.size
            if w > h:
                img.thumbnail((200, int(h * 200 / w)), PILImage.Resampling.LANCZOS)
            else:
                img.thumbnail((int(w * 200 / h), 200), PILImage.Resampling.LANCZOS)
            img.save(thumbnail_path, "JPEG", quality=85, optimize=True)
    except Exception as e:
        logger.debug(f"Thumbnail generation skipped for {image_path}: {e}")


def scan_library_on_startup(server: str, model: str):
    """Triggered at startup when scan_on_startup is enabled.

    Scans all active folders for images not yet in the DB. Each image is
    processed with Ollama if within the schedule window, or added as pending
    if outside it — handled automatically by process_existing_images().

    Updates globals.app_state so the UI shows progress.
    """
    def _run():
        _apply_low_priority_settings()
        from .models import SessionLocal, Folder as FolderModel

        globals.app_state.is_scanning = True
        globals.app_state.current_task = "Startup scan: preparing..."
        globals.app_state.task_progress = 0
        globals.app_state.last_error = None

        try:
            db = SessionLocal()
            try:
                folders = db.query(FolderModel).filter_by(active=True).all()
                folder_data = [(f.path, f.id) for f in folders]
            finally:
                db.close()

            if not folder_data:
                logger.info("Startup scan: no active folders found")
                globals.app_state.is_scanning = False
                globals.app_state.current_task = None
                return

            logger.info(f"Startup scan: scanning {len(folder_data)} folder(s)")
            total = 0
            for idx, (folder_path, folder_id) in enumerate(folder_data):
                globals.app_state.current_task = f"Startup scan: processing folder {idx + 1}/{len(folder_data)}"
                try:
                    db2 = SessionLocal()
                    try:
                        folder_obj = db2.query(FolderModel).get(folder_id)
                        if folder_obj:
                            total += process_existing_images(folder_obj, server, model)
                    finally:
                        db2.close()
                except Exception as e:
                    logger.error(f"Startup scan: error scanning {folder_path}: {e}")
                    globals.app_state.last_error = str(e)
            logger.info(f"Startup scan complete: {total} images handled")
            globals.app_state.current_task = f"Startup scan complete — {total} images handled"
            globals.app_state.task_progress = 100
        except Exception as e:
            logger.error(f"Startup scan: fatal error: {e}")
            globals.app_state.last_error = str(e)
        finally:
            globals.app_state.is_scanning = False

    threading.Thread(target=_run, name="StartupScan", daemon=True).start()


def start_folder_watchers(db_session: Session, server: str, model: str) -> Optional[Observer]:
    """Start watching folders for new images"""
    try:
        # Create fresh database session
        db = SessionLocal()
        
        try:
            # Get all active folders
            active_folders = db.query(Folder).filter_by(active=True).all()
            
            if not active_folders:
                logger.info("No active folders to watch")
                return None
            
            # Create observer
            observer = Observer()
            
            # Add handlers for each folder
            for folder in active_folders:
                try:
                    folder_path = Path(folder.path)
                    if folder_path.exists() and folder_path.is_dir():
                        event_handler = ImageEventHandler(server, model)
                        observer.schedule(event_handler, str(folder_path), recursive=folder.recursive)
                        logger.info(f"Added watcher for folder: {folder.path} (recursive: {folder.recursive})")
                    else:
                        logger.warning(f"Folder does not exist or is not a directory: {folder.path}")
                except Exception as e:
                    logger.error(f"Error adding watcher for folder {folder.path}: {e}")
            
            # Start the observer
            observer.start()
            logger.info(f"Started watching {len(active_folders)} folders")
            return observer
            
        except Exception as e:
            log_error_with_context(e, {"event": "start_folder_watchers"})
            logger.error(f"Error starting folder watchers: {e}")
            return None
        finally:
            db.close()
            
    except Exception as e:
        log_error_with_context(e, {"event": "start_folder_watchers"})
        logger.error(f"Fatal error starting folder watchers: {e}")
        return None

def stop_folder_watchers(observer: Observer):
    """Stop folder watchers"""
    try:
        if observer and observer.is_alive():
            observer.stop()
            observer.join()
            logger.info("Folder watchers stopped")
    except Exception as e:
        log_error_with_context(e, {"event": "stop_folder_watchers"})
        logger.error(f"Error stopping folder watchers: {e}")

def process_existing_images(folder: Folder, server: str, model: str, global_progress_offset: int = 0, total_global_images: int = 0):
    """Scan folder lazily and process new images without memory spikes."""
    db = SessionLocal()
    discovered_count = 0
    processed_count = 0
    queued_count = 0

    try:
        _apply_low_priority_settings()
        limits = _get_processing_limits()
        inter_delay = limits["llm_inter_image_delay_seconds"]
        pause_every_n = limits["scan_pause_every_n_files"]
        pause_seconds = limits["scan_pause_seconds"]

        logger.info(f"Processing existing images in folder: {folder.path}")
        folder_path = Path(folder.path)
        if not folder_path.exists():
            logger.warning(f"Folder does not exist: {folder.path}")
            return 0

        if hasattr(globals, "app_state"):
            globals.app_state.current_task = f"Scanning folder {folder.path}"
            globals.app_state.completed_tasks = global_progress_offset
            if total_global_images > 0:
                globals.app_state.task_total = total_global_images

        for file_path in _iter_image_files(folder_path, folder.recursive):
            if globals.app_state.cancel_requested:
                logger.info("process_existing_images: cancel requested — stopping loop")
                break

            discovered_count += 1
            if pause_every_n > 0 and discovered_count % pause_every_n == 0 and pause_seconds > 0:
                time.sleep(pause_seconds)

            existing = db.query(Image.id).filter_by(path=str(file_path)).first()
            if existing:
                continue

            if hasattr(globals, "app_state"):
                completed = global_progress_offset + processed_count + queued_count
                task_total = total_global_images if total_global_images > 0 else max(discovered_count, completed + 1)
                globals.app_state.task_total = task_total
                globals.app_state.completed_tasks = completed
                globals.app_state.task_progress = min((completed / task_total) * 100, 99.0)
                globals.app_state.current_task = f"Processing {file_path.name}"

            if not is_within_schedule_window():
                queued = Image(path=str(file_path), processing_status="pending")
                db.add(queued)
                db.commit()
                db.refresh(queued)
                _make_thumbnail(file_path, queued.id)
                queued_count += 1
                continue

            called_llm = False
            try:
                called_llm = True
                result = tagger.process_image(
                    file_path,
                    server,
                    model,
                    quiet=True,
                    return_data=True,
                    db_session=db,
                )

                if result[0] and result[0] != "skipped" and result[0] is not False:
                    description, tags = result[0], result[1]
                    new_image = Image(
                        path=str(file_path),
                        description=description,
                        processing_status="completed",
                        processing_error=None,
                    )
                    db.add(new_image)
                    _add_tags_to_image(db, new_image, tags)
                    db.commit()
                    db.refresh(new_image)
                    _make_thumbnail(file_path, new_image.id)
                    processed_count += 1
                elif result[0] == "skipped":
                    skipped = Image(path=str(file_path), processing_status="skipped")
                    db.add(skipped)
                    db.commit()
                else:
                    pending = Image(
                        path=str(file_path),
                        processing_status="pending",
                        processing_error="Initial scan attempt failed; kept pending for retry",
                    )
                    db.add(pending)
                    db.commit()
            except Exception as e:
                logger.error(f"Error processing image {file_path}: {e}")
                db.rollback()
                try:
                    retry_item = Image(
                        path=str(file_path),
                        processing_status="pending",
                        processing_error=f"Initial scan error: {e}",
                    )
                    db.add(retry_item)
                    db.commit()
                except Exception:
                    db.rollback()
            finally:
                if called_llm and inter_delay > 0 and not globals.app_state.cancel_requested:
                    time.sleep(inter_delay)

        total_handled = processed_count + queued_count
        if hasattr(globals, "app_state"):
            globals.app_state.completed_tasks = global_progress_offset + total_handled
            if globals.app_state.task_total > 0:
                globals.app_state.task_progress = min((globals.app_state.completed_tasks / globals.app_state.task_total) * 100, 100.0)

        if queued_count > 0:
            logger.info(f"Queued {queued_count} images for later AI processing in {folder.path}")
        logger.info(f"Completed {processed_count} images AI-processed in {folder.path}")
        return processed_count

    except Exception as e:
        logger.error(f"Fatal error in process_existing_images for folder {folder.path}: {e}")
        db.rollback()
        return 0
    finally:
        db.close()

def _soft_rollback_images(image_ids: list):
    """Reset DB records for the given image IDs back to 'pending' status
    and clear description + tag associations, so they will be reprocessed
    during the next schedule window. EXIF metadata in files is left as-is."""
    from .models import SessionLocal, Image as ImageModel, Tag, image_tags
    db = SessionLocal()
    try:
        images = db.query(ImageModel).filter(ImageModel.id.in_(image_ids)).all()
        for img in images:
            img.processing_status = 'pending'
            img.description = None
            img.processing_error = None
            img.tags.clear()
        db.commit()
        logger.info(f"Soft-rolled back {len(images)} images to pending")
    except Exception as e:
        logger.error(f"Error during soft rollback: {e}")
        db.rollback()
    finally:
        db.close()


def process_images_with_ai(images, server: str, model: str, progress_tracker=None):
    """Process a list of images with AI using a bounded worker pool, respecting pause/cancel and schedule flags."""
    _apply_low_priority_settings()
    limits = _get_processing_limits()
    inter_delay = limits["llm_inter_image_delay_seconds"]
    max_workers = limits["max_workers"]

    image_ids = []
    for item in images:
        if isinstance(item, int):
            image_ids.append(item)
        elif hasattr(item, "id"):
            image_ids.append(int(item.id))

    image_ids = list(dict.fromkeys(image_ids))
    total_images = len(image_ids)
    processed_count = 0
    error_count = 0
    stopped_by_schedule = False

    if not is_within_schedule_window():
        logger.info("Schedule: Skipping AI processing — outside allowed time window")
        globals.app_state.is_scanning = False
        if progress_tracker:
            progress_tracker.update({
                "current_task": "Skipped AI processing — outside schedule window",
                "progress": 0,
                "completed_tasks": 0,
                "task_total": total_images,
            })
            progress_tracker.is_scanning = False
        return

    try:
        cfg = tagger.load_config()
        max_retries = int(cfg.get("max_retries", 5))
        base_retry_delay = int(cfg.get("retry_base_delay_seconds", 5))
        max_retry_delay = int(cfg.get("retry_max_delay_seconds", 60))
    except Exception:
        max_retries = 5
        base_retry_delay = 5
        max_retry_delay = 60

    logger.info(f"Starting AI processing for {total_images} images with {max_workers} workers")

    def worker(image_id: int) -> bool:
        nonlocal stopped_by_schedule
        db = SessionLocal()
        llm_called = False
        try:
            image_rec = db.query(Image).filter(Image.id == image_id).first()
            if not image_rec:
                return True

            if globals.app_state.cancel_requested:
                image_rec.processing_status = "pending"
                db.commit()
                return False

            while globals.app_state.paused and not globals.app_state.cancel_requested:
                time.sleep(0.5)

            if is_schedule_enabled() and not is_within_schedule_window():
                stopped_by_schedule = True
                image_rec.processing_status = "pending"
                db.commit()
                return False

            if not Path(image_rec.path).exists():
                logger.warning(f"Skipping {image_rec.path} - file not found")
                image_rec.processing_status = "failed"
                image_rec.processing_error = "File not found"
                db.commit()
                return False

            for attempt in range(max_retries):
                if globals.app_state.cancel_requested:
                    image_rec.processing_status = "pending"
                    db.commit()
                    return False
                if is_schedule_enabled() and not is_within_schedule_window():
                    stopped_by_schedule = True
                    image_rec.processing_status = "pending"
                    db.commit()
                    return False

                try:
                    llm_called = True
                    result = tagger.process_image(
                        image_rec.path,
                        server,
                        model,
                        quiet=True,
                        return_data=True,
                        db_session=db,
                    )
                    if result[0] and result[0] != "skipped" and result[0] is not False:
                        description, tags = result[0], result[1]
                        image_rec.description = description if description else None
                        image_rec.processing_status = "completed"
                        image_rec.processing_error = None
                        image_rec.tags.clear()
                        _add_tags_to_image(db, image_rec, tags)
                        db.commit()
                        return True
                    if result[0] == "skipped":
                        image_rec.processing_status = "skipped"
                        db.commit()
                        return True

                    if attempt == max_retries - 1:
                        image_rec.processing_status = "failed"
                        image_rec.processing_error = "Failed after max retries"
                        db.commit()
                        return False

                    sleep_s = min(max_retry_delay, base_retry_delay * (2 ** attempt))
                    sleep_s *= (0.8 + 0.4 * random.random())
                    time.sleep(sleep_s)
                except Exception as e:
                    logger.error(f"Error processing {image_rec.path} (attempt {attempt + 1}): {e}")
                    if attempt == max_retries - 1:
                        image_rec.processing_status = "failed"
                        image_rec.processing_error = str(e)
                        db.commit()
                        return False
                    sleep_s = min(max_retry_delay, base_retry_delay * (2 ** attempt))
                    sleep_s *= (0.8 + 0.4 * random.random())
                    time.sleep(sleep_s)
            return False
        finally:
            if llm_called and inter_delay > 0 and not globals.app_state.cancel_requested:
                time.sleep(inter_delay)
            db.close()

    submitted_ids = []
    futures = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, image_id in enumerate(image_ids):
            if globals.app_state.cancel_requested:
                break
            if is_schedule_enabled() and not is_within_schedule_window():
                stopped_by_schedule = True
                logger.info("Schedule: Stopping AI submission — left allowed time window")
                break
            futures.append(executor.submit(worker, image_id))
            submitted_ids.append(image_id)
            if progress_tracker:
                progress_tracker.update({
                    "current_task": f"Queued image {idx + 1} of {total_images}",
                    "task_total": total_images,
                })

        if globals.app_state.cancel_requested or stopped_by_schedule:
            for fut in futures:
                if not fut.done():
                    fut.cancel()

        for fut in as_completed(futures):
            ok = False
            try:
                ok = bool(fut.result())
            except Exception as e:
                logger.error(f"Worker error: {e}")
                ok = False
            if ok:
                processed_count += 1
            else:
                error_count += 1
            if progress_tracker:
                done = processed_count + error_count
                progress_tracker.update({
                    "current_task": f"Processed {done} of {total_images}",
                    "completed_tasks": done,
                    "progress": (done / total_images) * 100 if total_images else 100.0,
                    "task_total": total_images,
                })

    # Roll back only when we left the schedule window (not on user cancel).
    if stopped_by_schedule and submitted_ids:
        logger.info(f"Schedule cancellation: soft rollback of {len(submitted_ids)} images")
        _soft_rollback_images(submitted_ids)

    if progress_tracker:
        progress_tracker.update({
            "current_task": f"AI processing completed - {processed_count} processed, {error_count} errors",
            "progress": 100.0,
            "completed_tasks": total_images,
            "task_total": total_images,
            "is_scanning": False,
        })
    globals.app_state.is_scanning = False

def scan_folders_for_images(folders, progress_tracker=None):
    """Scan folders for new images and add them to database"""
    # Create a fresh database session for this background task
    db = SessionLocal()
    
    try:
        total_folders = len(folders)
        new_images_count = 0
        
        # Update initial progress
        if progress_tracker:
            progress_tracker.update({
                "current_task": f"Starting scan of {total_folders} folders",
                "progress": 0.0,
                "completed_tasks": 0,
                "task_total": total_folders
            })
        
        for idx, folder in enumerate(folders):
            try:
                if progress_tracker:
                    progress_tracker.update({
                        "current_task": f"Scanning folder {idx + 1} of {total_folders}: {os.path.basename(folder.path)}",
                        "progress": (idx / total_folders) * 100,
                        "completed_tasks": idx,
                        "task_total": total_folders
                    })
                
                folder_path = Path(folder.path)
                if not folder_path.exists():
                    continue
                
                # Find image files in the folder
                if folder.recursive:
                    image_files = []
                    for ext in IMAGE_EXTENSIONS:
                        image_files.extend(folder_path.rglob(f"*{ext}"))
                        image_files.extend(folder_path.rglob(f"*{ext.upper()}"))
                else:
                    image_files = []
                    for ext in IMAGE_EXTENSIONS:
                        image_files.extend(folder_path.glob(f"*{ext}"))
                        image_files.extend(folder_path.glob(f"*{ext.upper()}"))
                
                # Add new images to database
                for image_file in image_files:
                    try:
                        existing = db.query(Image).filter_by(path=str(image_file)).first()
                        if not existing:
                            new_image = Image(path=str(image_file))
                            db.add(new_image)
                            new_images_count += 1
                    except Exception as e:
                        logger.error(f"Error adding image {image_file} to database: {e}")
                        continue
                
                db.commit()
                logger.info(f"Scanned folder {folder.path}: found {len(image_files)} images, {new_images_count} new")
                
            except Exception as e:
                logger.error(f"Error scanning folder {folder.path}: {e}")
                db.rollback()
                continue
        
        logger.info(f"Folder scanning completed: {new_images_count} new images found")
        return new_images_count
        
    except Exception as e:
        logger.error(f"Fatal error in scan_folders_for_images: {str(e)}")
        db.rollback()
        return 0
    finally:
        db.close()
