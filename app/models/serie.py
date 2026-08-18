from app.extensions import db

# Nombre de tons de reliure disponibles dans la palette (voir layout.html,
# classes CSS .spine-1 à .spine-NB_COULEURS_SERIE).
NB_COULEURS_SERIE = 8


class Serie(db.Model):
    __tablename__ = "series"

    id = db.Column(db.Integer, primary_key=True)
    nom = db.Column(db.String(255), nullable=False, unique=True, index=True)
    nb_tomes_prevu = db.Column(db.Integer, nullable=True)

    @property
    def classe_couleur(self):
        """Classe CSS de la couleur de reliure attribuée à cette série.

        Déterministe (basée sur l'id) plutôt que tirée au sort à chaque
        affichage : une même série garde toujours la même couleur.
        """
        return f"spine-{(self.id % NB_COULEURS_SERIE) + 1}"

    def __repr__(self):
        return f"<Serie {self.nom}>"
