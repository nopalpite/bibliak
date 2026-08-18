"""Récupération des métadonnées d'un ouvrage à partir de son ISBN/EAN.

Deux sources sont interrogées, avec repli automatique de l'une vers l'autre :
- Open Library (gratuite, sans clé)
- Google Books (gratuite, clé optionnelle pour des quotas plus élevés)

Les BD et mangas sont souvent mal référencés dans ces bases généralistes :
le résultat doit donc toujours être considéré comme un pré-remplissage,
jamais comme une vérité absolue.
"""

import requests
from flask import current_app

DELAI_MAX = 6  # secondes


def _nettoyer_isbn(isbn):
    return isbn.strip().replace("-", "").replace(" ", "")


def _en_tete_http():
    """Construit l'en-tête User-Agent envoyé à chaque appel.

    Open Library recommande explicitement de s'identifier (nom de
    l'application + contact) : les requêtes identifiées bénéficient d'une
    limite de débit 3x plus généreuse (3 req/s au lieu d'1 req/s). Le contact
    se configure via la variable d'environnement CONTACT_INFO (voir .env).
    """
    contact = (current_app.config.get("CONTACT_INFO") or "").strip()
    agent = "MaBibliotheque/1.0 (application locale de gestion de collection)"
    if contact:
        agent += f" - {contact}"
    return {"User-Agent": agent}


def _depuis_open_library(isbn):
    url = "https://openlibrary.org/api/books"
    params = {"bibkeys": f"ISBN:{isbn}", "format": "json", "jscmd": "data"}
    reponse = requests.get(url, params=params, headers=_en_tete_http(), timeout=DELAI_MAX)
    reponse.raise_for_status()
    donnees = reponse.json().get(f"ISBN:{isbn}")
    if not donnees:
        return None

    auteurs = [a.get("name") for a in donnees.get("authors", []) if a.get("name")]
    editeurs = [e.get("name") for e in donnees.get("publishers", []) if e.get("name")]
    couverture = donnees.get("cover", {}) or {}

    return {
        "titre": donnees.get("title"),
        "auteurs": auteurs,
        "editeur": editeurs[0] if editeurs else None,
        "date_parution": donnees.get("publish_date"),
        "resume": donnees.get("subtitle"),
        "image_url": couverture.get("large") or couverture.get("medium"),
        "source": "Open Library",
    }


def _depuis_google_books(isbn, cle_api=None):
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": f"isbn:{isbn}"}
    if cle_api:
        params["key"] = cle_api
    reponse = requests.get(url, params=params, headers=_en_tete_http(), timeout=DELAI_MAX)
    reponse.raise_for_status()
    items = reponse.json().get("items")
    if not items:
        return None

    info = items[0].get("volumeInfo", {})
    liens_images = info.get("imageLinks", {}) or {}

    return {
        "titre": info.get("title"),
        "auteurs": info.get("authors", []),
        "editeur": info.get("publisher"),
        "date_parution": info.get("publishedDate"),
        "resume": info.get("description"),
        "image_url": liens_images.get("thumbnail") or liens_images.get("smallThumbnail"),
        "source": "Google Books",
    }


def rechercher_par_isbn(isbn, api_prioritaire="openlibrary", cle_api_google=None):
    """Interroge les deux sources dans l'ordre de priorité choisi.

    Renvoie un tuple (resultat, sources_en_erreur) :
    - resultat : le premier résultat exploitable trouvé, ou None
    - sources_en_erreur : noms des sources n'ayant pas pu être contactées
      (timeout, erreur réseau, erreur HTTP) — à distinguer d'une source ayant
      répondu normalement mais ne connaissant pas cet ISBN.
    """
    isbn_normalise = _nettoyer_isbn(isbn)

    sources = [
        ("Open Library", _depuis_open_library),
        ("Google Books", lambda i: _depuis_google_books(i, cle_api_google)),
    ]
    if api_prioritaire == "googlebooks":
        sources.reverse()

    sources_en_erreur = []
    for nom_source, fonction in sources:
        try:
            resultat = fonction(isbn_normalise)
        except requests.RequestException:
            sources_en_erreur.append(nom_source)
            continue
        if resultat and resultat.get("titre"):
            resultat["isbn"] = isbn_normalise
            return resultat, sources_en_erreur

    return None, sources_en_erreur
