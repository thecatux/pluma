"""Ventana principal de Pluma.

Estructura: una barra lateral fija a la izquierda con las cinco
secciones (Capítulos, Personajes, Escenas, Esquema, Notas) y, a la
derecha, un QStackedWidget que muestra el panel correspondiente. Cada
panel es responsable de su propia UI y de leer/escribir en SQLite; esta
clase solo hace de anfitrión y gestiona el cambio de proyecto.
"""

from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                                QListWidget, QListWidgetItem, QStackedWidget,
                                QStatusBar, QLabel, QFrame)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QAction, QActionGroup, QKeySequence

import icons
import theme
from db import Database
from project_dialog import ProjectDialog
from theme import MODE_LABELS
from panels.info_panel import InfoPanel
from panels.chapters_panel import ChaptersPanel
from panels.characters_panel import CharactersPanel
from panels.scenes_panel import ScenesPanel
from panels.outline_panel import OutlinePanel
from panels.notes_panel import NotesPanel
from panels.settings_panel import SettingsPanel

SECTIONS = [
    ("info", "info", "Datos de la novela"),
    ("chapters", "book", "Capítulos"),
    ("characters", "user", "Personajes"),
    ("scenes", "clapper", "Escenas"),
    ("outline", "timeline", "Línea temporal"),
    ("notes", "note", "Notas"),
    ("settings", "settings", "Ajustes"),
]


class MainWindow(QMainWindow):
    def __init__(self, db: Database, theme_controller=None):
        super().__init__()
        self.db = db
        self.theme_controller = theme_controller
        self.project_id = None
        self.resize(1240, 780)
        self.setMinimumSize(920, 600)

        self._build_sidebar_and_stack()
        self._build_menu()
        self._build_status_bar()

        # El cambio de sección hace "flush" del autoguardado pendiente
        # del panel que se abandona, para no perder cambios recientes si
        # el usuario cambia de sección justo después de escribir.
        self.sidebar.currentRowChanged.connect(self._on_section_changed)

    # ------------------------------------------------------------------ #
    def _build_sidebar_and_stack(self):
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar_container = QWidget()
        sidebar_container.setFixedWidth(212)
        sidebar_layout = QVBoxLayout(sidebar_container)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        header = QFrame()
        header.setProperty("role", "sidebar-header")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 22, 20, 18)
        header_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.app_icon_label = QLabel()
        self.app_icon_label.setFixedSize(20, 20)
        title_row.addWidget(self.app_icon_label)
        app_title = QLabel("Pluma")
        app_title.setStyleSheet("color: #FFFFFF; font-size: 15pt; font-weight: 700;")
        title_row.addWidget(app_title)
        title_row.addStretch(1)
        header_layout.addLayout(title_row)

        self.project_label = QLabel("Sin proyecto")
        self.project_label.setStyleSheet("color: #7C8195; font-size: 9.5pt;")
        self.project_label.setWordWrap(True)
        header_layout.addWidget(self.project_label)

        sidebar_layout.addWidget(header)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setIconSize(QSize(18, 18))
        font = QFont()
        font.setPointSize(11)
        self.sidebar.setFont(font)
        sidebar_layout.addWidget(self.sidebar, 1)

        self.stack = QStackedWidget()
        self.panels = {}

        self.panels["info"] = InfoPanel(self.db)
        self.panels["chapters"] = ChaptersPanel(self.db)
        self.panels["characters"] = CharactersPanel(self.db)
        self.panels["scenes"] = ScenesPanel(self.db)
        self.panels["outline"] = OutlinePanel(self.db)
        self.panels["notes"] = NotesPanel(self.db)
        self.panels["settings"] = SettingsPanel(self.db, self.theme_controller)

        for key, icon_name, label in SECTIONS:
            item = QListWidgetItem(f"  {label}")
            item.setData(Qt.UserRole, icon_name)
            self.sidebar.addItem(item)
            self.stack.addWidget(self.panels[key])

        # Los iconos dependen del color activo (texto de la barra lateral
        # normal / seleccionado), así que se generan aparte y se
        # regeneran cuando cambia el tema, en vez de fijarse una vez al
        # construir la lista.
        self._refresh_sidebar_icons()
        theme.signals.changed.connect(self._refresh_sidebar_icons)

        layout.addWidget(sidebar_container)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _refresh_sidebar_icons(self, *_args):
        c = theme.colors()
        self.app_icon_label.setPixmap(icons.pixmap("pen", "#FFFFFF", size=20))
        for row in range(self.sidebar.count()):
            item = self.sidebar.item(row)
            icon_name = item.data(Qt.UserRole)
            item.setIcon(icons.dual_icon(
                icon_name, c["sidebar_text"], c["sidebar_text_selected"], size=18
            ))

    def _build_menu(self):
        menubar = self.menuBar()
        project_menu = menubar.addMenu("&Proyecto")

        switch_action = QAction("Cambiar de proyecto...", self)
        switch_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        switch_action.triggered.connect(self.prompt_switch_project)
        project_menu.addAction(switch_action)

        project_menu.addSeparator()

        quit_action = QAction("Salir", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.triggered.connect(self.close)
        project_menu.addAction(quit_action)

        self._build_view_menu(menubar)

    def _build_view_menu(self, menubar):
        if self.theme_controller is None:
            return
        view_menu = menubar.addMenu("&Ver")
        theme_menu = view_menu.addMenu("Tema")

        group = QActionGroup(self)
        group.setExclusive(True)
        self._theme_mode_actions = {}
        for mode in ("auto", "light", "dark"):
            action = QAction(MODE_LABELS[mode], self, checkable=True)
            action.setChecked(self.theme_controller.mode == mode)
            action.triggered.connect(lambda checked, m=mode: self.theme_controller.set_mode(m))
            group.addAction(action)
            theme_menu.addAction(action)
            self._theme_mode_actions[mode] = action

    def _build_status_bar(self):
        status = QStatusBar()
        self.setStatusBar(status)

    # ------------------------------------------------------------------ #
    def _on_section_changed(self, row: int):
        previous_row = self.stack.currentIndex()
        if previous_row != row and 0 <= previous_row < len(SECTIONS):
            previous_key = SECTIONS[previous_row][0]
            flush = getattr(self.panels[previous_key], "_flush_pending_save", None)
            if callable(flush):
                flush()
        self.stack.setCurrentIndex(row)
        if 0 <= row < len(SECTIONS):
            current_key = SECTIONS[row][0]
            refresh = getattr(self.panels[current_key], "refresh", None)
            if callable(refresh):
                refresh()

    def load_project(self, project_id: int, project_name: str):
        self.project_id = project_id
        self.setWindowTitle(f"Pluma — {project_name}")
        self.project_label.setText(project_name)
        for panel in self.panels.values():
            panel.load_project(project_id)
        if self.sidebar.currentRow() < 0:
            self.sidebar.setCurrentRow(0)
        self.statusBar().showMessage(f"Proyecto abierto: {project_name}", 3000)

    def prompt_switch_project(self):
        dialog = ProjectDialog(self.db, self)
        if dialog.exec() and dialog.selected_project_id is not None:
            row = next(p for p in self.db.list_projects() if p["id"] == dialog.selected_project_id)
            self.load_project(row["id"], row["name"])

    def closeEvent(self, event):
        # Cada panel gestiona su propio autoguardado con un pequeño
        # retardo; al cerrar la aplicación forzamos que se vuelque
        # cualquier cambio pendiente para no perder la última edición.
        for panel in self.panels.values():
            flush = getattr(panel, "_flush_pending_save", None)
            if callable(flush):
                flush()
        event.accept()