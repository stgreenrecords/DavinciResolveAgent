import time
import pyautogui
import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from automation.executor import ActionExecutor, Action
from vision.metrics import read_ui_value

def focus_resolve():
    print("Searching for DaVinci Resolve...")
    all_windows = pyautogui.getAllWindows()
    resolve_windows = [w for w in all_windows if "DaVinci Resolve" in w.title and "Google Chrome" not in w.title and "Microsoft Edge" not in w.title]
    if not resolve_windows:
        print("ERROR: DaVinci Resolve not found.")
        return False
    try:
        win = resolve_windows[0]
        if win.isMinimized: win.restore()
        win.activate()
        pyautogui.press('alt')
        time.sleep(1)
        win.activate()
        time.sleep(2)
        return True
    except:
        return False

def calibrate_slider(name, x, y):
    print(f"\nCalibrating {name} at ({x}, {y})...")
    
    # Use real OCR if possible, but for this measurement we might need manual help or test mode hacks
    # Actually, we'll try to use the REAL OCR (pytesseract) to get the ratio
    
    # 1. Get baseline
    ss1 = pyautogui.screenshot()
    val1 = read_ui_value(ss1, x, y)
    if val1 is None:
        print(f"  Could not read initial value for {name}. Ensure Tesseract is installed or values are visible.")
        return None
    
    # 2. Perform a fixed 100px drag
    print(f"  Performing 100px drag...")
    pyautogui.moveTo(x, y)
    pyautogui.mouseDown()
    pyautogui.moveRel(100, 0, duration=0.5)
    pyautogui.mouseUp()
    time.sleep(1)
    
    # 3. Get final value
    ss2 = pyautogui.screenshot()
    val2 = read_ui_value(ss2, x, y)
    
    # 4. Undo
    pyautogui.hotkey("ctrl", "z")
    time.sleep(0.5)
    
    if val2 is None:
        print(f"  Could not read final value for {name}.")
        return None
    
    delta = abs(val2 - val1)
    if delta == 0:
        print(f"  No change detected for {name}. Slider might be stuck or coordinates wrong.")
        return None
    
    ratio = 100.0 / delta
    print(f"  Result: {val1} -> {val2} (Delta: {delta:.2f})")
    print(f"  Ratio: {ratio:.4f} pixels per unit")
    return ratio

def main():
    if not focus_resolve(): return

    # Load coordinates
    with open("coordinates.json", "r") as f:
        coords = json.load(f)
    
    ratios = {}
    
    # We turn OFF agent test mode to get REAL values from the screen
    os.environ["AGENT_TEST_MODE"] = "0"
    
    for name, pos in coords["sliders"].items():
        ratio = calibrate_slider(name, pos["x"], pos["y"])
        if ratio:
            ratios[name] = ratio
        else:
            # Fallback if OCR fails
            print(f"  Skipping {name} due to measurement failure.")
    
    print("\n" + "="*30)
    print("   CALIBRATION SUMMARY")
    print("="*30)
    for name, ratio in ratios.items():
        print(f"{name:20}: {ratio:.4f}")
    
    # Save to a new file
    with open("slider_ratios.json", "w") as f:
        json.dump(ratios, f, indent=2)
    print("\nSaved to slider_ratios.json")

if __name__ == "__main__":
    main()
