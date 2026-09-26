"""Pluma — aplicación de escritura.

Punto de entrada: crea la base de datos (SQLite en
<directorio del programa>/data/pluma.db, sobreescribible con la
variable de entorno PLUMA_DB_PATH), pide al usuario que elija o cree
un proyecto y abre la ventana principal.
"""

import sys

from PySide6.QtWidgets import QApplication

from db import Database
from project_dialog import ProjectDialog
from main_window import MainWindow
from theme import apply_theme


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Pluma")
    app.setOrganizationName("Pluma")
    theme_controller = apply_theme(app)

    db = Database()

    dialog = ProjectDialog(db)
    if not dialog.exec() or dialog.selected_project_id is None:
        sys.exit(0)

    project_row = db.get_project(dialog.selected_project_id)

    window = MainWindow(db, theme_controller)
    window.load_project(project_row["id"], project_row["name"])
    window.show()

    exit_code = app.exec()
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
