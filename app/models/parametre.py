from app.extensions import db


class Parametre(db.Model):
    """Table clé/valeur utilisée par la page d'administration.

    La valeur est stockée en JSON (texte) pour pouvoir contenir aussi bien
    des chaînes simples que des listes (ex. types d'ouvrages disponibles).
    """

    __tablename__ = "parametres"

    cle = db.Column(db.String(100), primary_key=True)
    valeur = db.Column(db.Text, nullable=False)

    def __repr__(self):
        return f"<Parametre {self.cle}>"
