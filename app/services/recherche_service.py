"""Recherche et filtrage de la collection.

Le volume attendu (quelques centaines d'ouvrages, usage mono-utilisateur) ne
justifie pas de mécanisme de cache ou d'indexation avancée : une requête SQL
simple, avec les index de base posés sur les modèles, suffit largement.
"""

from sqlalchemy import or_

from app.models import Auteur, Editeur, Ouvrage, Serie, Tag

TRIS_DISPONIBLES = {
    "titre": (Ouvrage.titre.asc(),),
    "date_ajout_desc": (Ouvrage.date_ajout.desc(),),
    "date_ajout_asc": (Ouvrage.date_ajout.asc(),),
    "date_parution": (Ouvrage.date_parution.desc(),),
}


def rechercher_ouvrages(
    q=None,
    type_ouvrage=None,
    serie_id=None,
    editeur_id=None,
    tag_id=None,
    emplacement_id=None,
    etat=None,
    lecture=None,
    tri="titre",
):
    requete = Ouvrage.query

    if q:
        motif = f"%{q.strip()}%"
        requete = (
            requete.outerjoin(Ouvrage.auteurs)
            .outerjoin(Ouvrage.editeur)
            .outerjoin(Ouvrage.serie)
            .filter(
                or_(
                    Ouvrage.titre.ilike(motif),
                    Ouvrage.isbn.ilike(motif),
                    Auteur.nom_complet.ilike(motif),
                    Editeur.nom.ilike(motif),
                    Serie.nom.ilike(motif),
                )
            )
            .distinct()
        )

    if type_ouvrage:
        requete = requete.filter(Ouvrage.type_ouvrage == type_ouvrage)
    if serie_id:
        requete = requete.filter(Ouvrage.serie_id == serie_id)
    if editeur_id:
        requete = requete.filter(Ouvrage.editeur_id == editeur_id)
    if emplacement_id:
        requete = requete.filter(Ouvrage.emplacement_id == emplacement_id)
    if etat:
        requete = requete.filter(Ouvrage.etat == etat)
    if tag_id:
        requete = requete.filter(Ouvrage.tags.any(Tag.id == tag_id))
    if lecture == "a_lire":
        requete = requete.filter(Ouvrage.lu.is_(False))
    elif lecture == "lu":
        requete = requete.filter(Ouvrage.lu.is_(True))

    ordre = TRIS_DISPONIBLES.get(tri, TRIS_DISPONIBLES["titre"])
    return requete.order_by(*ordre).all()


def grouper_par_serie(ouvrages):
    """Regroupe une liste d'ouvrages par série pour l'affichage en "étagères" :
    chaque série devient un groupe, ses tomes triés par numéro. Les ouvrages
    sans série sont rassemblés dans un dernier groupe à part."""
    par_serie = {}
    sans_serie = []

    for o in ouvrages:
        if o.serie:
            par_serie.setdefault(o.serie, []).append(o)
        else:
            sans_serie.append(o)

    groupes = []
    for serie in sorted(par_serie.keys(), key=lambda s: s.nom.lower()):
        tomes = sorted(par_serie[serie], key=lambda o: (o.tome is None, o.tome or 0))
        groupes.append({"serie": serie, "ouvrages": tomes})

    if sans_serie:
        sans_serie.sort(key=lambda o: o.titre.lower())
        groupes.append({"serie": None, "ouvrages": sans_serie})

    return groupes
