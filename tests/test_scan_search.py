from app.services import isbn_service


def test_attempt_search_ok(monkeypatch):
    monkeypatch.setattr(isbn_service, "_from_open_library", lambda isbn: {"title": "XIII"})
    status, result = isbn_service.attempt_search("978-2505004900")
    assert status == "ok"
    assert result["title"] == "XIII"
    assert result["isbn"] == "9782505004900"  # dashes stripped


def test_attempt_search_not_found(monkeypatch):
    monkeypatch.setattr(isbn_service, "_from_open_library", lambda isbn: None)
    status, result = isbn_service.attempt_search("9782505004900")
    assert status == "not_found"
    assert result is None


def test_attempt_search_network_error(monkeypatch):
    def raise_error(isbn):
        raise isbn_service.requests.ConnectionError("boom")

    monkeypatch.setattr(isbn_service, "_from_open_library", raise_error)
    status, result = isbn_service.attempt_search("9782505004900")
    assert status == "network_error"
    assert result is None


def _patch_attempt_search(monkeypatch, outcomes):
    """outcomes: list of (status, result) tuples returned on successive calls."""
    calls = iter(outcomes)

    def fake_attempt_search(isbn):
        return next(calls)

    monkeypatch.setattr("app.routes.scan.attempt_search", fake_attempt_search)


def test_search_succeeds_on_first_try(client, db, monkeypatch):
    _patch_attempt_search(monkeypatch, [("ok", {"title": "XIII", "source": "Open Library"})])

    response = client.post("/scan/search", data={"isbn": "9782505004900"})
    assert response.status_code == 200
    assert "XIII".encode() in response.data


def test_search_shows_a_retrying_message_then_succeeds_on_the_next_step(client, db, monkeypatch):
    _patch_attempt_search(monkeypatch, [("network_error", None)])

    first = client.post("/scan/search", data={"isbn": "9782505004900"})
    assert first.status_code == 200
    html = first.get_data(as_text=True)
    assert "Open Library" in html
    assert "1/5" not in html and "2/5" in html  # attempt shown is the upcoming one

    _patch_attempt_search(monkeypatch, [("ok", {"title": "XIII", "source": "Open Library"})])
    second = client.post("/scan/search/retry")
    assert second.status_code == 200
    assert "XIII".encode() in second.data


def _drive_to_completion(client, response, max_steps=20):
    """Keeps POSTing to the retry endpoint as long as the response is a
    "retrying" fragment (identified by its auto-continuing htmx trigger)."""
    steps = 0
    while b'hx-trigger="load delay:' in response.data:
        steps += 1
        assert steps <= max_steps, "search never reached a final result"
        response = client.post("/scan/search/retry")
    return response


def test_search_gives_up_after_max_attempts(client, db, monkeypatch):
    outcomes = [("network_error", None)] * isbn_service.ISBN_SEARCH_MAX_ATTEMPTS
    _patch_attempt_search(monkeypatch, outcomes)

    first = client.post("/scan/search", data={"isbn": "9782505004900"})
    final = _drive_to_completion(client, first)

    assert final.status_code == 200
    assert f"after {isbn_service.ISBN_SEARCH_MAX_ATTEMPTS} attempts".encode() in final.data


def test_search_not_found_shows_generic_message(client, db, monkeypatch):
    _patch_attempt_search(monkeypatch, [("not_found", None)])

    response = client.post("/scan/search", data={"isbn": "9782505004900"})
    assert b"No information found for this ISBN" in response.data
    assert b'hx-post="/scan/search-title"' in response.data  # title-search fallback offered


def test_search_network_error_does_not_offer_the_title_search_fallback(client, db, monkeypatch):
    """A connection problem calls for retrying, not searching by a
    different key — the fallback is specific to "not found"."""
    outcomes = [("network_error", None)] * isbn_service.ISBN_SEARCH_MAX_ATTEMPTS
    _patch_attempt_search(monkeypatch, outcomes)

    first = client.post("/scan/search", data={"isbn": "9782505004900"})
    final = _drive_to_completion(client, first)
    assert b'hx-post="/scan/search-title"' not in final.data


def test_retry_without_prior_search_shows_expired_message(client, db):
    response = client.post("/scan/search/retry")
    assert response.status_code == 200
    assert "expired".encode() in response.data


def test_search_by_title_ok(app, monkeypatch):
    fake_docs = {
        "docs": [
            {
                "title": "XIII, tome 1",
                "author_name": ["Jean Van Hamme", "William Vance"],
                "publisher": ["Dargaud"],
                "first_publish_year": 1996,
                "cover_i": 10476562,
            }
        ]
    }
    monkeypatch.setattr(
        isbn_service.requests, "get", lambda *a, **k: _FakeJsonResponse(fake_docs)
    )

    results = isbn_service.search_by_title("XIII")
    assert len(results) == 1
    assert results[0]["title"] == "XIII, tome 1"
    assert results[0]["authors"] == ["Jean Van Hamme", "William Vance"]
    assert results[0]["publisher"] == "Dargaud"
    assert results[0]["publication_date"] == "1996"
    assert results[0]["image_url"] == "https://covers.openlibrary.org/b/id/10476562-M.jpg"


def test_search_by_title_empty_title_returns_no_results(monkeypatch):
    assert isbn_service.search_by_title("") == []
    assert isbn_service.search_by_title("   ") == []


def test_search_by_title_network_error_returns_no_results(app, monkeypatch):
    def raise_error(*args, **kwargs):
        raise isbn_service.requests.ConnectionError("boom")

    monkeypatch.setattr(isbn_service.requests, "get", raise_error)
    assert isbn_service.search_by_title("XIII") == []


class _FakeJsonResponse:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


def test_search_title_route_renders_results(client, db, monkeypatch):
    monkeypatch.setattr(
        "app.routes.scan.search_by_title",
        lambda title: [{"title": "XIII", "authors": ["Jean Van Hamme"], "publisher": "Dargaud",
                         "publication_date": "1984", "image_url": None, "source": "Open Library"}],
    )
    response = client.post("/scan/search-title", data={"title": "XIII"})
    assert response.status_code == 200
    assert b"XIII" in response.data
    assert b"Dargaud" in response.data


def test_search_title_route_with_blank_title_returns_no_results(client, db):
    response = client.post("/scan/search-title", data={"title": "  "})
    assert response.status_code == 200
    assert b"card" not in response.data


def test_select_title_result_prefills_the_new_book_form(client, db):
    response = client.post(
        "/scan/select-title-result",
        data={
            "title": "XIII",
            "authors": "Jean Van Hamme, William Vance",
            "publisher": "Dargaud",
            "publication_date": "1984",
            "image_url": "",
        },
    )
    assert response.status_code == 302
    assert response.location == "/books/new"

    form = client.get("/books/new")
    html = form.get_data(as_text=True)
    assert "XIII" in html
    assert "Jean Van Hamme, William Vance" in html
