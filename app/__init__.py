import os

from flask import Flask

from .config import Config
from .extensions import db, migrate


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["COVERS_DIR"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    # Import explicite des modèles pour qu'ils soient connus d'Alembic/Flask-Migrate
    from . import models  # noqa: F401

    from .routes.main import main_bp
    from .routes.ouvrages import ouvrages_bp
    from .routes.scan import scan_bp
    from .routes.admin import admin_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(ouvrages_bp, url_prefix="/ouvrages")
    app.register_blueprint(scan_bp, url_prefix="/scan")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.context_processor
    def injecter_globals():
        from .services.parametre_service import get_parametre
        try:
            vue_par_defaut = get_parametre("vue_par_defaut", "grille")
        except Exception:
            vue_par_defaut = "grille"
        return {"vue_par_defaut_globale": vue_par_defaut}

    @app.cli.command("init-db")
    def init_db():
        """Crée les tables si elles n'existent pas encore (premier lancement),
        et applique les petites migrations ad-hoc pour les colonnes ajoutées
        depuis (create_all() ne modifie jamais les tables existantes).

        Pour une gestion plus fine des évolutions de schéma par la suite,
        vous pouvez initialiser Alembic avec :
            flask db init
            flask db migrate -m "état initial"
            flask db upgrade
        """
        with app.app_context():
            db.create_all()
            _appliquer_migrations_adhoc()
        print("Base de données initialisée.")

    def _appliquer_migrations_adhoc():
        """Ajoute les colonnes manquantes sur une base déjà existante, sans
        toucher aux données. Idempotent : ne fait rien si la colonne existe déjà."""
        from sqlalchemy import inspect, text

        inspecteur = inspect(db.engine)
        if "ouvrages" not in inspecteur.get_table_names():
            return  # table pas encore créée, create_all() vient de tout poser correctement

        colonnes = {c["name"] for c in inspecteur.get_columns("ouvrages")}
        if "lu" not in colonnes:
            with db.engine.begin() as connexion:
                connexion.execute(
                    text("ALTER TABLE ouvrages ADD COLUMN lu BOOLEAN NOT NULL DEFAULT 0")
                )
            print("Migration ad-hoc appliquée : ouvrages.lu")

    return app
