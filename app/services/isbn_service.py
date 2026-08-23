"""Retrieval of a book's metadata from its ISBN/EAN, via Open Library.

A network failure (timeout, connection refused...) is retried a few times
before giving up: scanning happens over flaky mobile connections, where a
failed attempt often just means "try again in a second". Each attempt is a
separate HTTP request (driven by the client via app/routes/scan.py), so the
user sees live feedback between attempts instead of the page hanging for
tens of seconds.

Comics and manga are often poorly referenced there: the result must
therefore always be treated as a pre-fill, never as an absolute truth.
"""

import requests
from flask import current_app

TIMEOUT = 6  # seconds, per HTTP call

# How many times a search is attempted (first try + retries) after
# transient network failures before giving up. The only place this needs
# editing to change the policy.
ISBN_SEARCH_MAX_ATTEMPTS = 5

# Delay the browser waits before automatically retrying, in milliseconds
# (used directly in an htmx "delay:" trigger). Short on purpose: the point is
# quick feedback, not a long backoff.
ISBN_SEARCH_RETRY_DELAY_MS = 1500


def _clean_isbn(isbn):
    return isbn.strip().replace("-", "").replace(" ", "")


def _http_headers():
    """Builds the User-Agent header sent with every call.

    Open Library explicitly recommends identifying yourself (app name +
    contact): identified requests benefit from a 3x more generous rate limit
    (3 req/s instead of 1 req/s). The contact is configured via the
    CONTACT_INFO environment variable (see .env).
    """
    contact = (current_app.config.get("CONTACT_INFO") or "").strip()
    agent = "BIBLIAK/1.0 (application locale de gestion de collection)"
    if contact:
        agent += f" - {contact}"
    return {"User-Agent": agent}


def _from_open_library(isbn):
    url = "https://openlibrary.org/api/books"
    params = {"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"}
    response = requests.get(url, params=params, headers=_http_headers(), timeout=TIMEOUT)
    response.raise_for_status()
    data = response.json().get(f"ISBN:{isbn}")
    if not data:
        return None

    authors = [a.get("name") for a in data.get("authors", []) if a.get("name")]
    publishers = [p.get("name") for p in data.get("publishers", []) if p.get("name")]
    cover = data.get("cover", {}) or {}

    return {
        "title": data.get("title"),
        "authors": authors,
        "publisher": publishers[0] if publishers else None,
        "publication_date": data.get("publish_date"),
        "summary": data.get("subtitle"),
        "image_url": cover.get("large") or cover.get("medium"),
        "source": "Open Library",
    }


def attempt_search(isbn):
    """Tries Open Library, once.

    Returns a (status, result) tuple:
    - ("ok", result_dict): Open Library knows this ISBN
    - ("not_found", None): Open Library responded but doesn't know this ISBN
    - ("network_error", None): timeout, connection error, HTTP error...
      (transient — worth retrying, see ISBN_SEARCH_MAX_ATTEMPTS)
    """
    normalized_isbn = _clean_isbn(isbn)
    try:
        result = _from_open_library(normalized_isbn)
    except requests.RequestException:
        return "network_error", None

    if result and result.get("title"):
        result["isbn"] = normalized_isbn
        return "ok", result
    return "not_found", None
