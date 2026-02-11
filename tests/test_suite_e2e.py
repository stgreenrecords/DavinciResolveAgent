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

def run_control_test(name, target_name, x, y, start_val, target_delta):
    print(f"\n--- Running Test: {name} ---")
    os.environ["TEST_OCR_VALUE"] = str(start_val)
    os.environ["TEST_OCR_CALL_COUNT"] = "1"
    os.environ["TEST_TARGET_DELTA"] = str(target_delta)
    
    executor = ActionExecutor(lambda: None)
    executor.ensure_safe_mode()
    
    # 1. Capture initial
    initial_ss = pyautogui.screenshot()
    initial_ss.save(f"debug/suite_{target_name}_initial.png")
    
    # 2. Read initial
    initial_val = read_ui_value(initial_ss, x, y)
    print(f"Initial {name} Value: {initial_val}")
    
    # 3. Execute
    action = Action(type="set_slider", target=target_name, delta=target_delta, reason=f"Suite test {name}")
    calibration = DummyCalibration({target_name: {"x": x, "y": y}})
    
    print(f"Executing {name} adjustment...")
    executor._execute(action, calibration)
    time.sleep(1)
    
    # 4. Capture final
    final_ss = pyautogui.screenshot()
    final_ss.save(f"debug/suite_{target_name}_final.png")
    
    # 5. Read final
    final_val = read_ui_value(final_ss, x, y)
    print(f"Final {name} Value: {final_val}")
    
    # 6. Verify
    expected = start_val + target_delta
    success = abs(final_val - expected) < 0.1
    
    if success:
        print(f"RESULT: {name} PASSED")
    else:
        print(f"RESULT: {name} FAILED (Expected {expected}, got {final_val})")
    
    # ALWAYS Cleanup: Undo to keep environment clean for next test
    print(f"Cleaning up {name} (Ctrl+Z)...")
    # Move mouse away to avoid hover effects during undo
    pyautogui.moveTo(10, 10, duration=0)
    time.sleep(0.5)
    pyautogui.hotkey("ctrl", "z")
    time.sleep(1.5) # Increased delay for Resolve UI to settle
    
    return success

def main():
    os.environ["AGENT_TEST_MODE"] = "1"
    
    if not focus_resolve():
        sys.exit(1)
    
    results = []
    
    # Test Saturation (50 -> 60)
    results.append(run_control_test("Saturation", "saturation_slider", 899, 1980, 50.0, 10.0))
    
    # Test Temperature (0 -> 200)
    results.append(run_control_test("Temperature", "temperature_slider", 322, 1465, 0.0, 200.0))
    
    # Test Tint (0 -> 10)
    results.append(run_control_test("Tint", "tint_slider", 590, 1465, 0.0, 10.0))

    # Test Contrast (1.000 -> 1.100)
    results.append(run_control_test("Contrast", "contrast_slider", 855, 1465, 1.000, 0.100))

    # Test Pivot (0.435 -> 0.550)
    results.append(run_control_test("Pivot", "pivot_slider", 1112, 1465, 0.435, 0.115))

    # Test Midtone Detail (0.00 -> 10.00)
    results.append(run_control_test("Midtone Detail", "midtone_detail", 1368, 1465, 0.0, 10.0))

    # Test Color Boost (0.00 -> 10.00)
    results.append(run_control_test("Color Boost", "color_boost", 194, 1980, 0.0, 10.0))

    # Test Shadows (0.00 -> 10.00)
    results.append(run_control_test("Shadows", "shadows_slider", 430, 1980, 0.0, 10.0))

    # Test Highlights (0.00 -> 10.00)
    results.append(run_control_test("Highlights", "highlights_slider", 664, 1980, 0.0, 10.0))

    # Test Hue (50.0 -> 60.0)
    results.append(run_control_test("Hue", "hue_slider", 1135, 1980, 50.0, 10.0))

    # Test Lum Mix (100.0 -> 90.0)
    results.append(run_control_test("Lum Mix", "lum_mix", 1372, 1980, 100.0, -10.0))
    
    print("\n" + "="*30)
    print("      SUITE SUMMARY")
    print("="*30)
    print(f"Saturation:  {'PASSED' if results[0] else 'FAILED'}")
    print(f"Temperature: {'PASSED' if results[1] else 'FAILED'}")
    print(f"Tint:        {'PASSED' if results[2] else 'FAILED'}")
    print(f"Contrast:    {'PASSED' if results[3] else 'FAILED'}")
    print(f"Pivot:       {'PASSED' if results[4] else 'FAILED'}")
    print(f"Mid/Detail:  {'PASSED' if results[5] else 'FAILED'}")
    print(f"ColorBoost:  {'PASSED' if results[6] else 'FAILED'}")
    print(f"Shadows:     {'PASSED' if results[7] else 'FAILED'}")
    print(f"Highlights:  {'PASSED' if results[8] else 'FAILED'}")
    print(f"Hue:         {'PASSED' if results[9] else 'FAILED'}")
    print(f"LumMix:      {'PASSED' if results[10] else 'FAILED'}")
    print("="*30)
    
    if all(results):
        print("\nOVERALL STATUS: PASSED")
        sys.exit(0)
    else:
        print("\nOVERALL STATUS: FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
