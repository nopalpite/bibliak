from app.extensions import db


class Auteur(db.Model):
    __tablename__ = "auteurs"

    id = db.Column(db.Integer, primary_key=True)
    nom_complet = db.Column(db.String(255), nullable=False, unique=True, index=True)

    def __repr__(self):
        return f"<Auteur {self.nom_complet}>"
