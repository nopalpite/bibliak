"""UI translations, loaded from flat JSON files in app/translations/.

Deliberately simple, no build step: each app/translations/<code>.json is a
flat {"source French text": "translated text"} map, plus an optional
"_name" key giving the language's display name. French (fr.json) is the
reference: every key used anywhere in the app must exist there, and any
other language falls back to it for missing keys — a half-translated
language file never breaks the UI, it just shows French for the gaps.

Adding a language (e.g. Croatian) is just dropping a new hr.json in this
folder: available_languages() discovers it automatically, no code change.
"""

import json
from pathlib import Path

from flask import g

from app.services.settings_service import get_setting

TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "translations"
REFERENCE_LANGUAGE = "fr"

_cache = {}


def _load(locale):
    if locale in _cache:
        return _cache[locale]

    path = TRANSLATIONS_DIR / f"{locale}.json"
    if not path.exists():
        data = {}
    else:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

    _cache[locale] = data
    return data


def available_languages():
    """Returns {locale_code: display_name}, discovered from whatever
    <code>.json files are present in app/translations/."""
    languages = {}
    for path in sorted(TRANSLATIONS_DIR.glob("*.json")):
        code = path.stem
        data = _load(code)
        languages[code] = data.get("_name", code)
    return languages


def current_locale():
    if "locale" not in g:
        try:
            g.locale = get_setting("language", REFERENCE_LANGUAGE)
        except Exception:
            # Database not ready yet (e.g. very first request before
            # `flask init-db` has run) — fall back rather than break the page.
            g.locale = REFERENCE_LANGUAGE
    return g.locale


def t(key, **kwargs):
    """Translates `key` (the reference French text) into the current
    language. Falls back to French, then to the key itself, if the
    translation is missing. Supports {placeholder} interpolation via
    str.format()."""
    locale = current_locale()

    translations = _load(locale)
    text = translations.get(key)

    if text is None and locale != REFERENCE_LANGUAGE:
        text = _load(REFERENCE_LANGUAGE).get(key)

    if text is None:
        text = key

    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text


def tn(singular_key, plural_key, count, **kwargs):
    """Translates `singular_key` if count == 1, `plural_key` otherwise.
    Simple two-way split (no full CLDR plural categories) — enough for the
    languages this app targets. `{n}` is available in the translated string
    for the count itself; pass extra kwargs for any other placeholder."""
    key = singular_key if count == 1 else plural_key
    kwargs.setdefault("n", count)
    return t(key, **kwargs)
