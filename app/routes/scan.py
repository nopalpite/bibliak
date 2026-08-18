from flask import Blueprint, current_app, render_template, request, session

from app.services.isbn_service import rechercher_par_isbn
from app.services.parametre_service import get_parametre

scan_bp = Blueprint("scan", __name__)


@scan_bp.route("/")
def page_scan():
    """Page de scan : affiche la caméra sur smartphone (détection côté client),
    et un simple champ de saisie ISBN sur les autres plateformes."""
    return render_template("scan.html")


@scan_bp.route("/rechercher", methods=["POST"])
def rechercher_isbn():
    isbn = request.form.get("isbn", "").strip()
    if not isbn:
        return render_template(
            "partials/scan_resultat.html", erreur="Merci de renseigner un code ISBN/EAN."
        )

    resultat, sources_en_erreur = rechercher_par_isbn(
        isbn,
        api_prioritaire=get_parametre("api_prioritaire", "openlibrary"),
        cle_api_google=current_app.config.get("GOOGLE_BOOKS_API_KEY"),
    )

    if not resultat:
        if len(sources_en_erreur) == 2:
            erreur = (
                "Impossible de contacter Open Library et Google Books "
                "(pas de réponse ou connexion indisponible). Réessayez dans un instant, "
                "ou ajoutez l'ouvrage manuellement."
            )
            type_erreur = "reseau"
        elif sources_en_erreur:
            source_en_erreur = sources_en_erreur[0]
            autre_source = "Google Books" if source_en_erreur == "Open Library" else "Open Library"
            erreur = (
                f"{source_en_erreur} n'a pas répondu. {autre_source} a été interrogée en repli, "
                "mais ne connaît pas cet ISBN. Vous pouvez ajouter l'ouvrage manuellement."
            )
            type_erreur = "reseau"
        else:
            erreur = (
                "Aucune information trouvée pour cet ISBN (Open Library et Google Books "
                "interrogées). Vous pouvez ajouter l'ouvrage manuellement."
            )
            type_erreur = "introuvable"

        return render_template("partials/scan_resultat.html", erreur=erreur, isbn=isbn, type_erreur=type_erreur)

    session["prefill_scan"] = resultat
    return render_template("partials/scan_resultat.html", resultat=resultat)
