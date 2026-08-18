import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


class Config:
    """Configuration de l'application, lue depuis les variables d'environnement.

    Aucune donnée sensible n'est nécessaire : l'application est prévue pour un
    usage strictement local, sans authentification.
    """

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-a-changer")

    _db_path = os.environ.get("DATABASE_PATH", "instance/biblio.sqlite3")
    SQLALCHEMY_DATABASE_URI = "sqlite:///" + str(BASE_DIR / _db_path)
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Couvertures des ouvrages
    COVERS_DIR = BASE_DIR / "app" / "static" / "covers"
    COVER_MAX_SIZE = (600, 900)  # largeur / hauteur max en pixels

    # Certificat HTTPS auto-signé (généré par entrypoint.sh), exposé en
    # téléchargement pour permettre son installation comme profil de confiance
    # sur iOS (nécessaire pour débloquer l'accès caméra sur Safari).
    CERT_DIR = BASE_DIR / "certs"

    # Récupération des métadonnées par ISBN
    API_PRIORITAIRE = os.environ.get("API_PRIORITAIRE", "openlibrary")
    GOOGLE_BOOKS_API_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY", "")

    # Coordonnées de contact envoyées dans l'en-tête User-Agent des appels à
    # Open Library / Google Books : Open Library accorde une limite de débit
    # 3x plus généreuse aux requêtes identifiées (voir isbn_service.py).
    CONTACT_INFO = os.environ.get("CONTACT_INFO", "")

    ITEMS_PAR_PAGE = 60
