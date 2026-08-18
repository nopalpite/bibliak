from app.services import i18n_service, settings_service


def test_t_returns_french_by_default(app):
    assert i18n_service.t("Collection") == "Collection"


def test_t_translates_to_english_when_language_set(app):
    settings_service.set_setting("language", "en")
    assert i18n_service.t("Annuler") == "Cancel"


def test_t_falls_back_to_french_for_missing_key_in_other_language(app):
    settings_service.set_setting("language", "en")
    assert i18n_service.t("Clé qui n'existe dans aucun fichier") == "Clé qui n'existe dans aucun fichier"


def test_t_interpolates_placeholders(app):
    assert i18n_service.t("Tome {n}", n=3) == "Tome 3"


def test_tn_picks_singular_for_count_one(app):
    assert i18n_service.tn("{n} tome", "{n} tomes", 1) == "1 tome"


def test_tn_picks_plural_for_other_counts(app):
    assert i18n_service.tn("{n} tome", "{n} tomes", 0) == "0 tomes"
    assert i18n_service.tn("{n} tome", "{n} tomes", 3) == "3 tomes"


def test_tn_accepts_extra_placeholders_without_colliding_on_n(app):
    """Regression test: tn()'s count parameter used to be named `n`, which
    crashed with "got multiple values for argument 'n'" whenever a template
    also passed n= explicitly alongside the count."""
    result = i18n_service.tn(
        "{n} doublon ignoré (déjà présent dans la collection).",
        "{n} doublons ignorés (déjà présents dans la collection).",
        2,
    )
    assert result == "2 doublons ignorés (déjà présents dans la collection)."


def test_available_languages_includes_french_and_english(app):
    languages = i18n_service.available_languages()
    assert languages.get("fr") == "Français"
    assert languages.get("en") == "English"
