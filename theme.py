"""Tema visual centralizado de Pluma.

Un único lugar para colores, tipografía, espaciados y la hoja de
estilos (QSS) de toda la aplicación. Los paneles y diálogos no
definen sus propios colores sueltos: usan estas constantes/roles o
consultan `theme.colors()` para lo poco que necesita seguir el
esquema de color activo.

Pluma admite modo claro y modo oscuro. Por defecto sigue el tema del
sistema operativo ("automático"); el usuario puede forzar uno de los
dos desde el menú "Ver" de la ventana principal. La preferencia se
guarda con QSettings y se restaura al reabrir la aplicación.
"""

from PySide6.QtCore import QObject, Signal, QSettings
from PySide6.QtGui import QGuiApplication, QPalette

FONT_FAMILY = '"Segoe UI", "SF Pro Text", "Inter", "Helvetica Neue", Arial, sans-serif'
FONT_FAMILY_SERIF = '"Georgia", "Iowan Old Style", "Palatino Linotype", serif'

RADIUS = {"sm": 6, "md": 8, "lg": 12, "xl": 16}

# Paleta clara: fondos de papel cálido en lugar de gris frío, con un
# índigo contenido como único color de acento. Los textos secundarios
# mantienen al menos 4.5:1 de contraste sobre las superficies.
_LIGHT = {
    "bg": "#F5F3EF",
    "surface": "#FFFFFF",
    "surface_alt": "#FAF8F5",
    "border": "#E8E4DD",
    "border_strong": "#D8D3CA",
    "text": "#25231F",
    "text_secondary": "#6A655D",
    "text_muted": "#8E887E",
    "primary": "#4263EB",
    "primary_hover": "#3B5BDB",
    "primary_pressed": "#364FC7",
    "primary_light": "#ECEFFD",
    "primary_border": "#C7D0F8",
    # Texto/iconos sobre `primary_light` (selecciones, chips activos) y
    # sobre `primary` (botones principales). Separados de
    # `primary_pressed` porque en el tema oscuro el texto sobre un fondo
    # tintado necesita ser claro y el fondo pulsado de un botón, no.
    "primary_text": "#364FC7",
    "on_primary": "#FFFFFF",
    "danger": "#C92F2F",
    "danger_hover": "#B02525",
    "danger_light": "#FDEDED",
    "success": "#2B8A3E",
    "sidebar_bg": "#1E2130",
    "sidebar_bg_hover": "#2A2E42",
    "sidebar_bg_selected": "#4263EB",
    "sidebar_text": "#C9CDDB",
    "sidebar_text_muted": "#8A90A6",
    "sidebar_text_selected": "#FFFFFF",
}

# Paleta oscura: grises azulados suaves (nada de negro puro) y un
# acento algo más profundo que el claro para que el texto blanco de los
# botones principales siga siendo legible. La barra lateral sigue
# siendo la identidad visual de Pluma, un poco más oscura que el fondo.
_DARK = {
    "bg": "#14161D",
    "surface": "#1C1F29",
    "surface_alt": "#232735",
    "border": "#2E3342",
    "border_strong": "#3B4155",
    "text": "#E6E8EE",
    "text_secondary": "#A4AABA",
    "text_muted": "#7C8296",
    "primary": "#4D6AEA",
    "primary_hover": "#5873F0",
    "primary_pressed": "#4260DB",
    "primary_light": "#253056",
    "primary_border": "#3D4A85",
    "primary_text": "#A5B8FF",
    "on_primary": "#FFFFFF",
    "danger": "#FF7070",
    "danger_hover": "#FF8A8A",
    "danger_light": "#3B2229",
    "success": "#69DB7C",
    "sidebar_bg": "#101219",
    "sidebar_bg_hover": "#1B1E2B",
    "sidebar_bg_selected": "#4D6AEA",
    "sidebar_text": "#C9CDDB",
    "sidebar_text_muted": "#7C8296",
    "sidebar_text_selected": "#FFFFFF",
}

PALETTES = {"light": _LIGHT, "dark": _DARK}

MODE_LABELS = {
    "auto": "Automático (según el sistema)",
    "light": "Claro",
    "dark": "Oscuro",
}


class _ThemeSignals(QObject):
    """Punto de conexión global para que cualquier widget se entere de
    un cambio de esquema de color sin tener que recibir el controlador
    por constructor."""
    changed = Signal(str)  # "light" | "dark"


signals = _ThemeSignals()

_current_scheme = "light"
_current_colors = _LIGHT


def colors() -> dict:
    """Paleta de colores actualmente activa (según el esquema resuelto)."""
    return _current_colors


def current_scheme() -> str:
    """Esquema resuelto actualmente: 'light' o 'dark' (nunca 'auto')."""
    return _current_scheme


def build_stylesheet(palette: dict) -> str:
    c = palette
    return f"""
    * {{
        font-family: {FONT_FAMILY};
        outline: none;
    }}

    QMainWindow, QDialog {{
        background: {c['bg']};
    }}

    QWidget {{
        color: {c['text']};
        font-size: 10.5pt;
    }}

    QLabel {{
        background: transparent;
    }}

    QLabel[role="hint"] {{
        color: {c['text_secondary']};
    }}

    QLabel[role="muted"] {{
        color: {c['text_muted']};
        font-size: 9.5pt;
    }}

    QLabel[role="section-title"] {{
        color: {c['text']};
        font-size: 11.5pt;
        font-weight: 600;
        padding: 2px 0 4px 0;
    }}

    QLabel[role="avatar"] {{
        background: {c['primary_light']};
        color: {c['primary_text']};
        border-radius: 24px;
        font-size: 16pt;
        font-weight: 700;
    }}

    QLabel[role="sidebar-title"] {{
        color: {c['sidebar_text_selected']};
        font-size: 15pt;
        font-weight: 700;
    }}
    QLabel[role="sidebar-subtitle"] {{
        color: {c['sidebar_text_muted']};
        font-size: 9.5pt;
    }}

    /* -------------------------------------------------------------- */
    /* Botones                                                          */
    /* -------------------------------------------------------------- */
    QPushButton {{
        background: {c['surface']};
        border: 1px solid {c['border_strong']};
        border-radius: {RADIUS['md']}px;
        padding: 7px 14px;
        color: {c['text']};
        font-weight: 500;
    }}
    QPushButton:hover {{
        background: {c['surface_alt']};
        border-color: {c['text_muted']};
    }}
    QPushButton:pressed {{
        background: {c['border']};
    }}
    QPushButton:disabled {{
        color: {c['text_muted']};
        background: {c['surface_alt']};
        border-color: {c['border']};
    }}

    QPushButton[variant="primary"] {{
        background: {c['primary']};
        border: 1px solid {c['primary']};
        color: {c['on_primary']};
        font-weight: 600;
    }}
    QPushButton[variant="primary"]:hover {{
        background: {c['primary_hover']};
        border-color: {c['primary_hover']};
    }}
    QPushButton[variant="primary"]:pressed {{
        background: {c['primary_pressed']};
    }}

    QPushButton[variant="danger"] {{
        background: {c['surface']};
        border: 1px solid {c['border_strong']};
        color: {c['danger']};
    }}
    QPushButton[variant="danger"]:hover {{
        background: {c['danger_light']};
        border-color: {c['danger']};
    }}
    QPushButton[variant="danger"]:disabled, QPushButton[variant="primary"]:disabled {{
        color: {c['text_muted']};
        background: {c['surface_alt']};
        border-color: {c['border']};
    }}

    QPushButton[variant="flat"] {{
        background: transparent;
        border: none;
        padding: 4px 8px;
        color: {c['text_secondary']};
    }}
    QPushButton[variant="flat"]:hover {{
        color: {c['text']};
        background: {c['surface_alt']};
    }}

    QPushButton[variant="icon"] {{
        background: transparent;
        border: none;
        border-radius: {RADIUS['sm']}px;
        padding: 3px;
        color: {c['text_muted']};
        font-weight: 600;
    }}
    QPushButton[variant="icon"]:hover {{
        background: {c['danger_light']};
        color: {c['danger']};
    }}

    QPushButton[variant="chip"] {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: 13px;
        padding: 5px 12px;
        font-size: 9.5pt;
        font-weight: 500;
        color: {c['text_secondary']};
    }}
    QPushButton[variant="chip"]:hover {{
        border-color: {c['text_muted']};
        color: {c['text']};
    }}
    QPushButton[variant="chip"]:checked {{
        background: {c['primary_light']};
        border: 1px solid {c['primary_border']};
        color: {c['primary_text']};
        font-weight: 600;
    }}

    /* -------------------------------------------------------------- */
    /* Campos de texto                                                   */
    /* -------------------------------------------------------------- */
    QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{
        background: {c['surface']};
        border: 1px solid {c['border_strong']};
        border-radius: {RADIUS['sm']}px;
        padding: 6px 9px;
        selection-background-color: {c['primary_border']};
        selection-color: {c['text']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{
        border: 1px solid {c['primary']};
    }}
    QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {{
        background: {c['surface_alt']};
        color: {c['text_muted']};
    }}
    QLineEdit[variant="heading"] {{
        border: none;
        border-radius: 0;
        padding: 4px 2px;
        font-size: 18pt;
        font-weight: 700;
        background: transparent;
    }}
    QLineEdit[variant="heading"]:focus {{
        border-bottom: 2px solid {c['primary']};
    }}
    /* Sin borde ni radio a propósito: al estilizarlos Qt sustituye los
       botones arriba/abajo nativos por unos sin flechas. */
    QSpinBox {{
        background: {c['surface']};
        selection-background-color: {c['primary_border']};
        selection-color: {c['text']};
    }}
    QComboBox {{
        min-height: 20px;
    }}
    QComboBox::drop-down {{
        border: none;
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        selection-background-color: {c['primary_light']};
        selection-color: {c['text']};
        padding: 4px;
        outline: none;
    }}
    QComboBox QAbstractItemView::item {{
        padding: 6px 10px;
        min-height: 22px;
        border-radius: {RADIUS['sm']}px;
    }}

    /* -------------------------------------------------------------- */
    /* Listas                                                            */
    /* -------------------------------------------------------------- */
    QListWidget {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS['md']}px;
        padding: 4px;
    }}
    QListWidget::item {{
        border-radius: {RADIUS['sm']}px;
        padding: 8px 10px;
        margin: 1px 0;
        color: {c['text']};
    }}
    QListWidget::item:hover {{
        background: {c['surface_alt']};
    }}
    QListWidget::item:selected {{
        background: {c['primary_light']};
        color: {c['primary_text']};
        font-weight: 600;
    }}

    QListWidget#TimelineList {{
        background: transparent;
        border: none;
        padding: 0;
    }}
    QListWidget#TimelineList::item {{
        padding: 0;
        margin: 0;
        background: transparent;
    }}
    QListWidget#TimelineList::item:hover, QListWidget#TimelineList::item:selected {{
        background: transparent;
    }}

    QListWidget#Sidebar {{
        background: {c['sidebar_bg']};
        border: none;
        border-radius: 0;
        padding: 6px;
    }}
    QListWidget#Sidebar::item {{
        color: {c['sidebar_text']};
        padding: 11px 14px;
        margin: 2px 4px;
        border-radius: {RADIUS['md']}px;
        font-weight: 500;
    }}
    QListWidget#Sidebar::item:hover {{
        background: {c['sidebar_bg_hover']};
    }}
    QListWidget#Sidebar::item:selected {{
        background: {c['sidebar_bg_selected']};
        color: {c['sidebar_text_selected']};
    }}

    /* -------------------------------------------------------------- */
    /* Contenedores                                                      */
    /* -------------------------------------------------------------- */
    QFrame[role="card"] {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS['lg']}px;
    }}
    QFrame[role="field-row"] {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS['md']}px;
    }}
    QFrame[role="divider"] {{
        background: {c['border']};
        max-height: 1px;
        border: none;
    }}
    QFrame[role="sidebar-header"] {{
        background: {c['sidebar_bg']};
        border: none;
    }}
    QFrame[role="toolbar-strip"] {{
        background: {c['surface_alt']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS['md']}px;
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    QGroupBox {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS['md']}px;
        margin-top: 10px;
        padding-top: 14px;
        font-weight: 600;
        color: {c['text_secondary']};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 10px;
        padding: 0 4px;
        color: {c['text_secondary']};
        font-size: 9.5pt;
        text-transform: uppercase;
    }}

    QSplitter::handle {{
        background: {c['bg']};
        width: 1px;
    }}

    /* -------------------------------------------------------------- */
    /* Barras                                                            */
    /* -------------------------------------------------------------- */
    QToolBar {{
        background: {c['surface']};
        border: none;
        border-bottom: 1px solid {c['border']};
        padding: 5px 6px;
        spacing: 2px;
    }}
    QToolBar QToolButton {{
        border-radius: {RADIUS['sm']}px;
        padding: 5px 8px;
        color: {c['text']};
    }}
    QToolBar QToolButton:hover {{
        background: {c['surface_alt']};
    }}
    QToolBar QToolButton:checked {{
        background: {c['primary_light']};
        color: {c['primary_text']};
    }}
    QToolBar::separator {{
        background: {c['border']};
        width: 1px;
        margin: 4px 6px;
    }}

    QMenuBar {{
        background: {c['surface']};
        border-bottom: 1px solid {c['border']};
        padding: 2px;
    }}
    QMenuBar::item {{
        padding: 5px 10px;
        border-radius: {RADIUS['sm']}px;
    }}
    QMenuBar::item:selected {{
        background: {c['surface_alt']};
    }}
    QMenu {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: {RADIUS['md']}px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 7px 24px 7px 12px;
        border-radius: {RADIUS['sm']}px;
    }}
    QMenu::item:selected {{
        background: {c['primary_light']};
        color: {c['primary_text']};
    }}
    QMenu::separator {{
        height: 1px;
        background: {c['border']};
        margin: 4px 8px;
    }}

    QStatusBar {{
        background: {c['surface']};
        border-top: 1px solid {c['border']};
        color: {c['text_secondary']};
    }}

    /* -------------------------------------------------------------- */
    /* Casillas y radios                                                */
    /* -------------------------------------------------------------- */
    QListWidget::indicator {{
        width: 16px;
        height: 16px;
        border-radius: 4px;
        border: 1px solid {c['border_strong']};
        background: {c['surface']};
    }}
    QListWidget::indicator:checked {{
        background: {c['primary']};
        border-color: {c['primary']};
    }}

    /* -------------------------------------------------------------- */
    /* Scrollbars                                                        */
    /* -------------------------------------------------------------- */
    QScrollBar:vertical {{
        background: transparent;
        width: 11px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {c['border_strong']};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {c['text_muted']};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 11px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {c['border_strong']};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    QMessageBox QPushButton, QInputDialog QPushButton {{
        min-width: 76px;
    }}

    QToolTip {{
        background: {c['surface']};
        color: {c['text']};
        border: 1px solid {c['border_strong']};
        padding: 4px 8px;
    }}
    """


class ThemeController(QObject):
    """Gestiona el modo de tema (auto/claro/oscuro), lo persiste con
    QSettings y aplica la hoja de estilos correspondiente a la
    aplicación. Sigue los cambios de tema del sistema operativo en
    tiempo real cuando el modo es "auto" (Qt 6.5+; en versiones
    anteriores de Qt simplemente no hay auto-refresco en caliente y el
    tema del sistema se detecta al iniciar la aplicación)."""

    themeChanged = Signal(str)  # esquema resuelto: "light" | "dark"

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._settings = QSettings()
        mode = self._settings.value("theme/mode", "auto")
        self._mode = mode if mode in ("auto", "light", "dark") else "auto"
        self._scheme = "light"
        self._hook_system_signal()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def scheme(self) -> str:
        return self._scheme

    def set_mode(self, mode: str):
        if mode not in ("auto", "light", "dark") or mode == self._mode:
            return
        self._mode = mode
        self._settings.setValue("theme/mode", mode)
        self.apply()

    def _hook_system_signal(self):
        # Disponible desde Qt 6.5; si no existe, simplemente no hay
        # auto-refresco en vivo del tema del sistema.
        try:
            QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)
        except (AttributeError, RuntimeError):
            pass

    def _on_system_scheme_changed(self, *_args):
        if self._mode == "auto":
            self.apply()

    def _detect_system_scheme(self) -> str:
        try:
            from PySide6.QtCore import Qt as _Qt
            scheme = QGuiApplication.styleHints().colorScheme()
            if scheme == _Qt.ColorScheme.Dark:
                return "dark"
            if scheme == _Qt.ColorScheme.Light:
                return "light"
        except (AttributeError, RuntimeError):
            pass
        # Alternativa para versiones de Qt sin QStyleHints.colorScheme():
        # se estima a partir de la luminosidad del color de ventana del SO.
        window_color = self.app.palette().color(QPalette.Window)
        luminance = 0.299 * window_color.red() + 0.587 * window_color.green() + 0.114 * window_color.blue()
        return "dark" if luminance < 128 else "light"

    def apply(self):
        global _current_colors, _current_scheme
        self._scheme = self._mode if self._mode in ("light", "dark") else self._detect_system_scheme()
        palette = PALETTES[self._scheme]
        _current_colors = palette
        _current_scheme = self._scheme

        self.app.setStyleSheet(build_stylesheet(palette))
        font = self.app.font()
        font.setFamily("Segoe UI")
        font.setPointSize(10)
        self.app.setFont(font)

        signals.changed.emit(self._scheme)
        self.themeChanged.emit(self._scheme)


def apply_theme(app) -> ThemeController:
    controller = ThemeController(app)
    controller.apply()
    return controller