"""Cimientos de los temas visuales de Pluma y puente con el resto de la app.

Aquí NO hay paletas: cada tema vive en su propio módulo de datos dentro
de `pluma.ui.themes` (ver su `__init__` para añadir uno). Este módulo
ofrece:

* el registro `THEMES` (construido y validado a partir de esos módulos),
* la plantilla QSS compartida (`build_stylesheet`), que solo consume
  los colores/radios/fuente del tema activo,
* el cálculo del color de acento y la resolución de alias,
* el `ThemeController` (tema, modo auto/claro/oscuro y acento,
  persistidos con QSettings; sigue el tema del sistema operativo),
* la API que usa el resto de la aplicación: `colors()`,
  `current_scheme()`, `current_theme()`, `RADIUS`, `signals` y
  `apply_theme(app)`,
* el puente de pintura: `Panel`, `SidebarItemDelegate` y
  `paint_backdrop`, que delegan en los ganchos opcionales del tema
  activo y, sin ellos, pintan plano (ver `pluma.ui.themes`).
"""

import logging
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QObject, QRectF, Qt, Signal, QSettings
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import QFrame, QGroupBox, QStyle, QStyledItemDelegate, QWidget

from pluma.ui.themes import MODULES

log = logging.getLogger(__name__)

FONT_FALLBACK = '"Segoe UI", "SF Pro Text", "Inter", "Helvetica Neue", Arial, sans-serif'
FONT_FAMILY = FONT_FALLBACK  # nombre histórico; la fuente real la define cada tema
FONT_FAMILY_SERIF = '"Georgia", "Iowan Old Style", "Palatino Linotype", serif'

# Radios por defecto; cada tema solo declara los que cambia.
BASE_RADIUS = {"sm": 6, "md": 8, "lg": 12, "xl": 16,
               "button": 8, "field": 6, "chip": 13, "nav": 8}

# Radios del tema activo. Es un dict compartido que `apply()` actualiza
# EN SITIO, así quien haga `theme.RADIUS[...]` (p. ej. los ganchos de pintura) siempre
# ve los valores vigentes.
RADIUS: dict = {}

DEFAULT_THEME = "material"   # nombre del módulo en `pluma.ui.themes`

MODE_LABELS = {
    "auto": "Automático (según el sistema)",
    "light": "Claro",
    "dark": "Oscuro",
}


# --------------------------------------------------------------------- #
# Registro de temas
# --------------------------------------------------------------------- #
@dataclass(frozen=True)
class Theme:
    label: str
    palettes: dict            # esquema ("light" | "dark") -> paleta
    radius: dict              # BASE_RADIUS + los cambios del tema
    font: str                 # familia principal (el resto, FONT_FALLBACK)
    module: object            # módulo del tema: de él salen los ganchos de pintura

    def resolve(self, scheme: str) -> tuple[str, dict]:
        """Devuelve (esquema, paleta); si el tema no tiene `scheme`, usa el que tenga."""
        if scheme not in self.palettes:
            scheme = next(iter(self.palettes))
        return scheme, self.palettes[scheme]


def _load_theme(module) -> Theme:
    palettes = {scheme: palette
                for scheme, palette in (("light", getattr(module, "LIGHT", None)),
                                        ("dark", getattr(module, "DARK", None)))
                if palette}
    if not palettes:
        raise ValueError("no define LIGHT ni DARK")
    return Theme(label=module.LABEL,
                 palettes=palettes,
                 radius={**BASE_RADIUS, **getattr(module, "RADIUS", {})},
                 font=getattr(module, "FONT", "Segoe UI"),
                 module=module)


def _build_registry() -> dict:
    """Carga los módulos de `themes` y descarta (con aviso) los inválidos.
    El contrato de claves lo fija la paleta clara del tema por defecto."""
    themes = {}
    for module in MODULES:
        name = module.__name__.rsplit(".", 1)[-1]
        try:
            themes[name] = _load_theme(module)
        except (AttributeError, ValueError) as error:
            log.warning("Tema '%s' omitido: %s", name, error)
    if DEFAULT_THEME not in themes:
        raise RuntimeError(f"El tema por defecto '{DEFAULT_THEME}' no está disponible")
    required = set(next(iter(themes[DEFAULT_THEME].palettes.values())))
    for name, theme in list(themes.items()):
        missing = {key for palette in theme.palettes.values() for key in required - set(palette)}
        if missing:
            log.warning("Tema '%s' omitido: faltan claves %s", name, sorted(missing))
            del themes[name]
    return themes


THEMES = _build_registry()


# --------------------------------------------------------------------- #
# Estado y API para el resto de la aplicación
# --------------------------------------------------------------------- #
class _ThemeSignals(QObject):
    """Punto de conexión global para que cualquier widget se entere de
    un cambio de tema/esquema/acento sin tener que recibir el
    controlador por constructor."""
    changed = Signal(str)  # esquema resuelto: "light" | "dark"


signals = _ThemeSignals()


def _resolve_aliases(palette: dict) -> dict:
    """Sustituye los valores "@clave" por el valor de esa clave (un nivel)."""
    return {k: palette[v[1:]] if isinstance(v, str) and v.startswith("@") else v
            for k, v in palette.items()}


# Estado inicial (antes del primer `apply()`): tema por defecto, esquema claro.
_current_theme = THEMES[DEFAULT_THEME]
_current_scheme = "light"
_current_colors = _resolve_aliases(_current_theme.resolve("light")[1])
RADIUS.update(_current_theme.radius)


def colors() -> dict:
    """Paleta de colores actualmente activa (tema + esquema + acento)."""
    return _current_colors


def current_scheme() -> str:
    """Esquema resuelto actualmente: 'light' o 'dark' (nunca 'auto')."""
    return _current_scheme


def current_theme() -> Theme:
    """Tema activo (para que otros módulos consulten `.label`, `.font`...)."""
    return _current_theme


# --------------------------------------------------------------------- #
# Puente de pintura
# --------------------------------------------------------------------- #
# Los widgets de esta sección sirven a TODOS los temas: preguntan al tema
# activo por su gancho de pintura (si lo tiene) y, si no, pintan plano.
# El código de pintura de un tema solo se ejecuta mientras ese tema está
# activo.
def _hook(name: str, default=None):
    return getattr(_current_theme.module, name, default)


def _is_dark() -> bool:
    return _current_scheme == "dark"


def _flat_panel(p, bounds, body, radius, c, dark):
    p.setBrush(QColor(c["surface"]))
    p.setPen(QPen(QColor(c["border"]), 1.0))
    p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


def paint_backdrop(p: QPainter, rect):
    """Fondo extra de la ventana principal (por defecto, ninguno: basta el QSS)."""
    paint = _hook("paint_backdrop")
    if paint is not None:
        paint(p, rect, _current_colors, _is_dark())


class Panel(QWidget):
    """Panel flotante con esquinas redondeadas.

    El widget reserva `inset` píxeles alrededor (sombra en los temas que
    la pintan), así que el layout interior debe usar ese mismo margen.
    Se pinta una sola vez en una caché (QPixmap) que solo se regenera si
    cambian tamaño, tema, esquema o acento.
    """

    def __init__(self, parent=None, radius: float = 22.0, inset: int = 12):
        super().__init__(parent)
        self.radius = radius
        self.inset = inset
        self._cache = None
        self._cache_key = None
        signals.changed.connect(self._invalidate)

    def _invalidate(self, *_args):
        self._cache_key = None
        self.update()

    def body_rect(self) -> QRectF:
        i = self.inset
        return QRectF(self.rect()).adjusted(i, i, -i, -i)

    def _render(self, dpr: float) -> QPixmap:
        size = self.size()
        pm = QPixmap(round(size.width() * dpr), round(size.height() * dpr))
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        _hook("paint_panel", _flat_panel)(p, QRectF(self.rect()), self.body_rect(),
                                          self.radius, _current_colors, _is_dark())
        p.end()
        return pm

    def paintEvent(self, _event):
        dpr = self.devicePixelRatioF()
        key = (self.size(), dpr, _current_scheme, _current_colors["primary"])
        if key != self._cache_key or self._cache is None:
            self._cache = self._render(dpr)
            self._cache_key = key
        QPainter(self).drawPixmap(0, 0, self._cache)


class SidebarItemDelegate(QStyledItemDelegate):
    """Pastilla tras el elemento seleccionado o bajo el cursor, si el tema
    activo la pinta (`paint_pill`); icono y texto los pinta el estilo
    encima. Sin gancho, el fondo del elemento lo pone el QSS."""

    MARGIN_X = 4
    MARGIN_Y = 2

    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        paint = _hook("paint_pill")
        if paint is not None and (selected or hover):
            body = QRectF(option.rect).adjusted(self.MARGIN_X, self.MARGIN_Y,
                                                -self.MARGIN_X, -self.MARGIN_Y)
            paint(painter, body, selected, _current_colors, _is_dark())
        super().paint(painter, option, index)


class _Sheen(QWidget):
    """Overlay transparente que pinta solo los reflejos sobre un widget."""

    def __init__(self, target: QWidget, radius: float, strength: float):
        super().__init__(target)
        self.radius = radius
        self.strength = strength
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setGeometry(target.rect())

    def paintEvent(self, _event):
        paint = _hook("paint_sheen")
        if paint is not None:
            # El filo de 1 px y el recorte quedan alineados con el borde QSS.
            body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
            paint(QPainter(self), body, self.radius, self.strength,
                  _current_colors, _is_dark())


class _Sheens(QObject):
    """Reflejos automáticos sobre tarjetas (sin tocarlas). Solo existen
    mientras el tema activo defina `paint_sheen`: con otro tema no hay
    filtro de eventos ni overlays."""

    def __init__(self):
        super().__init__()
        self._active = False

    def sync(self, app):
        """Ajusta el filtro y los overlays al tema activo (llamar tras cambiarlo)."""
        active = _hook("paint_sheen") is not None
        if active != self._active:
            (app.installEventFilter if active else app.removeEventFilter)(self)
            self._active = active
        for widget in app.allWidgets():
            old = getattr(widget, "_sheen", None)
            if old is not None:
                old.deleteLater()
                widget._sheen = None
            if active and widget.isVisible():
                self._attach(widget)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Show and getattr(obj, "_sheen", None) is None:
            self._attach(obj)
        elif kind == QEvent.Resize:
            sheen = getattr(obj, "_sheen", None)
            if sheen is not None:
                sheen.setGeometry(obj.rect())
                sheen.raise_()
        return False

    def _attach(self, obj):
        roles = _hook("SHEEN", {})
        if isinstance(obj, QGroupBox):
            spec = roles.get("groupbox")
        elif isinstance(obj, QFrame):
            spec = roles.get(obj.property("role"))
        else:
            spec = None
        if spec is not None:
            radius_key, strength = spec
            obj._sheen = _Sheen(obj, RADIUS[radius_key], strength)
            obj._sheen.show()
            obj._sheen.raise_()


_sheens = _Sheens()


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


def build_stylesheet(palette: dict, font: str = FONT_FAMILY) -> str:
    c = palette
    r = RADIUS
    return f"""
    * {{
        font-family: {font};
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
        border-radius: {r['button']}px;
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
        border-top-color: {c['primary_rim']};
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
        border-radius: {r['sm']}px;
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
        border-radius: {r['chip']}px;
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
        border-radius: {r['field']}px;
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
        border-radius: {r['sm']}px;
    }}

    /* -------------------------------------------------------------- */
    /* Listas                                                            */
    /* -------------------------------------------------------------- */
    QListWidget {{
        background: {c['glass']};
        border: 1px solid {c['glass_border']};
        border-radius: {r['md']}px;
        padding: 4px;
    }}
    QListWidget::item {{
        border-radius: {r['sm']}px;
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
       pinta `theme.Panel` y la pastilla del elemento activo,
       `theme.SidebarItemDelegate`; en temas de cristal aquí todo es
       transparente (`sidebar_*_bg`); en los planos, lo pinta el QSS. */
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
        border-radius: {r['nav']}px;
        background: transparent;
        font-weight: 500;
    }}
    QListWidget#Sidebar::item:hover {{
        background: {c['sidebar_hover_bg']};
    }}
    QListWidget#Sidebar::item:selected {{
        background: {c['sidebar_selected_bg']};
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
        border-radius: {r['lg']}px;
    }}
    QFrame[role="field-row"] {{
        background: {c['glass_subtle']};
        border: 1px solid {c['glass_border']};
        border-top-color: {c['rim_top']};
        border-radius: {r['md']}px;
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
        border-radius: {r['md']}px;
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
        border-radius: {r['md']}px;
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
        border-radius: {r['sm']}px;
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
        border-radius: {r['sm']}px;
    }}
    QMenuBar::item:selected {{
        background: {c['surface_alt']};
    }}
    QMenu {{
        background: {c['surface']};
        border: 1px solid {c['border']};
        border-radius: {r['md']}px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 7px 24px 7px 12px;
        border-radius: {r['sm']}px;
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
    """Gestiona tema, modo (auto/claro/oscuro) y acento; los persiste con
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
        name = self._settings.value("theme/name", DEFAULT_THEME)
        self._theme_name = name if name in THEMES else DEFAULT_THEME
        mode = self._settings.value("theme/mode", "auto")
        self._mode = mode if mode in MODE_LABELS else "auto"
        saved_accent = QColor(self._settings.value("theme/accent_color", ""))
        self._accent_color = saved_accent.name() if saved_accent.isValid() else ""
        self._scheme = "light"
        self._hook_system_signal()

    @property
    def theme_name(self) -> str:
        return self._theme_name

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def scheme(self) -> str:
        return self._scheme

    @property
    def accent_color(self) -> str:
        return self._accent_color or THEMES[self._theme_name].resolve(self._scheme)[1]["primary"]

    @property
    def has_custom_accent(self) -> bool:
        return bool(self._accent_color)

    def _set(self, attr: str, key: str, value):
        """Guarda un ajuste y reaplica el tema (sin hacer nada si no cambia)."""
        if getattr(self, attr) == value:
            return
        setattr(self, attr, value)
        self._settings.setValue(key, value)
        self.apply()

    def set_theme(self, name: str):
        if name in THEMES:
            self._set("_theme_name", "theme/name", name)

    def set_mode(self, mode: str):
        if mode in MODE_LABELS:
            self._set("_mode", "theme/mode", mode)

    def set_accent_color(self, color: str | None):
        if color is None:
            if self._accent_color:
                self._accent_color = ""
                self._settings.remove("theme/accent_color")
                self.apply()
            return
        selected = QColor(color)
        if selected.isValid():
            self._set("_accent_color", "theme/accent_color", selected.name())

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
        global _current_theme, _current_colors, _current_scheme
        theme = THEMES[self._theme_name]
        wanted = self._mode if self._mode != "auto" else self._detect_system_scheme()
        self._scheme, palette = theme.resolve(wanted)
        if self._accent_color:
            palette = _palette_with_accent(palette, self._accent_color,
                                           dark=self._scheme == "dark")
        palette = _resolve_aliases(palette)
        _current_theme, _current_colors, _current_scheme = theme, palette, self._scheme
        RADIUS.clear()
        RADIUS.update(theme.radius)

        _sheens.sync(self.app)  # reflejos de tarjetas solo si el tema los define
        self.app.setStyleSheet(build_stylesheet(palette, f'"{theme.font}", {FONT_FALLBACK}'))
        font = self.app.font()
        font.setFamily(theme.font)
        font.setPointSize(10)
        self.app.setFont(font)

        signals.changed.emit(self._scheme)
        self.themeChanged.emit(self._scheme)


def apply_theme(app) -> ThemeController:
    controller = ThemeController(app)
    controller.apply()
    return controller