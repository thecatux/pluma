"""Version and build metadata shown by the About dialog."""

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

try:
    # Módulo generado por `stamp_build.py` justo antes de compilar. Al ser
    # un import estático, Nuitka lo incluye en el binario, de modo que el
    # build y la fecha viajan dentro del ejecutable y no dependen de que
    # exista git ni un repositorio en la máquina del usuario.
    from . import _build_stamp
except ImportError:
    _build_stamp = None


APP_NAME = "Pluma"
APP_VERSION = "0.9.1 (BETA 1)"


def _git_value(*arguments):
    return subprocess.run(
        ["git", *arguments],
        cwd=Path(__file__).resolve().parent,
        capture_output=True,
        check=True,
        text=True,
        timeout=2,
    ).stdout.strip()


def _build_number():
    supplied_number = os.environ.get("PLUMA_BUILD_NUMBER")
    if supplied_number:
        return supplied_number

    stamped_number = getattr(_build_stamp, "BUILD_NUMBER", "")
    if stamped_number:
        return stamped_number

    try:
        commit_count = _git_value("rev-list", "--count", "HEAD")
        commit_hash = _git_value("rev-parse", "--short", "HEAD")
        return f"{commit_count} ({commit_hash})"
    except (OSError, subprocess.SubprocessError):
        return "Desconocido"


def _build_date():
    supplied_date = os.environ.get("PLUMA_BUILD_DATE")
    if supplied_date:
        return supplied_date

    stamped_date = getattr(_build_stamp, "BUILD_DATE", "")
    if stamped_date:
        return stamped_date

    source_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_epoch:
        try:
            return datetime.fromtimestamp(int(source_epoch), timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OverflowError, OSError):
            pass

    return "Desarrollo"


BUILD_NUMBER = _build_number()
BUILD_DATE = _build_date()