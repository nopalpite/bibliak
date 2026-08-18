import json
from io import BytesIO

from flask import Blueprint, render_template, request, send_file

from app.extensions import db
from app.models import Editeur, Emplacement, Ouvrage, Serie, Tag
from app.services import ouvrage_service, parametre_service

admin_bp = Blueprint("admin", __name__)

# Référentiels "relationnels" gérables génériquement (modèle, champ texte)
MODELES_REFERENTIELS = {
    "editeurs": (Editeur, "nom"),
    "series": (Serie, "nom"),
    "tags": (Tag, "libelle"),
    "emplacements": (Emplacement, "libelle"),
}

# Référentiels "listes simples" stockés dans la table Parametre
LISTES_PARAMETRABLES = ("types_ouvrages", "etats_ouvrages")


def _contexte_parametres():
    return {
        "api_prioritaire": parametre_service.get_parametre("api_prioritaire"),
        "vue_par_defaut": parametre_service.get_parametre("vue_par_defaut"),
        "detection_doublons": parametre_service.get_parametre("detection_doublons"),
        "choix_detection_doublons": parametre_service.CHOIX_DETECTION_DOUBLONS,
    }


def _contexte_referentiels():
    return {
        "types_ouvrages": parametre_service.get_parametre("types_ouvrages", []),
        "etats_ouvrages": parametre_service.get_parametre("etats_ouvrages", []),
        "editeurs": Editeur.query.order_by(Editeur.nom).all(),
        "series": Serie.query.order_by(Serie.nom).all(),
        "tags": Tag.query.order_by(Tag.libelle).all(),
        "emplacements": Emplacement.query.order_by(Emplacement.libelle).all(),
    }


def _contexte_export_import(message=None):
    return {"nb_ouvrages": Ouvrage.query.count(), "message": message}


CONTEXTES_ONGLETS = {
    "parametres": _contexte_parametres,
    "referentiels": _contexte_referentiels,
    "export_import": _contexte_export_import,
}


@admin_bp.route("/")
def accueil():
    return render_template(
        "admin/layout_admin.html", onglet_actif="parametres", **_contexte_parametres()
    )


@admin_bp.route("/onglet/<nom>")
def onglet(nom):
    """Chargement d'un onglet en HTMX, sans rechargement de la page."""
    if nom not in CONTEXTES_ONGLETS:
        nom = "parametres"
    return render_template(f"admin/{nom}.html", **CONTEXTES_ONGLETS[nom]())


# --- Paramètres généraux ---

@admin_bp.route("/parametres", methods=["POST"])
def sauvegarder_parametres():
    parametre_service.set_parametre("api_prioritaire", request.form.get("api_prioritaire"))
    parametre_service.set_parametre("vue_par_defaut", request.form.get("vue_par_defaut"))
    parametre_service.set_parametre("detection_doublons", request.form.get("detection_doublons"))
    return render_template("admin/parametres.html", **_contexte_parametres())


# --- Référentiels "listes simples" : types et états d'ouvrage ---

@admin_bp.route("/referentiels/liste/<cle>/ajouter", methods=["POST"])
def ajouter_valeur_liste(cle):
    if cle in LISTES_PARAMETRABLES:
        valeur = request.form.get("valeur", "").strip()
        liste = parametre_service.get_parametre(cle, [])
        if valeur and valeur not in liste:
            liste.append(valeur)
            parametre_service.set_parametre(cle, liste)
    return render_template("admin/referentiels.html", **_contexte_referentiels())


@admin_bp.route("/referentiels/liste/<cle>/supprimer", methods=["POST"])
def supprimer_valeur_liste(cle):
    if cle in LISTES_PARAMETRABLES:
        valeur = request.form.get("valeur", "").strip()
        liste = parametre_service.get_parametre(cle, [])
        if valeur in liste:
            liste.remove(valeur)
            parametre_service.set_parametre(cle, liste)
    return render_template("admin/referentiels.html", **_contexte_referentiels())


# --- Référentiels relationnels : éditeurs, séries, tags, emplacements ---

@admin_bp.route("/referentiels/<nom_modele>/ajouter", methods=["POST"])
def ajouter_referentiel(nom_modele):
    if nom_modele in MODELES_REFERENTIELS:
        modele, champ = MODELES_REFERENTIELS[nom_modele]
        valeur = request.form.get("valeur", "").strip()
        if valeur and not modele.query.filter_by(**{champ: valeur}).first():
            db.session.add(modele(**{champ: valeur}))
            db.session.commit()
    return render_template("admin/referentiels.html", **_contexte_referentiels())


@admin_bp.route("/referentiels/<nom_modele>/<int:item_id>/renommer", methods=["POST"])
def renommer_referentiel(nom_modele, item_id):
    if nom_modele in MODELES_REFERENTIELS:
        modele, champ = MODELES_REFERENTIELS[nom_modele]
        item = modele.query.get_or_404(item_id)
        nouvelle_valeur = request.form.get("valeur", "").strip()
        if nouvelle_valeur:
            setattr(item, champ, nouvelle_valeur)
            db.session.commit()
    return render_template("admin/referentiels.html", **_contexte_referentiels())


@admin_bp.route("/referentiels/<nom_modele>/<int:item_id>/supprimer", methods=["POST"])
def supprimer_referentiel(nom_modele, item_id):
    if nom_modele in MODELES_REFERENTIELS:
        modele, _champ = MODELES_REFERENTIELS[nom_modele]
        item = modele.query.get_or_404(item_id)
        db.session.delete(item)
        db.session.commit()
    return render_template("admin/referentiels.html", **_contexte_referentiels())


@admin_bp.route("/referentiels/<nom_modele>/fusionner", methods=["POST"])
def fusionner_referentiel(nom_modele):
    """Fusionne un référentiel en doublon vers un autre (utile après un import
    ayant créé deux entrées légèrement différentes, ex. deux tags "SF" / "sf")."""
    if nom_modele in MODELES_REFERENTIELS:
        modele, _champ = MODELES_REFERENTIELS[nom_modele]
        source = db.session.get(modele, request.form.get("source_id", type=int))
        cible = db.session.get(modele, request.form.get("cible_id", type=int))

        if source and cible and source.id != cible.id:
            if nom_modele == "tags":
                for ouvrage in list(source.ouvrages):
                    if cible not in ouvrage.tags:
                        ouvrage.tags.append(cible)
                    ouvrage.tags.remove(source)
            else:
                for ouvrage in list(source.ouvrages):
                    if nom_modele == "editeurs":
                        ouvrage.editeur = cible
                    elif nom_modele == "series":
                        ouvrage.serie = cible
                    elif nom_modele == "emplacements":
                        ouvrage.emplacement = cible

            db.session.delete(source)
            db.session.commit()

    return render_template("admin/referentiels.html", **_contexte_referentiels())


# --- Export / Import (sauvegarde de la collection) ---

@admin_bp.route("/export.json")
def exporter_json():
    ouvrages = Ouvrage.query.all()
    donnees = [
        {
            "titre": o.titre,
            "type_ouvrage": o.type_ouvrage,
            "isbn": o.isbn,
            "serie": o.serie.nom if o.serie else None,
            "tome": o.tome,
            "auteurs": [a.nom_complet for a in o.auteurs],
            "editeur": o.editeur.nom if o.editeur else None,
            "date_parution": o.date_parution,
            "resume": o.resume,
            "image_couverture": o.image_couverture,
            "emplacement": o.emplacement.libelle if o.emplacement else None,
            "etat": o.etat,
            "notes_perso": o.notes_perso,
            "lu": o.lu,
            "tags": [t.libelle for t in o.tags],
        }
        for o in ouvrages
    ]

    buffer = BytesIO(json.dumps(donnees, ensure_ascii=False, indent=2).encode("utf-8"))
    return send_file(
        buffer,
        mimetype="application/json",
        as_attachment=True,
        download_name="collection_export.json",
    )


@admin_bp.route("/import", methods=["POST"])
def importer_json():
    fichier = request.files.get("fichier")
    if not fichier:
        return render_template("admin/export_import.html", **_contexte_export_import())

    donnees = json.load(fichier.stream)
    nb_importes = 0
    nb_ignores = 0

    for item in donnees:
        valeurs = {
            "titre": item.get("titre", ""),
            "type_ouvrage": item.get("type_ouvrage"),
            "isbn": item.get("isbn"),
            "tome": item.get("tome"),
            "date_parution": item.get("date_parution"),
            "resume": item.get("resume"),
            "etat": item.get("etat"),
            "notes_perso": item.get("notes_perso"),
            "lu": item.get("lu", (item.get("nombre_lectures", 0) or 0) >= 1),
            "editeur": item.get("editeur"),
            "serie": item.get("serie"),
            "emplacement": item.get("emplacement"),
            "auteurs": item.get("auteurs", []),
            "tags": item.get("tags", []),
        }

        # Applique la même politique de détection que le reste de l'application :
        # un ouvrage déjà présent est ignoré plutôt que dupliqué.
        doublon, _critere = ouvrage_service.trouver_doublon(valeurs)
        if doublon:
            nb_ignores += 1
            continue

        ouvrage_service.creer_ouvrage(valeurs)
        nb_importes += 1

    message = f"{nb_importes} ouvrage(s) importé(s)."
    if nb_ignores:
        message += f" {nb_ignores} doublon(s) ignoré(s) (déjà présents dans la collection)."

    return render_template("admin/export_import.html", **_contexte_export_import(message))
