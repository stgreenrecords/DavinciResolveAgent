import json
from dataclasses import dataclass
from pathlib import Path

try:
    import keyring
except Exception:  # pragma: no cover
    keyring = None

from calibration.profile import CalibrationProfile


@dataclass
class Settings:
    api_key: str | None = None
    model: str | None = None
    endpoint: str | None = None


class SettingsStore:
    def __init__(self):
        self.config_path = Path(__file__).resolve().parent.parent / "config.json"
        self.service_name = "resolve-agent"

    def save_settings(self, api_key: str, model: str, endpoint: str):
        data = {
            "model": model,
            "endpoint": endpoint,
        }
        self.config_path.write_text(json.dumps(data, indent=2))
        if keyring is not None:
            keyring.set_password(self.service_name, "api_key", api_key)
        else:
            data["api_key"] = api_key
            self.config_path.write_text(json.dumps(data, indent=2))

    def load_settings(self) -> Settings:
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
