"""Genera `src/pluma/core/_build_stamp.py` con el build y la fecha.

Ejecutar SIEMPRE justo antes de compilar con Nuitka (desde la raíz del
proyecto, donde está main.py y el repositorio git):

    python stamp_build.py
    python -m nuitka --standalone ... main.py

Valores (por orden de prioridad):
  - número de build: PLUMA_BUILD_NUMBER, o "<commits> (<hash corto>)" de git
  - fecha:           PLUMA_BUILD_DATE, o SOURCE_DATE_EPOCH, o hoy (UTC)
"""

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "src" / "pluma" / "core" / "_build_stamp.py"


def _git(*arguments):
    return subprocess.run(
        ["git", *arguments], cwd=ROOT, capture_output=True,
        check=True, text=True, timeout=10,
    ).stdout.strip()


def build_number():
    supplied = os.environ.get("PLUMA_BUILD_NUMBER")
    if supplied:
        return supplied
    try:
        return f"{_git('rev-list', '--count', 'HEAD')} ({_git('rev-parse', '--short', 'HEAD')})"
    except (OSError, subprocess.SubprocessError):
        return ""


def build_date():
    supplied = os.environ.get("PLUMA_BUILD_DATE")
    if supplied:
        return supplied
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch:
        try:
            return datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%Y-%m-%d")
        except (ValueError, OverflowError, OSError):
            pass
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main():
    number = build_number()
    if not number:
        print("AVISO: no se pudo obtener el número de build (¿git disponible? "
              "¿PLUMA_BUILD_NUMBER definida?). El Acerca de mostrará 'Desconocido'.",
              file=sys.stderr)
    OUTPUT.write_text(
        '"""Generado por stamp_build.py. No editar ni versionar."""\n\n'
        f"BUILD_NUMBER = {number!r}\n"
        f"BUILD_DATE = {build_date()!r}\n",
        encoding="utf-8",
    )
    print(f"Escrito {OUTPUT}: build={number or '(vacío)'} fecha={build_date()}")


if __name__ == "__main__":
    main()