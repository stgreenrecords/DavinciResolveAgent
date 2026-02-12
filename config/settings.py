from __future__ import annotations

from functools import lru_cache

try:
    from pydantic_settings import BaseSettings as PydanticBaseSettings
    from pydantic_settings import SettingsConfigDict as PydanticSettingsConfigDict
except ModuleNotFoundError:  # pragma: no cover - fallback for minimal test environments

    class SettingsConfigDict(dict):
        pass

    class BaseSettings:  # type: ignore[override]
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

else:
    BaseSettings = PydanticBaseSettings  # type: ignore[misc]
    SettingsConfigDict = PydanticSettingsConfigDict  # type: ignore[misc]

from config.constants import (
    DEFAULT_API_ENDPOINT,
    DEFAULT_CONTINUOUS_DELAY,
    DEFAULT_FOCUS_TITLE,
    DEFAULT_INTER_ACTION_DELAY,
    DEFAULT_JPEG_QUALITY,
    DEFAULT_MAX_IMAGE_DIM,
    DEFAULT_MODEL,
)


class AppSettings(BaseSettings):
    api_endpoint: str = DEFAULT_API_ENDPOINT
    default_model: str = DEFAULT_MODEL
    max_image_dim: int = DEFAULT_MAX_IMAGE_DIM
    jpeg_quality: int = DEFAULT_JPEG_QUALITY
    inter_action_delay: float = DEFAULT_INTER_ACTION_DELAY
    continuous_delay: float = DEFAULT_CONTINUOUS_DELAY
    focus_window_title: str = DEFAULT_FOCUS_TITLE
    debug_screenshots: bool = False

    model_config = SettingsConfigDict(env_prefix="RESOLVE_AGENT_", env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_app_settings() -> AppSettings:
    return AppSettings()
