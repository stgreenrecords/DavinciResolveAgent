from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
SESSIONS_DIR = PROJECT_ROOT / "sessions"
CONFIG_PATH = PROJECT_ROOT / "config.json"
CONTROLLER_CONFIG_PATH = PROJECT_ROOT / "controllerConfig.json"
DEBUG_DIR = PROJECT_ROOT / "debug"
