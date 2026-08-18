import json
from io import BytesIO

from flask import Blueprint, render_template, request, send_file

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
        "priority_api": settings_service.get_setting("priority_api"),
        "default_view": settings_service.get_setting("default_view"),
        "duplicate_detection": settings_service.get_setting("duplicate_detection"),
        "duplicate_detection_choices": settings_service.DUPLICATE_DETECTION_CHOICES,
        "language": settings_service.get_setting("language", "fr"),
        "available_languages": i18n_service.available_languages(),
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
    settings_service.set_setting("priority_api", request.form.get("priority_api"))
    settings_service.set_setting("default_view", request.form.get("default_view"))
    settings_service.set_setting("duplicate_detection", request.form.get("duplicate_detection"))
    settings_service.set_setting("language", request.form.get("language"))
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

@admin_bp.route("/export.json")
def export_json():
    books = Book.query.all()
    data = [
        {
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
        for b in books
    ]

    buffer = BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    return send_file(
        buffer,
        mimetype="application/json",
        as_attachment=True,
        download_name="collection_export.json",
    )


@admin_bp.route("/import", methods=["POST"])
def import_json():
    file = request.files.get("file")
    if not file:
        return render_template("admin/export_import.html", **_export_import_context())

    data = json.load(file.stream)
    imported_count = 0
    skipped_count = 0

    for item in data:
        values = {
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

        # Applies the same detection policy as the rest of the application:
        # a book already present is skipped rather than duplicated.
        duplicate, _criterion = book_service.find_duplicate(values)
        if duplicate:
            skipped_count += 1
            continue

        book_service.create_book(values)
        imported_count += 1

    message = i18n_service.tn(
        "{n} ouvrage importé.", "{n} ouvrages importés.", imported_count
    )
    if skipped_count:
        message += " " + i18n_service.tn(
            "{n} doublon ignoré (déjà présent dans la collection).",
            "{n} doublons ignorés (déjà présents dans la collection).",
            skipped_count,
        )

    return render_template("admin/export_import.html", **_export_import_context(message))
