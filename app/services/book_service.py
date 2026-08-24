"""Create / update / delete logic for a book.

Centralizes the resolution of related entities (authors, publisher, series,
tags, location): they are created on the fly if they don't exist yet, so the
user is never blocked by a prior setup step.
"""

from app.extensions import db
from app.models import Author, Book, Location, Publisher, Series, Tag
from app.services import settings_service
from app.services.image_service import delete_cover


def _get_or_create(model, **filters):
    instance = model.query.filter_by(**filters).first()
    if instance:
        return instance
    instance = model(**filters)
    db.session.add(instance)
    db.session.flush()
    return instance


def _resolve_publisher(data):
    """Resolves a book's publisher — same logic as _resolve_series:
    mandatory choice among existing ones from the form (publisher_id),
    with a fallback to the name for JSON import."""
    publisher_id = data.get("publisher_id")
    if publisher_id:
        return db.session.get(Publisher, publisher_id)

    name = (data.get("publisher") or "").strip()
    return _get_or_create(Publisher, name=name) if name else None


def _resolve_series(data):
    """Resolves a book's series.

    The add/edit form now requires choosing an existing series (passed by
    its id, `series_id`) rather than creating a new one on the fly by simply
    typing a name — this avoids duplicate series caused by a typo. Creation
    remains possible via the "+" button on the form (see
    books.quick_create_series) or Administration > References.

    Importing a JSON backup is still tolerated by name (`series`), so as not
    to require pre-creating every series before restoring a collection.
    """
    series_id = data.get("series_id")
    if series_id:
        return db.session.get(Series, series_id)

    name = (data.get("series") or "").strip()
    return _get_or_create(Series, name=name) if name else None


def resolve_location(label):
    """Finds or creates a Location by its label. Public: also used directly
    by the bulk "set location" action (see bulk_set_location below), which
    has no per-book form to resolve a full `data` dict from."""
    label = (label or "").strip()
    return _get_or_create(Location, label=label) if label else None


def _resolve_authors(names):
    result = []
    for name in names:
        name = name.strip()
        if name:
            result.append(_get_or_create(Author, full_name=name))
    return result


def resolve_tags(labels):
    """Finds or creates each Tag by label. Public: also used directly by
    the bulk "add tag" action (see bulk_add_tag below)."""
    result = []
    for label in labels:
        label = label.strip()
        if label:
            result.append(_get_or_create(Tag, label=label))
    return result


def _apply_data(book, data):
    book.title = (data.get("title") or "").strip()
    book.item_type = data.get("item_type") or "Autre"
    book.isbn = (data.get("isbn") or "").strip() or None
    book.volume = data.get("volume")
    book.publication_date = (data.get("publication_date") or "").strip() or None
    book.summary = (data.get("summary") or "").strip() or None
    book.condition = data.get("condition") or None
    book.personal_notes = (data.get("personal_notes") or "").strip() or None
    if "read" in data:
        # Only present when importing a JSON backup: the add/edit form
        # doesn't handle this field (it's toggled from the detail page), so
        # we never want to silently reset the status on edit.
        book.read = bool(data.get("read"))

    book.publisher = _resolve_publisher(data)
    book.series = _resolve_series(data)
    book.location = resolve_location(data.get("location"))
    book.authors = _resolve_authors(data.get("authors", []))
    book.tags = resolve_tags(data.get("tags", []))

    return book


def create_book(data):
    book = Book()
    _apply_data(book, data)
    db.session.add(book)
    db.session.commit()
    return book


def update_book(book, data):
    _apply_data(book, data)
    db.session.commit()
    return book


def delete_book(book):
    delete_cover(book.cover_image)
    db.session.delete(book)
    db.session.commit()


def set_cover(book, filename):
    if not filename:
        return
    if book.cover_image:
        delete_cover(book.cover_image)
    book.cover_image = filename
    db.session.commit()


def toggle_read(book):
    """Toggles a book's read / unread status."""
    book.read = not book.read
    db.session.commit()
    return book


# --- Bulk actions (multi-select on the collection view) ---

def bulk_delete(book_ids):
    """Deletes every book in `book_ids`. Goes through delete_book() one by
    one (not a bulk DB DELETE) so each cover file is cleaned up too."""
    books = Book.query.filter(Book.id.in_(book_ids)).all() if book_ids else []
    for book in books:
        delete_book(book)
    return len(books)


def bulk_set_location(book_ids, label):
    """Sets the same location on every book in `book_ids`, creating it if
    it doesn't exist yet. No-op (returns 0) if the label is blank."""
    location = resolve_location(label)
    if not book_ids or not location:
        return 0
    books = Book.query.filter(Book.id.in_(book_ids)).all()
    for book in books:
        book.location = location
    db.session.commit()
    return len(books)


def bulk_add_tag(book_ids, label):
    """Adds the same tag to every book in `book_ids` (creating it if it
    doesn't exist yet), without duplicating it on books that already have
    it. No-op (returns 0) if the label is blank."""
    tags = resolve_tags([label])
    if not book_ids or not tags:
        return 0
    tag = tags[0]
    books = Book.query.filter(Book.id.in_(book_ids)).all()
    for book in books:
        if tag not in book.tags:
            book.tags.append(tag)
    db.session.commit()
    return len(books)


def find_duplicate_by_isbn(isbn, exclude_id=None):
    """Returns an existing book with the same ISBN, or None."""
    isbn = (isbn or "").strip()
    if not isbn:
        return None

    query = Book.query.filter(Book.isbn == isbn)
    if exclude_id:
        query = query.filter(Book.id != exclude_id)
    return query.first()


def _find_duplicate_by_title_volume(title, volume, exclude_id=None):
    """Returns an existing book with the same title (case-insensitive) and
    the same volume (both None counting as equal), or None."""
    title = (title or "").strip()
    if not title:
        return None

    query = Book.query.filter(db.func.lower(Book.title) == title.lower())
    if volume is not None:
        query = query.filter(Book.volume == volume)
    else:
        query = query.filter(Book.volume.is_(None))
    if exclude_id:
        query = query.filter(Book.id != exclude_id)
    return query.first()


def find_duplicate(data, exclude_id=None):
    """Single entry point for the duplicate detection policy, applied
    everywhere a book can be created (manual form, scan, import): see
    Administration > Settings to make it configurable.

    Returns a tuple (existing_book_or_None, criterion_or_None), the
    criterion being "isbn" or "title" to allow a message tailored to the
    user.
    """
    policy = settings_service.get_setting("duplicate_detection", "isbn_and_title")
    if policy == "disabled":
        return None, None

    duplicate = find_duplicate_by_isbn(data.get("isbn"), exclude_id=exclude_id)
    if duplicate:
        return duplicate, "isbn"

    if policy == "isbn_only":
        return None, None

    # Fall back to title + volume only if no ISBN was entered: an ISBN
    # entered but different from an existing book should not trigger a
    # false alert based on title resemblance alone.
    if not (data.get("isbn") or "").strip():
        duplicate = _find_duplicate_by_title_volume(
            data.get("title"), data.get("volume"), exclude_id=exclude_id
        )
        if duplicate:
            return duplicate, "title"

    return None, None
