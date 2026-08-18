"""Téléchargement, upload et redimensionnement des couvertures d'ouvrages.

Toutes les images sont converties en JPEG et redimensionnées avant d'être
stockées dans app/static/covers, sous un nom de fichier généré (uuid) pour
éviter toute collision.
"""

import uuid
from io import BytesIO
from pathlib import Path

import requests
from flask import current_app
from PIL import Image, ImageOps

DELAI_MAX = 8  # secondes

# De nombreux sites bloquent (403, page de remplacement, redirection) les
# requêtes dont l'en-tête User-Agent ne ressemble pas à un navigateur — sans
# ça, une image qui s'affiche très bien dans l'aperçu du navigateur (qui, lui,
# envoie un vrai User-Agent) peut échouer silencieusement au téléchargement
# côté serveur, qui n'en envoyait aucun.
EN_TETE_TELECHARGEMENT = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


def _dossier_covers():
    return Path(current_app.config["COVERS_DIR"])


def _nom_fichier_unique():
    return f"{uuid.uuid4().hex}.jpg"


def _redimensionner_et_sauver(image):
    # Les photos prises au smartphone stockent l'orientation réelle dans une
    # métadonnée EXIF plutôt que de faire pivoter les pixels eux-mêmes ;
    # Image.open() ne l'applique jamais automatiquement, d'où les couvertures
    # basculées à 90°/180° une fois enregistrées si on ne le fait pas ici.
    image = ImageOps.exif_transpose(image)
    image = image.convert("RGB")
    largeur_max, hauteur_max = current_app.config["COVER_MAX_SIZE"]
    image.thumbnail((largeur_max, hauteur_max))

    nom_fichier = _nom_fichier_unique()
    chemin = _dossier_covers() / nom_fichier
    image.save(chemin, "JPEG", quality=88)
    return nom_fichier


def telecharger_couverture(url):
    """Télécharge une image depuis une URL distante (ex. Open Library / Google
    Books, ou lien collé manuellement). Renvoie (nom_fichier, erreur) : l'un
    des deux est toujours None."""
    if not url:
        return None, None

    try:
        reponse = requests.get(url, headers=EN_TETE_TELECHARGEMENT, timeout=DELAI_MAX)
        reponse.raise_for_status()
    except requests.RequestException as e:
        return None, f"Le lien n'a pas pu être téléchargé ({e.__class__.__name__})."

    type_contenu = reponse.headers.get("Content-Type", "")
    if type_contenu.startswith("text/html"):
        return None, "Ce lien pointe vers une page web, pas directement vers un fichier image."

    try:
        image = Image.open(BytesIO(reponse.content))
        image.load()  # force le décodage complet ici pour détecter un format non supporté
    except Exception:
        return None, "Le format de cette image n'a pas pu être lu (fichier corrompu ou format non supporté)."

    return _redimensionner_et_sauver(image), None


def sauvegarder_upload(fichier_werkzeug):
    """Sauvegarde une image envoyée via formulaire (upload classique ou photo prise sur mobile)."""
    try:
        image = Image.open(fichier_werkzeug.stream)
    except Exception:
        return None

    return _redimensionner_et_sauver(image)


def supprimer_couverture(nom_fichier):
    if not nom_fichier:
        return
    chemin = _dossier_covers() / nom_fichier
    if chemin.exists():
        chemin.unlink()
