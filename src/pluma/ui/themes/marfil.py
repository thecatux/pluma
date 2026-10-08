"""Tema "marfil": papel marfil suave para escribir largas horas.

Pensado como una mesa de trabajo de escritor: fondo marfil cálido en vez
de blanco o gris, tinta marrón en lugar de negro puro y un acento bronce
(pan de oro envejecido). En oscuro se convierte en "sepia nocturna":
marrón tabaco muy oscuro con el acento dorado aclarado.

Es un tema plano (superficies opacas, contornos finos, esquinas
discretas) con solo dos ganchos de pintura, ambos muy sutiles:

* `paint_backdrop`  Un halo de luz cálida arriba y una viñeta suave en
                    los bordes, como una hoja bajo una lámpara.
* `paint_panel`     Panel "de papel": sombra corta y cálida, relleno
                    opaco, filo de luz interior y borde fino.

No define `paint_pill` ni `paint_sheen`: la barra lateral y las tarjetas
las resuelve el QSS con alias, igual que en `material`.

Módulo de solo datos + pintura: no importa `theme`. Ver
`themes/__init__.py` para el contrato que debe cumplir cualquier tema.
"""

from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (QBrush, QColor, QPainter, QPainterPath, QPen,
                           QRadialGradient)

LABEL = "Marfil"
FONT = "Segoe UI"
# Solo lo que difiere de `theme.BASE_RADIUS`: esquinas algo más suaves
# en botones y campos, sin llegar a la píldora de Material.
RADIUS = {"sm": 6, "md": 10, "lg": 14, "button": 10, "field": 8, "chip": 14, "nav": 10}

# Roles de cristal reinterpretados como superficies de papel (alias "@clave"):
# así el QSS compartido sirve y el acento del usuario se propaga (los
# alias se resuelven DESPUÉS de aplicar el acento).
_ROLES = {
    "primary_rim": "@primary",
    "glass": "@surface",
    "glass_subtle": "@surface_alt",
    "glass_border": "@border",
    "bar_glass": "@bg",
    "card_glass": "@surface",
    "button_glass": "@surface",
    "button_glass_hover": "@surface_alt",
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
    "sidebar_hover_bg": "@glass_hover",
    "sidebar_selected_bg": "@primary_light",
}

LIGHT = {**_ROLES,
    # Marfil suave: crema con un punto de amarillo, nada de blanco hueso frío.
    "bg": "#F7F2E6", "surface": "#FDFBF5", "surface_alt": "#EFE8D8",
    "border": "#E0D6C0", "border_strong": "#9A8F78", "glass_hover": "#E8DFCB",
    "text": "#2B2620", "text_secondary": "#5C5446", "text_muted": "#766D5B",
    "primary": "#8A5A1E", "primary_hover": "#744A15", "primary_pressed": "#5F3C10",
    "primary_light": "#F1E3C8", "primary_border": "#DDC391",
    "primary_text": "#4F3208", "on_primary": "#FFFFFF",
    "danger": "#B3261E", "danger_hover": "#8C1D18", "danger_light": "#F9DEDA",
    "success": "#3F7D3A",
    "sidebar_bg": "#F0E9D9",
    "button_rim_top": "@border_strong",   # borde superior de botones (opcional)
    "bg_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                   "stop:0 #F9F5EA, stop:1 #F3EDDD)",
    "rim_top": "#FFFEF9",   # filo de luz en el borde superior de botones y tarjetas
}

DARK = {**_ROLES,
    # Sepia nocturna: marrón tabaco, no gris azulado.
    "bg": "#1A1713", "surface": "#231F1A", "surface_alt": "#2E2923",
    "border": "#40392F", "border_strong": "#8A8070", "glass_hover": "#383228",
    "text": "#EAE3D4", "text_secondary": "#C4BBA8", "text_muted": "#968D7B",
    "primary": "#E0B56A", "primary_hover": "#EEC57D", "primary_pressed": "#CBA05A",
    "primary_light": "#43361E", "primary_border": "#6B5630",
    "primary_text": "#F2DDB2", "on_primary": "#2A1C04",
    "danger": "#FFB4A9", "danger_hover": "#FFD0C9", "danger_light": "#4A2420",
    "success": "#8FD18A",
    "sidebar_bg": "#1E1B16",
    "button_rim_top": "@border_strong",   # borde superior de botones (opcional)
    "bg_gradient": "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
                   "stop:0 #1C1915, stop:1 #171410)",
    "rim_top": "#4A4236",
}


def _rounded(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def _tone(r: int, g: int, b: int, alpha: float) -> QColor:
    color = QColor(r, g, b)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


# ---------------------------------------------------------------------- #
# Fondo
# ---------------------------------------------------------------------- #
def paint_backdrop(p: QPainter, rect, c: dict, dark: bool):
    """Halo cálido arriba y viñeta en los bordes, sobre el degradado del QSS."""
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    w, h = rect.width(), rect.height()
    reach = max(w, h)

    # Luz de lámpara: una mancha ancha que entra por arriba, centrada.
    lamp = _tone(255, 196, 110, 0.07) if dark else _tone(255, 250, 232, 0.70)
    glow = QRadialGradient(QPointF(rect.x() + w * 0.5, rect.y() - h * 0.08), reach * 0.85)
    glow.setColorAt(0.0, lamp)
    glow.setColorAt(1.0, _tone(lamp.red(), lamp.green(), lamp.blue(), 0.0))
    p.setBrush(QBrush(glow))
    p.drawRect(rect)

    # Viñeta: oscurece apenas las esquinas para centrar la vista en el texto.
    edge = _tone(0, 0, 0, 0.30) if dark else _tone(120, 86, 30, 0.10)
    vignette = QRadialGradient(QPointF(rect.x() + w * 0.5, rect.y() + h * 0.5), reach * 0.80)
    vignette.setColorAt(0.0, _tone(edge.red(), edge.green(), edge.blue(), 0.0))
    vignette.setColorAt(0.62, _tone(edge.red(), edge.green(), edge.blue(), 0.0))
    vignette.setColorAt(1.0, edge)
    p.setBrush(QBrush(vignette))
    p.drawRect(rect)
    p.restore()


# ---------------------------------------------------------------------- #
# Panel
# ---------------------------------------------------------------------- #
def paint_panel(p: QPainter, bounds: QRectF, body: QRectF, radius: float,
                c: dict, dark: bool):
    """Panel de papel. `bounds` es todo el widget y `body` la hoja; la
    diferencia es el margen reservado para la sombra."""
    p.setRenderHint(QPainter.Antialiasing)
    inset = round(body.left() - bounds.left())

    # Sombra corta y cálida: capas concéntricas con caída cúbica,
    # recortadas para no tocar el interior de la hoja. El pico es bajo
    # porque las capas se acumulan cerca del borde.
    steps = max(2, inset - 3)
    outside = QPainterPath()
    outside.addRect(bounds)
    outside = outside.subtracted(_rounded(body, radius))
    p.save()
    p.setClipPath(outside)
    p.setPen(Qt.NoPen)
    peak = 0.06 if dark else 0.020
    for i in range(steps - 1, -1, -1):
        falloff = (1 - i / steps) ** 3
        p.setBrush(_tone(0, 0, 0, peak * falloff) if dark
                   else _tone(92, 64, 20, peak * falloff))
        p.drawRoundedRect(body.adjusted(-i, -i, i, i).translated(0, 2),
                          radius + i, radius + i)
    p.restore()

    # Hoja opaca.
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(c["surface"]))
    p.drawRoundedRect(body, radius, radius)

    # Filo de luz interior (apenas visible en oscuro).
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(_tone(255, 255, 255, 0.05 if dark else 0.75), 1.0))
    p.drawRoundedRect(body.adjusted(1.5, 1.5, -1.5, -1.5),
                      max(0.0, radius - 1.5), max(0.0, radius - 1.5))

    # Borde fino.
    p.setPen(QPen(QColor(c["border"]), 1.0))
    p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)