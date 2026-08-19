from app.services import isbn_service


def test_source_order_defaults_to_openlibrary_first():
    assert isbn_service.source_order("openlibrary") == ["openlibrary", "googlebooks"]


def test_source_order_can_be_reversed():
    assert isbn_service.source_order("googlebooks") == ["googlebooks", "openlibrary"]


def test_attempt_source_ok(monkeypatch):
    monkeypatch.setattr(isbn_service, "_from_open_library", lambda isbn: {"title": "XIII"})
    status, result = isbn_service.attempt_source("978-2505004900", "openlibrary")
    assert status == "ok"
    assert result["title"] == "XIII"
    assert result["isbn"] == "9782505004900"  # dashes stripped


def test_attempt_source_not_found(monkeypatch):
    monkeypatch.setattr(isbn_service, "_from_open_library", lambda isbn: None)
    status, result = isbn_service.attempt_source("9782505004900", "openlibrary")
    assert status == "not_found"
    assert result is None


def test_attempt_source_network_error(monkeypatch):
    def raise_error(isbn):
        raise isbn_service.requests.ConnectionError("boom")

    monkeypatch.setattr(isbn_service, "_from_open_library", raise_error)
    status, result = isbn_service.attempt_source("9782505004900", "openlibrary")
    assert status == "network_error"
    assert result is None


def _patch_attempt_source(monkeypatch, outcomes):
    """outcomes: list of (status, result) tuples returned on successive calls."""
    calls = iter(outcomes)

    def fake_attempt_source(isbn, source_key, google_api_key=None):
        return next(calls)

    monkeypatch.setattr("app.routes.scan.attempt_source", fake_attempt_source)


def test_search_succeeds_on_first_try(client, db, monkeypatch):
    _patch_attempt_source(monkeypatch, [("ok", {"title": "XIII", "source": "Open Library"})])

    response = client.post("/scan/search", data={"isbn": "9782505004900"})
    assert response.status_code == 200
    assert "XIII".encode() in response.data


def test_search_shows_a_retrying_message_then_succeeds_on_the_next_step(client, db, monkeypatch):
    _patch_attempt_source(monkeypatch, [("network_error", None)])

    first = client.post("/scan/search", data={"isbn": "9782505004900"})
    assert first.status_code == 200
    html = first.get_data(as_text=True)
    assert "Open Library" in html
    assert "1/5" not in html and "2/5" in html  # attempt shown is the upcoming one

    _patch_attempt_source(monkeypatch, [("ok", {"title": "XIII", "source": "Open Library"})])
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


def test_search_falls_back_to_second_source_after_max_attempts(client, db, monkeypatch):
    outcomes = [("network_error", None)] * isbn_service.ISBN_SEARCH_MAX_ATTEMPTS + [
        ("ok", {"title": "Found via fallback", "source": "Google Books"})
    ]
    _patch_attempt_source(monkeypatch, outcomes)

    first = client.post("/scan/search", data={"isbn": "9782505004900"})
    final = _drive_to_completion(client, first)

    assert final.status_code == 200
    assert "Found via fallback".encode() in final.data


def test_search_gives_up_after_both_sources_exhaust_retries(client, db, monkeypatch):
    outcomes = [("network_error", None)] * (isbn_service.ISBN_SEARCH_MAX_ATTEMPTS * 2)
    _patch_attempt_source(monkeypatch, outcomes)

    first = client.post("/scan/search", data={"isbn": "9782505004900"})
    final = _drive_to_completion(client, first)

    assert final.status_code == 200
    assert f"after {isbn_service.ISBN_SEARCH_MAX_ATTEMPTS} attempts each".encode() in final.data


def test_retry_without_prior_search_shows_expired_message(client, db):
    response = client.post("/scan/search/retry")
    assert response.status_code == 200
    assert "expired".encode() in response.data
