import csv
import io
import json
from io import BytesIO

from flask import Blueprint, render_template, request, send_file
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models import Book, Location, Publisher, Series, Tag
from app.services import book_service, i18n_service, settings_service

admin_bp = Blueprint("admin", __name__)

# "Relational" reference data manageable generically (model, text field)
REFERENCE_MODELS = {
    "publishers": (Publisher, "name"),
    "series": (Series, "name"),
    "tags": (Tag, "label"),
    "locations": (Location, "label"),
}

# "Simple list" reference data stored in the Setting table
CONFIGURABLE_LISTS = ("item_types", "conditions")


def _settings_context():
    return {
        "default_view": settings_service.get_setting("default_view"),
        "duplicate_detection": settings_service.get_setting("duplicate_detection"),
        "duplicate_detection_choices": settings_service.DUPLICATE_DETECTION_CHOICES,
        "language": settings_service.get_setting("language"),
        "available_languages": i18n_service.available_languages(),
        "theme": settings_service.get_setting("theme"),
        "theme_choices": settings_service.THEME_CHOICES,
    }


def _references_context():
    return {
        "item_types": settings_service.get_setting("item_types", []),
        "conditions": settings_service.get_setting("conditions", []),
        "publishers": Publisher.query.order_by(Publisher.name).all(),
        "series": Series.query.order_by(Series.name).all(),
        "tags": Tag.query.order_by(Tag.label).all(),
        "locations": Location.query.order_by(Location.label).all(),
    }


def _export_import_context(message=None):
    return {"book_count": Book.query.count(), "message": message}


TAB_CONTEXTS = {
    "settings": _settings_context,
    "references": _references_context,
    "export_import": _export_import_context,
}


@admin_bp.route("/")
def home():
    return render_template(
        "admin/layout_admin.html", active_tab="settings", **_settings_context()
    )


@admin_bp.route("/tab/<name>")
def tab(name):
    """Loads a tab via HTMX, without reloading the page."""
    if name not in TAB_CONTEXTS:
        name = "settings"
    return render_template(f"admin/{name}.html", **TAB_CONTEXTS[name]())


# --- General settings ---

@admin_bp.route("/settings", methods=["POST"])
def save_settings():
    settings_service.set_setting("default_view", request.form.get("default_view"))
    settings_service.set_setting("duplicate_detection", request.form.get("duplicate_detection"))
    settings_service.set_setting("language", request.form.get("language"))
    settings_service.set_setting("theme", request.form.get("theme"))
    return render_template("admin/settings.html", **_settings_context())


# --- "Simple list" reference data: item types and conditions ---

@admin_bp.route("/reference-lists/<key>/add", methods=["POST"])
def add_list_value(key):
    if key in CONFIGURABLE_LISTS:
        value = request.form.get("value", "").strip()
        values = settings_service.get_setting(key, [])
        if value and value not in values:
            values.append(value)
            settings_service.set_setting(key, values)
    return render_template("admin/references.html", **_references_context())


@admin_bp.route("/reference-lists/<key>/remove", methods=["POST"])
def remove_list_value(key):
    if key in CONFIGURABLE_LISTS:
        value = request.form.get("value", "").strip()
        values = settings_service.get_setting(key, [])
        if value in values:
            values.remove(value)
            settings_service.set_setting(key, values)
    return render_template("admin/references.html", **_references_context())


# --- Relational reference data: publishers, series, tags, locations ---

@admin_bp.route("/references/<model_name>/add", methods=["POST"])
def add_reference(model_name):
    if model_name in REFERENCE_MODELS:
        model, field = REFERENCE_MODELS[model_name]
        value = request.form.get("value", "").strip()
        if value and not model.query.filter_by(**{field: value}).first():
            db.session.add(model(**{field: value}))
            db.session.commit()
    return render_template("admin/references.html", **_references_context())


@admin_bp.route("/references/<model_name>/<int:item_id>/rename", methods=["POST"])
def rename_reference(model_name, item_id):
    if model_name in REFERENCE_MODELS:
        model, field = REFERENCE_MODELS[model_name]
        item = model.query.get_or_404(item_id)
        new_value = request.form.get("value", "").strip()
        if new_value:
            setattr(item, field, new_value)
            db.session.commit()
    return render_template("admin/references.html", **_references_context())


@admin_bp.route("/references/<model_name>/<int:item_id>/delete", methods=["POST"])
def delete_reference(model_name, item_id):
    if model_name in REFERENCE_MODELS:
        model, _field = REFERENCE_MODELS[model_name]
        item = model.query.get_or_404(item_id)
        db.session.delete(item)
        db.session.commit()
    return render_template("admin/references.html", **_references_context())


@admin_bp.route("/references/<model_name>/merge", methods=["POST"])
def merge_reference(model_name):
    """Merges a duplicate reference entry into another (useful after an
    import that created two slightly different entries, e.g. two tags "SF" /
    "sf")."""
    if model_name in REFERENCE_MODELS:
        model, _field = REFERENCE_MODELS[model_name]
        source = db.session.get(model, request.form.get("source_id", type=int))
        target = db.session.get(model, request.form.get("target_id", type=int))

        if source and target and source.id != target.id:
            if model_name == "tags":
                for book in list(source.books):
                    if target not in book.tags:
                        book.tags.append(target)
                    book.tags.remove(source)
            else:
                for book in list(source.books):
                    if model_name == "publishers":
                        book.publisher = target
                    elif model_name == "series":
                        book.series = target
                    elif model_name == "locations":
                        book.location = target

            db.session.delete(source)
            db.session.commit()

    return render_template("admin/references.html", **_references_context())


# --- Export / Import (collection backup) ---

CSV_COLUMNS = [
    "title", "item_type", "isbn", "series", "volume", "authors", "publisher",
    "publication_date", "summary", "cover_image", "location", "condition",
    "personal_notes", "read", "tags",
]


def _all_books_eager():
    return Book.query.options(
        selectinload(Book.authors),
        selectinload(Book.publisher),
        selectinload(Book.series),
        selectinload(Book.location),
        selectinload(Book.tags),
    ).all()


def _book_export_dict(b):
    return {
        "title": b.title,
        "item_type": b.item_type,
        "isbn": b.isbn,
        "series": b.series.name if b.series else None,
        "volume": b.volume,
        "authors": [a.full_name for a in b.authors],
        "publisher": b.publisher.name if b.publisher else None,
        "publication_date": b.publication_date,
        "summary": b.summary,
        "cover_image": b.cover_image,
        "location": b.location.label if b.location else None,
        "condition": b.condition,
        "personal_notes": b.personal_notes,
        "read": b.read,
        "tags": [t.label for t in b.tags],
    }


@admin_bp.route("/export.json")
def export_json():
    data = [_book_export_dict(b) for b in _all_books_eager()]
    buffer = BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    return send_file(
        buffer,
        mimetype="application/json",
        as_attachment=True,
        download_name="collection_export.json",
    )


@admin_bp.route("/export.csv")
def export_csv():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for b in _all_books_eager():
        row = _book_export_dict(b)
        row["authors"] = ", ".join(row["authors"])
        row["tags"] = ", ".join(row["tags"])
        writer.writerow(row)

    # utf-8-sig: Excel otherwise mis-reads accented characters without a BOM.
    buffer = BytesIO(output.getvalue().encode("utf-8-sig"))
    return send_file(
        buffer,
        mimetype="text/csv",
        as_attachment=True,
        download_name="collection_export.csv",
    )


def _import_values_from_json_item(item):
    return {
        "title": item.get("title", ""),
        "item_type": item.get("item_type"),
        "isbn": item.get("isbn"),
        "volume": item.get("volume"),
        "publication_date": item.get("publication_date"),
        "summary": item.get("summary"),
        "condition": item.get("condition"),
        "personal_notes": item.get("personal_notes"),
        "read": item.get("read", (item.get("read_count", 0) or 0) >= 1),
        "publisher": item.get("publisher"),
        "series": item.get("series"),
        "location": item.get("location"),
        "authors": item.get("authors", []),
        "tags": item.get("tags", []),
    }


def _split_csv_list(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def _import_values_from_csv_row(row):
    volume = (row.get("volume") or "").strip()
    return {
        "title": row.get("title", ""),
        "item_type": row.get("item_type") or None,
        "isbn": row.get("isbn") or None,
        "volume": int(volume) if volume.lstrip("-").isdigit() else None,
        "publication_date": row.get("publication_date") or None,
        "summary": row.get("summary") or None,
        "condition": row.get("condition") or None,
        "personal_notes": row.get("personal_notes") or None,
        "read": (row.get("read") or "").strip().lower() in ("true", "1", "yes"),
        "publisher": row.get("publisher") or None,
        "series": row.get("series") or None,
        "location": row.get("location") or None,
        "authors": _split_csv_list(row.get("authors")),
        "tags": _split_csv_list(row.get("tags")),
    }


def _import_all(values_list):
    """Shared create-or-skip loop for both JSON and CSV import: a book
    already present (per the configured duplicate detection policy) is
    skipped rather than duplicated."""
    imported_count = 0
    skipped_count = 0
    for values in values_list:
        duplicate, _criterion = book_service.find_duplicate(values)
        if duplicate:
            skipped_count += 1
            continue
        book_service.create_book(values)
        imported_count += 1
    return imported_count, skipped_count


def _import_message(imported_count, skipped_count):
    message = i18n_service.tn('{n} book imported.', '{n} books imported.', imported_count)
    if skipped_count:
        message += " " + i18n_service.tn(
            '{n} duplicate skipped (already in the collection).',
            '{n} duplicates skipped (already in the collection).',
            skipped_count,
        )
    return message


@admin_bp.route("/import", methods=["POST"])
def import_json():
    file = request.files.get("file")
    if not file:
        return render_template("admin/export_import.html", **_export_import_context())

    data = json.load(file.stream)
    imported_count, skipped_count = _import_all(_import_values_from_json_item(item) for item in data)
    return render_template(
        "admin/export_import.html", **_export_import_context(_import_message(imported_count, skipped_count))
    )


@admin_bp.route("/import-csv", methods=["POST"])
def import_csv():
    file = request.files.get("file")
    if not file:
        return render_template("admin/export_import.html", **_export_import_context())

    text = file.stream.read().decode("utf-8-sig")
    rows = csv.DictReader(io.StringIO(text))
    imported_count, skipped_count = _import_all(_import_values_from_csv_row(row) for row in rows)
    return render_template(
        "admin/export_import.html", **_export_import_context(_import_message(imported_count, skipped_count))
    )
