from datetime import datetime, timezone

from app.extensions import db

# A book can have several authors (writer, artist, colorist...)
book_author = db.Table(
    "book_author",
    db.Column("book_id", db.Integer, db.ForeignKey("books.id"), primary_key=True),
    db.Column("author_id", db.Integer, db.ForeignKey("authors.id"), primary_key=True),
)

# A book can carry several free-form tags
book_tag = db.Table(
    "book_tag",
    db.Column("book_id", db.Integer, db.ForeignKey("books.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


def _now():
    return datetime.now(timezone.utc)


class Book(db.Model):
    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(255), nullable=False, index=True)
    item_type = db.Column(db.String(50), nullable=False, default="BD", index=True)
    isbn = db.Column(db.String(20), index=True, nullable=True)

    series_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=True)
    volume = db.Column(db.Integer, nullable=True)

    publisher_id = db.Column(db.Integer, db.ForeignKey("publishers.id"), nullable=True)
    publication_date = db.Column(db.String(20), nullable=True)  # often partial (year only)

    summary = db.Column(db.Text, nullable=True)
    cover_image = db.Column(db.String(255), nullable=True)  # filename in static/covers

    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)
    condition = db.Column(db.String(50), nullable=True, default="Bon état")
    personal_notes = db.Column(db.Text, nullable=True)
    read = db.Column(db.Boolean, nullable=False, default=False)

    date_added = db.Column(db.DateTime, default=_now)
    date_modified = db.Column(db.DateTime, default=_now, onupdate=_now)

    series = db.relationship("Series", backref="books")
    publisher = db.relationship("Publisher", backref="books")
    location = db.relationship("Location", backref="books")
    authors = db.relationship("Author", secondary=book_author, backref="books")
    tags = db.relationship("Tag", secondary=book_tag, backref="books")

    @property
    def author_list(self):
        return ", ".join(a.full_name for a in self.authors)

    @property
    def tag_list(self):
        return [t.label for t in self.tags]

    @property
    def reading_status(self):
        return "Lu" if self.read else "À lire"

    def __repr__(self):
        return f"<Book {self.title}>"
