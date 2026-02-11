import logging
import random
import time
from dataclasses import dataclass

import pyautogui
from vision.metrics import read_ui_value
from pynput import keyboard


from pathlib import Path

@dataclass
class Action:
    type: str
    target: str
    dx: float | None = None
    dy: float | None = None
    value: float | None = None
    keys: list | None = None
    reason: str | None = None


class ActionExecutor:
    def __init__(self, stop_callback, log_callback=None, focus_title: str = "DaVinci Resolve"):
        self.stop_callback = stop_callback
        self.log_callback = log_callback
        self.focus_title = focus_title
        self.logger = logging.getLogger("app.executor")
        self._stop = False
        self._paused = False
        self._listener = keyboard.Listener(on_press=self._on_key)
        self._listener.start()
        self.last_action = None

    def _on_key(self, key):
        if key == keyboard.Key.pause or key == keyboard.Key.esc:
            self._stop = True
            self.stop_callback()

    def trigger_stop(self):
        self._stop = True

    def set_paused(self, paused: bool):
        self._paused = paused

    def ensure_safe_mode(self):
        pyautogui.PAUSE = 0.1
        pyautogui.FAILSAFE = True

    def _log(self, message: str):
        if self.log_callback:
            self.log_callback(message)
        self.logger.info(message)

    def _wait_if_paused(self):
        while self._paused and not self._stop:
            time.sleep(0.1)

    def _has_focus(self) -> bool:
        try:
            get_window = getattr(pyautogui, "getActiveWindow", None)
            if get_window is None:
                return True
            window = get_window()
            if window is None:
                return True
            title = window.title or ""
            return title.lower().startswith(self.focus_title.lower())
        except Exception:
            return True

    def _try_focus(self) -> bool:
        try:
            get_windows = getattr(pyautogui, "getWindowsWithTitle", None)
            if get_windows is None:
                return False
            # Filter to avoid matching browser tabs with "DaVinci Resolve" in title
            windows = [w for w in get_windows(self.focus_title) 
                      if "Google Chrome" not in w.title and "Microsoft Edge" not in w.title]
            if not windows:
                return False
            window = windows[0]
            if window.isMinimized:
                window.restore()
            window.activate()
            # Bring to top more forcefully
            pyautogui.press('alt')
            window.activate()
            
            # Wait for focus with timeout (event-based approach)
            start_time = time.time()
            while time.time() - start_time < 1.0:
                if self._has_focus():
                    # Small settle time for redraw
                    time.sleep(0.05)
                    return True
                time.sleep(0.02)
            
            return self._has_focus()
        except Exception:
            return False

    def execute_actions(self, actions, calibration, iter_idx: int = 0, session_logger=None, inter_action_delay: float = 0.1):
        executed = []
        for i, raw in enumerate(actions):
            if self._stop:
                break
            self._wait_if_paused()
            if not self._has_focus():
                if self._try_focus():
                    self._log("Resolve focused automatically.")
                else:
                    self._paused = True
                    self._log("Resolve not focused. Pausing actions.")
                    break
            try:
                allowed_keys = {"type", "target", "dx", "dy", "value", "keys", "reason"}
                payload = {key: raw[key] for key in raw.keys() if key in allowed_keys}
                dropped = [key for key in raw.keys() if key not in allowed_keys]
                if dropped:
                    self._log(f"Ignoring unsupported action fields: {dropped}")
                action = Action(**payload)
            except Exception as exc:
                self._log(f"Failed to parse action payload: {raw}. Error: {exc}")
                continue
            self._log(
                "Executing action: type=%s target=%s dx=%s dy=%s keys=%s reason=%s"
                % (
                    action.type,
                    action.target,
                    action.dx,
                    action.dy,
                    action.keys,
                    action.reason,
                )
            )
            if self._execute(action, calibration, iter_idx, i, session_logger):
                executed.append(action)
                self.last_action = action
            else:
                self._log("Action execution failed.")
            
            # Apply inter-action delay
            if i < len(actions) - 1: # No need to wait after the last action
                time.sleep(inter_action_delay)
            else:
                time.sleep(random.uniform(0.04, 0.09))
        return executed

    def _execute(self, action: Action, calibration, iter_idx: int = 0, action_idx: int = 0, session_logger=None) -> bool:
        try:
            if action.type == "keypress" and action.keys:
                self._log("Sending hotkey: %s" % action.keys)
                pyautogui.hotkey(*action.keys)
                return True

            # target is now expected to be flat from calibration.targets
            target = calibration.get_target(action.target) if calibration else None
            
            # If not found directly, try to see if it's a wheel action that needs mapping
            if target is None and action.type == "drag" and "_" not in action.target:
                # Legacy or simplified wheel target like "lift_wheel" -> "Lift_white" or similar?
                # Actually, our new scheme uses f"{wheel_name}_{comp_name}"
                # If LLM says "Lift" it might be ambiguous.
                pass

            if target is None:
                self._log(f"Skipping action: unknown target '{action.target}'.")
                return False

            self._log("Moving to target: %s" % target)
            base_x, base_y = target["x"], target["y"]
            pyautogui.moveTo(base_x, base_y, duration=0)
            
            # Take screenshot before action
            if session_logger and action.type in ["drag", "set_slider"]:
                try:
                    if calibration and "roi" in calibration.to_dict():
                        from vision.screenshot import capture_roi
                        ss = capture_roi(calibration.roi)
                    else:
                        ss = pyautogui.screenshot()
                    
                    # Debug crop
                    debug_dir = Path("debug") / "action_targets"
                    debug_dir.mkdir(parents=True, exist_ok=True)
                    full_ss = pyautogui.screenshot()
                    target_crop = full_ss.crop((target["x"] - 100, target["y"] - 50, target["x"] + 100, target["y"] + 50))
                    target_crop.save(debug_dir / f"target_{action.target}_iter{iter_idx}_act{action_idx}_before.png")

                    session_logger.log_action_screenshot(iter_idx, action_idx, action.type, ss)
                except Exception as e:
                    self.logger.warning(f"Failed to capture action screenshot: {e}")

            if action.type == "drag":
                dx = action.dx or 0
                dy = action.dy or 0
                self._log(f"Dragging by dx={dx} dy={dy}")
                pyautogui.mouseDown()
                pyautogui.moveRel(dx, dy, duration=0.3)
                pyautogui.mouseUp()
                # After-action screenshot
                if session_logger:
                    try:
                        if calibration and "roi" in calibration.to_dict():
                            from vision.screenshot import capture_roi
                            ss_after = capture_roi(calibration.roi)
                        else:
                            ss_after = pyautogui.screenshot()
                        session_logger.log_action_screenshot(iter_idx, action_idx, action.type, ss_after, phase="after")
                    except Exception as e:
                        self.logger.warning(f"Failed to capture action AFTER screenshot: {e}")
                return True

            if action.type == "set_slider" and action.value is not None:
                # Always set by double-clicking and typing the absolute value
                val = float(action.value)
                self._log(f"Setting slider '{action.target}' by typing value={val}")
                pyautogui.moveTo(base_x, base_y, duration=0)
                # Ensure we click exactly on the target
                pyautogui.click() # Click once to focus the controller if needed
                time.sleep(0.05)
                pyautogui.doubleClick()
                time.sleep(0.1)
                pyautogui.hotkey('ctrl', 'a') # Ensure current value is selected
                time.sleep(0.05)
                pyautogui.press('backspace') # Clear it for safety
                time.sleep(0.05)
                try:
                    txt = ("%0.3f" % val).rstrip('0').rstrip('.')
                except Exception:
                    txt = str(val)
                pyautogui.typewrite(txt)
                self._log(f"[DEBUG] Typed value '{txt}' for target '{action.target}'")
                time.sleep(0.05)
                pyautogui.press("enter")
                time.sleep(0.1) # Wait for Resolve to register the value
                # After-action screenshot
                if session_logger:
                    try:
                        if calibration and "roi" in calibration.to_dict():
                            from vision.screenshot import capture_roi
                            ss_after = capture_roi(calibration.roi)
                        else:
                            ss_after = pyautogui.screenshot()
                        session_logger.log_action_screenshot(iter_idx, action_idx, action.type, ss_after, phase="after")
                    except Exception as e:
                        self.logger.warning(f"Failed to capture action AFTER screenshot: {e}")
                return True

            self._log(f"Skipping action: unsupported type '{action.type}'.")
            return False
        except Exception as exc:
            self._log(f"Action execution exception: {exc}")
            return False

    def undo_last(self):
        pyautogui.hotkey("ctrl", "z")
