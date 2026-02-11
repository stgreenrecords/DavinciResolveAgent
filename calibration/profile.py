import json
from pathlib import Path
from dataclasses import dataclass

from app_ui.roi_selector import Roi


@dataclass
class CalibrationProfile:
    roi: dict
    screen_width: int
    screen_height: int
    targets: dict
    control_metadata: dict | None = None  # Store control type info

    @staticmethod
    def _load_coordinates() -> tuple[dict, dict]:
        coord_path = Path(__file__).resolve().parent.parent / "coordinates.json"
        if coord_path.exists():
            try:
                data = json.loads(coord_path.read_text())
                flat_targets = {}
                metadata = {}
                for category, controls in data.items():
                    ctype = "slider" if category == "sliders" else "wheel"
                    for name, coords in controls.items():
                        flat_targets[name] = {"x": coords["x"], "y": coords["y"]}
                        metadata[name] = {"type": ctype, "description": name.replace("_", " ").title()}
                return flat_targets, metadata
            except Exception:
                pass
        return {}, {}

    @staticmethod
    def from_roi(roi: Roi, screen_size: tuple[int, int] | None = None) -> "CalibrationProfile":
        width = screen_size[0] if screen_size else roi.width
        height = screen_size[1] if screen_size else roi.height
        center_x = roi.x + int(roi.width / 2)
        center_y = roi.y + int(roi.height / 2)
        
        targets, metadata = CalibrationProfile._load_coordinates()
        targets["roi_center"] = {"x": center_x, "y": center_y}
        metadata["roi_center"] = {"type": "point", "description": "ROI center"}

        return CalibrationProfile(
            roi={"x": roi.x, "y": roi.y, "width": roi.width, "height": roi.height},
            screen_width=width,
            screen_height=height,
            targets=targets,
            control_metadata=metadata
        )

    def update_roi(self, roi: Roi):
        """Update ROI while preserving other targets."""
        self.roi = {"x": roi.x, "y": roi.y, "width": roi.width, "height": roi.height}
        center_x = roi.x + int(roi.width / 2)
        center_y = roi.y + int(roi.height / 2)
        self.targets["roi_center"] = {"x": center_x, "y": center_y}

    def to_dict(self) -> dict:
        return {
            "roi": self.roi,
            "screen_width": self.screen_width,
            "screen_height": self.screen_height,
            "targets": self.targets,
            "control_metadata": self.control_metadata or {},
        }

    @staticmethod
    def from_dict(data: dict) -> "CalibrationProfile":
        cp = CalibrationProfile(
            roi=data["roi"],
            screen_width=data.get("screen_width", 0),
            screen_height=data.get("screen_height", 0),
            targets=data.get("targets", {}),
            control_metadata=data.get("control_metadata", {}),
        )
        # Ensure roi_center is always present and updated based on current ROI
        if "x" in cp.roi and "y" in cp.roi:
            center_x = cp.roi["x"] + int(cp.roi["width"] / 2)
            center_y = cp.roi["y"] + int(cp.roi["height"] / 2)
            cp.targets["roi_center"] = {"x": center_x, "y": center_y}
            if cp.control_metadata is None:
                cp.control_metadata = {}
            cp.control_metadata["roi_center"] = {"type": "point", "description": "ROI center"}
        return cp

    def get_target(self, name: str) -> dict | None:
        return self.targets.get(name)
