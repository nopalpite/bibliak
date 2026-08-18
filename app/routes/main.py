from flask import Blueprint, current_app, redirect, render_template, request, send_file, url_for

from app.extensions import db
from app.models import Editeur, Emplacement, Ouvrage, Serie, Tag
from app.services.parametre_service import get_parametre
from app.services.recherche_service import grouper_par_serie, rechercher_ouvrages

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    vue = request.args.get("vue", get_parametre("vue_par_defaut", "grille"))
    ouvrages = rechercher_ouvrages()

    return render_template(
        "index.html",
        ouvrages=ouvrages,
        groupes=grouper_par_serie(ouvrages),
        vue=vue,
        editeurs=Editeur.query.order_by(Editeur.nom).all(),
        series=Serie.query.order_by(Serie.nom).all(),
        tags=Tag.query.order_by(Tag.libelle).all(),
        emplacements=Emplacement.query.order_by(Emplacement.libelle).all(),
        types_ouvrages=get_parametre("types_ouvrages", []),
        etats_ouvrages=get_parametre("etats_ouvrages", []),
    )


@main_bp.route("/series/<int:serie_id>")
def serie_detail(serie_id):
    """Page "étagère" d'une série : tous les tomes possédés, triés, avec les
    tomes manquants signalés en creux si le nombre total de tomes est connu."""
    serie = Serie.query.get_or_404(serie_id)
    ouvrages = (
        Ouvrage.query.filter_by(serie_id=serie.id)
        .order_by(Ouvrage.tome.is_(None), Ouvrage.tome)
        .all()
    )

    tomes_possedes = {o.tome for o in ouvrages if o.tome is not None}
    tomes_manquants = []
    if serie.nb_tomes_prevu:
        tomes_manquants = [n for n in range(1, serie.nb_tomes_prevu + 1) if n not in tomes_possedes]

    return render_template(
        "serie_detail.html",
        serie=serie,
        ouvrages=ouvrages,
        tomes_manquants=tomes_manquants,
    )


@main_bp.route("/series/<int:serie_id>/nb-tomes", methods=["POST"])
def definir_nb_tomes(serie_id):
    """Renseigne (ou efface) le nombre total de tomes d'une série, pour
    permettre à la page "étagère" de signaler les tomes manquants."""
    serie = Serie.query.get_or_404(serie_id)
    serie.nb_tomes_prevu = request.form.get("nb_tomes_prevu", type=int)
    db.session.commit()
    return redirect(url_for("main.serie_detail", serie_id=serie.id))


@main_bp.route("/certificat")
def telecharger_certificat():
    """Sert le certificat HTTPS auto-signé pour installation comme profil de
    confiance sur iOS (Safari ne débloque pas la caméra sur un certificat
    simplement "accepté", il doit être installé et validé dans les réglages
    du système)."""
    chemin_certificat = current_app.config["CERT_DIR"] / "cert.pem"
    return send_file(
        chemin_certificat,
        mimetype="application/x-x509-ca-cert",
        as_attachment=True,
        download_name="ma-bibliotheque.pem",
    )
