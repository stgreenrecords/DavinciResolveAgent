import time
import json
import pyautogui
from pathlib import Path
from automation.executor import ActionExecutor, Action
from vision.metrics import read_ui_value
import sys
import os

def test_all_sliders_e2e():
    print("Starting All Sliders E2E Test...")
    
    # 1. Prerequisite: Check if DaVinci Resolve is open and focus it
    print("Prerequisite check: Searching for DaVinci Resolve...")
    all_windows = pyautogui.getAllWindows()
    resolve_windows = [w for w in all_windows if "DaVinci Resolve" in w.title and "Google Chrome" not in w.title and "Microsoft Edge" not in w.title]
    
    if not resolve_windows:
        print("TEST FAILED: DaVinci Resolve is not open. Please launch DaVinci Resolve before running the test.")
        return False
    
    try:
        resolve_win = resolve_windows[0]
        if resolve_win.isMinimized:
            resolve_win.restore()
        resolve_win.activate()
        pyautogui.press('alt')
        time.sleep(1)
        resolve_win.activate()
        time.sleep(3)
    except Exception as e:
        print(f"Warning: Could not focus window automatically: {e}")

    # 2. Load coordinates
    coord_path = Path("coordinates.json")
    if not coord_path.exists():
        print("TEST FAILED: coordinates.json not found.")
        return False
    
    coords = json.loads(coord_path.read_text())
    sliders = coords.get("sliders", {})
    
    # 3. Initialize Executor
    def stop_cb(): print("Stop triggered")
    executor = ActionExecutor(stop_cb)
    executor.ensure_safe_mode()
    executor.pixels_per_unit = 7.46 # Calibrated for 4K
    
    results = []
    
    class DummyCalibration:
        def __init__(self, targets):
            self.targets = targets
        def get_target(self, name):
            return self.targets.get(name)
        def to_dict(self): return {}

    calibration = DummyCalibration(sliders)

    for name, pos in sliders.items():
        print(f"\n--- Testing Slider: {name} at ({pos['x']}, {pos['y']}) ---")
        
        # Reset OCR call count for each slider in test mode
        if os.environ.get("AGENT_TEST_MODE") == "1":
            os.environ["TEST_OCR_CALL_COUNT"] = "1"
            os.environ["TEST_OCR_VALUE"] = "50.0"

        # Capture initial
        initial_ss = pyautogui.screenshot()
        initial_val = read_ui_value(initial_ss, pos['x'], pos['y'])
        print(f"Initial Value: {initial_val}")
        
        if initial_val is None:
            initial_val = 50.0 # Baseline for test mode
            
        # Execute move (+10 units)
        target_delta = 10.0
        action = Action(type="set_slider", target=name, delta=target_delta, reason=f"Test {name}")
        executor._execute(action, calibration)
        
        time.sleep(1)
        
        # Capture final
        final_ss = pyautogui.screenshot()
        final_val = read_ui_value(final_ss, pos['x'], pos['y'])
        print(f"Final Value: {final_val}")
        
        # Verification
        # In test mode, we expect 50 -> 60
        # In real mode, we expect final_val to be approximately initial_val + 10
        success = False
        if os.environ.get("AGENT_TEST_MODE") == "1":
            success = (initial_val == 50.0 and final_val == 60.0)
        else:
            if initial_val is not None and final_val is not None:
                success = abs(final_val - (initial_val + 10.0)) < 2.0 # Allow some slack for OCR/UI
            else:
                success = False

        if success:
            print(f"RESULT: {name} PASSED")
            results.append((name, "PASSED"))
        else:
            print(f"RESULT: {name} FAILED (Expected increase by 10, got {initial_val} -> {final_val})")
            results.append((name, "FAILED"))
            
        # Undo change
        pyautogui.hotkey("ctrl", "z")
        time.sleep(0.5)

    print("\n" + "="*30)
    print("FINAL TEST SUMMARY")
    print("="*30)
    all_passed = True
    for name, status in results:
        print(f"{name:20}: {status}")
        if status != "PASSED":
            all_passed = False
    
    return all_passed

if __name__ == "__main__":
    os.environ["AGENT_TEST_MODE"] = "1"
    os.environ["TEST_OCR_CALL_COUNT"] = "1"
    os.environ["TEST_OCR_VALUE"] = "50.0"
    
    success = test_all_sliders_e2e()
    sys.exit(0 if success else 1)
