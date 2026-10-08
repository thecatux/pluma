"""Ubicaciones compartidas de la aplicación y de los datos de usuario."""

import os
import sys
from pathlib import Path


def program_dir() -> str:
    """Devuelve el directorio de la aplicación tanto en desarrollo como en ejecutable compilado."""
    compiled = globals().get("__compiled__")
    if compiled is not None:
        containing = getattr(compiled, "containing_dir", None)
        if containing:
            return os.path.abspath(containing)
        return os.path.dirname(os.path.abspath(sys.argv[0]))
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return str(Path(__file__).resolve().parents[3])


def user_data_dir() -> str:
    """Devuelve el directorio de datos por usuario cuando el directorio de la app no tiene permisos de escritura."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "Pluma")