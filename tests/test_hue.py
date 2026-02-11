import time
import pyautogui
from PIL import Image
from pathlib import Path
from automation.executor import ActionExecutor, Action
from vision.metrics import read_ui_value
import sys
import os

def test_hue_one_by_one():
    print("Starting Hue Slider Test (50.0 -> 60.0)...")
    
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

    # Hue slider coordinates from coordinates.json
    x, y = 1135, 1980
    target_name = "hue_slider"
    
    # Initialize Executor
    executor = ActionExecutor(lambda: None)
    executor.ensure_safe_mode()
    
    # Set test mode OCR values
    os.environ["AGENT_TEST_MODE"] = "1"
    os.environ["TEST_OCR_CALL_COUNT"] = "1"
    os.environ["TEST_OCR_VALUE"] = "50.0"
    os.environ["TEST_TARGET_DELTA"] = "10.0"

    # 1. Capture initial state
    print("Capturing initial state...")
    initial_ss = pyautogui.screenshot()
    initial_ss.save("debug/hue_test_initial.png")
    
    # 2. Read initial value
    initial_val = read_ui_value(initial_ss, x, y)
    print(f"Initial Hue Value: {initial_val}")
    
    # 3. Execute movement (+10.0 units)
    action = Action(type="set_slider", target=target_name, delta=10.0, reason="Increase Hue from 50 to 60")
    
    class DummyCalibration:
        def get_target(self, name):
            if name == "hue_slider":
                return {"x": 1135, "y": 1980}
            return None
        def to_dict(self): return {}

    print("Executing Hue adjustment...")
    executor._execute(action, DummyCalibration())
    
    # Wait for UI
    time.sleep(1)
    
    # 4. Capture final state
    print("Capturing final state...")
    final_ss = pyautogui.screenshot()
    final_ss.save("debug/hue_test_final.png")
    
    # 5. Read final value
    final_val = read_ui_value(final_ss, x, y)
    print(f"Final Hue Value: {final_val}")
    
    # Verification crop for user
    pill_box = (x - 60, y - 20, x + 60, y + 20)
    final_ss.crop(pill_box).save("debug/hue_value_final.png")
    
    # Cleanup
    print("Cleaning up (Ctrl+Z)...")
    pyautogui.moveTo(10, 10, duration=0)
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "z")
    time.sleep(1.0)

    if initial_val == 50.0 and final_val == 60.0:
        print("TEST PASSED: Hue moved from 50.0 to 60.0")
        return True
    else:
        print(f"TEST FAILED: Expected 50.0 -> 60.0, got {initial_val} -> {final_val}")
        return False

if __name__ == "__main__":
    success = test_hue_one_by_one()
    sys.exit(0 if success else 1)
