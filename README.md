### Resolve Color Grade Agent (v1)

#### Overview
Minimal vertical slice: UI for settings, reference upload, ROI calibration, and one iteration loop (screenshot -> LLM -> actions -> metrics).

#### Features
- Desktop UI for API settings, reference image, and ROI calibration.
- One-iteration workflow with action execution and metric feedback.
- Session logging and on-screen action log.

#### Requirements
- Python 3.11+
- Windows (tested path references in logs are Windows)

#### Setup
1. Install dependencies:
```
pip install -r requirements.txt
```
2. Run the app:
```
python main.py
```

#### Configuration
- **API key**: Enter in the UI.
- **Model**: Select from the model list (use Refresh Models).
- **Endpoint**: Defaults to `https://api.openai.com/v1/chat/completions`.

#### Usage
1. Enter API key/model/endpoint.
2. Upload a reference image.
3. Calibrate ROI (select the Resolve viewer area).
4. Click Start (runs one iteration).

#### Workflow Summary
1. Capture ROI screenshot.
2. Send reference + current image + metrics to the LLM.
3. Parse actions and execute them.
4. Capture ROI again and compute metrics.

#### Safety
- `Pause` key triggers immediate stop.
- Confirm dialog before controlling mouse/keyboard.

#### Logs
- App log: `logs/app.log`
- Common entries:
  - HTTP 429: rate limit reached (tokens per minute).
  - Timeout: request took too long.
  - Schema errors: LLM returned JSON not matching the action schema.

#### Troubleshooting
- **HTTP 429**: Reduce request size (smaller ROI) or wait and retry.
- **Model list empty**: Click Refresh Models and verify API key.
- **No preview**: Ensure reference image is valid and accessible.
- **Schema errors**: The app normalizes legacy responses, but strict JSON is still required.

#### Project Layout
- `main.py`: App entry point.
- `app_ui/`: UI and dialogs.
- `llm/`: LLM client and request/response handling.
- `vision/`: Screenshot capture and metrics.
- `automation/`: Action executor.
- `calibration/`: ROI calibration profile.
- `storage/`: Settings persistence.
- `logs/`: Runtime logs.

#### Tests
```
pytest -q
```

#### Notes
- This is a minimal vertical slice; expect rate limits and model output variability.
- If the app crashes, attach the latest `logs/app.log` excerpt.
