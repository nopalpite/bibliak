from flask import Blueprint, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import Author, Book, Location, Publisher, Series, Tag
from app.services import book_service, image_service
from app.services.i18n_service import t
from app.services.settings_service import get_setting
from app.services.search_service import group_by_series, search_books

books_bp = Blueprint("books", __name__)


@books_bp.route("/search")
def search():
    """Endpoint called via HTMX on every keystroke / filter change."""
    books = search_books(
        q=request.args.get("q"),
        item_type=request.args.get("type") or None,
        series_id=request.args.get("series", type=int),
        publisher_id=request.args.get("publisher", type=int),
        tag_id=request.args.get("tag", type=int),
        location_id=request.args.get("location", type=int),
        condition=request.args.get("condition") or None,
        read_status=request.args.get("read_status") or None,
        sort=request.args.get("sort", "title"),
    )
    view = request.args.get("view", "grid")
    if view == "shelves":
        return render_template("partials/books_shelves.html", groups=group_by_series(books))
    template = "partials/books_grid.html" if view == "grid" else "partials/books_list.html"
    return render_template(template, books=books)


@books_bp.route("/check-duplicate")
def check_duplicate():
    """Called via HTMX on every keystroke in the ISBN / title / volume form
    fields: immediately flags a potential duplicate according to the
    configured policy (Administration > Settings)."""
    data = {
        "isbn": request.args.get("isbn", ""),
        "title": request.args.get("title", ""),
        "volume": request.args.get("volume", type=int),
    }
    exclude = request.args.get("exclude", type=int)
    duplicate, criterion = book_service.find_duplicate(data, exclude_id=exclude)
    return render_template("partials/duplicate_alert.html", duplicate=duplicate, criterion=criterion, variant="live")


@books_bp.route("/series/quick-create", methods=["POST"])
def quick_create_series():
    """Creates a series from the add/edit form (the "+" button next to the
    selector), without leaving the page. The newly created series is
    automatically selected in the returned field."""
    name = request.form.get("name", "").strip()

    if not name:
        return render_template(
            "partials/field_series.html",
            series=Series.query.order_by(Series.name).all(),
            values={"series_id": None},
            message=t("Merci de saisir un nom de série."),
            error=True,
            entered_name="",
        )

    series = Series.query.filter_by(name=name).first()
    already_existing = series is not None
    if not series:
        series = Series(name=name)
        db.session.add(series)
        db.session.commit()

    message = (
        t("« {name} » existait déjà : sélectionnée.", name=series.name)
        if already_existing
        else t("« {name} » créée et sélectionnée.", name=series.name)
    )

    return render_template(
        "partials/field_series.html",
        series=Series.query.order_by(Series.name).all(),
        values={"series_id": series.id},
        message=message,
        error=False,
        entered_name="",
    )


@books_bp.route("/publishers/quick-create", methods=["POST"])
def quick_create_publisher():
    """Creates a publisher from the add/edit form (the "+" button next to
    the selector), without leaving the page. The newly created publisher is
    automatically selected in the returned field."""
    name = request.form.get("name", "").strip()

    if not name:
        return render_template(
            "partials/field_publisher.html",
            publishers=Publisher.query.order_by(Publisher.name).all(),
            values={"publisher_id": None},
            message=t("Merci de saisir un nom d'éditeur."),
            error=True,
            entered_name="",
        )

    publisher = Publisher.query.filter_by(name=name).first()
    already_existing = publisher is not None
    if not publisher:
        publisher = Publisher(name=name)
        db.session.add(publisher)
        db.session.commit()

    message = (
        t("« {name} » existait déjà : sélectionné.", name=publisher.name)
        if already_existing
        else t("« {name} » créé et sélectionné.", name=publisher.name)
    )

    return render_template(
        "partials/field_publisher.html",
        publishers=Publisher.query.order_by(Publisher.name).all(),
        values={"publisher_id": publisher.id},
        message=message,
        error=False,
        entered_name="",
    )


@books_bp.route("/new", methods=["GET", "POST"])
def new():
    if request.method == "POST":
        data = _form_data()

        if not data.get("title", "").strip():
            return render_template(
                "book_form.html",
                book=None,
                values=_values_from_form(request.form),
                duplicate=None,
                criterion=None,
                title_error=True,
                **_form_context(),
            )

        duplicate, criterion = book_service.find_duplicate(data)

        if duplicate and request.form.get("ignore_duplicate") != "1":
            return render_template(
                "book_form.html",
                book=None,
                values=_values_from_form(request.form),
                duplicate=duplicate,
                criterion=criterion,
                **_form_context(),
            )

        book = book_service.create_book(data)
        image_error = _process_image(book)
        return redirect(url_for("books.detail", book_id=book.id, image_error=image_error))

    prefill = session.pop("prefill_scan", None)
    if not prefill and request.args.get("isbn"):
        prefill = {"isbn": request.args.get("isbn"), "title": "", "authors": [], "source": ""}

    values = _values_from_prefill(prefill) if prefill else _empty_values()
    if prefill and prefill.get("publisher"):
        values["publisher_id"] = _resolve_prefill_publisher(prefill["publisher"])
    series_id_arg = request.args.get("series_id", type=int)
    if series_id_arg:
        values["series_id"] = series_id_arg
    if request.args.get("volume"):
        values["volume"] = request.args.get("volume")

    return render_template(
        "book_form.html",
        book=None,
        values=values,
        duplicate=None,
        criterion=None,
        **_form_context(),
    )


@books_bp.route("/<int:book_id>")
def detail(book_id):
    book = Book.query.get_or_404(book_id)
    return render_template(
        "book_detail.html", book=book, image_error=request.args.get("image_error")
    )


@books_bp.route("/<int:book_id>/edit", methods=["GET", "POST"])
def edit(book_id):
    book = Book.query.get_or_404(book_id)

    if request.method == "POST":
        data = _form_data()

        if not data.get("title", "").strip():
            return render_template(
                "book_form.html",
                book=book,
                values=_values_from_form(request.form),
                duplicate=None,
                criterion=None,
                title_error=True,
                **_form_context(),
            )

        duplicate, criterion = book_service.find_duplicate(data, exclude_id=book.id)

        if duplicate and request.form.get("ignore_duplicate") != "1":
            return render_template(
                "book_form.html",
                book=book,
                values=_values_from_form(request.form),
                duplicate=duplicate,
                criterion=criterion,
                **_form_context(),
            )

        book_service.update_book(book, data)
        image_error = _process_image(book)
        return redirect(url_for("books.detail", book_id=book.id, image_error=image_error))

    return render_template(
        "book_form.html",
        book=book,
        values=_values_from_book(book),
        duplicate=None,
        criterion=None,
        **_form_context(),
    )


@books_bp.route("/<int:book_id>/delete", methods=["POST"])
def delete(book_id):
    book = Book.query.get_or_404(book_id)
    book_service.delete_book(book)
    return redirect(url_for("main.index"))


@books_bp.route("/<int:book_id>/read", methods=["POST"])
def toggle_read(book_id):
    """Toggles the read / unread status from the detail page, without going
    through the full edit form."""
    book = Book.query.get_or_404(book_id)
    book_service.toggle_read(book)
    return redirect(url_for("books.detail", book_id=book.id))


def _form_data():
    form = request.form
    return {
        "title": form.get("title", ""),
        "item_type": form.get("item_type"),
        "isbn": form.get("isbn"),
        "volume": form.get("volume", type=int),
        "publication_date": form.get("publication_date"),
        "summary": form.get("summary"),
        "condition": form.get("condition"),
        "personal_notes": form.get("personal_notes"),
        "publisher_id": form.get("publisher_id", type=int),
        "series_id": form.get("series_id", type=int),
        "location": form.get("location"),
        "authors": [a for a in form.get("authors", "").split(",") if a.strip()],
        "tags": [tag for tag in form.get("tags", "").split(",") if tag.strip()],
    }


def _process_image(book):
    """Processes the uploaded photo or the pasted image link. Returns an
    error message if the link could not be downloaded (None otherwise): as
    opposed to a silent failure, the user must know their cover was not
    saved."""
    file = request.files.get("photo")
    remote_image_url = request.form.get("remote_image_url")

    filename = None
    error = None
    if file and file.filename:
        filename = image_service.save_upload(file)
        if not filename:
            error = t("La photo importée n'a pas pu être lue (fichier corrompu ou format non supporté).")
    elif remote_image_url:
        filename, error = image_service.download_cover(remote_image_url)

    if filename:
        book_service.set_cover(book, filename)

    return error


def _form_context():
    return {
        "publishers": Publisher.query.order_by(Publisher.name).all(),
        "series": Series.query.order_by(Series.name).all(),
        "existing_tags": Tag.query.order_by(Tag.label).all(),
        "existing_authors": Author.query.order_by(Author.full_name).all(),
        "locations": Location.query.order_by(Location.label).all(),
        "item_types": get_setting("item_types", []),
        "conditions": get_setting("conditions", []),
    }


# --- Normalization of the values displayed in the form ---
# The add/edit form can be pre-filled from three different sources (an
# existing book being edited, an ISBN scan result, or a new submission
# blocked by a duplicate to fix): this uniform dict avoids duplicating this
# logic in the template.

def _empty_values():
    return {
        "title": "", "item_type": "", "isbn": "", "series_id": None, "volume": "",
        "authors": "", "publisher_id": None, "publication_date": "", "summary": "",
        "condition": "", "location": "", "tags": "", "personal_notes": "",
        "image_url": None, "remote_image_url": None,
    }


def _values_from_book(book):
    return {
        "title": book.title,
        "item_type": book.item_type or "",
        "isbn": book.isbn or "",
        "series_id": book.series_id,
        "volume": book.volume or "",
        "authors": book.author_list,
        "publisher_id": book.publisher_id,
        "publication_date": book.publication_date or "",
        "summary": book.summary or "",
        "condition": book.condition or "",
        "location": book.location.label if book.location else "",
        "tags": ", ".join(book.tag_list),
        "personal_notes": book.personal_notes or "",
        "image_url": url_for("static", filename="covers/" + book.cover_image) if book.cover_image else None,
        "remote_image_url": None,
    }


def _values_from_prefill(prefill):
    return {
        "title": prefill.get("title") or "",
        "item_type": "",
        "isbn": prefill.get("isbn") or "",
        "series_id": None,
        "volume": "",
        "authors": ", ".join(prefill.get("authors") or []),
        "publisher_id": None,  # resolved separately in new(): see _resolve_prefill_publisher
        "publication_date": prefill.get("publication_date") or "",
        "summary": prefill.get("summary") or "",
        "condition": "",
        "location": "",
        "tags": "",
        "personal_notes": "",
        "image_url": prefill.get("image_url"),
        "remote_image_url": prefill.get("image_url"),
    }


def _resolve_prefill_publisher(name):
    """The ISBN scan returns a publisher name as free text (Open Library /
    Google Books), but the form now requires choosing an existing publisher.
    It is resolved (or created) here so it's already selectable when the
    form loads, rather than losing this information or reopening a text
    field for this one case."""
    name = (name or "").strip()
    if not name:
        return None
    publisher = Publisher.query.filter_by(name=name).first()
    if not publisher:
        publisher = Publisher(name=name)
        db.session.add(publisher)
        db.session.commit()
    return publisher.id


def _values_from_form(form):
    return {
        "title": form.get("title", ""),
        "item_type": form.get("item_type", ""),
        "isbn": form.get("isbn", ""),
        "series_id": form.get("series_id", type=int),
        "volume": form.get("volume", ""),
        "authors": form.get("authors", ""),
        "publisher_id": form.get("publisher_id", type=int),
        "publication_date": form.get("publication_date", ""),
        "summary": form.get("summary", ""),
        "condition": form.get("condition", ""),
        "location": form.get("location", ""),
        "tags": form.get("tags", ""),
        "personal_notes": form.get("personal_notes", ""),
        "image_url": form.get("remote_image_url") or None,
        "remote_image_url": form.get("remote_image_url") or None,
    }
