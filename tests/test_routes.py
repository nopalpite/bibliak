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
