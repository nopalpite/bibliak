from app.models import Book
from app.services import book_service, settings_service


def _minimal_data(**overrides):
    data = {
        "title": "Le Jour du Soleil Noir",
        "item_type": "BD",
        "isbn": None,
        "volume": 1,
        "authors": [],
        "tags": [],
    }
    data.update(overrides)
    return data


def test_create_book_resolves_related_entities_on_the_fly(app, db):
    """Authors, series, publisher, tags, location should be created if they
    don't exist yet — no prior setup step required."""
    data = _minimal_data(
        series="XIII",
        publisher="Dargaud",
        authors=["Jean Van Hamme", "William Vance"],
        tags=["SF", "classique"],
        location="Salon",
    )

    book = book_service.create_book(data)

    assert book.id is not None
    assert book.series.name == "XIII"
    assert book.publisher.name == "Dargaud"
    assert {a.full_name for a in book.authors} == {"Jean Van Hamme", "William Vance"}
    assert {t.label for t in book.tags} == {"SF", "classique"}
    assert book.location.label == "Salon"


def test_create_book_reuses_existing_entities(app, db, series, publisher):
    """A second book pointing at the same series/publisher by id must reuse
    them rather than creating duplicates."""
    book = book_service.create_book(
        _minimal_data(series_id=series.id, publisher_id=publisher.id)
    )

    assert book.series_id == series.id
    assert book.publisher_id == publisher.id


def test_update_book_never_resets_read_status_from_the_edit_form(app, db):
    """The edit form doesn't send a "read" field: editing a book must not
    silently mark it unread again."""
    book = book_service.create_book(_minimal_data(read=True))
    assert book.read is True

    book_service.update_book(book, _minimal_data(title="Nouveau titre"))

    assert book.read is True
    assert book.title == "Nouveau titre"


def test_create_book_keeps_volume_zero(app, db):
    """Regression test: `data.get("volume") or None` used to silently
    discard a legitimately entered volume 0 (e.g. a prequel/tome 0), since
    0 is falsy in Python. The form's stepper explicitly allows 0."""
    book = book_service.create_book(_minimal_data(volume=0))
    assert book.volume == 0


def test_update_book_keeps_volume_zero(app, db):
    book = book_service.create_book(_minimal_data(volume=1))
    book_service.update_book(book, _minimal_data(volume=0))
    assert book.volume == 0


def test_toggle_read(app, db):
    book = book_service.create_book(_minimal_data())
    assert book.read is False

    book_service.toggle_read(book)
    assert book.read is True

    book_service.toggle_read(book)
    assert book.read is False


def test_delete_book(app, db):
    book = book_service.create_book(_minimal_data())
    book_id = book.id

    book_service.delete_book(book)

    assert db.session.get(Book, book_id) is None


def test_bulk_delete(app, db):
    a = book_service.create_book(_minimal_data(title="A"))
    b = book_service.create_book(_minimal_data(title="B"))
    kept = book_service.create_book(_minimal_data(title="C"))

    deleted_count = book_service.bulk_delete([a.id, b.id])

    assert deleted_count == 2
    assert db.session.get(Book, a.id) is None
    assert db.session.get(Book, b.id) is None
    assert db.session.get(Book, kept.id) is not None


def test_bulk_delete_with_empty_selection_is_a_noop(app, db):
    book = book_service.create_book(_minimal_data())
    assert book_service.bulk_delete([]) == 0
    assert db.session.get(Book, book.id) is not None


def test_bulk_set_location(app, db):
    a = book_service.create_book(_minimal_data(title="A"))
    b = book_service.create_book(_minimal_data(title="B"))

    count = book_service.bulk_set_location([a.id, b.id], "Salon")

    assert count == 2
    assert a.location.label == "Salon"
    assert b.location.label == "Salon"
    assert a.location_id == b.location_id  # same Location row, not duplicated


def test_bulk_set_location_blank_label_is_a_noop(app, db):
    book = book_service.create_book(_minimal_data())
    assert book_service.bulk_set_location([book.id], "  ") == 0
    assert book.location is None


def test_bulk_add_tag(app, db):
    a = book_service.create_book(_minimal_data(title="A", tags=["existing"]))
    b = book_service.create_book(_minimal_data(title="B"))

    count = book_service.bulk_add_tag([a.id, b.id], "new-tag")

    assert count == 2
    assert {t.label for t in a.tags} == {"existing", "new-tag"}  # not duplicated
    assert {t.label for t in b.tags} == {"new-tag"}


def test_bulk_add_tag_blank_label_is_a_noop(app, db):
    book = book_service.create_book(_minimal_data())
    assert book_service.bulk_add_tag([book.id], "") == 0
    assert book.tags == []


def test_find_duplicate_by_isbn_takes_priority_over_title(app, db):
    book_service.create_book(_minimal_data(isbn="9782505004900", volume=1))

    duplicate, criterion = book_service.find_duplicate(
        {"title": "Titre différent", "isbn": "9782505004900", "volume": 2}
    )

    assert duplicate is not None
    assert criterion == "isbn"


def test_find_duplicate_falls_back_to_title_and_volume_when_isbn_missing(app, db):
    book_service.create_book(_minimal_data(title="XIII", volume=1, isbn=None))

    duplicate, criterion = book_service.find_duplicate(
        {"title": "xiii", "isbn": "", "volume": 1}
    )

    assert duplicate is not None
    assert criterion == "title"


def test_find_duplicate_title_match_is_case_insensitive(app, db):
    book_service.create_book(_minimal_data(title="XIII", volume=1, isbn=None))

    duplicate, _criterion = book_service.find_duplicate(
        {"title": "xiii", "isbn": "", "volume": 1}
    )

    assert duplicate is not None


def test_find_duplicate_different_isbn_does_not_trigger_title_fallback(app, db):
    """A book with the same title but an explicitly different ISBN is not a
    false-positive duplicate."""
    book_service.create_book(_minimal_data(title="XIII", volume=1, isbn="1111111111111"))

    duplicate, _criterion = book_service.find_duplicate(
        {"title": "XIII", "isbn": "2222222222222", "volume": 1}
    )

    assert duplicate is None


def test_find_duplicate_respects_isbn_only_policy(app, db):
    settings_service.set_setting("duplicate_detection", "isbn_only")
    book_service.create_book(_minimal_data(title="XIII", volume=1, isbn=None))

    duplicate, _criterion = book_service.find_duplicate(
        {"title": "XIII", "isbn": "", "volume": 1}
    )

    assert duplicate is None


def test_find_duplicate_respects_disabled_policy(app, db):
    settings_service.set_setting("duplicate_detection", "disabled")
    book_service.create_book(_minimal_data(isbn="9782505004900"))

    duplicate, _criterion = book_service.find_duplicate(
        {"title": "Le Jour du Soleil Noir", "isbn": "9782505004900", "volume": 1}
    )

    assert duplicate is None


def test_find_duplicate_matches_volume_zero(app, db):
    """Regression test: `if volume:` treated volume 0 the same as "no
    volume", so it filtered by Book.volume IS NULL instead of == 0 —
    missing a real duplicate and risking a false positive against an
    unrelated volume-less book of the same title."""
    book_service.create_book(_minimal_data(title="XIII", volume=0, isbn=None))

    duplicate, criterion = book_service.find_duplicate(
        {"title": "XIII", "isbn": "", "volume": 0}
    )

    assert duplicate is not None
    assert criterion == "title"


def test_find_duplicate_excludes_the_book_being_edited(app, db):
    book = book_service.create_book(_minimal_data(isbn="9782505004900"))

    duplicate, _criterion = book_service.find_duplicate(
        {"title": book.title, "isbn": "9782505004900", "volume": book.volume},
        exclude_id=book.id,
    )

    assert duplicate is None
