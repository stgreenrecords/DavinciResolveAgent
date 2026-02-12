import json
from dataclasses import dataclass

from config.paths import CONTROLLER_CONFIG_PATH
from core.roi import Roi


@dataclass
class CalibrationProfile:
    roi: dict
    screen_width: int
    screen_height: int
    targets: dict
    control_metadata: dict | None = None
    full_config: dict | None = None  # Store the full controllerConfig.json structure
    _cached_config: dict | None = None

    @classmethod
    def _load_coordinates(cls) -> tuple[dict, dict, dict, dict]:
        if cls._cached_config is None:
            if CONTROLLER_CONFIG_PATH.exists():
                try:
                    cls._cached_config = json.loads(CONTROLLER_CONFIG_PATH.read_text())
                except Exception:
                    cls._cached_config = {}
            else:
                cls._cached_config = {}

        data = cls._cached_config or {}
        flat_targets = {}
        metadata = {}
        roi_data = data.get("ROICoordinates", {})
        
        # Sliders
        if "sliders" in data:
            for name, details in data["sliders"].items():
                if details.get("x") != "" and details.get("y") != "":
                    flat_targets[name] = {"x": int(details["x"]), "y": int(details["y"])}
                metadata[name] = {
                    "type": "slider",
                    "description": name,
                    "min": details.get("min"),
                    "max": details.get("max"),
                    "defaultValue": details.get("defaultValue"),
                }
        # Wheels
        if "wheels" in data:
            for wheel_name, components in data["wheels"].items():
                for comp_name, details in components.items():
                    target_name = f"{wheel_name}_{comp_name}"
                    if details.get("x") != "" and details.get("y") != "":
                        flat_targets[target_name] = {"x": int(details["x"]), "y": int(details["y"])}
                    metadata[target_name] = {
                        "type": "wheel_component",
                        "description": f"{wheel_name} {comp_name}",
                        "min": details.get("min"),
                        "max": details.get("max"),
                        "defaultValue": details.get("defaultValue"),
                    }
        return flat_targets, metadata, data, roi_data

    @staticmethod
    def from_roi(roi: Roi, screen_size: tuple[int, int] | None = None) -> "CalibrationProfile":
        width = screen_size[0] if screen_size else roi.width
        height = screen_size[1] if screen_size else roi.height
        center_x = roi.x + int(roi.width / 2)
        center_y = roi.y + int(roi.height / 2)

        targets, metadata, full_config, _ = CalibrationProfile._load_coordinates()
        targets["roi_center"] = {"x": center_x, "y": center_y}
        metadata["roi_center"] = {"type": "point", "description": "ROI center"}

        return CalibrationProfile(
            roi={"x": roi.x, "y": roi.y, "width": roi.width, "height": roi.height},
            screen_width=width,
            screen_height=height,
            targets=targets,
            control_metadata=metadata,
            full_config=full_config,
        )

    @staticmethod
    def from_config() -> "CalibrationProfile" | None:
        """Load calibration profile from controllerConfig.json if ROI is present."""
        targets, metadata, full_config, roi_data = CalibrationProfile._load_coordinates()
        if not roi_data or not roi_data.get("left_top") or not roi_data.get("right_bottom"):
            return None
        
        try:
            lt = roi_data["left_top"].split(",")
            rb = roi_data["right_bottom"].split(",")
            rx, ry = int(lt[0]), int(lt[1])
            rw, rh = int(rb[0]) - rx, int(rb[1]) - ry
            
            roi = Roi(rx, ry, rw, rh)
            # We don't have screen size easily here, but from_roi will handle it or use ROI size
            return CalibrationProfile.from_roi(roi)
        except (ValueError, IndexError, KeyError):
            return None

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
            "full_config": self.full_config or {},
        }

    @staticmethod
    def from_dict(data: dict) -> "CalibrationProfile":
        cp = CalibrationProfile(
            roi=data["roi"],
            screen_width=data.get("screen_width", 0),
            screen_height=data.get("screen_height", 0),
            targets=data.get("targets", {}),
            control_metadata=data.get("control_metadata", {}),
            full_config=data.get("full_config", {}),
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
