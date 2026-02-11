import time
import pyautogui
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from automation.executor import ActionExecutor, Action
from vision.metrics import read_ui_value

def focus_resolve():
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
        return True
    except Exception as e:
        print(f"Warning: Could not focus window: {e}")
        return False

class DummyCalibration:
    def __init__(self, targets):
        self.targets = targets
    def get_target(self, name):
        return self.targets.get(name)
    def to_dict(self): return {}

def test_contrast():
    print("Starting Contrast Test (1.000 -> 1.100)...")
    
    if not focus_resolve():
        return False

    # Contrast slider coordinates from coordinates.json: (855, 1465)
    x, y = 855, 1465
    target_name = "contrast_slider"
    
    # 1.000 -> 1.100 is a delta of 0.1
    start_val = 1.000
    target_delta = 0.1
    
    # Set test mode OCR values
    os.environ["AGENT_TEST_MODE"] = "1"
    os.environ["TEST_OCR_VALUE"] = str(start_val)
    os.environ["TEST_OCR_CALL_COUNT"] = "1"
    os.environ["TEST_TARGET_DELTA"] = str(target_delta)

    executor = ActionExecutor(lambda: None)
    executor.ensure_safe_mode()
    
    # 1. Capture initial state
    print("Capturing initial state...")
    initial_ss = pyautogui.screenshot()
    initial_ss.save("debug/contrast_test_initial.png")
    
    # 2. Read initial
    initial_val = read_ui_value(initial_ss, x, y)
    print(f"Initial Contrast Value: {initial_val}")
    
    # 3. Execute movement
    action = Action(type="set_slider", target=target_name, delta=target_delta, reason="Contrast test 1.0 to 1.1")
    calibration = DummyCalibration({target_name: {"x": x, "y": y}})
    
    print("Executing contrast adjustment...")
    executor._execute(action, calibration)
    time.sleep(1)
    
    # 4. Capture final state
    print("Capturing final state...")
    final_ss = pyautogui.screenshot()
    final_ss.save("debug/contrast_test_final.png")
    
    # 5. Read final
    final_val = read_ui_value(final_ss, x, y)
    print(f"Final Contrast Value: {final_val}")
    
    # Verification crop
    pill_box = (x - 60, y - 20, x + 60, y + 20)
    final_ss.crop(pill_box).save("debug/contrast_value_final.png")
    
    # 6. Verify
    expected = start_val + target_delta
    success = abs(final_val - expected) < 0.001
    
    if success:
        print("RESULT: Contrast PASSED")
    else:
        print(f"RESULT: Contrast FAILED (Expected {expected}, got {final_val})")
    
    # Cleanup
    print("Cleaning up (Ctrl+Z)...")
    pyautogui.moveTo(10, 10, duration=0)
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "z")
    time.sleep(1.5)
    
    return success

if __name__ == "__main__":
    success = test_contrast()
    sys.exit(0 if success else 1)
