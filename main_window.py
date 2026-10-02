"""Ventana principal de Pluma.

Estructura: una barra lateral fija a la izquierda con las cinco
secciones (Capítulos, Personajes, Escenas, Esquema, Notas) y, a la
derecha, un QStackedWidget que muestra el panel correspondiente. Cada
panel es responsable de su propia UI y de leer/escribir en SQLite; esta
clase solo hace de anfitrión y gestiona el cambio de proyecto.
"""

from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
                                QListWidget, QListWidgetItem, QStackedWidget,
                                QStatusBar, QLabel, QFrame, QPushButton, QToolBar)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QAction, QKeySequence, QPainter

import glass
import icons
import theme
from db import Database
from project_dialog import ProjectDialog
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

# Modos de la barra lateral, en el orden en que los recorre el botón.
SIDEBAR_MODES = ("full", "icons", "hidden")
# Anchos del cristal en sí; el contenedor suma el margen de la sombra
# (`glass.GlassPanel.inset`) a cada lado.
SIDEBAR_WIDTHS = {"full": 212, "icons": 66}
# En modo solo iconos el logo se centra en el ancho reducido.
SIDEBAR_HEADER_MARGINS = {"full": (20, 22, 20, 18), "icons": (23, 22, 23, 18)}
# Texto del botón: qué ocurre al pulsarlo desde cada modo.
SIDEBAR_TOGGLE_TIPS = {
    "full": "Mostrar solo iconos (Ctrl+Shift+B)",
    "icons": "Ocultar la barra lateral (Ctrl+Shift+B)",
    "hidden": "Mostrar la barra lateral (Ctrl+Shift+B)",
}


class MainWindow(QMainWindow):
    def __init__(self, db: Database, theme_controller=None):
        super().__init__()
        self.db = db
        self.theme_controller = theme_controller
        self.project_id = None
        self.resize(1240, 780)
        self.setMinimumSize(920, 600)

        self._build_sidebar_and_stack()
        self._build_global_controls()
        self._build_status_bar()
        self._set_sidebar_mode("full")

        # El cambio de sección hace "flush" del autoguardado pendiente
        # del panel que se abandona, para no perder cambios recientes si
        # el usuario cambia de sección justo después de escribir.
        self.sidebar.currentRowChanged.connect(self._on_section_changed)
        # El fondo con manchas de color depende del acento y del modo.
        theme.signals.changed.connect(lambda *_: self.update())

    # ------------------------------------------------------------------ #
    def _build_sidebar_and_stack(self):
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Panel flotante de cristal líquido: sombra, relleno translúcido,
        # reflejos y esquinas redondeadas se pintan en `glass.GlassPanel`.
        # Deja `inset` px alrededor para la sombra, y el layout interior
        # usa ese mismo margen.
        self.sidebar_container = glass.GlassPanel(radius=24, inset=12)
        self.sidebar_container.setObjectName("SidebarContainer")
        inset = self.sidebar_container.inset
        sidebar_layout = QVBoxLayout(self.sidebar_container)
        sidebar_layout.setContentsMargins(inset, inset, inset, inset)
        sidebar_layout.setSpacing(0)

        header = QFrame()
        header.setProperty("role", "sidebar-header")
        self.sidebar_header = header
        header_layout = QVBoxLayout(header)
        header_layout.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.app_icon_label = QLabel()
        self.app_icon_label.setFixedSize(20, 20)
        title_row.addWidget(self.app_icon_label)
        self.app_title = QLabel("Pluma")
        self.app_title.setProperty("role", "sidebar-title")
        title_row.addWidget(self.app_title)
        title_row.addStretch(1)
        header_layout.addLayout(title_row)

        self.project_label = QLabel("Sin proyecto")
        self.project_label.setProperty("role", "sidebar-subtitle")
        self.project_label.setWordWrap(True)
        header_layout.addWidget(self.project_label)

        sidebar_layout.addWidget(header)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setIconSize(QSize(18, 18))
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        font = QFont()
        font.setPointSize(11)
        self.sidebar.setFont(font)
        # Pastilla de cristal para el elemento activo / bajo el cursor.
        self.sidebar.setItemDelegate(glass.SidebarItemDelegate(self.sidebar))
        self.sidebar.setMouseTracking(True)
        sidebar_layout.addWidget(self.sidebar, 1)

        footer_divider = QFrame()
        footer_divider.setProperty("role", "divider")
        footer_divider.setFixedHeight(1)
        sidebar_layout.addWidget(footer_divider)

        footer = QFrame()
        footer.setProperty("role", "sidebar-header")
        self.sidebar_footer_layout = QVBoxLayout(footer)
        self.sidebar_footer_layout.setContentsMargins(10, 10, 10, 10)
        self.sidebar_footer_layout.setSpacing(0)

        self.switch_project_button = QPushButton("Cambiar proyecto")
        self.switch_project_button.setProperty("variant", "primary")
        self.switch_project_button.setIconSize(QSize(16, 16))
        self.switch_project_button.setMinimumHeight(36)
        self.switch_project_button.setToolTip("Cambiar proyecto")
        self.switch_project_button.setAccessibleName("Cambiar proyecto")
        self.switch_project_button.clicked.connect(self.prompt_switch_project)
        self.sidebar_footer_layout.addWidget(self.switch_project_button)
        sidebar_layout.addWidget(footer)

        self.stack = QStackedWidget()
        self.panels = {}

        self.panels["info"] = InfoPanel(self.db)
        self.panels["chapters"] = ChaptersPanel(self.db)
        self.panels["characters"] = CharactersPanel(self.db)
        self.panels["scenes"] = ScenesPanel(self.db)
        self.panels["outline"] = OutlinePanel(self.db)
        self.panels["notes"] = NotesPanel(self.db)
        self.panels["settings"] = SettingsPanel(self.db, self.theme_controller)

        for key, icon_name, _label in SECTIONS:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, icon_name)
            self.sidebar.addItem(item)
            self.stack.addWidget(self.panels[key])

        # Los iconos dependen del color activo (texto de la barra lateral
        # normal / seleccionado), así que se generan aparte y se
        # regeneran cuando cambia el tema, en vez de fijarse una vez al
        # construir la lista.
        self._refresh_sidebar_icons()
        theme.signals.changed.connect(self._refresh_sidebar_icons)

        layout.addWidget(self.sidebar_container)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(central)

    def _refresh_sidebar_icons(self, *_args):
        c = theme.colors()
        self.app_icon_label.setPixmap(icons.pixmap("pen", c["primary_text"], size=20))
        self.switch_project_button.setIcon(icons.icon("library", c["on_primary"], size=16))
        for row in range(self.sidebar.count()):
            item = self.sidebar.item(row)
            icon_name = item.data(Qt.UserRole)
            item.setIcon(icons.dual_icon(
                icon_name, c["sidebar_text"], c["sidebar_text_selected"], size=18
            ))

    def _build_sidebar_toggle(self, toolbar):
        self.sidebar_toggle_button = QPushButton()
        self.sidebar_toggle_button.setProperty("variant", "flat")
        self.sidebar_toggle_button.setIconSize(QSize(16, 16))
        self.sidebar_toggle_button.setFixedSize(34, 34)
        self.sidebar_toggle_button.setAccessibleName("Mostrar u ocultar la barra lateral")
        self.sidebar_toggle_button.clicked.connect(self._cycle_sidebar_mode)
        toolbar.addWidget(self.sidebar_toggle_button)
        self._refresh_sidebar_toggle_icon()
        theme.signals.changed.connect(self._refresh_sidebar_toggle_icon)

    def _refresh_sidebar_toggle_icon(self, *_args):
        self.sidebar_toggle_button.setIcon(
            icons.icon("sidebar", theme.colors()["text_secondary"], size=16)
        )

    def _cycle_sidebar_mode(self):
        next_index = (SIDEBAR_MODES.index(self._sidebar_mode) + 1) % len(SIDEBAR_MODES)
        self._set_sidebar_mode(SIDEBAR_MODES[next_index])

    def _set_sidebar_mode(self, mode: str):
        self._sidebar_mode = mode
        self.sidebar_toggle_button.setToolTip(SIDEBAR_TOGGLE_TIPS[mode])
        self.sidebar_container.setVisible(mode != "hidden")
        if mode == "hidden":
            return
        compact = mode == "icons"
        self.sidebar_container.setFixedWidth(
            SIDEBAR_WIDTHS[mode] + 2 * self.sidebar_container.inset)
        self.sidebar_header.layout().setContentsMargins(*SIDEBAR_HEADER_MARGINS[mode])
        self.app_title.setVisible(not compact)
        self.project_label.setVisible(not compact)
        self.sidebar_footer_layout.setContentsMargins(6 if compact else 10, 10,
                                  6 if compact else 10, 10)
        self.switch_project_button.setText("" if compact else "Cambiar proyecto")
        self._set_sidebar_labels(compact)

    def _set_sidebar_labels(self, compact: bool):
        """En modo solo iconos el texto pasa a ser un tooltip."""
        for row, (_key, _icon_name, label) in enumerate(SECTIONS):
            item = self.sidebar.item(row)
            item.setText("" if compact else f"  {label}")
            item.setToolTip(label if compact else "")

    def _build_global_controls(self):
        toolbar = QToolBar("Controles de ventana", self)
        toolbar.setObjectName("GlobalControls")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        self._build_sidebar_toggle(toolbar)

        switch_action = QAction("Cambiar de proyecto...", self)
        switch_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        switch_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        switch_action.triggered.connect(self.prompt_switch_project)
        self.addAction(switch_action)

        quit_action = QAction("Salir", self)
        quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        quit_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        quit_action.triggered.connect(self.close)
        self.addAction(quit_action)

        toggle_action = QAction("Mostrar u ocultar la barra lateral", self)
        toggle_action.setShortcut(QKeySequence("Ctrl+Shift+B"))
        toggle_action.setShortcutContext(Qt.ShortcutContext.ApplicationShortcut)
        toggle_action.triggered.connect(self._cycle_sidebar_mode)
        self.addAction(toggle_action)

    def _build_status_bar(self):
        status = QStatusBar()
        self.setStatusBar(status)

    # ------------------------------------------------------------------ #
    def paintEvent(self, event):
        # Primero el degradado del QSS y encima las manchas de color que
        # el cristal "refracta" (ver `glass.paint_backdrop`).
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setClipRect(event.rect())
        glass.paint_backdrop(painter, self.rect())
        painter.end()

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