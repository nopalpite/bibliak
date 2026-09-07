from flask import Blueprint, redirect, render_template, request, session, url_for

from app.services import book_service, image_service
from app.services.i18n_service import t
from app.services.isbn_service import (
    ISBN_SEARCH_MAX_ATTEMPTS,
    ISBN_SEARCH_RETRY_DELAY_MS,
    attempt_search,
    search_by_title,
)
from app.services.settings_service import get_setting

scan_bp = Blueprint("scan", __name__)


@scan_bp.route("/")
def scan_page():
    """Scan page: shows the camera on smartphone (client-side detection),
    and a plain ISBN input field on other platforms."""
    return render_template("scan.html", item_types=get_setting("item_types", []))


@scan_bp.route("/search", methods=["POST"])
def search_isbn():
    isbn = request.form.get("isbn", "").strip()
    if not isbn:
        return render_template(
            "partials/scan_result.html", error=t('Please enter an ISBN/EAN code.')
        )

    state = {
        "isbn": isbn,
        "attempt": 1,
        # Rafale mode: scan several books in a row, each match added
        # automatically (with this session's chosen type) instead of
        # stopping to fill in the full form — see _rafale_outcome below.
        "rafale": request.form.get("rafale") == "1",
        "item_type": request.form.get("item_type", ""),
    }
    return _search_step(state)


@scan_bp.route("/search/retry", methods=["POST"])
def retry_search():
    """Continues a search started by search_isbn(), one attempt at a time.

    Triggered automatically by the "retrying" fragment (htmx load-delay), so
    the browser gets a fresh message at each attempt instead of one request
    hanging for up to ISBN_SEARCH_MAX_ATTEMPTS x TIMEOUT seconds."""
    state = session.get("isbn_search")
    if not state:
        return render_template(
            "partials/scan_result.html",
            error=t("The search took too long and expired. Please try the ISBN again."),
        )
    return _search_step(state)


def _search_step(state):
    status, result = attempt_search(state["isbn"])

    if status == "ok":
        session.pop("isbn_search", None)
        if state.get("rafale"):
            return _rafale_outcome(result, state.get("item_type", ""))
        session["prefill_scan"] = result
        return render_template("partials/scan_result.html", result=result)

    if status == "network_error" and state["attempt"] < ISBN_SEARCH_MAX_ATTEMPTS:
        state["attempt"] += 1
        session["isbn_search"] = state
        return render_template(
            "partials/scan_retrying.html",
            attempt=state["attempt"],
            max_attempts=ISBN_SEARCH_MAX_ATTEMPTS,
            delay_ms=ISBN_SEARCH_RETRY_DELAY_MS,
        )

    session.pop("isbn_search", None)
    if status == "network_error":
        error = t(
            "Open Library could not be reached after {attempts} attempts. You can add the book manually.",
            attempts=ISBN_SEARCH_MAX_ATTEMPTS,
        )
        error_type = "network"
    else:
        error = t("No information found for this ISBN. You can add the book manually.")
        error_type = "not_found"

    return render_template(
        "partials/scan_result.html", error=error, isbn=state["isbn"], error_type=error_type
    )


def _rafale_data(title, isbn, authors, publisher, publication_date, item_type):
    return {
        "title": title or "",
        "item_type": item_type or "",
        "isbn": isbn or None,
        "publication_date": publication_date or None,
        "publisher": publisher or None,
        "authors": authors or [],
        "tags": [],
    }


def _rafale_create(data, image_url):
    book = book_service.create_book(data)
    filename, _error = image_service.download_cover(image_url)
    book_service.set_cover(book, filename)
    return book


def _rafale_outcome(result, item_type):
    """A match during rafale scanning is added straight away — unless it
    looks like a duplicate, which still needs a decision (see
    rafale_confirm below)."""
    data = _rafale_data(
        result.get("title"), result.get("isbn"), result.get("authors"),
        result.get("publisher"), result.get("publication_date"), item_type,
    )
    duplicate, criterion = book_service.find_duplicate(data)
    if duplicate:
        return render_template(
            "partials/scan_rafale_result.html",
            outcome="duplicate", duplicate=duplicate, criterion=criterion,
            result=result, item_type=item_type,
        )
    book = _rafale_create(data, result.get("image_url"))
    return render_template("partials/scan_rafale_result.html", outcome="added", book=book)


@scan_bp.route("/rafale-confirm", methods=["POST"])
def rafale_confirm():
    """Creates the book anyway after a duplicate warning during rafale
    scanning. The scanned data travels as hidden fields in the warning
    form itself rather than session state: scanning doesn't pause while a
    warning is pending, so a later scan could otherwise overwrite it
    before this one is resolved."""
    form = request.form
    data = _rafale_data(
        form.get("title", ""),
        form.get("isbn") or None,
        [a for a in form.get("authors", "").split(",") if a.strip()],
        form.get("publisher") or None,
        form.get("publication_date") or None,
        form.get("item_type", ""),
    )
    book = _rafale_create(data, form.get("image_url") or None)
    return render_template("partials/scan_rafale_result.html", outcome="added", book=book)


@scan_bp.route("/search-title", methods=["POST"])
def search_title():
    """Fallback search when the ISBN scan found nothing: Open Library may
    still have the book under a different edition, findable by title."""
    isbn = request.form.get("isbn", "").strip()
    title = request.form.get("title", "").strip()
    if not title:
        return render_template(
            "partials/title_search_results.html", results=[], searched=False, isbn=isbn
        )
    return render_template(
        "partials/title_search_results.html", results=search_by_title(title), searched=True, isbn=isbn
    )


@scan_bp.route("/select-title-result", methods=["POST"])
def select_title_result():
    """Prefills the add-book form from a title search result the user
    picked, the same way a successful ISBN scan does. Carries over the
    originally scanned ISBN (this specific edition's own identifier, not
    part of the matched title-search result — that one belongs to a
    *different* edition) so it isn't lost."""
    session["prefill_scan"] = {
        "isbn": request.form.get("isbn", "").strip() or None,
        "title": request.form.get("title", ""),
        "authors": [a.strip() for a in request.form.get("authors", "").split(",") if a.strip()],
        "publisher": request.form.get("publisher") or None,
        "publication_date": request.form.get("publication_date", ""),
        "image_url": request.form.get("image_url") or None,
        "source": "Open Library",
    }
    return redirect(url_for("books.new"))
