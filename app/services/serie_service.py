"""Suggestion (best-effort) du nombre total de tomes d'une série.

Il n'existe pas de base de données fiable et exhaustive pour cette
information, en particulier pour les BD francophones. Deux approches
complémentaires sont utilisées :

- AniList (gratuite, sans clé) : assez fiable pour les mangas, qui y sont
  bien référencés avec leur nombre de tomes officiel.
- Google Books : à défaut, une heuristique qui cherche le plus grand numéro
  de tome mentionné parmi les éditions cataloguées sous ce nom de série.
  C'est une estimation, pas une donnée officielle — elle doit toujours être
  présentée comme telle et jamais appliquée automatiquement sans confirmation
  de l'utilisateur.
"""

import re

import requests

DELAI_MAX = 6

MOTIFS_NUMERO_TOME = [
    re.compile(r"tome\s*#?\s*(\d{1,3})", re.IGNORECASE),
    re.compile(r"\bvol(?:ume)?\.?\s*#?\s*(\d{1,3})", re.IGNORECASE),
    re.compile(r"\bt\.?\s*(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"#(\d{1,3})"),
]


def _extraire_numero_tome(texte):
    if not texte:
        return None
    for motif in MOTIFS_NUMERO_TOME:
        correspondance = motif.search(texte)
        if correspondance:
            try:
                return int(correspondance.group(1))
            except ValueError:
                continue
    return None


def _depuis_anilist(nom_serie):
    """AniList référence explicitement le nombre de tomes (champ `volumes`)
    pour la plupart des mangas connus : une source assez fiable quand elle
    trouve une correspondance."""
    requete_graphql = """
    query ($recherche: String) {
      Media(search: $recherche, type: MANGA) {
        title { romaji english }
        volumes
        status
      }
    }
    """
    try:
        reponse = requests.post(
            "https://graphql.anilist.co",
            json={"query": requete_graphql, "variables": {"recherche": nom_serie}},
            timeout=DELAI_MAX,
        )
        reponse.raise_for_status()
        media = reponse.json().get("data", {}).get("Media")
    except requests.RequestException:
        return None

    if not media or not media.get("volumes"):
        return None

    titre_trouve = media["title"].get("romaji") or media["title"].get("english") or nom_serie
    return {
        "valeur": media["volumes"],
        "source": f"AniList — {titre_trouve}",
        "fiable": media.get("status") == "FINISHED",
    }


def _depuis_google_books(nom_serie):
    """Heuristique : cherche le plus grand numéro de tome mentionné parmi les
    éditions référencées sous ce nom de série. Fonctionne surtout pour les
    séries bien cataloguées ; à traiter comme une estimation basse, jamais
    comme un chiffre officiel."""
    try:
        reponse = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f'intitle:"{nom_serie}"', "maxResults": 40},
            timeout=DELAI_MAX,
        )
        reponse.raise_for_status()
        items = reponse.json().get("items", [])
    except requests.RequestException:
        return None

    numeros = []
    for item in items:
        info = item.get("volumeInfo", {})
        for champ in (info.get("title"), info.get("subtitle")):
            numero = _extraire_numero_tome(champ)
            if numero:
                numeros.append(numero)

    if not numeros:
        return None

    return {
        "valeur": max(numeros),
        "source": "Google Books (estimation d'après les éditions référencées)",
        "fiable": False,
    }


def suggerer_nb_tomes(nom_serie, type_ouvrage=None):
    """Renvoie {"valeur": int, "source": str, "fiable": bool}, ou None si
    aucune suggestion n'a pu être trouvée. `fiable=False` signale une
    estimation à vérifier plutôt qu'un chiffre officiel confirmé."""
    if type_ouvrage == "Manga":
        suggestion = _depuis_anilist(nom_serie)
        if suggestion:
            return suggestion

    return _depuis_google_books(nom_serie)
