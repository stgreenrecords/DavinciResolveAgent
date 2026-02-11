# Project Analysis Report

## Project Overview

**Project Name:** Resolve Color Grade Agent (v1)

**Purpose:** An AI-powered automated color grading assistant for DaVinci Resolve that uses vision-based analysis and LLM decision-making to adjust color controls through GUI automation.

**Architecture:** Desktop application with PyQt UI that captures screenshots from DaVinci Resolve, sends them to an LLM (OpenAI GPT-4), receives color grading instructions, and executes them via mouse/keyboard automation.

---

## Key Components

### 1. **UI Layer** (`app_ui/`)
- **main_window.py**: Primary Qt application window with settings, controls, and workflow orchestration
- **roi_selector.py**: Tool for calibrating the Region of Interest (ROI) - the DaVinci Resolve viewer area

### 2. **LLM Integration** (`llm/client.py`)
- **LlmClient**: Handles communication with OpenAI API
- Sends reference image + current screenshot + metrics to GPT-4
- Receives JSON-formatted action instructions
- Implements retry logic, rate limit handling, and response validation

### 3. **Automation Executor** (`automation/executor.py`)
- **ActionExecutor**: Translates LLM actions into mouse/keyboard commands
- Supports three action types:
  - `set_slider`: Adjusts slider controls (temperature, saturation, contrast, etc.)
  - `drag`: Moves color wheels or relative positioning
  - `keypress`: Sends keyboard shortcuts
- Uses calibrated pixel-to-value ratios for precise slider adjustments

### 4. **Vision System** (`vision/`)
- Screenshot capture from ROI
- Image similarity metrics computation (MSE, SSIM, histogram comparison)
- UI value reading from DaVinci Resolve interface

### 5. **Calibration** (`calibration/profile.py`)
- Stores screen coordinates of DaVinci Resolve controls
- Maps target names (e.g., "saturation_slider") to pixel coordinates
- Loaded from `coordinates.json`

---

## Workflow

1. **Setup Phase:**
   - User provides OpenAI API key and model selection
   - User uploads reference image (target look)
   - User calibrates ROI (selects DaVinci Resolve viewer area)

2. **Execution Phase:**
   - Captures current screenshot from ROI
   - Computes similarity metrics between reference and current
   - Sends to LLM with prompt requesting color grading actions
   - LLM returns JSON with recommended adjustments
   - Executor performs mouse movements and drags on calibrated controls
   - Captures after-action screenshot and computes new metrics
   - Repeats if in continuous mode

3. **Safety Mechanisms:**
   - Pause/Esc key triggers immediate stop
   - Focus detection (only acts when DaVinci Resolve is active)
   - Action limit (3 actions per iteration to prevent runaway behavior)

---

## Log Analysis: Recent Execution

### Event Timeline (2026-02-11 20:16:16 - 20:16:25)

**Line 54-61:** LLM prompt construction
- Payload size: 56,493 bytes (includes base64-encoded images)
- System prompt clearly defines expected JSON schema
- Lists all 16 calibration targets with types and ranges
- Provides clear coordinate system rules and action type definitions

**Line 64-99:** LLM Response
- Status: 200 OK (successful)
- Model: `gpt-4.1-mini-2025-04-14`
- Token usage: 38,041 prompt + 213 completion = 38,254 total
- Cached tokens: 23,680 (significant optimization from prompt caching)

**Response Content (Line 74):**
```json
{
  "summary": "Increase saturation and contrast, adjust temperature and tint slightly, lift shadows, reduce highlights, and tweak gain wheel for better color balance.",
  "actions": [
    {"type": "set_slider", "target": "saturation_slider", "delta": 20, "reason": "..."},
    {"type": "set_slider", "target": "contrast_slider", "delta": 0.3, "reason": "..."},
    {"type": "set_slider", "target": "temperature_slider", "delta": 500, "reason": "..."},
    {"type": "set_slider", "target": "tint_slider", "delta": 10, "reason": "..."},
    {"type": "set_slider", "target": "shadows_slider", "delta": 15, "reason": "..."},
    {"type": "set_slider", "target": "highlights_slider", "delta": -20, "reason": "..."},
    {"type": "drag", "target": "gain_wheel", "dx": 10, "dy": -10, "reason": "..."}
  ],
  "stop": false,
  "confidence": 0.85
}
```

**Line 101:** Action Limiting
- LLM returned 7 actions but only 3 were executed
- Code: `actions = response.actions[:3]` (line 681 in main_window.py)
- This is a safety mechanism to prevent excessive changes per iteration

**Line 102-119:** Action Execution
Only these 3 actions were executed:

1. **Saturation Slider** (line 102-107)
   - Target coordinates: (899, 1980)
   - Delta requested: +20
   - Pixel drag calculated: 149.20 pixels (ratio: 7.46 px/unit)

2. **Contrast Slider** (line 108-113)
   - Target coordinates: (855, 1465)
   - Delta requested: +0.3
   - Pixel drag calculated: 228.70 pixels (ratio: 762.33 px/unit)

3. **Temperature Slider** (line 114-119)
   - Target coordinates: (322, 1465)
   - Delta requested: +500
   - Pixel drag calculated: 76.10 pixels (ratio: 0.1522 px/unit)

---

## Critical Issues Identified

### ⚠️ ISSUE #1: Action Truncation Without LLM Knowledge

**Problem:** The application limits execution to 3 actions but the LLM doesn't know this constraint.

**Evidence:**
- LLM returned 7 actions (line 120-169 in log shows full response)
- Only 3 were executed (line 101: "Executing 3 actions")
- The remaining 4 actions (tint, shadows, highlights, gain wheel) were silently dropped

**Impact:**
- LLM makes decisions assuming all 7 actions will be applied together
- Color balance is disrupted when only partial adjustments are made
- Example: LLM might increase temperature (+500) expecting highlights to be reduced (-20) to compensate
- When highlights adjustment is skipped, the image becomes too warm

**Solution:**
Either:
1. Tell the LLM in the system prompt: "You MUST return exactly 3 actions or fewer per iteration"
2. Remove the action limit and trust the LLM's confidence score
3. Implement action batching with clear iteration boundaries

---

### ⚠️ ISSUE #2: Mouse Cursor Movement Misalignment

**User Report:** "when I click start mouse cursor is moving in wrong direction"

**Root Cause Analysis:**

Looking at `automation/executor.py` lines 205-223:

```python
# Base target coordinates from calibration
base_x, base_y = target["x"], target["y"]
pyautogui.moveTo(base_x, base_y, duration=0)

if action.type == "set_slider" and action.delta is not None:
    ratio = self.ratios.get(action.target, self.default_pixels_per_unit)
    dx = float(action.delta) * float(ratio)
    
    # Press slightly below the coordinate to avoid hitting the numeric pill directly
    start_y = base_y + 12  # ← Offset added here
    pyautogui.moveTo(base_x, start_y, duration=0)
    time.sleep(0.05)
    pyautogui.mouseDown()
    
    # Prime a 1px move to ensure UI enters drag mode
    p_dx = 1 if dx > 0 else -1
    pyautogui.moveRel(p_dx, 0, duration=0.08)
    
    # Main move minus the prime pixel
    m_dx = dx - p_dx
    if abs(m_dx) > 0:
        pyautogui.moveRel(m_dx, 0, duration=0.22)  # ← Horizontal drag
```

**Potential Issues:**

1. **Coordinate Calibration Mismatch:**
   - Coordinates in `coordinates.json` are hardcoded: `{"x": 899, "y": 1980}` for saturation
   - These may not match the user's screen resolution or DaVinci Resolve window position
   - DaVinci Resolve may be in windowed mode at different position than expected

2. **ROI vs Absolute Coordinates:**
   - ROI is defined as: `{'x': 465, 'y': 159, 'width': 852, 'height': 481}`
   - But slider coordinates are absolute screen coordinates
   - If DaVinci Resolve window moved since calibration, coordinates become invalid

3. **Multi-Monitor Setup:**
   - If user has multiple monitors, coordinate system origin may be different
   - PyAutoGUI uses primary monitor's top-left as (0, 0)

4. **Y-Axis Offset:**
   - Code adds +12 pixels to Y coordinate (`start_y = base_y + 12`)
   - This is to avoid clicking the numeric value display above the slider
   - But if calibration already points to the drag area, this offset causes misalignment

**Recommended Fixes:**

1. **Implement Dynamic Calibration:**
   - Instead of hardcoded coordinates, use visual detection to find controls
   - Use template matching or OCR to locate sliders each iteration

2. **Add Calibration Verification:**
   - Before starting automation, show user where each control will be clicked
   - Allow manual adjustment of control positions

3. **Make Coordinates Relative to ROI:**
   - Store control positions relative to the DaVinci Resolve window
   - Recalculate absolute coordinates based on current window position

4. **Add Debug Visualization:**
   - Draw circles/markers on screen showing where mouse will click
   - Save screenshots with overlay showing detected vs expected positions

---

### ⚠️ ISSUE #3: Missing Model Filtering in Logs

**User Report:** "exclude list of the models from logs"

**Problem:** The log shows (line 6):
```
2026-02-11 20:15:40,964 INFO app.llm: LLM models response count: 115
```

This includes all 115 models from OpenAI API, many irrelevant for this task.

**Current Code** (`llm/client.py` lines 338-348):
```python
def list_models(self) -> list[str]:
    settings = self.settings_store.load_settings()
    headers = {"Authorization": f"Bearer {settings.api_key}"}
    models_url = self._models_url(settings.endpoint)
    self.logger.info("LLM models request: %s", models_url)
    response = requests.get(models_url, headers=headers, timeout=(10, 30))
    self.logger.info("LLM models response status %s", response.status_code)
    response.raise_for_status()
    data = response.json()
    models = [item.get("id") for item in data.get("data", []) if isinstance(item, dict)]
    all_models = sorted({m for m in models if isinstance(m, str) and m.strip()})
    self.logger.info("LLM models response count: %d", len(all_models))  # ← Logs all 115 models
    return all_models
```

**Solution:**
Filter models to only show vision-capable models suitable for this task:
- Keep: `gpt-4-vision`, `gpt-4o`, `gpt-4-turbo`, `gpt-4.1-mini` (with vision support)
- Exclude: `whisper-*`, `tts-*`, `dall-e-*`, `text-embedding-*`, old `gpt-3.5-*` models

---

## Prompt Quality Assessment

### ✅ Strengths

1. **Schema Definition:** Clear JSON schema with all required fields
2. **Target Documentation:** Lists all 16 targets with types and ranges
3. **Coordinate System:** Explicitly defines origin and axis directions
4. **Action Examples:** Provides concrete examples for each action type
5. **Safety Instructions:** Warns against using ROI center for adjustments
6. **Value Ranges:** Specifies valid ranges for each slider

### ⚠️ Weaknesses

1. **No Action Limit Mentioned:**
   - Prompt doesn't say "return maximum 3 actions"
   - LLM returned 7 actions, only 3 executed
   - Creates mismatch between LLM's plan and actual execution

2. **Current State Not Visible:**
   - Prompt says "Consider the initial parameters provided in the current state"
   - But the actual user data payload structure isn't shown in logs
   - Cannot verify if current slider values are actually included

3. **Delta Calculation Ambiguity:**
   - "Deltas should be calculated relative to the current state"
   - But example says "if Saturation is 50 and you want 60, delta is +10"
   - LLM doesn't actually know current saturation value from the prompt alone
   - It must be in the user data payload (56KB) but we can't verify

4. **Missing Feedback Loop:**
   - No indication of previous iteration's results
   - LLM doesn't know if previous actions succeeded or failed
   - No way to correct overcorrection or undercorrection

---

## Response Schema Validation

### ✅ LLM Response Matches Expected Schema

**Expected Schema** (from `ACTION_SCHEMA` in llm/client.py):
```json
{
  "type": "object",
  "properties": {
    "summary": {"type": "string"},
    "actions": {"type": "array", "items": {...}},
    "stop": {"type": "boolean"},
    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0}
  },
  "required": ["summary", "actions", "stop", "confidence"]
}
```

**Actual Response** (from log line 74):
```json
{
  "summary": "Increase saturation and contrast...",  ✓ string
  "actions": [{...}, {...}, ...],                    ✓ array
  "stop": false,                                      ✓ boolean
  "confidence": 0.85                                  ✓ number in range [0,1]
}
```

**Action Schema** (each action in array):
```json
{
  "type": {"type": "string"},           ✓ "set_slider" or "drag"
  "target": {"type": "string"},         ✓ Valid targets like "saturation_slider"
  "delta": {"type": "number"},          ✓ Present for set_slider actions
  "dx": {"type": "number"},             ✓ Present for drag actions
  "dy": {"type": "number"},             ✓ Present for drag actions
  "reason": {"type": "string"}          ✓ All actions have reasons
}
```

**✅ Validation Result:** LLM response perfectly matches expected schema.

---

## Recommendations

### 1. **Fix Action Limit Mismatch** (High Priority)

**Option A:** Update prompt to enforce limit
```python
prompt = (
    "You are controlling DaVinci Resolve color grading. "
    "IMPORTANT: You MUST return EXACTLY 3 ACTIONS OR FEWER per iteration. "
    "The system will only execute the first 3 actions, so plan accordingly. "
    # ... rest of prompt
)
```

**Option B:** Remove the limit
```python
# In main_window.py line 681, change:
actions = response.actions[:3]  # Remove this limit
# To:
actions = response.actions  # Execute all actions
```

**Option C:** Implement proper batching
```python
actions = response.actions
if len(actions) > 3:
    self._append_log(f"LLM returned {len(actions)} actions. Executing in batches of 3.")
    for i in range(0, len(actions), 3):
        batch = actions[i:i+3]
        self.executor.execute_actions(batch, ...)
```

### 2. **Fix Cursor Misalignment** (High Priority)

**Add Coordinate Validation:**
```python
def _validate_calibration(self) -> bool:
    """Show user where controls will be clicked."""
    import pyautogui
    from PIL import ImageDraw
    
    screenshot = pyautogui.screenshot()
    draw = ImageDraw.Draw(screenshot)
    
    for name, coords in self.calibration.targets.items():
        x, y = coords["x"], coords["y"]
        # Draw red circle at calibrated position
        draw.ellipse([x-10, y-10, x+10, y+10], outline="red", width=3)
        draw.text((x+15, y), name, fill="red")
    
    screenshot.show()
    
    reply = QMessageBox.question(
        self,
        "Verify Calibration",
        "Red circles show where the mouse will click. Do these positions look correct?",
        QMessageBox.Yes | QMessageBox.No
    )
    return reply == QMessageBox.Yes
```

**Call before starting:**
```python
def _start_clicked(self):
    if not self._validate_calibration():
        self._append_log("Calibration verification failed. Please recalibrate.")
        return
    # ... continue with automation
```

### 3. **Filter Model List** (Medium Priority)

**Update `list_models()` method:**
```python
def list_models(self) -> list[str]:
    # ... existing code ...
    all_models = sorted({m for m in models if isinstance(m, str) and m.strip()})
    
    # Filter to vision-capable models only
    vision_models = [
        m for m in all_models
        if any(keyword in m.lower() for keyword in [
            "gpt-4o", "gpt-4-turbo", "gpt-4-vision", "gpt-4.1"
        ])
        and not any(exclude in m.lower() for exclude in [
            "whisper", "tts", "dall-e", "embedding", "audio"
        ])
    ]
    
    self.logger.info("LLM models response count: %d (filtered from %d)", 
                     len(vision_models), len(all_models))
    return vision_models
```

### 4. **Add Current State to Prompt** (Medium Priority)

The LLM needs to see current parameter values to calculate proper deltas:

```python
# In _build_payload method, add:
current_state = {
    "saturation": self._read_slider_value("saturation_slider"),
    "contrast": self._read_slider_value("contrast_slider"),
    "temperature": self._read_slider_value("temperature_slider"),
    # ... etc for all sliders
}

instructions = {
    # ... existing fields ...
    "current_state": current_state,  # Add this
}
```

Update prompt to reference it:
```python
"The 'current_state' field shows current slider values. "
"Calculate deltas to reach target values within the specified ranges. "
```

### 5. **Add Iteration History** (Low Priority)

Help LLM learn from previous attempts:

```python
if ctx.previous_image:
    instructions["previous_actions"] = self.last_actions
    instructions["previous_metrics"] = self.last_metrics.__dict__
    
prompt += (
    "If previous_actions and previous_metrics are provided, "
    "analyze what worked and what didn't. Adjust your strategy accordingly."
)
```

---

## Conclusion

### Summary

The application is **architecturally sound** and the LLM integration is **well-implemented**:

✅ **Prompt is correctly formed** - Clear schema, good documentation, proper constraints
✅ **Response matches expectations** - Valid JSON, correct structure, sensible values  
✅ **Code structure is clean** - Good separation of concerns, proper error handling

### But there are **3 critical bugs**:

❌ **Bug #1:** Action limit (3) not communicated to LLM - causes incomplete color corrections  
❌ **Bug #2:** Mouse coordinates likely misaligned - hardcoded absolute positions fail when window moves  
❌ **Bug #3:** Excessive model list logging - clutters logs with irrelevant models  

### Immediate Actions Required:

1. **Add action limit to prompt** or remove the [:3] slice (5 min fix)
2. **Add calibration verification UI** to debug coordinate issues (2 hour fix)
3. **Filter model list** to vision-capable models only (10 min fix)

Once these are addressed, the system should work as intended.

---

## Alternative Architecture Suggestion

You mentioned considering "using DaVinci API to control everything" instead of GUI automation.

### ✅ Pros of API Approach:
- **Reliable:** No coordinate calibration needed
- **Precise:** Direct value setting instead of pixel-based dragging
- **Fast:** No mouse movement delays
- **Robust:** Works regardless of window position or resolution

### ❌ Cons of API Approach:
- **Limited Access:** DaVinci Resolve API requires **Studio version** (paid)
- **Learning Curve:** Need to learn Resolve's Python/Lua scripting API
- **Scope Limitation:** API may not expose all UI controls (some advanced features are GUI-only)

### 📋 Recommended Hybrid Approach:

1. **Use API for basic controls** (when available):
   - Timeline operations
   - Clip selection
   - Basic color adjustments (lift/gamma/gain, saturation)
   - Export settings

2. **Keep GUI automation for advanced controls**:
   - Specific plugins/effects
   - UI-only features
   - Complex interactions API doesn't support

3. **Vision + LLM remains valuable** regardless of control method:
   - LLM analyzes before/after screenshots to decide actions
   - Execution layer (API vs GUI) is swappable

### Example Hybrid Code:
```python
class ActionExecutor:
    def __init__(self, use_api=True):
        self.use_api = use_api
        if use_api:
            import DaVinciResolveScript as dvr
            self.resolve = dvr.scriptapp("Resolve")
    
    def execute_action(self, action):
        if self.use_api and self._api_supports(action.target):
            return self._execute_via_api(action)
        else:
            return self._execute_via_gui(action)
    
    def _execute_via_api(self, action):
        # Use Resolve scripting API
        project = self.resolve.GetProjectManager().GetCurrentProject()
        timeline = project.GetCurrentTimeline()
        current_clip = timeline.GetCurrentVideoItem()
        # ... set color parameters directly
    
    def _execute_via_gui(self, action):
        # Fallback to existing pyautogui approach
        # ... existing code
```

This gives you best of both worlds: reliability of API where available, flexibility of GUI automation where needed.

