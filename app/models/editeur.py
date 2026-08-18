from app.extensions import db


class Editeur(db.Model):
    __tablename__ = "editeurs"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(255), nullable=False, unique=True, index=True)

    def __repr__(self):
        return f"<Editeur {self.nom}>"
