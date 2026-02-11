import base64
import io
import json
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import requests
from jsonschema import validate, ValidationError
from PIL import Image

from calibration.profile import CalibrationProfile
from storage.settings import SettingsStore
from vision.metrics import SimilarityMetrics


ACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "target": {"type": "string"},
                    "dx": {"type": "number"},
                    "dy": {"type": "number"},
                    "value": {"type": "number"},
                    "keys": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                },
                "required": ["type", "target", "reason"],
            },
        },
        "stop": {"type": "boolean"},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
    },
    "required": ["summary", "actions", "stop", "confidence"],
}


@dataclass
class LlmResponse:
    raw: dict
    actions: list
    stop: bool
    confidence: float


@dataclass
class LlmRequestContext:
    reference_image_path: Path
    current_image: Image.Image
    previous_image: Image.Image | None
    metrics: SimilarityMetrics
    calibration: CalibrationProfile
    instructions: str | None = None
    current_state: dict | None = None


class LlmClient:
    def __init__(self, settings_store: SettingsStore, min_confidence: float = 0.3, max_retries: int = 2):
        self.settings_store = settings_store
        self.min_confidence = min_confidence
        self.max_retries = max_retries
        self.logger = logging.getLogger("app.llm")
        self.max_image_dim = 512
        self.jpeg_quality = 70

    def test_connection(self) -> dict:
        settings = self.settings_store.load_settings()
        headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": settings.model,
            "messages": [
                {"role": "system", "content": "You are a connectivity test. Reply with OK."},
                {"role": "user", "content": "ping"},
            ],
            "temperature": 0.0,
        }
        self.logger.info("LLM test connection request")
        response = requests.post(settings.endpoint, headers=headers, json=payload, timeout=(10, 30))
        self.logger.info("LLM test response status %s", response.status_code)
        self.logger.info("LLM test response body: %s", response.text)
        response.raise_for_status()
        return response.json()

    def request_actions(self, ctx: LlmRequestContext) -> LlmResponse:
        settings = self.settings_store.load_settings()
        payload = self._build_payload(ctx, settings.model)
        headers = {"Authorization": f"Bearer {settings.api_key}", "Content-Type": "application/json"}
        last_error = None
        rate_limited = False
        for attempt in range(self.max_retries + 1):
            try:
                self.logger.info("LLM request attempt %d", attempt + 1)
                response = requests.post(
                    settings.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=(10, 120),
                )
                self.logger.info("LLM response status %s", response.status_code)
                self.logger.info("LLM response body: %s", response.text)
                if response.status_code == 429:
                    rate_limited = True
                    retry_after = response.headers.get("Retry-After")
                    wait_s = float(retry_after) if retry_after else min(2 ** attempt, 8)
                    self.logger.warning("Rate limited (429). Waiting %.1fs", wait_s)
                    time.sleep(wait_s)
                    continue
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                normalized = self._normalize_response(parsed)
                self._validate(normalized)
                llm_response = LlmResponse(
                    raw=normalized,
                    actions=normalized["actions"],
                    stop=normalized["stop"],
                    confidence=normalized["confidence"],
                )
                if llm_response.confidence < self.min_confidence:
                    return LlmResponse(
                        raw=normalized,
                        actions=[],
                        stop=True,
                        confidence=llm_response.confidence,
                    )
                return llm_response
            except (json.JSONDecodeError, KeyError, ValidationError, ValueError) as exc:
                last_error = exc
                self.logger.exception("LLM response parsing failed")
                payload = self._build_payload(ctx, settings.model, retry_hint="Return STRICT JSON only.")
            except requests.exceptions.Timeout as exc:
                last_error = exc
                wait_s = min(2 ** attempt, 8)
                self.logger.warning("LLM request timed out. Waiting %.1fs", wait_s)
                time.sleep(wait_s)
                continue
            except requests.HTTPError as exc:
                last_error = exc
                if exc.response is not None and exc.response.status_code == 429:
                    rate_limited = True
                    continue
                break
            except requests.RequestException as exc:
                last_error = exc
                self.logger.exception("LLM request failed")
                break
        if rate_limited:
            raise ValueError("Rate limited by OpenAI API (HTTP 429). Please wait and try again.")
        raise ValueError(f"Invalid LLM response after retries: {last_error}")

    def _build_payload(self, ctx: LlmRequestContext, model: str, retry_hint: str | None = None):
        ref_b64 = self._encode_reference(ctx.reference_image_path)
        cur_b64 = self._encode_pil(ctx.current_image)
        instructions = {
            "reference_image": ref_b64,
            "current_image": cur_b64,
            "metrics": ctx.metrics.__dict__,
            "allowed_actions": ["drag", "set_slider", "keypress"],
            "user_instructions": ctx.instructions,
            "current_state": ctx.current_state or {},
            "controls": []
        }
        
        for name, meta in ctx.calibration.control_metadata.items():
            if name == "roi_center":
                continue
            instructions["controls"].append({
                "name": name,
                "type": meta.get("type"),
                "description": meta.get("description"),
                "min": meta.get("min"),
                "max": meta.get("max"),
                "defaultValue": meta.get("defaultValue")
            })

        payload_text = json.dumps(instructions)
        self.logger.info("LLM payload size: %d bytes", len(payload_text.encode("utf-8")))
        target_names = sorted(ctx.calibration.targets.keys())
        target_hint = ", ".join(target_names) if target_names else "roi_center"
        
        # Add descriptions and ranges from metadata to help LLM understand what each target is
        detailed_targets = []
        for name, meta in ctx.calibration.control_metadata.items():
            if name == "roi_center":
                continue
            desc = meta.get("description", name)
            ctype = meta.get("type", "")
            cmin = meta.get("min", "Unknown")
            cmax = meta.get("max", "Unknown")
            cdef = meta.get("defaultValue", "Unknown")
            detailed_targets.append(f"'{name}' ({ctype}: {desc}, Range: [{cmin}, {cmax}], Default: {cdef})")
        detailed_target_hint = "; ".join(detailed_targets)

        prompt = (
            "You are controlling DaVinci Resolve color grading. "
            "Return ONLY a JSON object that matches this schema exactly (no extra keys, no markdown): "
            "{summary: string, actions: [{type: string, target: string, dx?: number, dy?: number, "
            "value?: number, keys?: string[], reason: string}], stop: boolean, confidence: number}. "
            "Rules: summary and reason must be short strings; confidence must be 0.0-1.0. "
            "Coordinate system: origin is top-left of the screen; positive dx moves right, positive dy moves down. "
            f"The 'target' field MUST be one of these calibration targets: {target_hint}. "
            f"Target Details & valid ranges: {detailed_target_hint}. "
            "The 'current_state' shows the current values of the controllers in Resolve. "
            "Use these values as a baseline for your adjustments. "
            f"USER INSTRUCTIONS: {ctx.instructions if ctx.instructions else 'Follow standard color matching rules.'} "
            "DO NOT use 'roi_center' for adjusting sliders or wheels. "
            "Action Types:\n"
            "- 'set_slider': RECOMMENDED for all sliders and wheel components (contrast, saturation, Lift red, Gain blue, etc.). YOU MUST provide the absolute 'value' to enter from the valid range. Deltas are not supported.\n"
            "- 'drag': Use ONLY for color wheels or relative movement if a target does not have a defined numeric range. Requires dx (horizontal) and dy (vertical) in pixels. Typically 10-100px.\n"
            "- 'keypress': Use for hotkeys. Requires keys (list of strings).\n"
            "If no action is needed to match the reference look, return an empty actions array and stop=true.\n"
            "Note: The 'reason' field for each action should explicitly state the new target value (e.g., 'Set Gain_blue to 1.2 to warm highlights')."
        )
        if retry_hint:
            prompt = f"{prompt} {retry_hint}"
        
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": prompt},
                {"role": "user", "content": payload_text},
            ],
            "temperature": 0.2,
        }
        
        # Log the full prompt for debugging
        self.logger.info("LLM Full Prompt (System): %s", prompt)
        self.logger.info("LLM Full Prompt (User Data Size): %d bytes", len(payload_text))
        
        return payload

    def _encode_reference(self, path: Path) -> str:
        with Image.open(path) as image:
            image = image.convert("RGB")
            return self._encode_pil(image)

    def _encode_pil(self, image: Image.Image) -> str:
        if image is None:
            raise ValueError("Current screenshot is empty.")
        if image.mode != "RGB":
            image = image.convert("RGB")
        image = self._resize_pil(image, self.max_image_dim)
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self.jpeg_quality)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    def _resize_pil(self, image: Image.Image, max_dim: int) -> Image.Image:
        if max(image.size) <= max_dim:
            return image
        resized = image.copy()
        resized.thumbnail((max_dim, max_dim), Image.LANCZOS)
        return resized

    @staticmethod
    def _validate(data: dict):
        try:
            validate(instance=data, schema=ACTION_SCHEMA)
        except ValidationError as exc:
            raise ValueError(f"Invalid LLM response: {exc.message}") from exc

    @staticmethod
    def _normalize_response(data: dict) -> dict:
        if not isinstance(data, dict):
            raise ValueError("LLM response must be a JSON object.")
        if all(k in data for k in ("summary", "actions", "stop", "confidence")):
            return data

        actions = data.get("actions")
        if actions is None and "action" in data:
            actions = [data]
        if not isinstance(actions, list):
            raise ValueError("LLM response missing actions list.")

        normalized_actions: list[dict] = []
        for raw_action in actions:
            if not isinstance(raw_action, dict):
                continue
            action_type = raw_action.get("type") or raw_action.get("action")
            params = raw_action.get("params") or raw_action.get("parameters") or {}
            reason = (
                raw_action.get("reason")
                or raw_action.get("justification")
                or "Auto-converted from legacy action format."
            )

            normalized = {"type": action_type, "target": "", "reason": reason}

            if action_type == "set_slider":
                slider = params.get("slider") or raw_action.get("target")
                normalized["target"] = str(slider or "unknown")
                value = params.get("value")
                if value is None:
                    value = raw_action.get("value")
                if value is not None:
                    normalized["value"] = float(value)
            elif action_type == "drag":
                normalized["target"] = raw_action.get("target") or "canvas"
                start = params.get("start") or {}
                end = params.get("end") or {}
                if isinstance(start, dict) and isinstance(end, dict):
                    if "x" in start and "x" in end:
                        normalized["dx"] = float(end["x"] - start["x"])
                    if "y" in start and "y" in end:
                        normalized["dy"] = float(end["y"] - start["y"])
                if "dx" in params:
                    normalized["dx"] = float(params["dx"])
                if "dy" in params:
                    normalized["dy"] = float(params["dy"])
            elif action_type == "keypress":
                normalized["target"] = raw_action.get("target") or "keyboard"
                keys = params.get("keys") or raw_action.get("keys")
                if isinstance(keys, list):
                    normalized["keys"] = [str(k) for k in keys]
            else:
                normalized["target"] = raw_action.get("target") or "unknown"

            if not normalized["type"]:
                raise ValueError("Action type missing in LLM response.")
            normalized_actions.append(normalized)

        return {
            "summary": data.get("summary") or "Auto-normalized response.",
            "actions": normalized_actions,
            "stop": bool(data.get("stop", False)),
            "confidence": float(data.get("confidence", 0.5)),
        }

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
        self.logger.info("LLM models response count: %d", len(all_models))
        return all_models

    @staticmethod
    def _models_url(endpoint: str) -> str:
        parsed = urlparse(endpoint)
        path = "/v1/models"
        return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))
