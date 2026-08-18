"""Management of the settings configurable from the administration page.

Settings are stored in the database (`settings` table) as key/value pairs,
the value being JSON-serialized so it can hold lists too.
"""

import json

from app.extensions import db
from app.models import Setting

DEFAULT_VALUES = {
    "item_types": ["BD", "Manga", "Comics", "Roman", "Autre"],
    "conditions": ["Neuf", "Bon état", "Usagé", "Abîmé"],
    "priority_api": "openlibrary",
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
    changed = False
    for key, value in DEFAULT_VALUES.items():
        if db.session.get(Setting, key) is None:
            db.session.add(Setting(key=key, value=json.dumps(value)))
            changed = True
    if changed:
        db.session.commit()


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
