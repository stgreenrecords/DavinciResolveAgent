from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from app_logging.session_logger import SessionLogger
from automation.executor import ActionExecutor
from calibration.profile import CalibrationProfile
from controllers.agent_state import AgentState, AgentStateMachine
from controllers.iteration_runner import IterationRunner
from llm.client import LlmClient
from vision.metrics import SimilarityMetrics


class AgentController:
    def __init__(
        self,
        executor: ActionExecutor,
        llm_client: LlmClient,
        iteration_runner: IterationRunner,
        logger: logging.Logger | None = None,
    ) -> None:
        self._executor = executor
        self._llm_client = llm_client
        self._iteration_runner = iteration_runner
        self._logger = logger or logging.getLogger("app.agent")
        self._state_machine = AgentStateMachine()
        self.iteration = 0
        self.last_metrics: SimilarityMetrics | None = None
        self.current_state: dict = {}
        self.session_logger: SessionLogger | None = None

    def set_stop_callback(self, callback: Callable[[], None]) -> None:
        self._executor.stop_callback = callback

    def set_log_callback(self, callback: Callable[[str], None]) -> None:
        self._executor.log_callback = callback

    @property
    def executor(self) -> ActionExecutor:
        return self._executor

    @property
    def state(self) -> AgentState:
        return self._state_machine.state

    def transition(self, target: AgentState) -> None:
        self._state_machine.transition(target)

    def ensure_session_logger(self) -> None:
        if self.session_logger is None:
            self.session_logger = SessionLogger()

    def log_session_info(self, settings: dict, calibration: dict) -> None:
        if self.session_logger is None:
            return
        self.session_logger.log_session_info(settings, calibration)

    def run_iteration(
        self,
        reference_image_path: Path,
        calibration: CalibrationProfile | None,
        instructions: str,
        continuous: bool,
        on_iteration_updated: Callable[[int, SimilarityMetrics, object, dict, str], None],
        on_log: Callable[[str], None],
    ) -> tuple[int, SimilarityMetrics | None, dict]:
        if self.state == AgentState.IDLE:
            self.transition(AgentState.READY)
        self.transition(AgentState.RUNNING)
        try:
            iteration, last_metrics, current_state = self._iteration_runner.run(
                reference_image_path=reference_image_path,
                calibration=calibration,
                instructions=instructions,
                current_state=self.current_state,
                iteration=self.iteration,
                continuous=continuous,
                session_logger=self.session_logger,
                on_iteration_updated=on_iteration_updated,
                on_log=on_log,
            )
            self.iteration = iteration
            self.last_metrics = last_metrics
            self.current_state = current_state
            if self._executor.is_stopped():
                self.transition(AgentState.STOPPED)
            else:
                self.transition(AgentState.READY)
            return iteration, last_metrics, current_state
        except Exception:
            self.transition(AgentState.ERROR)
            raise

    def stop(self) -> None:
        self._executor.trigger_stop()
        try:
            self.transition(AgentState.STOPPED)
        except ValueError:
            self._logger.info("Stop requested in state=%s", self.state.name)

    def rollback(self) -> None:
        self._executor.undo_last()

    def test_connection(self) -> dict:
        return self._llm_client.test_connection()

    def list_models(self) -> list[str]:
        return self._llm_client.list_models()
