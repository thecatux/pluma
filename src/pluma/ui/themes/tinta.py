"""Tema "tinta": sobrio y editorial, azul tinta sobre papel frío.

Propuesta libre: un tema para quien escribe con la cabeza fría. Claro,
es un papel blanco azulado con tinta índigo; oscuro, una noche de tinta
china con el acento en un lavanda claro. Es el contrapunto de `marfil`
(cálido) y de `material`/`crystal` (verde petróleo): aquí domina el azul.

Rasgos propios:
* Esquinas contenidas (3-8 px) y botones casi rectos: aspecto de
  maquetación editorial, no de app "blanda".
* Superficies planas y opacas; el contorno hace el trabajo de la sombra.
* `paint_pill`: en la barra lateral, el elemento activo lleva un
  marcador vertical de acento a la izquierda (como un subrayado de
  editor) sobre un velo del color de acento.

Solo define `paint_pill`. Como la pastilla se pinta con QPainter, los
fondos QSS de la barra lateral (`sidebar_hover_bg` / `sidebar_selected_bg`)
deben ser transparentes, como en `crystal`.

Módulo de solo datos + pintura: no importa `theme`. Ver
`themes/__init__.py` para el contrato que debe cumplir cualquier tema.
"""

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter

LABEL = "Tinta"
FONT = "Inter"   # si no está instalada, Qt usa FONT_FALLBACK de `theme`
RADIUS = {"sm": 3, "md": 5, "lg": 8, "xl": 10,
          "button": 6, "field": 3, "chip": 6, "nav": 6}

PILL_RADIUS = 6.0
MARKER_WIDTH = 3.0

# Roles de cristal reinterpretados como superficies planas (alias "@clave").
# Los fondos de la barra lateral son transparentes porque los pinta
# `paint_pill` (ver más abajo).
_ROLES = {
    "primary_rim": "@primary",
    "glass": "@surface",
    "glass_subtle": "@surface_alt",
    "glass_border": "@border",
    "bar_glass": "@bg",
    "card_glass": "@surface",
    "button_glass": "@surface",
    "button_glass_hover": "@surface_alt",
    "rim_top": "@border",
    "sidebar_bg_hover": "@glass_hover",
    "sidebar_bg_selected": "@primary_light",
    "sidebar_text": "@text_secondary",
    "sidebar_text_muted": "@text_muted",
    "sidebar_text_selected": "@primary_text",
    "sidebar_title": "@text",
    "sidebar_glass": "@sidebar_bg",
    "sidebar_edge": "@border",
    "sidebar_item_hover": "@glass_hover",
    "sidebar_item_selected": "@primary_light",
    "sidebar_item_selected_border": "@primary_border",
    "sidebar_hover_bg": "transparent",
    "sidebar_selected_bg": "transparent",
}

LIGHT = {**_ROLES,
    "bg": "#F2F4F9", "surface": "#FFFFFF", "surface_alt": "#E8ECF4",
    "border": "#D5DBE8", "border_strong": "#7E879C", "glass_hover": "#DFE4EF",
    "text": "#141A2E", "text_secondary": "#444D66", "text_muted": "#656E87",
    "primary": "#3949AB", "primary_hover": "#2F3C91", "primary_pressed": "#26327A",
    "primary_light": "#E0E4F8", "primary_border": "#B3BCEA",
    "primary_text": "#1A2260", "on_primary": "#FFFFFF",
    "danger": "#C62828", "danger_hover": "#9F1F1F", "danger_light": "#FBE0E0",
    "success": "#2E7D4F",
    "sidebar_bg": "#EAEEF6",
    "button_rim_top": "@border_strong",   # borde superior de botones (opcional)
    "bg_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                   "stop:0 #F5F7FB, stop:1 #EEF1F8)",
}

DARK = {**_ROLES,
    "bg": "#0D1120", "surface": "#141A2E", "surface_alt": "#1D2540",
    "border": "#2C3558", "border_strong": "#7A84A6", "glass_hover": "#27304F",
    "text": "#E4E8F5", "text_secondary": "#B5BDD6", "text_muted": "#8089A8",
    "primary": "#9FB0FF", "primary_hover": "#B7C4FF", "primary_pressed": "#8799F0",
    "primary_light": "#273166", "primary_border": "#3F4D96",
    "primary_text": "#DCE2FF", "on_primary": "#0C1440",
    "danger": "#FFB3B3", "danger_hover": "#FFD0D0", "danger_light": "#4A2025",
    "success": "#86D9A4",
    "sidebar_bg": "#101528",
    "button_rim_top": "@border_strong",   # borde superior de botones (opcional)
    "bg_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                   "stop:0 #0F1424, stop:1 #0B0F1C)",
}


def paint_pill(p: QPainter, body: QRectF, selected: bool, c: dict, dark: bool):
    """Elemento activo: velo de acento + marcador vertical a la izquierda.
    Elemento bajo el cursor: solo un velo tenue, sin marcador."""
    radius = min(PILL_RADIUS, body.height() / 2)
    accent = QColor(c["primary"])
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)

    veil = QColor(accent)
    if selected:
        veil.setAlphaF(0.22 if dark else 0.13)
    else:
        veil.setAlphaF(0.09 if dark else 0.06)
    p.setBrush(veil)
    p.drawRoundedRect(body, radius, radius)

    if selected:
        marker_h = body.height() * 0.56
        marker = QRectF(body.left() + 2.0, body.center().y() - marker_h / 2,
                        MARKER_WIDTH, marker_h)
        p.setBrush(accent)
        p.drawRoundedRect(marker, MARKER_WIDTH / 2, MARKER_WIDTH / 2)
    p.restore()