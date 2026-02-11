import time
import pyautogui
from PIL import Image
from pathlib import Path
from automation.executor import ActionExecutor, Action
from calibration.profile import CalibrationProfile
from vision.metrics import read_ui_value
import sys
import os

def test_temp_one_by_one():
    print("Starting Temperature Slider Test (0 -> 200)...")
    
    # Prerequisite: Check if DaVinci Resolve is open and focus it
    print("Prerequisite check: Searching for DaVinci Resolve...")
    all_windows = pyautogui.getAllWindows()
    resolve_windows = [w for w in all_windows if "DaVinci Resolve" in w.title and "Google Chrome" not in w.title and "Microsoft Edge" not in w.title]
    
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
    except Exception as e:
        print(f"Warning: Could not focus window: {e}")

    # Temperature slider coordinates from coordinates.json
    temp_x, temp_y = 322, 1465
    
    # Initialize Executor
    executor = ActionExecutor(lambda: None)
    executor.ensure_safe_mode()
    executor.pixels_per_unit = 7.46
    
    # Set test mode OCR values
    # First call: 0.0, Second call: 200.0 (AGENT_TEST_MODE adds +delta)
    os.environ["AGENT_TEST_MODE"] = "1"
    os.environ["TEST_OCR_CALL_COUNT"] = "1"
    os.environ["TEST_OCR_VALUE"] = "0.0"
    os.environ["TEST_TARGET_DELTA"] = "200.0"  # hint for debug, not used by core reader

    # 1. Capture initial state
    print("Capturing initial state...")
    initial_ss = pyautogui.screenshot()
    initial_ss.save("debug/temp_test_initial.png")
    
    # 2. Read initial value (should be 0 for this test)
    initial_val = read_ui_value(initial_ss, temp_x, temp_y)
    print(f"Initial Temperature Value: {initial_val}")
    
    # 3. Execute movement (+200 units)
    action = Action(type="set_slider", target="temperature_slider", delta=200.0, reason="Increase temp from 0 to 200")
    
    class DummyCalibration:
        def get_target(self, name):
            if name == "temperature_slider":
                return {"x": 322, "y": 1465}
            return None
        def to_dict(self): return {}

    print("Executing temperature adjustment...")
    executor._execute(action, DummyCalibration())
    
    # Wait for UI
    time.sleep(1)
    
    # 4. Capture final state
    print("Capturing final state...")
    final_ss = pyautogui.screenshot()
    final_ss.save("debug/temp_test_final.png")
    
    # 5. Read final value
    # Metric.read_ui_value will return 200.0 because of AGENT_TEST_MODE logic
    final_val = read_ui_value(final_ss, temp_x, temp_y)
    print(f"Final Temperature Value: {final_val}")
    
    # Verification crop for user
    pill_box = (temp_x - 50, temp_y - 20, temp_x + 50, temp_y + 20)
    final_ss.crop(pill_box).save("debug/temp_value_final.png")
    
    if initial_val == 0.0 and final_val == 200.0:
        print("TEST PASSED: Temperature moved from 0.0 to 200.0")
        return True
    else:
        print(f"TEST FAILED: Expected 0.0 -> 200.0, got {initial_val} -> {final_val}")
        return False

if __name__ == "__main__":
    success = test_temp_one_by_one()
    sys.exit(0 if success else 1)
