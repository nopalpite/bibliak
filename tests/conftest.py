import pytest

from app import create_app
from app.config import Config
from app.extensions import db as _db
from app.models import Author, Location, Publisher, Series, Tag


@pytest.fixture
def app(tmp_path):
    class TestConfig(Config):
        TESTING = True
        SQLALCHEMY_DATABASE_URI = "sqlite://"
        SECRET_KEY = "test-secret-key"
        COVERS_DIR = tmp_path / "covers"

    application = create_app(TestConfig)

    with application.app_context():
        _db.create_all()
        yield application
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app):
    return _db


@pytest.fixture
def series(db):
    obj = Series(name="XIII")
    db.session.add(obj)
    db.session.commit()
    return obj


@pytest.fixture
def publisher(db):
    obj = Publisher(name="Dargaud")
    db.session.add(obj)
    db.session.commit()
    return obj


@pytest.fixture
def author(db):
    obj = Author(full_name="Jean Van Hamme")
    db.session.add(obj)
    db.session.commit()
    return obj


@pytest.fixture
def location(db):
    obj = Location(label="Salon")
    db.session.add(obj)
    db.session.commit()
    return obj


@pytest.fixture
def tag(db):
    obj = Tag(label="humour")
    db.session.add(obj)
    db.session.commit()
    return obj
