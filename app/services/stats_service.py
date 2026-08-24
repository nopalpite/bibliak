"""Read-only aggregation of the collection for the Stats page.

Pure aggregation over what's already stored — no new data, no external
calls. Kept as plain Python over the loaded rows (not SQL GROUP BY):
the app's own stated scale is a few hundred books, so this is simpler to
read and just as fast as building several separate aggregate queries.
"""

import re
from collections import Counter

from app.models import Book, Series

_TOP_N = 10

_YEAR_RE = re.compile(r"(1\d{3}|20\d{2})")


def _decade(publication_date):
    """Best-effort decade extraction from a free-text publication date
    (often just a year, e.g. "2003" or "12/2019", sometimes partial or
    missing). Returns e.g. "2000s", or None if no plausible year is found."""
    if not publication_date:
        return None
    match = _YEAR_RE.search(publication_date)
    if not match:
        return None
    year = int(match.group(1))
    return f"{(year // 10) * 10}s"


def _top_counts(counter, limit=_TOP_N):
    return counter.most_common(limit)


def collection_stats():
    books = Book.query.all()
    total = len(books)

    read_count = sum(1 for b in books if b.read)

    by_item_type = Counter(b.item_type for b in books if b.item_type)
    by_publisher = Counter(b.publisher.name for b in books if b.publisher)
    by_author = Counter(a.full_name for b in books for a in b.authors)
    by_decade = Counter(d for b in books if (d := _decade(b.publication_date)))

    series_list = Series.query.all()
    tracked_series = [s for s in series_list if s.expected_volume_count]
    complete_series = 0
    for series in tracked_series:
        owned = {b.volume for b in series.books if b.volume is not None}
        if all(n in owned for n in range(1, series.expected_volume_count + 1)):
            complete_series += 1

    return {
        "total": total,
        "read_count": read_count,
        "unread_count": total - read_count,
        "series_count": len(series_list),
        "tracked_series_count": len(tracked_series),
        "complete_series_count": complete_series,
        "by_item_type": _top_counts(by_item_type, limit=None) if by_item_type else [],
        "by_publisher": _top_counts(by_publisher),
        "by_author": _top_counts(by_author),
        "by_decade": sorted(by_decade.items()),
    }
