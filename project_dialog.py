"""Diálogo de selección de proyecto.

Se muestra al arrancar la aplicación (y desde el menú "Proyecto ▸
Cambiar de proyecto..."). Permite abrir un proyecto existente, crear
uno nuevo, renombrarlo o eliminarlo. Todos los proyectos comparten la
misma base de datos SQLite (junto al propio programa, en
`data/pluma.db`); lo único que cambia es
el `project_id` con el que se filtran capítulos, personajes, etc.
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget,
                                QListWidgetItem, QPushButton, QLabel, QInputDialog,
                                QMessageBox, QLineEdit, QStackedWidget, QWidget)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter

import glass
import icons
import theme


class ProjectDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.selected_project_id = None

        self.setWindowTitle("Pluma — Proyectos")
        self.resize(460, 480)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 20)
        layout.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.title_icon = QLabel()
        title_row.addWidget(self.title_icon)
        title = QLabel("Tus novelas")
        title.setStyleSheet("font-size: 16pt; font-weight: 700;")
        title_row.addWidget(title)
        title_row.addStretch(1)
        layout.addLayout(title_row)
        subtitle = QLabel("Elige un proyecto para continuar o crea uno nuevo.")
        subtitle.setProperty("role", "hint")
        layout.addWidget(subtitle)

        self._refresh_icons()
        theme.signals.changed.connect(self._on_theme_changed)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_empty_state())
        self.stack.addWidget(self._build_list_widget())
        layout.addWidget(self.stack, 1)

        buttons = QHBoxLayout()
        new_btn = QPushButton("+ Nuevo proyecto")
        new_btn.setProperty("variant", "primary")
        new_btn.clicked.connect(self._create_project)
        rename_btn = QPushButton("Renombrar")
        rename_btn.clicked.connect(self._rename_project)
        delete_btn = QPushButton("Eliminar")
        delete_btn.setProperty("variant", "danger")
        delete_btn.clicked.connect(self._delete_project)
        buttons.addWidget(new_btn)
        buttons.addStretch(1)
        buttons.addWidget(rename_btn)
        buttons.addWidget(delete_btn)
        layout.addLayout(buttons)

        open_row = QHBoxLayout()
        open_row.addStretch(1)
        self.open_btn = QPushButton("Abrir proyecto")
        self.open_btn.setProperty("variant", "primary")
        self.open_btn.setDefault(True)
        self.open_btn.clicked.connect(self._open_selected)
        open_row.addWidget(self.open_btn)
        layout.addLayout(open_row)

        self._reload_list()

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setClipRect(event.rect())
        glass.paint_backdrop(painter, self.rect())
        painter.end()

    def _refresh_icons(self):
        c = theme.colors()
        self.title_icon.setPixmap(icons.pixmap("pen", c["primary_text"], size=20))
        if hasattr(self, "empty_icon"):
            self.empty_icon.setPixmap(icons.pixmap("library", c["text_muted"], size=48))

    def _on_theme_changed(self, *_args):
        self._refresh_icons()
        self._reload_list(select_id=self._current_project_id())
        self.update()

    def _build_list_widget(self) -> QWidget:
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.setIconSize(QSize(18, 18))
        self.list_widget.itemDoubleClicked.connect(self._open_selected)
        return self.list_widget

    def _build_empty_state(self) -> QWidget:
        empty = QWidget()
        layout = QVBoxLayout(empty)
        layout.addStretch(1)
        self.empty_icon = QLabel()
        self.empty_icon.setPixmap(icons.pixmap("library", theme.colors()["text_muted"], size=48))
        self.empty_icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_icon)
        message = QLabel("Todavía no has creado ninguna novela")
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("font-size: 12pt; font-weight: 600;")
        layout.addWidget(message)
        subtitle = QLabel("Pulsa \"+ Nuevo proyecto\" para empezar a escribir.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setProperty("role", "hint")
        layout.addWidget(subtitle)
        layout.addStretch(1)
        return empty

    def _reload_list(self, select_id=None):
        self.list_widget.clear()
        projects = self.db.list_projects()
        target_row = None
        book_icon = icons.icon("book", theme.colors()["text_secondary"], size=18)
        for row in projects:
            when = row["last_opened_at"] or row["created_at"] or ""
            item = QListWidgetItem(f"{row['name']}\nÚltima apertura: {when}" if when else row["name"])
            item.setIcon(book_icon)
            item.setData(Qt.UserRole, row["id"])
            self.list_widget.addItem(item)
            if select_id is not None and row["id"] == select_id:
                target_row = self.list_widget.count() - 1
        self.stack.setCurrentIndex(1 if projects else 0)
        self.open_btn.setEnabled(bool(projects))
        if target_row is not None:
            self.list_widget.setCurrentRow(target_row)
        elif self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _current_project_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _create_project(self):
        name, ok = QInputDialog.getText(self, "Nuevo proyecto", "Nombre de la novela:")
        if not ok or not name.strip():
            return
        try:
            new_id = self.db.create_project(name.strip())
        except ValueError as e:
            QMessageBox.warning(self, "Nombre inválido", str(e))
            return
        except Exception:
            QMessageBox.warning(self, "Nombre en uso", "Ya existe un proyecto con ese nombre.")
            return
        self._reload_list(select_id=new_id)

    def _rename_project(self):
        project_id = self._current_project_id()
        if project_id is None:
            return
        current_row = self.db.get_project(project_id)
        name, ok = QInputDialog.getText(self, "Renombrar proyecto", "Nuevo nombre:",
                                         QLineEdit.Normal, current_row["name"])
        if not ok or not name.strip():
            return
        try:
            self.db.rename_project(project_id, name.strip())
        except Exception:
            QMessageBox.warning(self, "No se pudo renombrar", "Ya existe un proyecto con ese nombre.")
            return
        self._reload_list(select_id=project_id)

    def _delete_project(self):
        project_id = self._current_project_id()
        if project_id is None:
            return
        current_row = self.db.get_project(project_id)
        ret = QMessageBox.question(
            self, "Eliminar proyecto",
            f"¿Seguro que quieres eliminar \"{current_row['name']}\"?\n"
            "Se borrarán todos sus capítulos, personajes, escenas, esquema y notas. "
            "Esta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        self.db.delete_project(project_id)
        self._reload_list()

    def _open_selected(self):
        project_id = self._current_project_id()
        if project_id is None:
            QMessageBox.information(self, "Ningún proyecto", "Crea o selecciona un proyecto primero.")
            return
        self.selected_project_id = project_id
        self.db.touch_project(project_id)
        self.accept()