"""Locate application assets in source, installed, and frozen builds."""

import sys
from pathlib import Path


def asset_path(name: str) -> Path:
    """Return the path to a bundled asset or raise if it is unavailable."""
    if Path(name).name != name:
        raise ValueError("Asset name must not contain a directory")

    bases = []
    bundle_dir = getattr(sys, "_MEIPASS", None)
    if bundle_dir:
        bases.append(Path(bundle_dir))
    bases.append(Path(sys.executable).resolve().parent)
    bases.append(Path(__file__).resolve().parents[3])
    bases.append(Path(sys.prefix))

    for base in bases:
        for candidate in (base / "assets" / name, base / name):
            if candidate.is_file():
                return candidate

    raise FileNotFoundError(f"Pluma asset not found: {name}")