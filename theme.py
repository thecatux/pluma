"""Tema visual centralizado de Pluma.

Un único lugar para colores, tipografía, espaciados y la hoja de
estilos (QSS) de toda la aplicación. Los paneles y diálogos no
definen sus propios colores sueltos: usan estas constantes/roles o
consultan `theme.colors()` para lo poco que necesita seguir el
esquema de color activo.

Estilo "cristal": fondos en degradado suave con paneles translúcidos
(rgba) y bordes finos. Qt Style Sheets no puede desenfocar lo que hay
detrás de un widget, así que el efecto se consigue con transparencias y
degradados, no con un blur real.

Pluma admite modo claro y modo oscuro. Por defecto sigue el tema del
sistema operativo ("automático"); el usuario puede forzar uno de los
dos desde el menú "Ver" de la ventana principal. La preferencia se
guarda con QSettings y se restaura al reabrir la aplicación.
"""

from PySide6.QtCore import QObject, Signal, QSettings
from PySide6.QtGui import QColor, QGuiApplication, QPalette

FONT_FAMILY = '"Segoe UI", "SF Pro Text", "Inter", "Helvetica Neue", Arial, sans-serif'
FONT_FAMILY_SERIF = '"Georgia", "Iowan Old Style", "Palatino Linotype", serif'

RADIUS = {"sm": 6, "md": 8, "lg": 12, "xl": 16}

# Paleta clara "cristal": fondo neutro de papel, superficies blancas
# translúcidas y un acento verde petróleo sobrio, de inspiración editorial.
#
# IMPORTANTE: las claves "clásicas" (bg, surface, border, primary...)
# siguen siendo colores hexadecimales planos, porque otros módulos
# (p. ej. el lienzo de la línea temporal) las pasan a QColor. Las claves
# de cristal (bg_gradient, glass*, sidebar_glass...) contienen rgba() y
# degradados de QSS: solo se usan dentro de `build_stylesheet`.
_LIGHT = {
    "bg": "#F0F3F0",
    "surface": "#FFFFFF",
    "surface_alt": "#F6F8F6",
    "border": "#E0E6E1",
    "border_strong": "#C8D2CB",
    "text": "#202722",
    "text_secondary": "#58645C",
    "text_muted": "#7C887F",
    "primary": "#36776A",
    "primary_hover": "#2E695D",
    "primary_pressed": "#275A50",
    "primary_light": "#E3EFEB",
    "primary_border": "#BFD8D0",
    # Texto/iconos sobre `primary_light` (selecciones, chips activos) y
    # sobre `primary` (botones principales). Separados de
    # `primary_pressed` porque en el tema oscuro el texto sobre un fondo
    # tintado necesita ser claro y el fondo pulsado de un botón, no.
    "primary_text": "#285D52",
    "on_primary": "#FFFFFF",
    "danger": "#C92F2F",
    "danger_hover": "#B02525",
    "danger_light": "#FDEDED",
    "success": "#2B8A3E",
    # Barra lateral (valores planos de reserva; el aspecto real lo da
    # `sidebar_glass`). En claro ya NO es oscura: es un cristal esmerilado.
    "sidebar_bg": "#F1F4F1",
    "sidebar_bg_hover": "#E8EDE9",
    "sidebar_bg_selected": "#FFFFFF",
    "sidebar_text": "#4D5A52",
    "sidebar_text_muted": "#758178",
    "sidebar_text_selected": "#285D52",
    "sidebar_title": "#202722",
    # --- Efecto cristal (solo QSS) ---
    "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                   "stop:0 #E9F0EB, stop:0.55 #F1F4F0, stop:1 #F5F3EE)",
    "glass": "rgba(255, 255, 255, 62%)",
    "glass_hover": "rgba(255, 255, 255, 88%)",
    "glass_subtle": "rgba(255, 255, 255, 42%)",
    "glass_border": "rgba(92, 117, 101, 22%)",
    "bar_glass": "rgba(255, 255, 255, 68%)",
    "sidebar_glass": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                     "stop:0 rgba(255, 255, 255, 86%), stop:1 rgba(255, 255, 255, 58%))",
    "sidebar_edge": "rgba(77, 105, 87, 30%)",
    "sidebar_item_hover": "rgba(255, 255, 255, 60%)",
    "sidebar_item_selected": "rgba(255, 255, 255, 92%)",
    "sidebar_item_selected_border": "rgba(54, 119, 106, 30%)",
    # Tarjetas y botones de cristal: degradado vertical + luz en el borde
    # superior (`rim_top`). Los reflejos curvos los pinta `glass.py`.
    "card_glass": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                  "stop:0 rgba(255, 255, 255, 74%), stop:1 rgba(255, 255, 255, 44%))",
    "button_glass": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                    "stop:0 rgba(255, 255, 255, 96%), stop:1 rgba(255, 255, 255, 66%))",
    "button_glass_hover": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                          "stop:0 rgba(255, 255, 255, 100%), stop:1 rgba(255, 255, 255, 84%))",
    "rim_top": "rgba(255, 255, 255, 95%)",
}

# Paleta oscura: grafito suave, superficies de cristal ahumado y el
# mismo acento verde petróleo aclarado para conservar el contraste.
_DARK = {
    "bg": "#171B19",
    "surface": "#202622",
    "surface_alt": "#282F2B",
    "border": "#343D37",
    "border_strong": "#465249",
    "text": "#E8ECE9",
    "text_secondary": "#ADB8B0",
    "text_muted": "#818E85",
    "primary": "#58A08E",
    "primary_hover": "#69AF9D",
    "primary_pressed": "#498F7D",
    "primary_light": "#263B35",
    "primary_border": "#3B6559",
    "primary_text": "#B1DBCE",
    "on_primary": "#FFFFFF",
    "danger": "#FF7070",
    "danger_hover": "#FF8A8A",
    "danger_light": "#3B2229",
    "success": "#69DB7C",
    "sidebar_bg": "#191F1B",
    "sidebar_bg_hover": "#232A25",
    "sidebar_bg_selected": "#263B35",
    "sidebar_text": "#BAC5BD",
    "sidebar_text_muted": "#818E85",
    "sidebar_text_selected": "#B1DBCE",
    "sidebar_title": "#EEF2EF",
    # --- Efecto cristal (solo QSS) ---
    "bg_gradient": "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                   "stop:0 #151B17, stop:1 #1A201D)",
    "glass": "rgba(255, 255, 255, 5%)",
    "glass_hover": "rgba(255, 255, 255, 9%)",
    "glass_subtle": "rgba(255, 255, 255, 3%)",
    "glass_border": "rgba(205, 224, 211, 11%)",
    "bar_glass": "rgba(255, 255, 255, 4%)",
    "sidebar_glass": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                     "stop:0 rgba(224, 239, 228, 8%), stop:1 rgba(224, 239, 228, 3%))",
    "sidebar_edge": "rgba(205, 224, 211, 12%)",
    "sidebar_item_hover": "rgba(255, 255, 255, 7%)",
    "sidebar_item_selected": "rgba(82, 155, 131, 20%)",
    "sidebar_item_selected_border": "rgba(113, 190, 166, 32%)",
    "card_glass": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                  "stop:0 rgba(255, 255, 255, 8%), stop:1 rgba(255, 255, 255, 3%))",
    "button_glass": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                    "stop:0 rgba(255, 255, 255, 13%), stop:1 rgba(255, 255, 255, 6%))",
    "button_glass_hover": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                          "stop:0 rgba(255, 255, 255, 20%), stop:1 rgba(255, 255, 255, 10%))",
    "rim_top": "rgba(255, 255, 255, 26%)",
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


def _blend_colors(foreground: QColor, background: QColor, ratio: float) -> QColor:
    return QColor(
        round(background.red() * (1 - ratio) + foreground.red() * ratio),
        round(background.green() * (1 - ratio) + foreground.green() * ratio),
        round(background.blue() * (1 - ratio) + foreground.blue() * ratio),
    )


def _contrast_ratio(first: QColor, second: QColor) -> float:
    def luminance(color: QColor) -> float:
        channels = [color.redF(), color.greenF(), color.blueF()]
        linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4
                  for value in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    values = sorted((luminance(first), luminance(second)))
    return (values[1] + 0.05) / (values[0] + 0.05)


def _palette_with_accent(palette: dict, accent_value: str, dark: bool) -> dict:
    accent = QColor(accent_value)
    result = dict(palette)
    surface = QColor(palette["surface"])
    text = QColor(palette["text"])
    light_text = QColor(palette["on_primary"])
    hover = accent.darker(108)
    pressed = accent.darker(118)
    tint_ratio = 0.22 if dark else 0.13
    border_ratio = 0.46 if dark else 0.34
    tint = _blend_colors(accent, surface, tint_ratio)
    border = _blend_colors(accent, surface, border_ratio)
    accent_text = accent.lighter(155) if dark else accent.darker(170)
    tint_text = max((text, accent_text), key=lambda color: _contrast_ratio(color, tint))
    button_text = max((light_text, text), key=lambda color: _contrast_ratio(color, accent))

    result.update({
        "primary": accent.name(),
        "primary_hover": hover.name(),
        "primary_pressed": pressed.name(),
        "primary_light": tint.name(),
        "primary_border": border.name(),
        "primary_text": tint_text.name(),
        "on_primary": button_text.name(),
        "sidebar_item_selected": f"rgba({accent.red()}, {accent.green()}, {accent.blue()}, "
                                  f"{22 if dark else 14}%)",
        "sidebar_item_selected_border": f"rgba({accent.red()}, {accent.green()}, "
                                         f"{accent.blue()}, 34%)",
    })
    return result


def build_stylesheet(palette: dict) -> str:
    c = palette
    return f"""
    * {{
        font-family: {FONT_FAMILY};
        outline: none;
    }}

    QMainWindow, QDialog {{
        background: {c['bg_gradient']};
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
        color: {c['sidebar_title']};
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
        background: {c['button_glass']};
        border: 1px solid {c['border_strong']};
        border-top-color: {c['rim_top']};
        border-radius: {RADIUS['md']}px;
        padding: 7px 14px;
        color: {c['text']};
        font-weight: 500;
    }}
    QPushButton:hover {{
        background: {c['button_glass_hover']};
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
        border-top-color: rgba(255, 255, 255, 55%);
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
        background: {c['glass_hover']};
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
        background: {c['glass']};
        border: 1px solid {c['glass_border']};
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
        background: {c['glass_hover']};
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

    /* Barra lateral: el cristal (sombra, relleno, reflejos y borde) lo
       pinta `glass.GlassPanel` y la pastilla del elemento activo,
       `glass.SidebarItemDelegate`; aquí todo es transparente. */
    QWidget#SidebarContainer {{
        background: transparent;
        border: none;
    }}
    QListWidget#Sidebar {{
        background: transparent;
        border: none;
        border-radius: 0;
        padding: 6px;
    }}
    QListWidget#Sidebar::item {{
        color: {c['sidebar_text']};
        padding: 10px 13px;
        margin: 2px 4px;
        border: 1px solid transparent;
        border-radius: {RADIUS['md']}px;
        background: transparent;
        font-weight: 500;
    }}
    QListWidget#Sidebar::item:hover {{
        background: transparent;
    }}
    QListWidget#Sidebar::item:selected {{
        background: transparent;
        color: {c['sidebar_text_selected']};
        font-weight: 600;
    }}

    /* -------------------------------------------------------------- */
    /* Contenedores                                                      */
    /* -------------------------------------------------------------- */
    QFrame[role="card"] {{
        background: {c['card_glass']};
        border: 1px solid {c['glass_border']};
        border-top-color: {c['rim_top']};
        border-radius: {RADIUS['lg']}px;
    }}
    QFrame[role="field-row"] {{
        background: {c['glass_subtle']};
        border: 1px solid {c['glass_border']};
        border-top-color: {c['rim_top']};
        border-radius: {RADIUS['md']}px;
    }}
    QFrame[role="divider"] {{
        background: {c['border']};
        max-height: 1px;
        border: none;
    }}
    QFrame[role="sidebar-header"] {{
        background: transparent;
        border: none;
    }}
    QFrame[role="toolbar-strip"] {{
        background: {c['glass_subtle']};
        border: 1px solid {c['glass_border']};
        border-top-color: {c['rim_top']};
        border-radius: {RADIUS['md']}px;
    }}
    QFrame[role="toolbar-strip"] QToolBar {{
        background: transparent;
        border: none;
    }}

    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}

    QGroupBox {{
        background: {c['glass']};
        border: 1px solid {c['glass_border']};
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
        background: {c['glass_border']};
        width: 1px;
    }}

    /* -------------------------------------------------------------- */
    /* Barras                                                            */
    /* -------------------------------------------------------------- */
    QToolBar {{
        background: {c['bar_glass']};
        border: none;
        border-bottom: 1px solid {c['glass_border']};
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
        background: {c['bar_glass']};
        border-bottom: 1px solid {c['glass_border']};
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
        background: {c['bar_glass']};
        border-top: 1px solid {c['glass_border']};
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
        saved_accent = QColor(self._settings.value("theme/accent_color", ""))
        self._accent_color = saved_accent.name() if saved_accent.isValid() else ""
        self._scheme = "light"
        self._hook_system_signal()

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def scheme(self) -> str:
        return self._scheme

    @property
    def accent_color(self) -> str:
        return self._accent_color or PALETTES[self._scheme]["primary"]

    @property
    def has_custom_accent(self) -> bool:
        return bool(self._accent_color)

    def set_mode(self, mode: str):
        if mode not in ("auto", "light", "dark") or mode == self._mode:
            return
        self._mode = mode
        self._settings.setValue("theme/mode", mode)
        self.apply()

    def set_accent_color(self, color: str | None):
        if color is None:
            if not self._accent_color:
                return
            self._accent_color = ""
            self._settings.remove("theme/accent_color")
        else:
            selected = QColor(color)
            if not selected.isValid() or selected.name() == self._accent_color:
                return
            self._accent_color = selected.name()
            self._settings.setValue("theme/accent_color", self._accent_color)
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
        if self._accent_color:
            palette = _palette_with_accent(palette, self._accent_color,
                                           dark=self._scheme == "dark")
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
    import glass  # import local: glass importa theme
    glass.install(app)
    controller = ThemeController(app)
    controller.apply()
    return controller