from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from pathlib import Path

from automation.executor import ActionExecutor
from calibration.profile import CalibrationProfile
from llm.client import LlmClient, LlmRequestContext
from vision.metrics import ConvergenceDetector, SimilarityMetrics, compute_metrics
from vision.screenshot import capture_roi


class IterationRunner:
    """Runs the iteration loop that captures frames, requests actions, and executes them."""

    def __init__(self, executor: ActionExecutor, llm_client: LlmClient, logger: logging.Logger | None = None):
        self._executor = executor
        self._llm_client = llm_client
        self._logger = logger or logging.getLogger("app.iteration")

    def run(
        self,
        reference_image_path: Path,
        calibration: CalibrationProfile | None,
        instructions: str,
        current_state: dict,
        iteration: int,
        continuous: bool,
        session_logger,
        on_iteration_updated: Callable[[int, SimilarityMetrics, object, dict, str], None],
        on_log: Callable[[str], None],
        on_thinking_started: Callable[[], None] | None = None,
        on_recommendation_received: Callable[[str], None] | None = None,
        on_recommendation_closed: Callable[[], None] | None = None,
    ) -> tuple[int, SimilarityMetrics | None, dict]:
        """Run one or more iterations and return updated iteration, metrics, and state."""
        last_metrics: SimilarityMetrics | None = None
        convergence_detector = ConvergenceDetector()
        try:
            self._executor.ensure_safe_mode()
            while True:
                if self._executor.is_stopped():
                    break
                if calibration is None:
                    on_log("Calibration missing. Stopping automation.")
                    break

                roi_image = capture_roi(calibration.roi)
                metrics = compute_metrics(reference_image_path, roi_image)

                if not current_state and calibration.control_metadata:
                    for name, meta in calibration.control_metadata.items():
                        if name != "roi_center":
                            current_state[name] = float(meta.get("defaultValue", 0))

                ctx = LlmRequestContext(
                    reference_image_path=reference_image_path,
                    current_image=roi_image,
                    previous_image=None,
                    metrics=metrics,
                    calibration=calibration,
                    instructions=instructions,
                    current_state=current_state,
                )

                self._logger.info("Requesting LLM actions")
                if on_thinking_started:
                    on_thinking_started()
                response = self._llm_client.request_actions(ctx)

                summary = response.raw.get("summary", "")
                if on_recommendation_received:
                    on_recommendation_received(summary)
                    time.sleep(3.0)
                if on_recommendation_closed:
                    on_recommendation_closed()

                if response.stop:
                    on_log("LLM requested stop or low confidence.")
                    break

                actions = response.actions
                self._logger.info("Executing %d actions", len(actions))
                self._executor.execute_actions(actions, calibration, iteration, session_logger)

                for action in actions:
                    if action.get("type") == "set_slider" and action.get("target") in current_state:
                        current_state[action["target"]] = action["value"]

                after_image = capture_roi(calibration.roi)
                after_metrics = compute_metrics(reference_image_path, after_image)
                iteration += 1
                last_metrics = after_metrics

                if session_logger:
                    session_logger.log_iteration(iteration, roi_image, after_image, metrics, response)

                on_iteration_updated(
                    iteration,
                    after_metrics,
                    (after_image.tobytes(), (after_image.width, after_image.height)),
                    response.raw,
                    response.raw.get("summary", ""),
                )

                if continuous and convergence_detector.add(after_metrics):
                    on_log("Convergence detected. Stopping automation.")
                    break

                if not continuous:
                    break

                time.sleep(1.0)
        except Exception as exc:
            self._logger.exception("Iteration failed")
            on_log(f"Iteration failed: {exc}")
        return iteration, last_metrics, current_state

    @staticmethod
    def format_response_payload(raw: dict) -> str:
        return json.dumps(raw, indent=2)
