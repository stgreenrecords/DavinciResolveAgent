import time
import pyautogui
import os
import sys
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

def diagnose_tint():
    if not focus_resolve(): return
    
    x, y = 590, 1465
    print(f"\nDiagnosing Tint at ({x}, {y})...")
    
    # 1. Capture initial
    ss1 = pyautogui.screenshot()
    ss1.save("debug/tint_diag_initial.png")
    # We use real OCR here
    os.environ["AGENT_TEST_MODE"] = "0"
    val1 = read_ui_value(ss1, x, y)
    print(f"  Initial Tint (Real): {val1}")
    
    # 2. Perform a fixed 50px drag
    print(f"  Performing 50px drag (positive)...")
    pyautogui.moveTo(x, y)
    pyautogui.mouseDown()
    pyautogui.moveRel(50, 0, duration=0.5)
    pyautogui.mouseUp()
    time.sleep(1)
    
    # 3. Get final value
    ss2 = pyautogui.screenshot()
    ss2.save("debug/tint_diag_drag1.png")
    val2 = read_ui_value(ss2, x, y)
    print(f"  After 50px drag: {val2}")
    
    # 4. Cleanup
    pyautogui.hotkey("ctrl", "z")
    time.sleep(1)

    if val1 is not None and val2 is not None:
        delta = abs(val2 - val1)
        if delta > 0:
            ratio = 50.0 / delta
            print(f"  CALCULATED RATIO: {ratio:.4f} pixels per unit")
        else:
            print("  ERROR: No change detected in UI.")
    else:
        print("  ERROR: OCR failed to read Tint value.")

if __name__ == "__main__":
    diagnose_tint()
