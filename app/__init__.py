import os

from flask import Flask
from sqlalchemy import inspect, text

from .config import Config
from .extensions import db, migrate


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["COVERS_DIR"], exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    # Explicit model import so they're known to Alembic/Flask-Migrate
    from . import models  # noqa: F401
    from .routes.admin import admin_bp
    from .routes.books import books_bp
    from .routes.main import main_bp
    from .routes.scan import scan_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(books_bp, url_prefix="/books")
    app.register_blueprint(scan_bp, url_prefix="/scan")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    from .services.i18n_service import current_locale, t, tn
    app.jinja_env.globals["t"] = t
    app.jinja_env.globals["tn"] = tn
    app.jinja_env.globals["current_locale"] = current_locale

    @app.context_processor
    def inject_globals():
        from .services.settings_service import get_setting
        try:
            global_default_view = get_setting("default_view", "grid")
            global_theme = get_setting("theme", "classic")
        except Exception:
            global_default_view = "grid"
            global_theme = "classic"
        return {"global_default_view": global_default_view, "global_theme": global_theme}

    @app.cli.command("init-db")
    def init_db():
        """Brings the database up to the latest schema via Alembic
        (migrations/), run on every container start.

        A database created before Alembic was wired up here (tables already
        exist, no alembic_version table yet) is stamped as already matching
        the baseline migration instead of Alembic trying to re-create tables
        that are already there — after applying the one ad-hoc column fix
        that predates the baseline, for anyone jumping straight from a very
        old version.
        """
        from flask_migrate import stamp, upgrade

        with app.app_context():
            inspector = inspect(db.engine)
            pre_alembic_db = (
                "books" in inspector.get_table_names()
                and "alembic_version" not in inspector.get_table_names()
            )
            if pre_alembic_db:
                _apply_adhoc_migrations()
                stamp()
            upgrade()
        print("Database initialized.")

    def _apply_adhoc_migrations():
        """Adds the "read" column to a database predating both it and
        Alembic being wired up here. Idempotent: does nothing if the column
        already exists."""
        inspector = inspect(db.engine)
        columns = {c["name"] for c in inspector.get_columns("books")}
        if "read" not in columns:
            with db.engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE books ADD COLUMN read BOOLEAN NOT NULL DEFAULT 0")
                )
            print("Ad-hoc migration applied: books.read")

    return app
