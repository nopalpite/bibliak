from .author import Author
from .book import Book, book_author, book_tag
from .location import Location
from .publisher import Publisher
from .series import Series
from .setting import Setting
from .tag import Tag

__all__ = [
    "Author",
    "Publisher",
    "Series",
    "Tag",
    "Location",
    "Setting",
    "Book",
    "book_author",
    "book_tag",
]
