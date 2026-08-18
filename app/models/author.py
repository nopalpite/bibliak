from app.extensions import db


class Author(db.Model):
    __tablename__ = "authors"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(255), nullable=False, unique=True, index=True)

    def __repr__(self):
        return f"<Author {self.full_name}>"
