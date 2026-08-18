"""Downloading, uploading and resizing book covers.

All images are converted to JPEG and resized before being stored in
app/static/covers, under a generated (uuid) filename to avoid any collision.
"""

import uuid
from io import BytesIO
from pathlib import Path

import requests
from flask import current_app
from PIL import Image, ImageOps

from app.services.i18n_service import t

TIMEOUT = 8  # seconds

# Many sites block (403, replacement page, redirect) requests whose
# User-Agent header doesn't look like a browser — without this, an image
# that displays perfectly fine in the browser preview (which sends a real
# User-Agent) can silently fail to download server-side, which sent none.
DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def _covers_dir():
    return Path(current_app.config["COVERS_DIR"])


def _unique_filename():
    return f"{uuid.uuid4().hex}.jpg"


def _resize_and_save(image):
    # Smartphone photos store the actual orientation in EXIF metadata rather
    # than rotating the pixels themselves; Image.open() never applies it
    # automatically, hence covers ending up flipped 90°/180° once saved if
    # this isn't done here.
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    max_width, max_height = current_app.config["COVER_MAX_SIZE"]
    image.thumbnail((max_width, max_height))

    filename = _unique_filename()
    path = _covers_dir() / filename
    image.save(path, "JPEG", quality=88)
    return filename


def download_cover(url):
    """Downloads an image from a remote URL (e.g. Open Library / Google
    Books, or a manually pasted link). Returns (filename, error): exactly
    one of the two is always None."""
    if not url:
        return None, None

    try:
        response = requests.get(url, headers=DOWNLOAD_HEADERS, timeout=TIMEOUT)
        response.raise_for_status()
    except requests.RequestException as e:
        return None, t("Le lien n'a pas pu être téléchargé ({error}).", error=e.__class__.__name__)

    content_type = response.headers.get("Content-Type", "")
    if content_type.startswith("text/html"):
        return None, t("Ce lien pointe vers une page web, pas directement vers un fichier image.")

    try:
        image = Image.open(BytesIO(response.content))
        image.load()  # force full decoding here to detect an unsupported format
    except Exception:
        return None, t("Le format de cette image n'a pas pu être lu (fichier corrompu ou format non supporté).")

    return _resize_and_save(image), None


def save_upload(werkzeug_file):
    """Saves an image sent via form (regular upload or a photo taken on mobile)."""
    try:
        image = Image.open(werkzeug_file.stream)
    except Exception:
        return None

    return _resize_and_save(image)


def delete_cover(filename):
    if not filename:
        return
    path = _covers_dir() / filename
    if path.exists():
        path.unlink()
