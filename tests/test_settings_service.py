from app.services import settings_service


def test_get_setting_returns_default_value_when_unset(app, db):
    assert settings_service.get_setting("language") == "fr"
    assert settings_service.get_setting("default_view") == "grid"


def test_get_setting_unknown_key_returns_explicit_default(app, db):
    assert settings_service.get_setting("does_not_exist", "fallback") == "fallback"


def test_set_setting_then_get_roundtrip(app, db):
    settings_service.set_setting("language", "en")
    assert settings_service.get_setting("language") == "en"


def test_set_setting_persists_list_values(app, db):
    settings_service.set_setting("item_types", ["BD", "Artbook"])
    assert settings_service.get_setting("item_types") == ["BD", "Artbook"]


def test_set_setting_overwrites_existing_value(app, db):
    settings_service.set_setting("default_view", "list")
    settings_service.set_setting("default_view", "shelves")
    assert settings_service.get_setting("default_view") == "shelves"
