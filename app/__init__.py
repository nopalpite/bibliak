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
        except Exception:
            global_default_view = "grid"
        return {"global_default_view": global_default_view}

    @app.cli.command("init-db")
    def init_db():
        """Creates the tables if they don't exist yet (first launch), and
        applies small ad-hoc migrations for columns added since
        (create_all() never alters existing tables).

        For finer-grained schema evolution management going forward, you can
        initialize Alembic with:
            flask db init
            flask db migrate -m "initial state"
            flask db upgrade
        """
        with app.app_context():
            db.create_all()
            _apply_adhoc_migrations()
        print("Database initialized.")

    def _apply_adhoc_migrations():
        """Adds missing columns to an already existing database, without
        touching the data. Idempotent: does nothing if the column already
        exists."""
        from sqlalchemy import inspect, text

        inspector = inspect(db.engine)
        if "books" not in inspector.get_table_names():
            return  # table not created yet, create_all() just laid everything out correctly

        columns = {c["name"] for c in inspector.get_columns("books")}
        if "read" not in columns:
            with db.engine.begin() as connection:
                connection.execute(
                    text("ALTER TABLE books ADD COLUMN read BOOLEAN NOT NULL DEFAULT 0")
                )
            print("Ad-hoc migration applied: books.read")

    return app
