from flask import Blueprint, redirect, render_template, request, session, url_for

from app.extensions import db
from app.models import Auteur, Editeur, Emplacement, Ouvrage, Serie, Tag
from app.services import image_service, ouvrage_service
from app.services.parametre_service import get_parametre
from app.services.recherche_service import grouper_par_serie, rechercher_ouvrages

ouvrages_bp = Blueprint("ouvrages", __name__)


@ouvrages_bp.route("/rechercher")
def rechercher():
    """Endpoint appelé en HTMX à chaque frappe / changement de filtre."""
    ouvrages = rechercher_ouvrages(
        q=request.args.get("q"),
        type_ouvrage=request.args.get("type") or None,
        serie_id=request.args.get("serie", type=int),
        editeur_id=request.args.get("editeur", type=int),
        tag_id=request.args.get("tag", type=int),
        emplacement_id=request.args.get("emplacement", type=int),
        etat=request.args.get("etat") or None,
        lecture=request.args.get("lecture") or None,
        tri=request.args.get("tri", "titre"),
    )
    vue = request.args.get("vue", "grille")
    if vue == "etageres":
        return render_template("partials/ouvrages_etageres.html", groupes=grouper_par_serie(ouvrages))
    template = "partials/ouvrages_grille.html" if vue == "grille" else "partials/ouvrages_liste.html"
    return render_template(template, ouvrages=ouvrages)


@ouvrages_bp.route("/verifier-doublon")
def verifier_doublon():
    """Appelé en HTMX à chaque frappe dans les champs ISBN / titre / tome du
    formulaire : signale immédiatement un doublon potentiel selon la politique
    configurée (Administration > Paramètres)."""
    donnees = {
        "isbn": request.args.get("isbn", ""),
        "titre": request.args.get("titre", ""),
        "tome": request.args.get("tome", type=int),
    }
    exclure = request.args.get("exclure", type=int)
    doublon, critere = ouvrage_service.trouver_doublon(donnees, exclure_id=exclure)
    return render_template("partials/alerte_doublon.html", doublon=doublon, critere=critere, variante="live")


@ouvrages_bp.route("/series/creer-rapide", methods=["POST"])
def creer_serie_rapide():
    """Création d'une série depuis le formulaire d'ajout/édition (bouton "+"
    à côté du sélecteur), sans quitter la page. La série nouvellement créée
    est automatiquement sélectionnée dans le champ renvoyé."""
    nom = request.form.get("nom", "").strip()

    if not nom:
        return render_template(
            "partials/champ_serie.html",
            series=Serie.query.order_by(Serie.nom).all(),
            valeurs={"serie_id": None},
            message="Merci de saisir un nom de série.",
            erreur=True,
            nom_saisi="",
        )

    serie = Serie.query.filter_by(nom=nom).first()
    deja_existante = serie is not None
    if not serie:
        serie = Serie(nom=nom)
        db.session.add(serie)
        db.session.commit()

    message = (
        f"« {serie.nom} » existait déjà : sélectionnée."
        if deja_existante
        else f"« {serie.nom} » créée et sélectionnée."
    )

    return render_template(
        "partials/champ_serie.html",
        series=Serie.query.order_by(Serie.nom).all(),
        valeurs={"serie_id": serie.id},
        message=message,
        erreur=False,
        nom_saisi="",
    )


@ouvrages_bp.route("/editeurs/creer-rapide", methods=["POST"])
def creer_editeur_rapide():
    """Création d'un éditeur depuis le formulaire d'ajout/édition (bouton "+"
    à côté du sélecteur), sans quitter la page. L'éditeur nouvellement créé
    est automatiquement sélectionné dans le champ renvoyé."""
    nom = request.form.get("nom", "").strip()

    if not nom:
        return render_template(
            "partials/champ_editeur.html",
            editeurs=Editeur.query.order_by(Editeur.nom).all(),
            valeurs={"editeur_id": None},
            message="Merci de saisir un nom d'éditeur.",
            erreur=True,
            nom_saisi="",
        )

    editeur = Editeur.query.filter_by(nom=nom).first()
    deja_existant = editeur is not None
    if not editeur:
        editeur = Editeur(nom=nom)
        db.session.add(editeur)
        db.session.commit()

    message = (
        f"« {editeur.nom} » existait déjà : sélectionné."
        if deja_existant
        else f"« {editeur.nom} » créé et sélectionné."
    )

    return render_template(
        "partials/champ_editeur.html",
        editeurs=Editeur.query.order_by(Editeur.nom).all(),
        valeurs={"editeur_id": editeur.id},
        message=message,
        erreur=False,
        nom_saisi="",
    )


@ouvrages_bp.route("/nouveau", methods=["GET", "POST"])
def nouveau():
    if request.method == "POST":
        donnees = _donnees_formulaire()

        if not donnees.get("titre", "").strip():
            return render_template(
                "ouvrage_form.html",
                ouvrage=None,
                valeurs=_valeurs_depuis_formulaire(request.form),
                doublon=None,
                critere=None,
                erreur_titre=True,
                **_contexte_formulaire(),
            )

        doublon, critere = ouvrage_service.trouver_doublon(donnees)

        if doublon and request.form.get("ignorer_doublon") != "1":
            return render_template(
                "ouvrage_form.html",
                ouvrage=None,
                valeurs=_valeurs_depuis_formulaire(request.form),
                doublon=doublon,
                critere=critere,
                **_contexte_formulaire(),
            )

        ouvrage = ouvrage_service.creer_ouvrage(donnees)
        erreur_image = _traiter_image(ouvrage)
        return redirect(url_for("ouvrages.detail", ouvrage_id=ouvrage.id, erreur_image=erreur_image))

    prefill = session.pop("prefill_scan", None)
    if not prefill and request.args.get("isbn"):
        prefill = {"isbn": request.args.get("isbn"), "titre": "", "auteurs": [], "source": ""}

    valeurs = _valeurs_depuis_prefill(prefill) if prefill else _valeurs_vides()
    if prefill and prefill.get("editeur"):
        valeurs["editeur_id"] = _resoudre_editeur_prefill(prefill["editeur"])
    serie_id_arg = request.args.get("serie_id", type=int)
    if serie_id_arg:
        valeurs["serie_id"] = serie_id_arg
    if request.args.get("tome"):
        valeurs["tome"] = request.args.get("tome")

    return render_template(
        "ouvrage_form.html",
        ouvrage=None,
        valeurs=valeurs,
        doublon=None,
        critere=None,
        **_contexte_formulaire(),
    )


@ouvrages_bp.route("/<int:ouvrage_id>")
def detail(ouvrage_id):
    ouvrage = Ouvrage.query.get_or_404(ouvrage_id)
    return render_template(
        "ouvrage_detail.html", ouvrage=ouvrage, erreur_image=request.args.get("erreur_image")
    )


@ouvrages_bp.route("/<int:ouvrage_id>/modifier", methods=["GET", "POST"])
def modifier(ouvrage_id):
    ouvrage = Ouvrage.query.get_or_404(ouvrage_id)

    if request.method == "POST":
        donnees = _donnees_formulaire()

        if not donnees.get("titre", "").strip():
            return render_template(
                "ouvrage_form.html",
                ouvrage=ouvrage,
                valeurs=_valeurs_depuis_formulaire(request.form),
                doublon=None,
                critere=None,
                erreur_titre=True,
                **_contexte_formulaire(),
            )

        doublon, critere = ouvrage_service.trouver_doublon(donnees, exclure_id=ouvrage.id)

        if doublon and request.form.get("ignorer_doublon") != "1":
            return render_template(
                "ouvrage_form.html",
                ouvrage=ouvrage,
                valeurs=_valeurs_depuis_formulaire(request.form),
                doublon=doublon,
                critere=critere,
                **_contexte_formulaire(),
            )

        ouvrage_service.modifier_ouvrage(ouvrage, donnees)
        erreur_image = _traiter_image(ouvrage)
        return redirect(url_for("ouvrages.detail", ouvrage_id=ouvrage.id, erreur_image=erreur_image))

    return render_template(
        "ouvrage_form.html",
        ouvrage=ouvrage,
        valeurs=_valeurs_depuis_ouvrage(ouvrage),
        doublon=None,
        critere=None,
        **_contexte_formulaire(),
    )


@ouvrages_bp.route("/<int:ouvrage_id>/supprimer", methods=["POST"])
def supprimer(ouvrage_id):
    ouvrage = Ouvrage.query.get_or_404(ouvrage_id)
    ouvrage_service.supprimer_ouvrage(ouvrage)
    return redirect(url_for("main.index"))


@ouvrages_bp.route("/<int:ouvrage_id>/lecture", methods=["POST"])
def basculer_lecture(ouvrage_id):
    """Bascule le statut lu / à lire depuis la fiche détail, sans passer par
    le formulaire d'édition complet."""
    ouvrage = Ouvrage.query.get_or_404(ouvrage_id)
    ouvrage_service.basculer_lu(ouvrage)
    return redirect(url_for("ouvrages.detail", ouvrage_id=ouvrage.id))


def _donnees_formulaire():
    form = request.form
    return {
        "titre": form.get("titre", ""),
        "type_ouvrage": form.get("type_ouvrage"),
        "isbn": form.get("isbn"),
        "tome": form.get("tome", type=int),
        "date_parution": form.get("date_parution"),
        "resume": form.get("resume"),
        "etat": form.get("etat"),
        "notes_perso": form.get("notes_perso"),
        "editeur_id": form.get("editeur_id", type=int),
        "serie_id": form.get("serie_id", type=int),
        "emplacement": form.get("emplacement"),
        "auteurs": [a for a in form.get("auteurs", "").split(",") if a.strip()],
        "tags": [t for t in form.get("tags", "").split(",") if t.strip()],
    }


def _traiter_image(ouvrage):
    """Traite la photo uploadée ou le lien d'image collé. Renvoie un message
    d'erreur si le lien n'a pas pu être téléchargé (None sinon) : contrairement
    à un échec silencieux, l'utilisateur doit savoir que sa couverture n'a pas
    été enregistrée."""
    fichier = request.files.get("photo")
    url_image = request.form.get("image_url_distante")

    nom_fichier = None
    erreur = None
    if fichier and fichier.filename:
        nom_fichier = image_service.sauvegarder_upload(fichier)
        if not nom_fichier:
            erreur = "La photo importée n'a pas pu être lue (fichier corrompu ou format non supporté)."
    elif url_image:
        nom_fichier, erreur = image_service.telecharger_couverture(url_image)

    if nom_fichier:
        ouvrage_service.definir_couverture(ouvrage, nom_fichier)

    return erreur


def _contexte_formulaire():
    return {
        "editeurs": Editeur.query.order_by(Editeur.nom).all(),
        "series": Serie.query.order_by(Serie.nom).all(),
        "tags_existants": Tag.query.order_by(Tag.libelle).all(),
        "auteurs_existants": Auteur.query.order_by(Auteur.nom_complet).all(),
        "emplacements": Emplacement.query.order_by(Emplacement.libelle).all(),
        "types_ouvrages": get_parametre("types_ouvrages", []),
        "etats_ouvrages": get_parametre("etats_ouvrages", []),
    }


# --- Normalisation des valeurs affichées dans le formulaire ---
# Le formulaire d'ajout/édition peut être pré-rempli depuis trois sources
# différentes (un ouvrage existant à modifier, un résultat de scan ISBN, ou
# une nouvelle soumission bloquée par un doublon à corriger) : ce dictionnaire
# uniformisé évite de dupliquer cette logique dans le template.

def _valeurs_vides():
    return {
        "titre": "", "type_ouvrage": "", "isbn": "", "serie_id": None, "tome": "",
        "auteurs": "", "editeur_id": None, "date_parution": "", "resume": "",
        "etat": "", "emplacement": "", "tags": "", "notes_perso": "",
        "image_url": None, "image_url_distante": None,
    }


def _valeurs_depuis_ouvrage(ouvrage):
    return {
        "titre": ouvrage.titre,
        "type_ouvrage": ouvrage.type_ouvrage or "",
        "isbn": ouvrage.isbn or "",
        "serie_id": ouvrage.serie_id,
        "tome": ouvrage.tome or "",
        "auteurs": ouvrage.liste_auteurs,
        "editeur_id": ouvrage.editeur_id,
        "date_parution": ouvrage.date_parution or "",
        "resume": ouvrage.resume or "",
        "etat": ouvrage.etat or "",
        "emplacement": ouvrage.emplacement.libelle if ouvrage.emplacement else "",
        "tags": ", ".join(ouvrage.liste_tags),
        "notes_perso": ouvrage.notes_perso or "",
        "image_url": url_for("static", filename="covers/" + ouvrage.image_couverture) if ouvrage.image_couverture else None,
        "image_url_distante": None,
    }


def _valeurs_depuis_prefill(prefill):
    return {
        "titre": prefill.get("titre") or "",
        "type_ouvrage": "",
        "isbn": prefill.get("isbn") or "",
        "serie_id": None,
        "tome": "",
        "auteurs": ", ".join(prefill.get("auteurs") or []),
        "editeur_id": None,  # résolu séparément dans nouveau() : voir _resoudre_editeur_prefill
        "date_parution": prefill.get("date_parution") or "",
        "resume": prefill.get("resume") or "",
        "etat": "",
        "emplacement": "",
        "tags": "",
        "notes_perso": "",
        "image_url": prefill.get("image_url"),
        "image_url_distante": prefill.get("image_url"),
    }


def _resoudre_editeur_prefill(nom):
    """Le scan ISBN renvoie un nom d'éditeur en texte libre (Open Library /
    Google Books), mais le formulaire impose désormais de choisir un éditeur
    existant dans une liste. On le résout (ou le crée) ici pour qu'il soit
    déjà sélectionnable au chargement du formulaire, plutôt que de perdre
    cette information ou de rouvrir un champ texte pour ce seul cas."""
    nom = (nom or "").strip()
    if not nom:
        return None
    editeur = Editeur.query.filter_by(nom=nom).first()
    if not editeur:
        editeur = Editeur(nom=nom)
        db.session.add(editeur)
        db.session.commit()
    return editeur.id


def _valeurs_depuis_formulaire(form):
    return {
        "titre": form.get("titre", ""),
        "type_ouvrage": form.get("type_ouvrage", ""),
        "isbn": form.get("isbn", ""),
        "serie_id": form.get("serie_id", type=int),
        "tome": form.get("tome", ""),
        "auteurs": form.get("auteurs", ""),
        "editeur_id": form.get("editeur_id", type=int),
        "date_parution": form.get("date_parution", ""),
        "resume": form.get("resume", ""),
        "etat": form.get("etat", ""),
        "emplacement": form.get("emplacement", ""),
        "tags": form.get("tags", ""),
        "notes_perso": form.get("notes_perso", ""),
        "image_url": form.get("image_url_distante") or None,
        "image_url_distante": form.get("image_url_distante") or None,
    }
