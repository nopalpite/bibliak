from app.services import i18n_service, settings_service


def test_t_returns_english_by_default(app):
    assert i18n_service.t("Collection") == "Collection"


def test_t_translates_to_french_when_language_set(app):
    settings_service.set_setting("language", "fr")
    assert i18n_service.t("Cancel") == "Annuler"


def test_t_falls_back_to_english_for_missing_key_in_other_language(app):
    settings_service.set_setting("language", "fr")
    assert i18n_service.t("A key that exists in no translation file") == "A key that exists in no translation file"


def test_t_interpolates_placeholders(app):
    assert i18n_service.t("Volume {n}", n=3) == "Volume 3"


def test_tn_picks_singular_for_count_one(app):
    assert i18n_service.tn("{n} volume", "{n} volumes", 1) == "1 volume"


def test_tn_picks_plural_for_other_counts(app):
    assert i18n_service.tn("{n} volume", "{n} volumes", 0) == "0 volumes"
    assert i18n_service.tn("{n} volume", "{n} volumes", 3) == "3 volumes"


def test_tn_accepts_extra_placeholders_without_colliding_on_n(app):
    """Regression test: tn()'s count parameter used to be named `n`, which
    crashed with "got multiple values for argument 'n'" whenever a template
    also passed n= explicitly alongside the count."""
    result = i18n_service.tn(
        "{n} duplicate skipped (already in the collection).",
        "{n} duplicates skipped (already in the collection).",
        2,
    )
    assert result == "2 duplicates skipped (already in the collection)."


def test_available_languages_includes_french_and_english(app):
    languages = i18n_service.available_languages()
    assert languages.get("fr") == "Français"
    assert languages.get("en") == "English"
