"""Contributing a book back to Open Library's public catalog.

Opt-in, one book at a time, always behind an explicit confirmation in the
UI — this posts data to a shared, third-party resource under the user's own
Open Library account, so it must never happen silently or in bulk.

Deliberately hand-rolled with plain `requests` against the same endpoints
Open Library's own "Add a book" web form uses, rather than depending on the
official `openlibrary-client` package: its latest PyPI release is from 2020
with hard-pinned, now years-stale dependencies that conflict with this
project's own (e.g. requests==2.31.0 vs our requests==2.32.3), and its
current GitHub source pulls in the much heavier `internetarchive` SDK for
what amounts to two POST requests and one lookup.
"""

import mimetypes
import re
from pathlib import Path

import requests
from flask import current_app

from app.services.settings_service import get_setting

BASE_URL = "https://openlibrary.org"
TIMEOUT = 10  # seconds — a deliberate, one-off action, not a hot path


def _http_headers():
    """A default `requests` User-Agent is silently rejected by some sites on
    sensitive endpoints (login, form submissions) even though it's fine on
    plain read APIs — mirrors isbn_service._http_headers()."""
    contact = (current_app.config.get("CONTACT_INFO") or "").strip()
    agent = "BIBLIAK/1.0 (application locale de gestion de collection)"
    if contact:
        agent += f" - {contact}"
    return {"User-Agent": agent}


def is_configured():
    """Whether an Open Library account is set up at all (env vars)."""
    return bool(current_app.config.get("OPENLIBRARY_ACCESS_KEY")) and bool(
        current_app.config.get("OPENLIBRARY_SECRET_KEY")
    )


def is_enabled():
    """Whether the feature is both configured AND explicitly turned on in
    Administration > Settings — the extra toggle is deliberate: setting an
    env var once shouldn't be the only thing standing between the app and
    writing to a public catalog under the user's identity."""
    return is_configured() and bool(get_setting("openlibrary_contribution_enabled", False))


def _login(session):
    response = session.post(
        f"{BASE_URL}/account/login",
        json={
            "access": current_app.config.get("OPENLIBRARY_ACCESS_KEY"),
            "secret": current_app.config.get("OPENLIBRARY_SECRET_KEY"),
        },
        headers=_http_headers(),
        timeout=TIMEOUT,
    )
    if response.ok and session.cookies:
        return True
    current_app.logger.warning(
        "Open Library login failed: HTTP %s, body: %.300s", response.status_code, response.text
    )
    return False


def _find_author_key(session, name):
    """Looks up an existing Open Library author with this exact name, to
    avoid creating a duplicate Author record for every contribution. Returns
    an OLID, or None if no exact match was found (a new author record is
    then created inline by the /books/add form itself)."""
    try:
        response = session.get(
            f"{BASE_URL}/authors/_autocomplete",
            params={"q": name, "limit": 5},
            headers=_http_headers(),
            timeout=TIMEOUT,
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    target = name.lower().strip()
    for author in response.json():
        if author.get("name", "").lower().strip() == target:
            return author["key"].split("/")[-1]
    return None


def _add_cover(session, olid, cover_path):
    """Uploads a locally-stored cover image to the given edition, by
    sending its bytes directly rather than a URL — the app usually isn't
    publicly reachable (self-signed HTTPS, local network), so Open Library
    could not fetch a cover from it even if we gave it one. Best-effort:
    the edition itself is already created either way."""
    try:
        cover_bytes = cover_path.read_bytes()
    except OSError:
        return False

    mime_type = mimetypes.guess_type(cover_path.name)[0] or "image/jpeg"
    try:
        response = session.post(
            f"{BASE_URL}/books/{olid}/-/add-cover",
            files={
                "file": (cover_path.name, cover_bytes, mime_type),
                "url": (None, "https://"),
                "upload": (None, "Submit"),
            },
            headers=_http_headers(),
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return False
    return response.ok


# Open Library edition IDs always look like "OL" + digits + "M" (works are
# "...W", authors "...A"). Matching this precisely — instead of any
# alphanumeric path segment — matters: /books/add itself matches a loose
# "/books/(\w+)" pattern (the literal word "add"), so a response that didn't
# actually redirect to a new edition was being reported as a success with
# a bogus "olid" of "add", silently breaking both the "View" link and the
# cover upload (posted to the nonsensical /books/add/-/add-cover).
_OLID_PATTERN = re.compile(r"(OL\d+M)")


def _extract_olid(response):
    match = _OLID_PATTERN.search(response.url)
    if match:
        return match.group(1)
    # Some outcomes (e.g. a first-time-contributor interstitial) don't
    # redirect to the new edition at all, but still mention it in the page.
    match = _OLID_PATTERN.search(response.text)
    return match.group(1) if match else None


def _primary_identifier(isbn):
    digits = (isbn or "").replace("-", "").replace(" ", "")
    if len(digits) == 13:
        return "isbn_13", digits
    if len(digits) == 10:
        return "isbn_10", digits
    return None, None


def contribute_book(book):
    """Submits `book` (an app.models.Book) to Open Library as a new edition.

    Returns a (status, olid, cover_uploaded) tuple. cover_uploaded is only
    meaningful when status is "ok": True if a cover was uploaded, False if
    the book has one but the upload failed (the edition is still created
    either way), None if the book has no cover to upload.

    status values:
    - "ok": created successfully, olid is the new edition's ID
    - "not_configured": no Open Library account keys are set
    - "disabled": keys are set but the admin toggle is off
    - "missing_author": Open Library requires a full name (first and last)
      for at least one author, and the book has none usable
    - "missing_isbn": Open Library requires an ISBN-10/13
    - "auth_failed": the configured account credentials were rejected
    - "network_error": could not reach Open Library
    - "rejected": Open Library responded but didn't redirect to a newly
      created edition (unexpected server-side outcome)
    """
    if not is_configured():
        return "not_configured", None, None
    if not is_enabled():
        return "disabled", None, None

    author_name = next((a.full_name for a in book.authors if len(a.full_name.split()) > 1), None)
    if not author_name:
        return "missing_author", None, None

    id_name, id_value = _primary_identifier(book.isbn)
    if not id_name:
        return "missing_isbn", None, None

    session = requests.Session()
    try:
        if not _login(session):
            return "auth_failed", None, None

        author_olid = _find_author_key(session, author_name)
        author_key = f"/authors/{author_olid}" if author_olid else "__new__"

        response = session.post(
            f"{BASE_URL}/books/add",
            data={
                "title": book.title,
                "author_name": author_name,
                "author_key": author_key,
                "publish_date": book.publication_date or "",
                "publisher": book.publisher.name if book.publisher else "",
                "id_name": id_name,
                "id_value": id_value,
                "_save": "",
            },
            headers=_http_headers(),
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return "network_error", None, None

    olid = _extract_olid(response)
    if not olid:
        current_app.logger.warning(
            "Open Library did not return an edition ID: final URL %s, HTTP %s, body: %.300s",
            response.url, response.status_code, response.text,
        )
        return "rejected", None, None

    cover_uploaded = None
    if book.cover_image:
        cover_path = Path(current_app.config["COVERS_DIR"]) / book.cover_image
        cover_uploaded = _add_cover(session, olid, cover_path)

    return "ok", olid, cover_uploaded
