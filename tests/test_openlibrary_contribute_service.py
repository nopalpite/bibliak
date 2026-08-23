import pytest
import requests

from app.models import Author, Book
from app.services import openlibrary_contribute_service as ol_service
from app.services import settings_service


@pytest.fixture(autouse=True)
def _configured_and_enabled(app):
    app.config["OPENLIBRARY_ACCESS_KEY"] = "test-access"
    app.config["OPENLIBRARY_SECRET_KEY"] = "test-secret"


def _book(db, title="XIII", isbn="9782505004900", author_name="Jean Van Hamme", cover_image=None):
    book = Book(title=title, item_type="BD", isbn=isbn, cover_image=cover_image)
    if author_name:
        author = Author(full_name=author_name)
        db.session.add(author)
        book.authors.append(author)
    db.session.add(book)
    db.session.commit()
    return book


def _make_ok(monkeypatch):
    monkeypatch.setattr(ol_service, "_login", lambda session: True)
    monkeypatch.setattr(ol_service, "_find_author_key", lambda session, name: None)

    class FakeResponse:
        url = "https://openlibrary.org/books/OL123M/XIII"
        ok = True

    monkeypatch.setattr(requests.Session, "post", lambda self, *a, **k: FakeResponse())


def test_is_configured_true_with_both_keys(app):
    assert ol_service.is_configured() is True


def test_is_configured_false_when_a_key_is_missing(app):
    app.config["OPENLIBRARY_SECRET_KEY"] = ""
    assert ol_service.is_configured() is False


def test_is_enabled_false_by_default_even_when_configured(app, db):
    assert ol_service.is_configured() is True
    assert ol_service.is_enabled() is False  # setting defaults to off


def test_is_enabled_true_once_configured_and_turned_on(app, db):
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    assert ol_service.is_enabled() is True


def test_contribute_book_not_configured(app, db):
    app.config["OPENLIBRARY_ACCESS_KEY"] = ""
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    book = _book(db)
    assert ol_service.contribute_book(book) == ("not_configured", None, None)


def test_contribute_book_disabled_by_setting(app, db):
    settings_service.set_setting("openlibrary_contribution_enabled", False)
    book = _book(db)
    assert ol_service.contribute_book(book) == ("disabled", None, None)


def test_contribute_book_missing_author(app, db):
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    book = _book(db, author_name=None)
    assert ol_service.contribute_book(book) == ("missing_author", None, None)


def test_contribute_book_rejects_single_word_author_name(app, db):
    """Open Library's /books/add form requires a first + last name."""
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    book = _book(db, author_name="Prince")
    assert ol_service.contribute_book(book) == ("missing_author", None, None)


def test_contribute_book_missing_isbn(app, db):
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    book = _book(db, isbn=None)
    assert ol_service.contribute_book(book) == ("missing_isbn", None, None)


def test_contribute_book_auth_failed(app, db, monkeypatch):
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    monkeypatch.setattr(ol_service, "_login", lambda session: False)
    book = _book(db)
    assert ol_service.contribute_book(book) == ("auth_failed", None, None)


def test_contribute_book_network_error(app, db, monkeypatch):
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    monkeypatch.setattr(ol_service, "_login", lambda session: True)
    monkeypatch.setattr(ol_service, "_find_author_key", lambda session, name: None)

    def raise_error(self, *args, **kwargs):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(requests.Session, "post", raise_error)

    book = _book(db)
    assert ol_service.contribute_book(book) == ("network_error", None, None)


def test_contribute_book_ok_without_a_cover(app, db, monkeypatch):
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    _make_ok(monkeypatch)

    book = _book(db)  # no cover_image
    assert ol_service.contribute_book(book) == ("ok", "OL123M", None)


def test_contribute_book_rejected_when_response_has_no_edition_olid(app, db, monkeypatch):
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    monkeypatch.setattr(ol_service, "_login", lambda session: True)
    monkeypatch.setattr(ol_service, "_find_author_key", lambda session, name: None)

    class FakeResponse:
        url = "https://openlibrary.org/account/login"  # didn't redirect to a new edition

    monkeypatch.setattr(requests.Session, "post", lambda self, *a, **k: FakeResponse())

    book = _book(db)
    assert ol_service.contribute_book(book) == ("rejected", None, None)


def test_contribute_book_uploads_the_cover_when_present(app, db, monkeypatch, tmp_path):
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    app.config["COVERS_DIR"] = tmp_path
    (tmp_path / "cover.jpg").write_bytes(b"fake-jpeg-bytes")

    monkeypatch.setattr(ol_service, "_login", lambda session: True)
    monkeypatch.setattr(ol_service, "_find_author_key", lambda session, name: None)
    monkeypatch.setattr(ol_service, "_add_cover", lambda session, olid, cover_path: True)

    class FakeResponse:
        url = "https://openlibrary.org/books/OL123M/XIII"

    monkeypatch.setattr(requests.Session, "post", lambda self, *a, **k: FakeResponse())

    book = _book(db, cover_image="cover.jpg")
    assert ol_service.contribute_book(book) == ("ok", "OL123M", True)


def test_contribute_book_reports_cover_upload_failure_without_failing_the_whole_thing(app, db, monkeypatch, tmp_path):
    settings_service.set_setting("openlibrary_contribution_enabled", True)
    app.config["COVERS_DIR"] = tmp_path

    monkeypatch.setattr(ol_service, "_login", lambda session: True)
    monkeypatch.setattr(ol_service, "_find_author_key", lambda session, name: None)
    monkeypatch.setattr(ol_service, "_add_cover", lambda session, olid, cover_path: False)

    class FakeResponse:
        url = "https://openlibrary.org/books/OL123M/XIII"

    monkeypatch.setattr(requests.Session, "post", lambda self, *a, **k: FakeResponse())

    book = _book(db, cover_image="missing-cover.jpg")
    assert ol_service.contribute_book(book) == ("ok", "OL123M", False)


def test_add_cover_returns_false_when_file_is_missing(app, tmp_path):
    session = requests.Session()
    assert ol_service._add_cover(session, "OL123M", tmp_path / "does-not-exist.jpg") is False


def test_primary_identifier_prefers_isbn13():
    assert ol_service._primary_identifier("978-2-505-00490-0") == ("isbn_13", "9782505004900")


def test_primary_identifier_falls_back_to_isbn10():
    assert ol_service._primary_identifier("2-505-00490-1") == ("isbn_10", "2505004901")


def test_primary_identifier_none_when_unusable():
    assert ol_service._primary_identifier("") == (None, None)
    assert ol_service._primary_identifier(None) == (None, None)
