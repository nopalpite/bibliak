import io
import json
import re

from app.models import Book, Tag


def test_index_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Collection".encode() in response.data


def test_add_book_page_loads(client):
    response = client.get("/books/new")
    assert response.status_code == 200


def test_add_book_full_cycle(client, db):
    response = client.post(
        "/books/new",
        data={"title": "Le Jour du Soleil Noir", "item_type": "BD", "authors": "", "tags": ""},
    )
    assert response.status_code == 302

    detail = client.get(response.location)
    assert detail.status_code == 200
    assert "Le Jour du Soleil Noir".encode() in detail.data


def test_add_book_without_title_shows_error_instead_of_crashing(client, db):
    response = client.post("/books/new", data={"title": "", "item_type": "BD"})
    assert response.status_code == 200  # re-renders the form, no redirect
    assert Book.query.count() == 0


def test_edit_book(client, db):
    create = client.post("/books/new", data={"title": "Titre original", "item_type": "BD"})
    book_id = create.location.rstrip("/").rsplit("/", 1)[-1]

    response = client.post(
        f"/books/{book_id}/edit",
        data={"title": "Titre modifié", "item_type": "BD"},
    )
    assert response.status_code == 302

    detail = client.get(response.location)
    assert "Titre modifié".encode() in detail.data


def test_editing_a_book_preserves_an_item_type_removed_from_admin(client, db):
    """Regression test: the item_type <select> only marks an <option>
    selected if the book's stored value is still in the configurable list.
    If it was removed from Administration > References since, none of the
    options matched, so the browser silently defaulted to the first option
    — saving the form for *any* unrelated reason silently rewrote the
    book's type to something else entirely, with no warning."""
    create = client.post("/books/new", data={"title": "Vieux type", "item_type": "Fanzine"})
    book_id = create.location.rstrip("/").rsplit("/", 1)[-1]

    edit_page = client.get(f"/books/{book_id}/edit")
    html = edit_page.get_data(as_text=True)
    assert '<option value="Fanzine" selected>Fanzine</option>' in html

    response = client.post(
        f"/books/{book_id}/edit",
        data={"title": "Vieux type", "item_type": "Fanzine", "condition": "Bon état"},
    )
    assert response.status_code == 302

    book = db.session.get(Book, int(book_id))
    assert book.item_type == "Fanzine"


def test_toggle_read_route(client, db):
    create = client.post("/books/new", data={"title": "Un livre", "item_type": "BD"})
    book_id = int(create.location.rstrip("/").rsplit("/", 1)[-1])

    book = db.session.get(Book, book_id)
    assert book.read is False

    client.post(f"/books/{book_id}/read")
    db.session.refresh(book)
    assert book.read is True


def test_delete_book_route(client, db):
    create = client.post("/books/new", data={"title": "À supprimer", "item_type": "BD"})
    book_id = int(create.location.rstrip("/").rsplit("/", 1)[-1])

    response = client.post(f"/books/{book_id}/delete")
    assert response.status_code == 302
    assert db.session.get(Book, book_id) is None


def test_bulk_delete_route(client, db):
    a = int(client.post("/books/new", data={"title": "A", "item_type": "BD"}).location.rstrip("/").rsplit("/", 1)[-1])
    b = int(client.post("/books/new", data={"title": "B", "item_type": "BD"}).location.rstrip("/").rsplit("/", 1)[-1])

    response = client.post("/books/bulk-delete", data={"book_ids": [str(a), str(b)]})

    assert response.status_code == 302
    assert db.session.get(Book, a) is None
    assert db.session.get(Book, b) is None


def test_bulk_set_location_route(client, db):
    a = int(client.post("/books/new", data={"title": "A", "item_type": "BD"}).location.rstrip("/").rsplit("/", 1)[-1])

    response = client.post("/books/bulk-set-location", data={"book_ids": [str(a)], "location": "Salon"})

    assert response.status_code == 302
    book = db.session.get(Book, a)
    assert book.location.label == "Salon"


def test_bulk_add_tag_route(client, db):
    a = int(client.post("/books/new", data={"title": "A", "item_type": "BD"}).location.rstrip("/").rsplit("/", 1)[-1])

    response = client.post("/books/bulk-add-tag", data={"book_ids": [str(a)], "tag": "favoris"})

    assert response.status_code == 302
    book = db.session.get(Book, a)
    assert {t.label for t in book.tags} == {"favoris"}


def test_collection_page_offers_bulk_selection(client, db):
    client.post("/books/new", data={"title": "A", "item_type": "BD"})
    response = client.get("/")
    html = response.get_data(as_text=True)
    assert 'name="book_ids"' in html
    assert 'id="bulk-actions-form"' in html


def test_delete_confirm_survives_quotes_and_apostrophes_in_title(client, db):
    """Regression test: the delete form's onsubmit embeds a |tojson payload.
    tojson wraps its output in literal double quotes, so if the surrounding
    HTML attribute is also double-quoted, a title containing a quote breaks
    the attribute (and silently kills the confirm() dialog). The attribute
    must be single-quoted and the payload must stay valid JSON no matter
    what's in the title."""
    tricky_title = """Test O'Brien "Special" Édition"""
    create = client.post("/books/new", data={"title": tricky_title, "item_type": "BD"})
    book_id = int(create.location.rstrip("/").rsplit("/", 1)[-1])

    html = client.get(f"/books/{book_id}").get_data(as_text=True)

    match = re.search(r"onsubmit='return confirm\((.*?)\);'", html)
    assert match, "delete form's onsubmit attribute is missing or malformed"
    message = json.loads(match.group(1))
    assert tricky_title in message


def test_reference_delete_confirm_survives_quotes_and_apostrophes_in_name(client, db):
    tricky_label = """Tag O'Brien "Special\""""
    tag = Tag(label=tricky_label)
    db.session.add(tag)
    db.session.commit()

    html = client.get("/admin/tab/references").get_data(as_text=True)

    match = re.search(r"onsubmit='return confirm\((.*?)\);'", html)
    assert match, "reference delete form's onsubmit attribute is missing or malformed"
    message = json.loads(match.group(1))
    assert tricky_label in message


def test_duplicate_submission_is_blocked_then_can_be_confirmed(client, db):
    client.post("/books/new", data={"title": "XIII", "item_type": "BD", "volume": "1"})

    blocked = client.post("/books/new", data={"title": "XIII", "item_type": "BD", "volume": "1"})
    assert blocked.status_code == 200  # re-renders the form with a duplicate warning
    assert Book.query.count() == 1

    confirmed = client.post(
        "/books/new",
        data={"title": "XIII", "item_type": "BD", "volume": "1", "ignore_duplicate": "1"},
    )
    assert confirmed.status_code == 302
    assert Book.query.count() == 2


def test_quick_create_series_route(client, db):
    response = client.post("/books/series/quick-create", data={"name": "Blacksad"})
    assert response.status_code == 200
    assert "Blacksad".encode() in response.data


def test_quick_create_tag_route(client, db):
    response = client.post("/books/tags/quick-create", data={"name": "favoris"})
    assert response.status_code == 200
    assert b"favoris" in response.data
    assert Tag.query.filter_by(label="favoris").first() is not None


def test_quick_create_tag_keeps_already_selected_tags(client, db):
    """The "+" button must not lose tags already picked from the dropdown
    before the new one is created — the form sends them via "selected"."""
    response = client.post(
        "/books/tags/quick-create", data={"name": "new-tag", "selected": "existing-tag"}
    )
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'value="existing-tag,new-tag"' in html


def test_quick_create_tag_reuses_an_existing_tag_instead_of_duplicating(client, db):
    client.post("/books/tags/quick-create", data={"name": "favoris"})
    response = client.post("/books/tags/quick-create", data={"name": "favoris"})
    assert response.status_code == 200
    assert Tag.query.filter_by(label="favoris").count() == 1


def test_book_form_offers_a_tags_dropdown_with_existing_tags(client, db):
    db.session.add(Tag(label="humour"))
    db.session.commit()

    html = client.get("/books/new").get_data(as_text=True)
    assert 'id="tags-select"' in html
    assert '<option value="humour">humour</option>' in html


def test_stats_page_loads_with_empty_collection(client, db):
    response = client.get("/stats")
    assert response.status_code == 200


def test_stats_page_loads_with_books(client, db):
    client.post("/books/new", data={"title": "XIII", "item_type": "BD"})
    response = client.get("/stats")
    assert response.status_code == 200
    assert b"XIII" not in response.data  # aggregate page, not a book list
    assert "1".encode() in response.data


def test_scan_page_loads(client):
    response = client.get("/scan/")
    assert response.status_code == 200


def test_admin_home_and_tabs_load(client):
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/tab/settings").status_code == 200
    assert client.get("/admin/tab/references").status_code == 200
    assert client.get("/admin/tab/export_import").status_code == 200


def test_index_page_is_english_by_default(client):
    response = client.get("/")
    assert "No book matches".encode() in response.data


def test_admin_language_setting_changes_rendered_text(client, db):
    client.post(
        "/admin/settings",
        data={
            "language": "fr",
            "default_view": "grid",
            "duplicate_detection": "isbn_and_title",
        },
    )

    response = client.get("/")
    assert "Aucun ouvrage ne correspond".encode() in response.data


def test_index_page_uses_classic_theme_by_default(client, db):
    response = client.get("/")
    assert 'class="scroll-smooth theme-classic"' in response.get_data(as_text=True)


def test_admin_theme_setting_changes_the_rendered_theme_class(client, db):
    client.post(
        "/admin/settings",
        data={
            "language": "en",
            "default_view": "grid",
            "duplicate_detection": "isbn_and_title",
            "theme": "slate",
        },
    )

    response = client.get("/")
    assert 'class="scroll-smooth theme-slate"' in response.get_data(as_text=True)


def test_export_json_contains_created_book(client, db):
    client.post("/books/new", data={"title": "Export moi", "item_type": "BD"})

    response = client.get("/admin/export.json")
    assert response.status_code == 200
    payload = json.loads(response.data)
    assert any(item["title"] == "Export moi" for item in payload)


def test_import_json_skips_existing_duplicate(client, db):
    client.post("/books/new", data={"title": "Déjà là", "item_type": "BD", "volume": "1"})

    backup = json.dumps([{"title": "Déjà là", "item_type": "BD", "volume": 1}]).encode()
    response = client.post(
        "/admin/import",
        data={"file": (io.BytesIO(backup), "backup.json")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert Book.query.count() == 1


def test_export_csv_contains_created_book(client, db):
    client.post(
        "/books/new",
        data={"title": "Export CSV", "item_type": "BD", "authors": "Jean Van Hamme, William Vance"},
    )

    response = client.get("/admin/export.csv")
    assert response.status_code == 200
    assert b"Export CSV" in response.data
    assert b"Jean Van Hamme, William Vance" in response.data


def test_import_csv_creates_a_book_with_authors_and_tags(client, db):
    csv_content = (
        "title,item_type,isbn,series,volume,authors,publisher,publication_date,summary,"
        "cover_image,location,condition,personal_notes,read,tags\r\n"
        'XIII,BD,,,"1","Jean Van Hamme, William Vance",Dargaud,1984,,,,,,"true","action, bd"\r\n'
    ).encode("utf-8-sig")

    response = client.post(
        "/admin/import-csv",
        data={"file": (io.BytesIO(csv_content), "backup.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    book = Book.query.filter_by(title="XIII").first()
    assert book is not None
    assert book.volume == 1
    assert book.read is True
    assert {a.full_name for a in book.authors} == {"Jean Van Hamme", "William Vance"}
    assert {t.label for t in book.tags} == {"action", "bd"}
    assert book.publisher.name == "Dargaud"


def test_import_csv_skips_existing_duplicate(client, db):
    client.post("/books/new", data={"title": "Déjà là", "item_type": "BD", "volume": "1"})

    csv_content = "title,item_type,volume\r\nDéjà là,BD,1\r\n".encode("utf-8-sig")
    response = client.post(
        "/admin/import-csv",
        data={"file": (io.BytesIO(csv_content), "backup.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert Book.query.count() == 1


def test_csv_export_then_import_round_trips_a_book(client, db):
    """The export format must be re-importable as-is."""
    client.post(
        "/books/new",
        data={
            "title": "Round Trip",
            "item_type": "BD",
            "authors": "Author One, Author Two",
            "tags": "sf, classique",
            "volume": "2",
        },
    )
    exported = client.get("/admin/export.csv").data

    for book in Book.query.all():
        db.session.delete(book)
    db.session.commit()

    response = client.post(
        "/admin/import-csv",
        data={"file": (io.BytesIO(exported), "backup.csv")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    book = Book.query.filter_by(title="Round Trip").first()
    assert book is not None
    assert book.volume == 2
    assert {a.full_name for a in book.authors} == {"Author One", "Author Two"}
    assert {t.label for t in book.tags} == {"sf", "classique"}
