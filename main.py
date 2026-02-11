from app_ui.main_window import run_app


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
    from pathlib import Path

    project_root = Path(__file__).resolve().parent
    log_dir = project_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

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
    run_app()
