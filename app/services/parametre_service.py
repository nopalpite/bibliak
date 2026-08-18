"""Gestion des paramètres configurables depuis la page d'administration.

Les paramètres sont stockés en base (table `parametres`) sous forme clé/valeur,
la valeur étant sérialisée en JSON pour pouvoir contenir des listes.
"""

import json

from app.extensions import db
from app.models import Parametre

VALEURS_PAR_DEFAUT = {
    "types_ouvrages": ["BD", "Manga", "Comics", "Roman", "Autre"],
    "etats_ouvrages": ["Neuf", "Bon état", "Usagé", "Abîmé"],
    "api_prioritaire": "openlibrary",
    "vue_par_defaut": "grille",
    # Politique de détection des doublons, appliquée uniformément partout où
    # un ouvrage est créé (ajout manuel, scan, import) : voir ouvrage_service.trouver_doublon
    "detection_doublons": "isbn_et_titre",
}

# Choix possibles pour "detection_doublons", utilisés par la page d'administration
CHOIX_DETECTION_DOUBLONS = [
    ("isbn_et_titre", "ISBN, puis titre + tome si l'ISBN est absent (recommandé)"),
    ("isbn_uniquement", "ISBN uniquement"),
    ("desactivee", "Désactivée"),
]


def _garantir_valeurs_par_defaut():
    modifie = False
    for cle, valeur in VALEURS_PAR_DEFAUT.items():
        if db.session.get(Parametre, cle) is None:
            db.session.add(Parametre(cle=cle, valeur=json.dumps(valeur)))
            modifie = True
    if modifie:
        db.session.commit()


def get_parametre(cle, defaut=None):
    _garantir_valeurs_par_defaut()
    parametre = db.session.get(Parametre, cle)
    if parametre is None:
        return VALEURS_PAR_DEFAUT.get(cle, defaut)
    return json.loads(parametre.valeur)


def set_parametre(cle, valeur):
    parametre = db.session.get(Parametre, cle)
    if parametre is None:
        parametre = Parametre(cle=cle, valeur=json.dumps(valeur))
        db.session.add(parametre)
    else:
        parametre.valeur = json.dumps(valeur)
    db.session.commit()
