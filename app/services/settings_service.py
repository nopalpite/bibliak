"""Management of the settings configurable from the administration page.

Settings are stored in the database (`settings` table) as key/value pairs,
the value being JSON-serialized so it can hold lists too.
"""

import json

from flask import g

from app.extensions import db
from app.models import Setting

DEFAULT_VALUES = {
    "item_types": ["BD", "Manga", "Comics", "Roman", "Autre"],
    "conditions": ["Neuf", "Bon état", "Usagé", "Abîmé"],
    "default_view": "grid",
    "language": "en",
    # Duplicate detection policy, applied uniformly wherever a book is
    # created (manual add, scan, import) — see book_service.find_duplicate
    "duplicate_detection": "isbn_and_title",
}

# Possible choices for "duplicate_detection", used by the administration page
DUPLICATE_DETECTION_CHOICES = [
    ("isbn_and_title", "ISBN, then title + volume if the ISBN is missing (recommended)"),
    ("isbn_only", "ISBN only"),
    ("disabled", "Disabled"),
]


def _ensure_default_values():
    """Seeds any DEFAULT_VALUES key missing from the settings table.

    Runs at most once per request (cached on `g`): get_setting() is called
    several times rendering a single page, and every one of those calls used
    to re-check all of DEFAULT_VALUES with its own SELECT, even though
    nothing can have changed mid-request.
    """
    if getattr(g, "_settings_defaults_ensured", False):
        return
    changed = False
    for key, value in DEFAULT_VALUES.items():
        if db.session.get(Setting, key) is None:
            db.session.add(Setting(key=key, value=json.dumps(value)))
            changed = True
    if changed:
        db.session.commit()
    g._settings_defaults_ensured = True


def get_setting(key, default=None):
    _ensure_default_values()
    setting = db.session.get(Setting, key)
    if setting is None:
        return DEFAULT_VALUES.get(key, default)
    return json.loads(setting.value)


def set_setting(key, value):
    setting = db.session.get(Setting, key)
    if setting is None:
        setting = Setting(key=key, value=json.dumps(value))
        db.session.add(setting)
    else:
        setting.value = json.dumps(value)
    db.session.commit()
