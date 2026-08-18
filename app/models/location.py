from app.extensions import db


class Location(db.Model):
    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    label = db.Column(db.String(150), nullable=False, unique=True, index=True)
    description = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Location {self.label}>"
