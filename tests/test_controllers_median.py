import json
import logging
import os
import sys
import time
from pathlib import Path

# Add project root to path before other local imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

import pyautogui  # noqa: E402
from PySide6 import QtCore, QtWidgets  # noqa: E402

from automation.executor import Action, ActionExecutor  # noqa: E402


def setup_logging():
    project_root = Path(__file__).resolve().parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    # Configure logging to append to the existing app.log
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger("test.median")


def focus_resolve(logger):
    logger.info("Searching for DaVinci Resolve...")
    all_windows = pyautogui.getAllWindows()
    resolve_windows = [
        w
        for w in all_windows
        if "DaVinci Resolve" in w.title and "Google Chrome" not in w.title and "Microsoft Edge" not in w.title
    ]

    if not resolve_windows:
        logger.error("TEST FAILED: DaVinci Resolve is not open.")
        return False

    try:
        resolve_win = resolve_windows[0]
        if resolve_win.isMinimized:
            resolve_win.restore()
        resolve_win.activate()
        pyautogui.press("alt")
        time.sleep(0.5)
        resolve_win.activate()
        time.sleep(1.0)
        return True
    except Exception as e:
        logger.warning(f"Could not focus window: {e}")
        return False


class DummyCalibration:
    def __init__(self, targets):
        self.targets = targets

    def get_target(self, name):
        return self.targets.get(name)

    def to_dict(self):
        return {}


def main():
    logger = setup_logging()
    logger.info("Starting Median Controller Test...")

    if os.environ.get("AGENT_E2E") != "1":
        logger.warning("E2E controller test skipped. Set AGENT_E2E=1 to run.")
        return

    if not focus_resolve(logger):
        sys.exit(1)

    # Load coordinates
    config_path = Path("controllerConfig.json")
    if not config_path.exists():
        logger.error("TEST FAILED: controllerConfig.json not found.")
        sys.exit(1)

    config = json.loads(config_path.read_text())

    # Collect all calibrated targets and their ranges
    targets = {}
    test_actions = []

    # Sliders
    for name, data in config.get("sliders", {}).items():
        if data.get("x") != "" and data.get("y") != "":
            x, y = int(data["x"]), int(data["y"])
            min_val = float(data["min"])
            max_val = float(data["max"])
            default_val = float(data.get("defaultValue", 0))

            # Use median, but if median is same as default, shift it by 10% of range
            median = (min_val + max_val) / 2
            if abs(median - default_val) < 0.001:
                range_val = max_val - min_val
                if range_val > 0:
                    # Shift by 10% of range, but stay within bounds
                    shift = range_val * 0.1
                    if median + shift <= max_val:
                        median += shift
                    else:
                        median -= shift

            logger.info(
                f"[DEBUG] Slider {name}: min={min_val}, max={max_val}, default={default_val}, test_val={median}"
            )
            targets[name] = {"x": x, "y": y}
            test_actions.append(
                Action(type="set_slider", target=name, value=median, reason=f"Setting {name} to test value {median}")
            )

    # Wheels (also set absolute values via double click for components)
    for wheel_name, components in config.get("wheels", {}).items():
        for comp_name, data in components.items():
            if data.get("x") != "" and data.get("y") != "":
                x, y = int(data["x"]), int(data["y"])
                min_val = float(data["min"])
                max_val = float(data["max"])
                default_val = float(data.get("defaultValue", 0))

                # Use median, but if median is same as default, shift it by 10% of range
                median = (min_val + max_val) / 2
                if abs(median - default_val) < 0.001:
                    range_val = max_val - min_val
                    if range_val > 0:
                        shift = range_val * 0.1
                        if median + shift <= max_val:
                            median += shift
                        else:
                            median -= shift

                target_name = f"{wheel_name}_{comp_name}"
                logger.info(
                    f"[DEBUG] Wheel {target_name}: min={min_val}, max={max_val}, "
                    f"default={default_val}, test_val={median}"
                )
                targets[target_name] = {"x": x, "y": y}
                test_actions.append(
                    Action(
                        type="set_slider",
                        target=target_name,
                        value=median,
                        reason=f"Setting {target_name} to test value {median}",
                    )
                )

    if not test_actions:
        logger.error("TEST FAILED: No calibrated controllers found.")
        sys.exit(1)

    executor = ActionExecutor(lambda: None, log_callback=logger.info)
    executor.ensure_safe_mode()
    calibration = DummyCalibration(targets)

    logger.info("Executing %d adjustments to median positions...", len(test_actions))

    # Use execute_actions which handles the stop flag (ESC/Pause)
    logger.info("Action sequence starting...")
    # Flush stdout to ensure debug logs appear in MainWindow's ACTION LOG
    sys.stdout.flush()
    executed = executor.execute_actions(
        actions=[{"type": a.type, "target": a.target, "value": a.value, "reason": a.reason} for a in test_actions],
        calibration=calibration,
        inter_action_delay=0.5,
    )

    if len(executed) < len(test_actions) and executor.is_stopped():
        logger.info("TEST STOPPED: User pressed ESC or Pause.")
        sys.exit(0)

    if len(executed) < len(test_actions):
        logger.error("TEST FAILED: Not all actions were executed.")
        sys.exit(1)

    # Ask user for verification
    app = QtWidgets.QApplication.instance()
    if not app:
        app = QtWidgets.QApplication(sys.argv)

    msg = QtWidgets.QMessageBox()
    msg.setWindowTitle("Verification")
    msg.setText("If all controllers that you calibrated were moved?")
    msg.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No)
    msg.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Yes)
    msg.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)

    # We need to bring the message box to front
    msg.show()
    msg.raise_()
    msg.activateWindow()

    result = msg.exec()

    if result == QtWidgets.QMessageBox.StandardButton.Yes:
        logger.info("User confirmed. Clicking fullResetButton...")
        reset_data = config.get("fullResetButton", {})
        if reset_data.get("x") != "" and reset_data.get("y") != "":
            rx, ry = int(reset_data["x"]), int(reset_data["y"])
            pyautogui.click(rx, ry)
            logger.info("TEST PASSED")
            sys.exit(0)
        else:
            logger.error("Error: fullResetButton is not calibrated.")
            sys.exit(1)
    else:
        logger.info("User denied. Suggesting recalibration.")
        msg2 = QtWidgets.QMessageBox()
        msg2.setWindowTitle("Test Failed")
        msg2.setText("Test failed. Would you like to recalibrate controllers?")
        msg2.setStandardButtons(QtWidgets.QMessageBox.StandardButton.Retry | QtWidgets.QMessageBox.StandardButton.Close)
        msg2.setWindowFlags(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        result2 = msg2.exec()
        if result2 == QtWidgets.QMessageBox.StandardButton.Retry:
            logger.info("Status: RECALIBRATE")
            sys.exit(2)  # Special exit code for recalibration
        else:
            logger.info("Status: EXIT")
            sys.exit(1)


if __name__ == "__main__":
    main()
