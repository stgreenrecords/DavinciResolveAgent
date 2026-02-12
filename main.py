from PySide6 import QtWidgets

from app_ui.main_window import MainWindow
from automation.executor import ActionExecutor
from config.paths import LOG_DIR
from controllers.agent_controller import AgentController
from controllers.calibration_manager import CalibrationManager
from controllers.iteration_runner import IterationRunner
from controllers.settings_manager import SettingsManager
from controllers.task_queue import TaskQueue
from llm.client import LlmClient
from storage.settings import SettingsStore


class _StreamToLogger:
    def __init__(self, logger, level):
        self._logger = logger
        self._level = level

    def write(self, message):
        message = message.strip()
        if message:
            self._logger.log(self._level, message)

    def flush(self):
        return


def _install_exception_hooks():
    import faulthandler
    import logging
    import sys
    import threading
    import traceback

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / "app.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
    )
    logger = logging.getLogger("app")

    sys.stdout = _StreamToLogger(logging.getLogger("stdout"), logging.INFO)
    sys.stderr = _StreamToLogger(logging.getLogger("stderr"), logging.ERROR)

    log_file = log_path.open("a", encoding="utf-8")

    def _write_exception(prefix: str, exc_type, exc_value, exc_tb):
        logger.error("%s unhandled exception", prefix)
        log_file.write(f"\n[{prefix}] Unhandled exception\n")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=log_file)
        log_file.flush()

    def _sys_hook(exc_type, exc_value, exc_tb):
        _write_exception("sys", exc_type, exc_value, exc_tb)

    def _thread_hook(args):
        _write_exception("thread", args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _sys_hook
    threading.excepthook = _thread_hook
    faulthandler.enable(log_file)


if __name__ == "__main__":
    _install_exception_hooks()
    app = QtWidgets.QApplication([])
    settings_store = SettingsStore()
    settings_manager = SettingsManager(settings_store)
    executor = ActionExecutor(lambda: None)
    llm_client = LlmClient(settings_store)
    iteration_runner = IterationRunner(executor, llm_client)
    agent_controller = AgentController(executor, llm_client, iteration_runner)
    calibration_manager = CalibrationManager(settings_store)
    task_queue = TaskQueue()
    window = MainWindow(settings_manager, calibration_manager, agent_controller, task_queue)
    window.resize(700, 620)
    window.show()
    app.exec()
