from app.extensions import db


class Publisher(db.Model):
    __tablename__ = "publishers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True, index=True)

    def __repr__(self):
        return f"<Publisher {self.name}>"
