"""Shared application and user data locations."""

import os
import sys
from pathlib import Path


def program_dir() -> str:
    """Return the application directory in source and compiled builds."""
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
    """Return the per-user data directory when the app directory is unavailable."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "Pluma")