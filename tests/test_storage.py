import storage.settings as settings_module

from storage.settings import SettingsStore


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "keyring", None)
    store = SettingsStore()
    store.config_path = tmp_path / "config.json"
    store.save_settings("key", "model", "endpoint")
    settings = store.load_settings()
    assert settings.model == "model"
    assert settings.endpoint == "endpoint"
