from app.models import Series
from app.services import book_service, stats_service


def _book(**overrides):
    data = {"title": "Book", "item_type": "BD", "authors": [], "tags": []}
    data.update(overrides)
    return book_service.create_book(data)


def test_collection_stats_empty(app, db):
    stats = stats_service.collection_stats()
    assert stats["total"] == 0
    assert stats["read_count"] == 0
    assert stats["by_item_type"] == []


def test_collection_stats_counts_read_and_unread(app, db):
    read = _book(title="Read one")
    book_service.toggle_read(read)
    _book(title="Unread one")

    stats = stats_service.collection_stats()

    assert stats["total"] == 2
    assert stats["read_count"] == 1
    assert stats["unread_count"] == 1


def test_collection_stats_by_item_type(app, db):
    _book(title="A", item_type="BD")
    _book(title="B", item_type="BD")
    _book(title="C", item_type="Manga")

    stats = stats_service.collection_stats()

    assert dict(stats["by_item_type"]) == {"BD": 2, "Manga": 1}


def test_collection_stats_by_publisher_and_author(app, db):
    _book(title="A", publisher="Dargaud", authors=["Jean Van Hamme"])
    _book(title="B", publisher="Dargaud", authors=["Jean Van Hamme", "William Vance"])

    stats = stats_service.collection_stats()

    assert dict(stats["by_publisher"]) == {"Dargaud": 2}
    assert dict(stats["by_author"]) == {"Jean Van Hamme": 2, "William Vance": 1}


def test_collection_stats_by_decade_parses_leading_year(app, db):
    _book(title="A", publication_date="2003")
    _book(title="B", publication_date="12/2019")
    _book(title="C", publication_date="unknown")

    stats = stats_service.collection_stats()

    assert dict(stats["by_decade"]) == {"2000s": 1, "2010s": 1}


def test_collection_stats_series_completion(app, db):
    complete = Series(name="Complete", expected_volume_count=2)
    incomplete = Series(name="Incomplete", expected_volume_count=3)
    db.session.add_all([complete, incomplete])
    db.session.commit()

    _book(title="C1", series_id=complete.id, volume=1)
    _book(title="C2", series_id=complete.id, volume=2)
    _book(title="I1", series_id=incomplete.id, volume=1)

    stats = stats_service.collection_stats()

    assert stats["series_count"] == 2
    assert stats["tracked_series_count"] == 2
    assert stats["complete_series_count"] == 1
