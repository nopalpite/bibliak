from flask import Blueprint, current_app, redirect, render_template, request, send_file, url_for

from app.extensions import db
from app.models import Book, Location, Publisher, Series, Tag
from app.services.settings_service import get_setting
from app.services.search_service import group_by_series, search_books

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    view = request.args.get("view", get_setting("default_view", "grid"))
    books = search_books()

    return render_template(
        "index.html",
        books=books,
        groups=group_by_series(books),
        view=view,
        publishers=Publisher.query.order_by(Publisher.name).all(),
        series=Series.query.order_by(Series.name).all(),
        tags=Tag.query.order_by(Tag.label).all(),
        locations=Location.query.order_by(Location.label).all(),
        item_types=get_setting("item_types", []),
        conditions=get_setting("conditions", []),
    )


@main_bp.route("/series/<int:series_id>")
def series_detail(series_id):
    """Series "shelf" page: every owned volume, sorted, with missing volumes
    flagged as gaps if the total volume count is known."""
    series = Series.query.get_or_404(series_id)
    books = (
        Book.query.filter_by(series_id=series.id)
        .order_by(Book.volume.is_(None), Book.volume)
        .all()
    )

    owned_volumes = {b.volume for b in books if b.volume is not None}
    missing_volumes = []
    if series.expected_volume_count:
        missing_volumes = [n for n in range(1, series.expected_volume_count + 1) if n not in owned_volumes]

    return render_template(
        "series_detail.html",
        series=series,
        books=books,
        missing_volumes=missing_volumes,
    )


@main_bp.route("/series/<int:series_id>/volume-count", methods=["POST"])
def set_volume_count(series_id):
    """Sets (or clears) a series' expected total volume count, so the
    "shelf" page can flag missing volumes."""
    series = Series.query.get_or_404(series_id)
    series.expected_volume_count = request.form.get("expected_volume_count", type=int)
    db.session.commit()
    return redirect(url_for("main.series_detail", series_id=series.id))


@main_bp.route("/certificate")
def download_certificate():
    """Serves the self-signed HTTPS certificate for installation as a
    trusted profile on iOS (Safari doesn't unlock camera access on a
    certificate simply "accepted"; it must be installed and validated in
    system settings)."""
    certificate_path = current_app.config["CERT_DIR"] / "cert.pem"
    return send_file(
        certificate_path,
        mimetype="application/x-x509-ca-cert",
        as_attachment=True,
        download_name="bibliak.pem",
    )
