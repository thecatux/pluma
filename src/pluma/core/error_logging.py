"""Application error logging for Python and Qt exceptions."""

import logging
import sys
import threading
from pathlib import Path

from pluma.core.paths import program_dir, user_data_dir


def _log_unhandled_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.critical(
        "Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback)
    )


def _log_thread_exception(args):
    _log_unhandled_exception(args.exc_type, args.exc_value, args.exc_traceback)


def configure_error_logging():
    log_handler = None
    for log_dir in (Path(program_dir()) / "data", Path(user_data_dir())):
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_handler = logging.FileHandler(log_dir / "pluma.log", encoding="utf-8")
            log_handler.terminator = "\n\n"
            break
        except OSError:
            continue

    if log_handler is None:
        raise OSError("Unable to create the Pluma error log")

    logging.basicConfig(
        handlers=[log_handler],
        level=logging.ERROR,
        format="%(asctime)s | %(levelname)s | %(threadName)s\n%(message)s\n",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    sys.excepthook = _log_unhandled_exception
    threading.excepthook = _log_thread_exception


def install_qt_message_handler():
    from PySide6.QtCore import QtMsgType, qInstallMessageHandler

    def log_qt_message(message_type, context, message):
        if message_type in (QtMsgType.QtCriticalMsg, QtMsgType.QtFatalMsg):
            logging.error("Critical Qt message: %s", message)

    qInstallMessageHandler(log_qt_message)