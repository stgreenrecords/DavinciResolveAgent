from __future__ import annotations

import logging

from storage.settings import Settings, SettingsStore


class SettingsManager:
    """Coordinates settings persistence and logging for the UI layer."""

    def __init__(self, settings_store: SettingsStore, logger: logging.Logger | None = None):
        self._settings_store = settings_store
        self._logger = logger or logging.getLogger("app.settings")

    def load(self) -> Settings:
        """Load persisted settings from storage."""
        settings = self._settings_store.load_settings()
        self._logger.info("Settings loaded")
        return settings

    def save(self, api_key: str, model: str, endpoint: str, allow_insecure: bool = False) -> None:
        """Persist settings to storage, optionally allowing insecure API key storage."""
        self._settings_store.save_settings(
            api_key=api_key,
            model=model,
            endpoint=endpoint,
            allow_insecure=allow_insecure,
        )
        self._logger.info("Settings saved")
