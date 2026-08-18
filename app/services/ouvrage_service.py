"""Logique de création / modification / suppression d'un ouvrage.

Centralise la résolution des entités liées (auteurs, éditeur, série, tags,
emplacement) : elles sont créées à la volée si elles n'existent pas encore,
pour ne jamais bloquer l'utilisateur avec une étape de configuration préalable.
"""

from app.extensions import db
from app.models import Auteur, Editeur, Emplacement, Ouvrage, Serie, Tag
from app.services import parametre_service
from app.services.image_service import supprimer_couverture


def _recuperer_ou_creer(modele, **filtres):
    instance = modele.query.filter_by(**filtres).first()
    if instance:
        return instance
    instance = modele(**filtres)
    db.session.add(instance)
    db.session.flush()
    return instance


def _resoudre_editeur(donnees):
    """Résout l'éditeur d'un ouvrage — même logique que _resoudre_serie :
    choix obligatoire parmi l'existant depuis le formulaire (editeur_id),
    avec repli sur le nom pour l'import JSON."""
    editeur_id = donnees.get("editeur_id")
    if editeur_id:
        return db.session.get(Editeur, editeur_id)

    nom = (donnees.get("editeur") or "").strip()
    return _recuperer_ou_creer(Editeur, nom=nom) if nom else None


def _resoudre_serie(donnees):
    """Résout la série d'un ouvrage.

    Le formulaire d'ajout/édition impose désormais de choisir une série
    existante (transmise par son id, `serie_id`) plutôt que d'en créer une
    nouvelle à la volée par simple frappe — cela évite les doublons de séries
    dus à une faute de frappe. La création reste possible via le bouton "+"
    du formulaire (voir ouvrages.creer_serie_rapide) ou Administration >
    Référentiels.

    L'import d'une sauvegarde JSON reste toléré par nom (`serie`), pour ne
    pas obliger à précréer chaque série avant de restaurer une collection.
    """
    serie_id = donnees.get("serie_id")
    if serie_id:
        return db.session.get(Serie, serie_id)

    nom = (donnees.get("serie") or "").strip()
    return _recuperer_ou_creer(Serie, nom=nom) if nom else None


def _resoudre_emplacement(libelle):
    libelle = (libelle or "").strip()
    return _recuperer_ou_creer(Emplacement, libelle=libelle) if libelle else None


def _resoudre_auteurs(noms):
    resultat = []
    for nom in noms:
        nom = nom.strip()
        if nom:
            resultat.append(_recuperer_ou_creer(Auteur, nom_complet=nom))
    return resultat


def _resoudre_tags(libelles):
    resultat = []
    for libelle in libelles:
        libelle = libelle.strip()
        if libelle:
            resultat.append(_recuperer_ou_creer(Tag, libelle=libelle))
    return resultat


def _appliquer_donnees(ouvrage, donnees):
    ouvrage.titre = (donnees.get("titre") or "").strip()
    ouvrage.type_ouvrage = donnees.get("type_ouvrage") or "Autre"
    ouvrage.isbn = (donnees.get("isbn") or "").strip() or None
    ouvrage.tome = donnees.get("tome") or None
    ouvrage.date_parution = (donnees.get("date_parution") or "").strip() or None
    ouvrage.resume = (donnees.get("resume") or "").strip() or None
    ouvrage.etat = donnees.get("etat") or None
    ouvrage.notes_perso = (donnees.get("notes_perso") or "").strip() or None
    if "lu" in donnees:
        # Présent uniquement lors d'un import de sauvegarde JSON : le
        # formulaire d'ajout/édition ne gère pas ce champ (il se pilote
        # depuis la fiche détail), on ne veut donc jamais réinitialiser
        # silencieusement le statut à l'édition.
        ouvrage.lu = bool(donnees.get("lu"))

    ouvrage.editeur = _resoudre_editeur(donnees)
    ouvrage.serie = _resoudre_serie(donnees)
    ouvrage.emplacement = _resoudre_emplacement(donnees.get("emplacement"))
    ouvrage.auteurs = _resoudre_auteurs(donnees.get("auteurs", []))
    ouvrage.tags = _resoudre_tags(donnees.get("tags", []))

    return ouvrage


def creer_ouvrage(donnees):
    ouvrage = Ouvrage()
    _appliquer_donnees(ouvrage, donnees)
    db.session.add(ouvrage)
    db.session.commit()
    return ouvrage


def modifier_ouvrage(ouvrage, donnees):
    _appliquer_donnees(ouvrage, donnees)
    db.session.commit()
    return ouvrage


def supprimer_ouvrage(ouvrage):
    supprimer_couverture(ouvrage.image_couverture)
    db.session.delete(ouvrage)
    db.session.commit()


def definir_couverture(ouvrage, nom_fichier):
    if not nom_fichier:
        return
    if ouvrage.image_couverture:
        supprimer_couverture(ouvrage.image_couverture)
    ouvrage.image_couverture = nom_fichier
    db.session.commit()


def basculer_lu(ouvrage):
    """Bascule le statut lu / à lire d'un ouvrage."""
    ouvrage.lu = not ouvrage.lu
    db.session.commit()
    return ouvrage


def trouver_doublon_isbn(isbn, exclure_id=None):
    """Renvoie un ouvrage existant portant le même ISBN, ou None."""
    isbn = (isbn or "").strip()
    if not isbn:
        return None

    requete = Ouvrage.query.filter(Ouvrage.isbn == isbn)
    if exclure_id:
        requete = requete.filter(Ouvrage.id != exclure_id)
    return requete.first()


def _trouver_doublon_titre_tome(titre, tome, exclure_id=None):
    """Renvoie un ouvrage existant avec le même titre (insensible à la casse)
    et le même tome (les deux None comptant comme égaux), ou None."""
    titre = (titre or "").strip()
    if not titre:
        return None

    requete = Ouvrage.query.filter(db.func.lower(Ouvrage.titre) == titre.lower())
    if tome:
        requete = requete.filter(Ouvrage.tome == tome)
    else:
        requete = requete.filter(Ouvrage.tome.is_(None))
    if exclure_id:
        requete = requete.filter(Ouvrage.id != exclure_id)
    return requete.first()


def trouver_doublon(donnees, exclure_id=None):
    """Point d'entrée unique de la politique de détection des doublons,
    appliquée partout où un ouvrage peut être créé (formulaire manuel, scan,
    import) : voir Administration > Paramètres pour la rendre configurable.

    Renvoie un tuple (ouvrage_existant_ou_None, critere_ou_None), le critère
    valant "isbn" ou "titre" pour permettre un message adapté à l'utilisateur.
    """
    politique = parametre_service.get_parametre("detection_doublons", "isbn_et_titre")
    if politique == "desactivee":
        return None, None

    doublon = trouver_doublon_isbn(donnees.get("isbn"), exclure_id=exclure_id)
    if doublon:
        return doublon, "isbn"

    if politique == "isbn_uniquement":
        return None, None

    # Repli sur titre + tome uniquement si aucun ISBN n'a été saisi : un ISBN
    # renseigné mais différent d'un ouvrage existant ne doit pas déclencher
    # une fausse alerte sur la seule ressemblance de titre.
    if not (donnees.get("isbn") or "").strip():
        doublon = _trouver_doublon_titre_tome(
            donnees.get("titre"), donnees.get("tome"), exclure_id=exclure_id
        )
        if doublon:
            return doublon, "titre"

    return None, None
