from app.extensions import db


class Emplacement(db.Model):
    __tablename__ = "emplacements"

    id = db.Column(db.Integer, primary_key=True)
    libelle = db.Column(db.String(150), nullable=False, unique=True, index=True)
    description = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<Emplacement {self.libelle}>"
