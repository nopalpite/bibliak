from flask import Blueprint, current_app, render_template, request, session

from app.services.i18n_service import t
from app.services.isbn_service import (
    ISBN_SEARCH_MAX_ATTEMPTS,
    ISBN_SEARCH_RETRY_DELAY_MS,
    SOURCE_NAMES,
    attempt_source,
    available_sources,
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
        "sources": available_sources(
            get_setting("priority_api", "openlibrary"), current_app.config.get("GOOGLE_BOOKS_API_KEY")
        ),
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

        # Either the source doesn't know this ISBN, or it's unreachable and
        # out of retries: either way we're moving to the next source. Say
        # which of the two it was explicitly — a "doesn't know this ISBN"
        # (no problem, just no data) must never read like a connection
        # issue, and vice versa.
        reason = "not_found" if status == "not_found" else "network_error"
        state["source_index"] += 1
        state["attempt"] = 1

        if state["source_index"] < len(sources):
            session["isbn_search"] = state
            return render_template(
                "partials/scan_switching_source.html",
                reason=reason,
                source_name=SOURCE_NAMES[source_key],
                next_source_name=SOURCE_NAMES[sources[state["source_index"]]],
                max_attempts=ISBN_SEARCH_MAX_ATTEMPTS,
                delay_ms=ISBN_SEARCH_RETRY_DELAY_MS,
            )

    session.pop("isbn_search", None)
    return render_template(
        "partials/scan_result.html",
        error=_final_error_message(state),
        isbn=state["isbn"],
        error_type="network" if state["network_failed"] else "not_found",
    )


def _final_error_message(state):
    """Builds the error shown once every available source is exhausted.

    The two sources are tried in the user's configured priority order
    (state["sources"][0] is the primary, [1] the fallback) — the wording
    must reflect which one actually failed to respond, since it isn't always
    the primary (e.g. the primary can respond fine and simply not know the
    ISBN, while the fallback is the one that's unreachable). Google Books is
    absent from state["sources"] entirely when no API key is configured
    (see isbn_service.available_sources), leaving Open Library as the sole
    source to report on."""
    if len(state["sources"]) == 1:
        (primary_key,) = state["sources"]
        primary_name = SOURCE_NAMES[primary_key]
        if primary_key in state["network_failed"]:
            return t(
                "{primary} could not be reached after {attempts} attempts. You can add the book manually.",
                primary=primary_name, attempts=ISBN_SEARCH_MAX_ATTEMPTS,
            )
        return t(
            "No information found for this ISBN via {primary}. You can add the book manually.",
            primary=primary_name,
        )

    primary_key, secondary_key = state["sources"]
    primary_name = SOURCE_NAMES[primary_key]
    secondary_name = SOURCE_NAMES[secondary_key]
    primary_failed = primary_key in state["network_failed"]
    secondary_failed = secondary_key in state["network_failed"]

    if primary_failed and secondary_failed:
        return t(
            "Could not reach {primary} or {secondary} after {attempts} attempts each "
            "(no response or connection unavailable). Try again shortly, or add the book manually.",
            primary=primary_name, secondary=secondary_name, attempts=ISBN_SEARCH_MAX_ATTEMPTS,
        )

    if primary_failed:
        return t(
            "{primary} did not respond after {attempts} attempts. {secondary} was queried as a "
            "fallback but doesn't know this ISBN. You can add the book manually.",
            primary=primary_name, secondary=secondary_name, attempts=ISBN_SEARCH_MAX_ATTEMPTS,
        )

    if secondary_failed:
        return t(
            "{primary} doesn't know this ISBN. The fallback source, {secondary}, did not respond "
            "after {attempts} attempts. You can add the book manually.",
            primary=primary_name, secondary=secondary_name, attempts=ISBN_SEARCH_MAX_ATTEMPTS,
        )

    return t(
        "No information found for this ISBN (Open Library and Google Books were "
        "queried). You can add the book manually."
    )
