import base64
import json
import logging
import re
import subprocess
import tempfile
import time
from pathlib import Path

import requests
from PIL import Image

from .core import (
    clean_description,
    extract_tags_from_description,
    is_image_already_processed_in_db,
    is_file_processed,
    load_config,
    mark_file_as_processed,
    normalize_tags,
    update_image_processing_status,
)


def _write_xmp_sidecar(video_path: Path, description: str, tags: list) -> bool:
    import xml.sax.saxutils as saxutils
    sidecar = video_path.with_suffix(".xmp")
    subjects = "".join(f"      <rdf:li>{saxutils.escape(t)}</rdf:li>\n" for t in tags)
    xmp = (
        "<?xpacket begin='\xef\xbb\xbf' id='W5M0MpCehiHzreSzNTczkc9d'?>\n"
        "<x:xmpmeta xmlns:x='adobe:ns:meta/'>\n"
        "  <rdf:RDF xmlns:rdf='http://www.w3.org/1999/02/22-rdf-syntax-ns#'>\n"
        "    <rdf:Description rdf:about=''\n"
        "      xmlns:dc='http://purl.org/dc/elements/1.1/'>\n"
        "      <dc:description><rdf:Alt>\n"
        f"        <rdf:li xml:lang='x-default'>{saxutils.escape(description)}</rdf:li>\n"
        "      </rdf:Alt></dc:description>\n"
        "      <dc:subject><rdf:Bag>\n"
        f"{subjects}"
        "      </rdf:Bag></dc:subject>\n"
        "    </rdf:Description>\n"
        "  </rdf:RDF>\n"
        "</x:xmpmeta>\n"
        "<?xpacket end='w'?>\n"
    )
    try:
        sidecar.write_text(xmp, encoding="utf-8")
        logging.info(f"✅ Wrote XMP sidecar: {sidecar}")
        return True
    except Exception as e:
        logging.warning(f"⚠️ XMP sidecar write failed for {video_path}: {e}")
        return False
from ..config import Config


def get_video_duration(path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, timeout=30
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def extract_frame_montage(path: Path, tmp_dir: str, n_frames: int = 9) -> Path:
    duration = get_video_duration(path)
    timestamps = [duration * i / (n_frames + 1) for i in range(1, n_frames + 1)]

    frames = []
    for i, ts in enumerate(timestamps):
        frame_path = Path(tmp_dir) / f"frame_{i:02d}.jpg"
        subprocess.run(
            ["ffmpeg", "-ss", str(ts), "-i", str(path),
             "-frames:v", "1", "-q:v", "2", str(frame_path), "-y"],
            capture_output=True, timeout=30
        )
        if frame_path.exists():
            frames.append(frame_path)

    if not frames:
        raise RuntimeError(f"No frames extracted from {path}")

    # Build 3-column grid
    cols = 3
    rows = -(-len(frames) // cols)  # ceil div
    thumb_w, thumb_h = 512, 288
    grid = Image.new("RGB", (thumb_w * cols, thumb_h * rows), (0, 0, 0))
    for idx, fp in enumerate(frames):
        with Image.open(fp) as img:
            img = img.convert("RGB")
            img.thumbnail((thumb_w, thumb_h))
            x = (idx % cols) * thumb_w + (thumb_w - img.width) // 2
            y = (idx // cols) * thumb_h + (thumb_h - img.height) // 2
            grid.paste(img, (x, y))

    montage_path = Path(tmp_dir) / "montage.jpg"
    grid.save(montage_path, "JPEG", quality=85)
    return montage_path


def process_video(path, server, model, return_data=False, quiet=False, db_session=None):
    path = Path(path)
    cfg = load_config()
    max_retries = int(cfg.get("max_retries", 5))
    temperature = float(cfg.get("temperature", 0.7))
    max_output_tokens = int(cfg.get("max_output_tokens", 4096))
    api_type = Config.get("ollama", "api_type", fallback="openai")

    if is_image_already_processed_in_db(path, db_session):
        if not quiet:
            logging.info(f"🔄 Skipping already processed video (database): {path}")
        return ("skipped", None) if return_data else "skipped"

    if is_file_processed(path):
        if not quiet:
            logging.info(f"🔄 Skipping already processed video (tracking): {path}")
        return ("skipped", None) if return_data else "skipped"

    update_image_processing_status(path, "processing", db_session=db_session)

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            montage_path = extract_frame_montage(path, tmp_dir)
            with Image.open(montage_path) as img:
                import io
                buf = io.BytesIO()
                img.save(buf, "JPEG", quality=85)
                base64_image = base64.b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        logging.error(f"❌ Frame extraction failed for {path}: {e}")
        update_image_processing_status(path, "failed", str(e), db_session=db_session)
        return (False, None) if return_data else False

    prompt_text = (
        "You are analyzing frames sampled from a video. "
        "Describe what the video shows based on these frames. "
        "Return ONLY a JSON object with two keys: "
        "'description' (a detailed string describing the video contents) and "
        "'tags' (an array of relevant keyword strings). "
        "Example: {\"description\": \"A dog running on a beach\", \"tags\": [\"dog\", \"beach\", \"running\"]}. "
        "Return only the JSON object, no markdown, no code fences, no extra text."
    )

    for attempt in range(max_retries):
        try:
            if api_type == "openai":
                url = f"{server}/v1/chat/completions"
                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": prompt_text},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]}],
                    "temperature": temperature,
                    "max_tokens": max_output_tokens,
                }
                response = requests.post(url, json=payload, timeout=300)
                if response.status_code != 200:
                    logging.error(f"❌ Video API error (HTTP {response.status_code}) attempt {attempt+1}/{max_retries}")
                    if attempt == max_retries - 1:
                        update_image_processing_status(path, "failed", f"HTTP {response.status_code}", db_session=db_session)
                    time.sleep(3)
                    continue
                content = (response.json().get("choices", [{}])[0]
                           .get("message", {}).get("content", "")).strip()
            else:
                url = f"{server}/api/generate"
                payload = {
                    "model": model,
                    "prompt": prompt_text,
                    "images": [base64_image],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": temperature, "num_predict": max_output_tokens},
                }
                response = requests.post(url, json=payload, timeout=300)
                content = response.json().get("response", "").strip()

            if not content:
                raise ValueError("Empty response")

            cleaned = content.strip()
            if cleaned.startswith("```"):
                cleaned = "\n".join(l for l in cleaned.split("\n") if not l.strip().startswith("```")).strip()

            description, tags = None, None
            try:
                inner = json.loads(cleaned)
                if isinstance(inner, dict):
                    description = (inner.get("description") or "").strip() or None
                    tags = normalize_tags(inner.get("tags") or [])
            except Exception:
                m = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', cleaned)
                if m:
                    description = m.group(1).strip()
                mt = re.search(r'"tags"\s*:\s*\[(.*?)\]', cleaned, re.DOTALL)
                if mt:
                    tags = normalize_tags([t.strip().strip('"\'') for t in mt.group(1).split(",") if t.strip().strip('"\'')])
                if not description:
                    description = content

            if not description:
                raise ValueError("Empty description")
            if not tags:
                tags = normalize_tags(extract_tags_from_description(description))
            description = clean_description(description)

            if not quiet:
                logging.info(f"✅ Generated description for video {path}")
                logging.info(f"📝 {description[:100]}…")
                logging.info(f"🏷️ {', '.join(tags)}")

            _write_xmp_sidecar(path, description, tags)
            mark_file_as_processed(path)
            update_image_processing_status(path, "completed", db_session=db_session)
            return (description, tags) if return_data else True

        except Exception as e:
            logging.error(f"❌ Video processing error for {path} (attempt {attempt+1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                update_image_processing_status(path, "failed", str(e), db_session=db_session)
            time.sleep(3)

    return (False, None) if return_data else False
