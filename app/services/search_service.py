"""Search and filtering of the collection.

The expected volume (a few hundred items, single-user usage) does not
justify a caching or advanced indexing mechanism: a simple SQL query, with
the basic indexes set on the models, is largely sufficient.
"""

from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app.models import Author, Book, Publisher, Series, Tag

AVAILABLE_SORTS = {
    "title": (Book.title.asc(),),
    "date_added_desc": (Book.date_added.desc(),),
    "date_added_asc": (Book.date_added.asc(),),
    "publication_date": (Book.publication_date.desc(),),
}

# LIKE wildcards a typed search query must not be allowed to trigger:
# searching for a literal "_" (a real character in plenty of titles/ISBNs)
# must not match "any single character" instead.
_LIKE_ESCAPE = "\\"


def _escape_like(text):
    return (
        text.replace(_LIKE_ESCAPE, _LIKE_ESCAPE * 2)
        .replace("%", _LIKE_ESCAPE + "%")
        .replace("_", _LIKE_ESCAPE + "_")
    )


def search_books(
    q=None,
    item_type=None,
    series_id=None,
    publisher_id=None,
    tag_id=None,
    location_id=None,
    condition=None,
    read_status=None,
    sort="title",
):
    query = Book.query.options(
        selectinload(Book.authors),
        selectinload(Book.publisher),
        selectinload(Book.series),
        selectinload(Book.location),
        selectinload(Book.tags),
    )

    if q:
        pattern = f"%{_escape_like(q.strip())}%"
        query = (
            query.outerjoin(Book.authors)
            .outerjoin(Book.publisher)
            .outerjoin(Book.series)
            .filter(
                or_(
                    Book.title.ilike(pattern, escape=_LIKE_ESCAPE),
                    Book.isbn.ilike(pattern, escape=_LIKE_ESCAPE),
                    Author.full_name.ilike(pattern, escape=_LIKE_ESCAPE),
                    Publisher.name.ilike(pattern, escape=_LIKE_ESCAPE),
                    Series.name.ilike(pattern, escape=_LIKE_ESCAPE),
                )
            )
            .distinct()
        )

    if item_type:
        query = query.filter(Book.item_type == item_type)
    if series_id:
        query = query.filter(Book.series_id == series_id)
    if publisher_id:
        query = query.filter(Book.publisher_id == publisher_id)
    if location_id:
        query = query.filter(Book.location_id == location_id)
    if condition:
        query = query.filter(Book.condition == condition)
    if tag_id:
        query = query.filter(Book.tags.any(Tag.id == tag_id))
    if read_status == "unread":
        query = query.filter(Book.read.is_(False))
    elif read_status == "read":
        query = query.filter(Book.read.is_(True))

    order = AVAILABLE_SORTS.get(sort, AVAILABLE_SORTS["title"])
    return query.order_by(*order).all()


def group_by_series(books):
    """Groups a list of books by series for the "shelves" view: each series
    becomes a group, its volumes sorted by number. Books without a series
    are gathered in a last, separate group."""
    by_series = {}
    without_series = []

    for b in books:
        if b.series:
            by_series.setdefault(b.series, []).append(b)
        else:
            without_series.append(b)

    groups = []
    for series in sorted(by_series.keys(), key=lambda s: s.name.lower()):
        volumes = sorted(by_series[series], key=lambda b: (b.volume is None, b.volume or 0))
        groups.append({"series": series, "books": volumes})

    if without_series:
        without_series.sort(key=lambda b: b.title.lower())
        groups.append({"series": None, "books": without_series})

    return groups
