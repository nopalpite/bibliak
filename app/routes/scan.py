from flask import Blueprint, render_template, request, session

from app.services.i18n_service import t
from app.services.isbn_service import ISBN_SEARCH_MAX_ATTEMPTS, ISBN_SEARCH_RETRY_DELAY_MS, attempt_search

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
