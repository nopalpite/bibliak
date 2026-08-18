from datetime import datetime, timezone

from app.extensions import db

# Un ouvrage peut avoir plusieurs auteurs (scénariste, dessinateur, coloriste...)
ouvrage_auteur = db.Table(
    "ouvrage_auteur",
    db.Column("ouvrage_id", db.Integer, db.ForeignKey("ouvrages.id"), primary_key=True),
    db.Column("auteur_id", db.Integer, db.ForeignKey("auteurs.id"), primary_key=True),
)

# Un ouvrage peut porter plusieurs tags libres
ouvrage_tag = db.Table(
    "ouvrage_tag",
    db.Column("ouvrage_id", db.Integer, db.ForeignKey("ouvrages.id"), primary_key=True),
    db.Column("tag_id", db.Integer, db.ForeignKey("tags.id"), primary_key=True),
)


def _maintenant():
    return datetime.now(timezone.utc)


class Ouvrage(db.Model):
    __tablename__ = "ouvrages"

    id = db.Column(db.Integer, primary_key=True)

    titre = db.Column(db.String(255), nullable=False, index=True)
    type_ouvrage = db.Column(db.String(50), nullable=False, default="BD", index=True)
    isbn = db.Column(db.String(20), index=True, nullable=True)

    serie_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=True)
    tome = db.Column(db.Integer, nullable=True)

    editeur_id = db.Column(db.Integer, db.ForeignKey("editeurs.id"), nullable=True)
    date_parution = db.Column(db.String(20), nullable=True)  # souvent partielle (juste l'année)

    resume = db.Column(db.Text, nullable=True)
    image_couverture = db.Column(db.String(255), nullable=True)  # nom de fichier dans static/covers

    emplacement_id = db.Column(db.Integer, db.ForeignKey("emplacements.id"), nullable=True)
    etat = db.Column(db.String(50), nullable=True, default="Bon état")
    notes_perso = db.Column(db.Text, nullable=True)
    lu = db.Column(db.Boolean, nullable=False, default=False)

    date_ajout = db.Column(db.DateTime, default=_maintenant)
    date_modification = db.Column(db.DateTime, default=_maintenant, onupdate=_maintenant)

    serie = db.relationship("Serie", backref="ouvrages")
    editeur = db.relationship("Editeur", backref="ouvrages")
    emplacement = db.relationship("Emplacement", backref="ouvrages")
    auteurs = db.relationship("Auteur", secondary=ouvrage_auteur, backref="ouvrages")
    tags = db.relationship("Tag", secondary=ouvrage_tag, backref="ouvrages")

    @property
    def liste_auteurs(self):
        return ", ".join(a.nom_complet for a in self.auteurs)

    @property
    def liste_tags(self):
        return [t.libelle for t in self.tags]

    @property
    def statut_lecture(self):
        return "Lu" if self.lu else "À lire"

    def __repr__(self):
        return f"<Ouvrage {self.titre}>"
