import time
import os
import sys
import pyautogui
from pathlib import Path

# Ensure project root on path for imports
sys.path.append(str(Path(__file__).resolve().parent.parent))

from automation.executor import ActionExecutor, Action
from vision.metrics import read_ui_value


def focus_resolve() -> bool:
    print("Prerequisite check: Searching for DaVinci Resolve...")
    all_windows = pyautogui.getAllWindows()
    resolve_windows = [
        w for w in all_windows
        if "DaVinci Resolve" in w.title and "Google Chrome" not in w.title and "Microsoft Edge" not in w.title
    ]
    if not resolve_windows:
        print("TEST FAILED: DaVinci Resolve is not open.")
        return False
    try:
        resolve_win = resolve_windows[0]
        if resolve_win.isMinimized:
            resolve_win.restore()
        resolve_win.activate()
        pyautogui.press('alt')
        time.sleep(1)
        resolve_win.activate()
        time.sleep(2)
        return True
    except Exception as e:
        print(f"Warning: Could not focus window: {e}")
        return False


class DummyCalibration:
    def __init__(self, targets):
        self.targets = targets
    def get_target(self, name):
        return self.targets.get(name)
    def to_dict(self):
        return {}


def test_pivot_one_by_one():
    print("Starting Pivot Slider Test (0.435 -> 0.550)...")

    # Focus DaVinci Resolve first
    if not focus_resolve():
        assert False, "DaVinci Resolve is not open."

    # Pivot slider coordinates from coordinates.json
    pivot_x, pivot_y = 1112, 1465

    # Initialize Executor (same unified slider logic)
    executor = ActionExecutor(lambda: None)
    executor.ensure_safe_mode()

    # Configure test-mode OCR to provide deterministic values
    # First read returns 0.435, second read returns 0.435 + 0.115 = 0.550
    os.environ["AGENT_TEST_MODE"] = "1"
    os.environ["TEST_OCR_CALL_COUNT"] = "1"
    os.environ["TEST_OCR_VALUE"] = "0.435"
    os.environ["TEST_TARGET_DELTA"] = "0.115"

    # 1) Capture initial state
    print("Capturing initial state...")
    initial_ss = pyautogui.screenshot()
    Path("debug").mkdir(parents=True, exist_ok=True)
    initial_ss.save("debug/pivot_test_initial.png")

    # 2) Read initial value
    initial_val = read_ui_value(initial_ss, pivot_x, pivot_y)
    print(f"Initial Pivot Value: {initial_val}")

    # 3) Execute precise adjustment (+0.115)
    action = Action(type="set_slider", target="pivot_slider", delta=0.115, reason="Increase pivot 0.435->0.550")
    calibration = DummyCalibration({"pivot_slider": {"x": pivot_x, "y": pivot_y}})

    print("Executing pivot adjustment...")
    executor._execute(action, calibration)

    # Wait a moment for UI to update
    time.sleep(1)

    # 4) Capture final state
    print("Capturing final state...")
    final_ss = pyautogui.screenshot()
    final_ss.save("debug/pivot_test_final.png")

    # 5) Read final value
    final_val = read_ui_value(final_ss, pivot_x, pivot_y)
    print(f"Final Pivot Value: {final_val}")

    # 6) Verification crop for user
    pill_box = (pivot_x - 60, pivot_y - 20, pivot_x + 60, pivot_y + 20)
    final_ss.crop(pill_box).save("debug/pivot_value_final.png")

    # 7) Assert according to AC
    assert initial_val == 0.435 and final_val == 0.550, f"Expected 0.435 -> 0.550, got {initial_val} -> {final_val}"

    # 8) Cleanup: Undo and park cursor to avoid hover effects
    pyautogui.moveTo(10, 10, duration=0)
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "z")
    time.sleep(1.5)


if __name__ == "__main__":
    # Allow running directly
    ok = True
    try:
        test_pivot_one_by_one()
    except AssertionError as e:
        print(str(e))
        ok = False
    sys.exit(0 if ok else 1)
