"""Retrieval of a book's metadata from its ISBN/EAN.

Two sources are queried, with automatic fallback from one to the other:
- Open Library (free, no key)
- Google Books (free, optional key for higher quotas)

Comics and manga are often poorly referenced in these general-purpose
databases: the result must therefore always be treated as a pre-fill,
never as an absolute truth.
"""

import requests
from flask import current_app

TIMEOUT = 6  # seconds


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
    agent = "MaBibliotheque/1.0 (application locale de gestion de collection)"
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


def _from_google_books(isbn, api_key=None):
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": f"isbn:{isbn}"}
    if api_key:
        params["key"] = api_key
    response = requests.get(url, params=params, headers=_http_headers(), timeout=TIMEOUT)
    response.raise_for_status()
    items = response.json().get("items")
    if not items:
        return None

    info = items[0].get("volumeInfo", {})
    image_links = info.get("imageLinks", {}) or {}

    return {
        "title": info.get("title"),
        "authors": info.get("authors", []),
        "publisher": info.get("publisher"),
        "publication_date": info.get("publishedDate"),
        "summary": info.get("description"),
        "image_url": image_links.get("thumbnail") or image_links.get("smallThumbnail"),
        "source": "Google Books",
    }


def search_by_isbn(isbn, priority_api="openlibrary", google_api_key=None):
    """Queries both sources in the chosen priority order.

    Returns a tuple (result, failed_sources):
    - result: the first usable result found, or None
    - failed_sources: names of sources that could not be contacted
      (timeout, network error, HTTP error) — as distinguished from a source
      that responded normally but doesn't know this ISBN.
    """
    normalized_isbn = _clean_isbn(isbn)

    sources = [
        ("Open Library", _from_open_library),
        ("Google Books", lambda i: _from_google_books(i, google_api_key)),
    ]
    if priority_api == "googlebooks":
        sources.reverse()

    failed_sources = []
    for source_name, function in sources:
        try:
            result = function(normalized_isbn)
        except requests.RequestException:
            failed_sources.append(source_name)
            continue
        if result and result.get("title"):
            result["isbn"] = normalized_isbn
            return result, failed_sources

    return None, failed_sources
