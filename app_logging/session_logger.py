import json
from pathlib import Path

from PIL import Image
from PySide6 import QtGui

from config.paths import SESSIONS_DIR


class SessionLogger:
    """Writes per-session artifacts (images, metrics, responses) to disk."""

    def __init__(self):
        self.root = SESSIONS_DIR
        self.root.mkdir(parents=True, exist_ok=True)
        self.session_dir = self.root / f"session_{self._timestamp()}"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    def log_session_info(self, settings_dict: dict, calibration_dict: dict):
        info = {"settings": settings_dict, "calibration": calibration_dict, "timestamp": self._timestamp()}
        (self.session_dir / "session_info.json").write_text(json.dumps(info, indent=2))

    def log_iteration(self, idx, before_image, after_image, metrics, response):
        iter_dir = self.session_dir / f"iter_{idx:03d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        self._save_image(iter_dir / "before.png", before_image)
        self._save_image(iter_dir / "after.png", after_image)
        (iter_dir / "metrics.json").write_text(json.dumps(metrics.__dict__, indent=2))
        (iter_dir / "response.json").write_text(json.dumps(response.raw, indent=2))

    def log_action_screenshot(self, iter_idx, action_idx, action_type, image, phase: str = "before"):
        iter_dir = self.session_dir / f"iter_{iter_idx:03d}"
        iter_dir.mkdir(parents=True, exist_ok=True)
        actions_dir = iter_dir / "actions"
        actions_dir.mkdir(parents=True, exist_ok=True)

        safe_phase = phase if phase in ("before", "after") else "before"
        path = actions_dir / f"action_{action_idx:02d}_{action_type}_{safe_phase}.png"
        self._save_image(path, image)

    def _save_image(self, path: Path, image):
        if isinstance(image, Image.Image):
            image.save(path)
            return
        if isinstance(image, QtGui.QImage):
            image.save(str(path))
            return
        raise ValueError("Unsupported image type for logging.")

    @staticmethod
    def _timestamp() -> str:
        from datetime import datetime

        return datetime.now().strftime("%Y%m%d_%H%M%S")
