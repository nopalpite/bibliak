from flask import Blueprint, current_app, render_template, request, session

from app.services.i18n_service import t
from app.services.isbn_service import (
    ISBN_SEARCH_MAX_ATTEMPTS,
    ISBN_SEARCH_RETRY_DELAY_MS,
    SOURCE_NAMES,
    attempt_source,
    source_order,
)
from app.services.settings_service import get_setting

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

    state = {
        "isbn": isbn,
        "sources": source_order(get_setting("priority_api", "openlibrary")),
        "source_index": 0,
        "attempt": 1,
        "network_failed": [],
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
    sources = state["sources"]

    while state["source_index"] < len(sources):
        source_key = sources[state["source_index"]]
        status, result = attempt_source(
            state["isbn"], source_key, google_api_key=current_app.config.get("GOOGLE_BOOKS_API_KEY")
        )

        if status == "ok":
            session.pop("isbn_search", None)
            session["prefill_scan"] = result
            return render_template("partials/scan_result.html", result=result)

        if status == "network_error":
            if state["attempt"] < ISBN_SEARCH_MAX_ATTEMPTS:
                state["attempt"] += 1
                session["isbn_search"] = state
                return render_template(
                    "partials/scan_retrying.html",
                    source_name=SOURCE_NAMES[source_key],
                    attempt=state["attempt"],
                    max_attempts=ISBN_SEARCH_MAX_ATTEMPTS,
                    delay_ms=ISBN_SEARCH_RETRY_DELAY_MS,
                )
            state["network_failed"].append(source_key)

        state["source_index"] += 1
        state["attempt"] = 1

    session.pop("isbn_search", None)
    return render_template(
        "partials/scan_result.html",
        error=_final_error_message(state),
        isbn=state["isbn"],
        error_type="network" if state["network_failed"] else "not_found",
    )


def _final_error_message(state):
    failed = state["network_failed"]

    if len(failed) == len(state["sources"]):
        return t(
            "Could not reach Open Library or Google Books after {attempts} attempts each "
            "(no response or connection unavailable). Try again shortly, or add the book manually.",
            attempts=ISBN_SEARCH_MAX_ATTEMPTS,
        )

    if failed:
        failed_source = SOURCE_NAMES[failed[0]]
        other_key = next(s for s in state["sources"] if s not in failed)
        other_source = SOURCE_NAMES[other_key]
        return t(
            "{failed_source} did not respond after {attempts} attempts. {other_source} was queried as a "
            "fallback but doesn't know this ISBN. You can add the book manually.",
            failed_source=failed_source, other_source=other_source, attempts=ISBN_SEARCH_MAX_ATTEMPTS,
        )

    return t(
        "No information found for this ISBN (Open Library and Google Books were "
        "queried). You can add the book manually."
    )
