from __future__ import annotations

import json
import logging

from PySide6 import QtWidgets

from app_ui.controller_calibrator import ControllerCalibratorDialog
from automation.executor import ActionExecutor
from calibration.profile import CalibrationProfile
from config.constants import (
    ERROR_CALIBRATION_FAILED,
    ERROR_CONTROLLER_CONFIG_MISSING,
    ERROR_PRIMARY_SCREEN,
    ERROR_ROI_TOO_SMALL,
)
from config.paths import CONTROLLER_CONFIG_PATH
from core.roi import Roi
from storage.settings import SettingsStore


class CalibrationManager:
    """Handles ROI and controller calibration workflows."""

    def __init__(self, settings_store: SettingsStore, logger: logging.Logger | None = None) -> None:
        self._settings_store = settings_store
        self._logger = logger or logging.getLogger("app.calibration")

    def load(self) -> CalibrationProfile | None:
        """Load persisted calibration data, if available."""
        return self._settings_store.load_calibration()

    def save(self, calibration: CalibrationProfile) -> None:
        """Persist calibration data to storage."""
        self._settings_store.save_calibration(calibration)

    def calibrate_controllers(
        self,
        parent: QtWidgets.QWidget,
        executor: ActionExecutor,
        calibration: CalibrationProfile | None,
    ) -> CalibrationProfile | None:
        """Launch controller calibration and persist updated coordinates."""
        try:
            if not executor.try_focus_resolve():
                self._logger.warning("Could not automatically focus DaVinci Resolve.")

            screen = QtWidgets.QApplication.primaryScreen()
            if not screen:
                QtWidgets.QMessageBox.critical(parent, "Error", ERROR_PRIMARY_SCREEN)
                return calibration
            pixmap = screen.grabWindow(0)

            if not CONTROLLER_CONFIG_PATH.exists():
                QtWidgets.QMessageBox.critical(parent, "Error", ERROR_CONTROLLER_CONFIG_MISSING)
                return calibration
            config = json.loads(CONTROLLER_CONFIG_PATH.read_text())

            dialog = ControllerCalibratorDialog(pixmap, config, parent)
            if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
                return calibration
            coords = dialog.coordinates
            for name, c in coords.items():
                if name in config["sliders"]:
                    config["sliders"][name]["x"] = str(c["x"])
                    config["sliders"][name]["y"] = str(c["y"])
                elif name in config["wheels"]:
                    for comp_name, comp_c in c.items():
                        if comp_name in config["wheels"][name]:
                            config["wheels"][name][comp_name]["x"] = str(comp_c["x"])
                            config["wheels"][name][comp_name]["y"] = str(comp_c["y"])
                elif name == "fullResetButton":
                    config["fullResetButton"]["x"] = str(c["x"])
                    config["fullResetButton"]["y"] = str(c["y"])

            CONTROLLER_CONFIG_PATH.write_text(json.dumps(config, indent=2))

            # Update ROI if it was calibrated during this session
            if dialog.roi_coordinates:
                config["ROICoordinates"] = dialog.roi_coordinates
                CONTROLLER_CONFIG_PATH.write_text(json.dumps(config, indent=2))
                
                # Update calibration profile with the new ROI
                lt = dialog.roi_coordinates["left_top"].split(",")
                rb = dialog.roi_coordinates["right_bottom"].split(",")
                rx, ry = int(lt[0]), int(lt[1])
                rw, rh = int(rb[0]) - rx, int(rb[1]) - ry
                
                new_roi = Roi(rx, ry, rw, rh)
                if calibration:
                    calibration.update_roi(new_roi)
                else:
                    calibration = CalibrationProfile.from_roi(new_roi)
                self.save(calibration)

            if calibration:
                calibration = CalibrationProfile.from_roi(
                    Roi(
                        calibration.roi["x"],
                        calibration.roi["y"],
                        calibration.roi["width"],
                        calibration.roi["height"],
                    ),
                    (calibration.screen_width, calibration.screen_height),
                )
                self.save(calibration)

            QtWidgets.QMessageBox.information(parent, "Success", "Controllers calibrated successfully")
            return calibration
        except Exception as exc:
            self._logger.exception("Calibration failed")
            QtWidgets.QMessageBox.critical(
                parent,
                "Error",
                ERROR_CALIBRATION_FAILED.format(details=exc),
            )
            return calibration

    def is_controllers_calibrated(self) -> bool:
        """Return True if controllerConfig.json contains any calibrated targets."""
        if not CONTROLLER_CONFIG_PATH.exists():
            return False
        try:
            config = json.loads(CONTROLLER_CONFIG_PATH.read_text())
            for slider in config.get("sliders", {}).values():
                if slider.get("x") and slider.get("y"):
                    return True
            for wheel in config.get("wheels", {}).values():
                for comp in wheel.values():
                    if comp.get("x") and comp.get("y"):
                        return True
            return False
        except Exception:
            return False
