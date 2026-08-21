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

import re

import requests
from flask import current_app

from app.services.settings_service import get_setting

BASE_URL = "https://openlibrary.org"
TIMEOUT = 10  # seconds — a deliberate, one-off action, not a hot path


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
        timeout=TIMEOUT,
    )
    return response.ok and bool(session.cookies)


def _find_author_key(session, name):
    """Looks up an existing Open Library author with this exact name, to
    avoid creating a duplicate Author record for every contribution. Returns
    an OLID, or None if no exact match was found (a new author record is
    then created inline by the /books/add form itself)."""
    try:
        response = session.get(
            f"{BASE_URL}/authors/_autocomplete", params={"q": name, "limit": 5}, timeout=TIMEOUT
        )
        response.raise_for_status()
    except requests.RequestException:
        return None

    target = name.lower().strip()
    for author in response.json():
        if author.get("name", "").lower().strip() == target:
            return author["key"].split("/")[-1]
    return None


def _extract_olid(url):
    match = re.search(r"/books/([0-9a-zA-Z]+)", url)
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

    Returns a (status, value) tuple:
    - ("ok", olid): created successfully, olid is the new edition's ID
    - ("not_configured", None): no Open Library account keys are set
    - ("disabled", None): keys are set but the admin toggle is off
    - ("missing_author", None): Open Library requires a full name (first
      and last) for at least one author, and the book has none usable
    - ("missing_isbn", None): Open Library requires an ISBN-10/13
    - ("auth_failed", None): the configured account credentials were rejected
    - ("network_error", None): could not reach Open Library
    - ("rejected", None): Open Library responded but didn't redirect to a
      newly created edition (unexpected server-side outcome)
    """
    if not is_configured():
        return "not_configured", None
    if not is_enabled():
        return "disabled", None

    author_name = next((a.full_name for a in book.authors if len(a.full_name.split()) > 1), None)
    if not author_name:
        return "missing_author", None

    id_name, id_value = _primary_identifier(book.isbn)
    if not id_name:
        return "missing_isbn", None

    session = requests.Session()
    try:
        if not _login(session):
            return "auth_failed", None

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
            timeout=TIMEOUT,
        )
    except requests.RequestException:
        return "network_error", None

    olid = _extract_olid(response.url)
    if not olid:
        return "rejected", None
    return "ok", olid
