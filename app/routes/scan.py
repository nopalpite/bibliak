from flask import Blueprint, redirect, render_template, request, session, url_for

from app.services.i18n_service import t
from app.services.isbn_service import (
    ISBN_SEARCH_MAX_ATTEMPTS,
    ISBN_SEARCH_RETRY_DELAY_MS,
    attempt_search,
    search_by_title,
)

scan_bp = Blueprint("scan", __name__)


@scan_bp.route("/")
def scan_page():
    """Scan page: shows the camera on smartphone (client-side detection),
    and a plain ISBN input field on other platforms."""
    return render_template("scan.html")


@scan_bp.route("/search", methods=["POST"])
def search_isbn():
    isbn = request.form.get("isbn", "").strip()
    if not isbn:
        return render_template(
            "partials/scan_result.html", error=t('Please enter an ISBN/EAN code.')
        )

    return _search_step({"isbn": isbn, "attempt": 1})


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
