from flask import Blueprint, current_app, render_template, request, session

from app.services.i18n_service import t
from app.services.isbn_service import search_by_isbn
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

    result, failed_sources = search_by_isbn(
        isbn,
        priority_api=get_setting("priority_api", "openlibrary"),
        google_api_key=current_app.config.get("GOOGLE_BOOKS_API_KEY"),
    )

    if not result:
        if len(failed_sources) == 2:
            error = t(
                "Could not reach Open Library or Google Books (no response or connection "
                "unavailable). Try again shortly, or add the book manually."
            )
            error_type = "network"
        elif failed_sources:
            failed_source = failed_sources[0]
            other_source = "Google Books" if failed_source == "Open Library" else "Open Library"
            error = t(
                "{failed_source} did not respond. {other_source} was queried as a fallback "
                "but doesn't know this ISBN. You can add the book manually.",
                failed_source=failed_source, other_source=other_source,
            )
            error_type = "network"
        else:
            error = t(
                "No information found for this ISBN (Open Library and Google Books were "
                "queried). You can add the book manually."
            )
            error_type = "not_found"

        return render_template("partials/scan_result.html", error=error, isbn=isbn, error_type=error_type)

    session["prefill_scan"] = result
    return render_template("partials/scan_result.html", result=result)
