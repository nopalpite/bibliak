from app.services import book_service, search_service


def _book(**overrides):
    data = {"title": "Book", "item_type": "BD", "authors": [], "tags": []}
    data.update(overrides)
    return book_service.create_book(data)


def test_search_by_text_matches_title(app, db):
    _book(title="Le Jour du Soleil Noir")
    _book(title="Complot")

    results = search_service.search_books(q="Soleil")

    assert [b.title for b in results] == ["Le Jour du Soleil Noir"]


def test_search_filters_by_item_type(app, db):
    _book(title="A", item_type="BD")
    _book(title="B", item_type="Manga")

    results = search_service.search_books(item_type="Manga")

    assert [b.title for b in results] == ["B"]


def test_search_filters_by_read_status(app, db):
    read_book = _book(title="Read one")
    book_service.toggle_read(read_book)
    _book(title="Unread one")

    unread = search_service.search_books(read_status="unread")
    read = search_service.search_books(read_status="read")

    assert [b.title for b in unread] == ["Unread one"]
    assert [b.title for b in read] == ["Read one"]


def test_search_sort_by_title(app, db):
    _book(title="Zorro")
    _book(title="Astérix")

    results = search_service.search_books(sort="title")

    assert [b.title for b in results] == ["Astérix", "Zorro"]


def test_group_by_series_separates_books_without_series(app, db):
    _book(title="XIII 1", series="XIII", volume=1)
    _book(title="XIII 2", series="XIII", volume=2)
    _book(title="Standalone")

    groups = search_service.group_by_series(search_service.search_books())

    assert len(groups) == 2
    with_series = next(g for g in groups if g["series"] is not None)
    without_series = next(g for g in groups if g["series"] is None)
    assert with_series["series"].name == "XIII"
    assert [b.volume for b in with_series["books"]] == [1, 2]
    assert [b.title for b in without_series["books"]] == ["Standalone"]
