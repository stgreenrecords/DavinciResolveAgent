import json
import logging
from dataclasses import dataclass
from typing import Any

from calibration.profile import CalibrationProfile
from config.constants import DEFAULT_KEYRING_SERVICE, ERROR_INSECURE_STORAGE_WARNING, ERROR_SECURE_STORAGE_UNAVAILABLE
from config.paths import CONFIG_PATH

keyring_module: Any | None
try:
    import keyring as keyring_module
except Exception:  # pragma: no cover
    keyring_module = None

keyring: Any | None = keyring_module


@dataclass
class Settings:
    """User-configured API settings loaded from storage."""

    api_key: str | None = None
    model: str | None = None
    endpoint: str | None = None


class SettingsStore:
    """Persists settings and calibration data to disk and keyring."""

    def __init__(self):
        self.config_path = CONFIG_PATH
        self.service_name = DEFAULT_KEYRING_SERVICE

    def save_settings(self, api_key: str, model: str, endpoint: str, allow_insecure: bool = False):
        """Persist API settings, optionally allowing insecure API key storage."""
        data = {
            "model": model,
            "endpoint": endpoint,
        }
        self.config_path.write_text(json.dumps(data, indent=2))
        if keyring is not None:
            try:
                keyring.set_password(self.service_name, "api_key", api_key)
                return
            except Exception as exc:  # pragma: no cover - depends on keyring backend
                logging.warning("Keyring storage failed: %s", exc)
        if not allow_insecure:
            raise RuntimeError(ERROR_SECURE_STORAGE_UNAVAILABLE)
        logging.warning(ERROR_INSECURE_STORAGE_WARNING)
        data["api_key"] = api_key
        self.config_path.write_text(json.dumps(data, indent=2))

    def load_settings(self) -> Settings:
        """Load API settings and retrieve API key from keyring when available."""
        if not self.config_path.exists():
            return Settings()
        data = json.loads(self.config_path.read_text())
        api_key = None
        if keyring is not None:
            api_key = keyring.get_password(self.service_name, "api_key")
        else:
            api_key = data.get("api_key")
        return Settings(
            api_key=api_key,
            model=data.get("model"),
            endpoint=data.get("endpoint"),
        )

    def save_calibration(self, calibration: CalibrationProfile):
        """Persist calibration data into the config JSON."""
        data = {"calibration": calibration.to_dict()}
        if self.config_path.exists():
            try:
                current = json.loads(self.config_path.read_text())
                current.update(data)
                data = current
            except json.JSONDecodeError:
                pass
        self.config_path.write_text(json.dumps(data, indent=2))

    def load_calibration(self) -> CalibrationProfile | None:
        """Load calibration data from the config JSON if present."""
        if not self.config_path.exists():
            return None
        try:
            data = json.loads(self.config_path.read_text())
            cal = data.get("calibration")
            if not cal:
                return None
            return CalibrationProfile.from_dict(cal)
        except (json.JSONDecodeError, KeyError):
            return None
