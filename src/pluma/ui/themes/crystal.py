"""Tema "crystal" (cristal): el estilo original de Pluma, en un solo módulo.

Degradados suaves, paneles translúcidos (rgba), bordes finos y un efecto
de "cristal líquido". Qt Style Sheets solo sabe pintar rectángulos con un
degradado y un borde plano, y no puede desenfocar lo que hay detrás; por
eso, además de las paletas, este tema aporta los ganchos de pintura con
QPainter que `theme` usa SOLO cuando este tema está activo:

* `paint_backdrop`  Manchas de color difuminadas tras toda la interfaz.
                    Un cristal sobre un fondo liso no se ve; necesita
                    algo que "refractar".
* `paint_panel`     Panel flotante: sombra suave, relleno translúcido,
                    reflejos y borde (la caché la gestiona `theme.Panel`).
* `paint_pill`      Pastilla de la barra lateral (elemento activo/hover).
* `paint_sheen` +   Reflejos sobre tarjetas, barras de herramientas y
  `SHEEN`           grupos, sin tocar esos widgets.

No importa `theme`: recibe los colores (`c`) y el esquema (`dark`) como
argumentos, así que sigue el modo claro/oscuro y el acento del usuario.
Ver `themes/__init__.py` para el contrato de un tema.
"""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QPainter, QPainterPath, QColor, QLinearGradient,
                           QRadialGradient, QPen, QBrush)

LABEL = "Cristal"
FONT = "Segoe UI"
# RADIUS: sin cambios, usa los valores base de `theme.BASE_RADIUS`.

# Rol / clase de widget -> (clave de RADIUS, intensidad del reflejo)
SHEEN = {"card": ("lg", 0.55), "toolbar-strip": ("md", 0.40),
         "field-row": ("md", 0.35), "groupbox": ("md", 0.40)}

PILL_RADIUS = 12.0

# Claves que solo existen para el efecto cristal / la barra lateral con
# pastilla pintada por `paint_pill` (vía `theme.SidebarItemDelegate`); comunes a claro y oscuro.
_EXTRA = {
    "primary_rim": "rgba(255, 255, 255, 55%)",  # luz en el borde del botón principal
    "sidebar_hover_bg": "transparent",
    "sidebar_selected_bg": "transparent",
}

# Paleta clara: fondo neutro de papel, superficies blancas translúcidas y
# un acento verde petróleo sobrio, de inspiración editorial.
LIGHT = {**_EXTRA,
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
    # superior (`rim_top`). Los reflejos curvos los pintan los ganchos de este módulo.
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
DARK = {**_EXTRA,
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


# ---------------------------------------------------------------------- #
# Utilidades
# ---------------------------------------------------------------------- #
def _white(alpha: float) -> QColor:
    """Devuelve un blanco puro con la opacidad indicada (0.0–1.0 → 0–255)."""
    return QColor(255, 255, 255, max(0, min(255, round(alpha * 255))))


def _accent(c: dict, alpha: float = 1.0) -> QColor:
    """Devuelve el color de acento de la paleta con la opacidad indicada."""
    color = QColor(c["primary"])
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


def _rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    """Crea un QPainterPath de rectángulo redondeado listo para recortar o trazar."""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


# ---------------------------------------------------------------------- #
# Fondo
# ---------------------------------------------------------------------- #
def paint_backdrop(p: QPainter, rect, c: dict, dark: bool):
    """Manchas de color grandes y difusas sobre el degradado del QSS.

    Se dibuja encima del fondo de `QMainWindow` (que ya es un degradado)
    y debajo de todos los widgets. Como las manchas ya son suaves, el
    resultado se lee como cristal esmerilado sin necesidad de un blur real.
    """
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    w, h = rect.width(), rect.height()
    reach = max(w, h)

    if dark:
        blobs = [
            (0.10, 0.12, 0.55, _accent(c, 0.34)),
            (0.88, 0.20, 0.50, QColor(104, 92, 214, 62)),
            (0.62, 1.02, 0.60, QColor(36, 142, 160, 56)),
        ]
    else:
        blobs = [
            (0.08, 0.14, 0.55, _accent(c, 0.40)),
            (0.90, 0.10, 0.50, QColor(245, 184, 132, 92)),
            (0.58, 1.05, 0.62, QColor(124, 170, 232, 84)),
        ]

    for fx, fy, fr, color in blobs:
        center = QPointF(rect.x() + fx * w, rect.y() + fy * h)
        gradient = QRadialGradient(center, fr * reach)
        faded = QColor(color)
        faded.setAlphaF(0.0)
        mid = QColor(color)
        mid.setAlphaF(color.alphaF() * 0.38)
        gradient.setColorAt(0.0, color)
        gradient.setColorAt(0.55, mid)
        gradient.setColorAt(1.0, faded)
        p.setBrush(QBrush(gradient))
        p.drawRect(rect)
    p.restore()


# ---------------------------------------------------------------------- #
# Reflejos
# ---------------------------------------------------------------------- #
def _reflections(p: QPainter, body: QRectF, radius: float, dark: bool,
                 strength: float = 1.0, bevel: float = 5.0):
    """Pinta los brillos de un cristal dentro de `body` (redondeado).

    `strength` escala todas las opacidades (1.0 = panel grande,
    ~0.5 = tarjetas pequeñas). `bevel` es el grosor del borde refractivo.
    """
    k = strength * (0.55 if dark else 1.0)
    left, top = body.left(), body.top()
    w, h = body.width(), body.height()
    if w < 8 or h < 8:
        return

    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    path = _rounded_path(body, radius)
    p.setClipPath(path)
    p.setPen(Qt.NoPen)

    # 1) Brillo curvo superior: el reflejo de una fuente de luz sobre una
    #    superficie abombada. Una elipse más ancha que el panel cuyo borde
    #    inferior forma la curva característica.
    gloss_h = min(h * 0.46, 150.0)
    cap = QPainterPath()
    cap.addEllipse(QRectF(left - w * 0.35, top - gloss_h, w * 1.7, gloss_h * 2.0))
    gloss = QLinearGradient(0, top, 0, top + gloss_h)
    gloss.setColorAt(0.0, _white(0.46 * k))
    gloss.setColorAt(0.55, _white(0.12 * k))
    gloss.setColorAt(1.0, _white(0.02 * k))
    p.setBrush(QBrush(gloss))
    p.drawPath(cap)

    # 2) Franja diagonal: dos bandas suaves, una ancha y otra fina, como
    #    la luz que cruza el cristal en ángulo.
    axis_end = QPointF(left + w, top + min(h, w * 1.2))
    streak = QLinearGradient(QPointF(left, top), axis_end)
    streak.setColorAt(0.00, _white(0.0))
    streak.setColorAt(0.36, _white(0.0))
    streak.setColorAt(0.45, _white(0.11 * k))
    streak.setColorAt(0.53, _white(0.0))
    streak.setColorAt(0.58, _white(0.06 * k))
    streak.setColorAt(0.62, _white(0.0))
    streak.setColorAt(1.00, _white(0.0))
    p.setBrush(QBrush(streak))
    p.drawRect(body)

    # 3) Rebote de luz en la parte baja (el cristal recoge luz del fondo).
    glow_h = min(h * 0.28, 70.0)
    glow = QLinearGradient(0, top + h - glow_h, 0, top + h)
    glow.setColorAt(0.0, _white(0.0))
    glow.setColorAt(1.0, _white(0.13 * k))
    p.setBrush(QBrush(glow))
    p.drawRect(QRectF(left, top + h - glow_h, w, glow_h))

    # 4) Bisel interior: trazo grueso centrado en el borde; al estar
    #    recortado solo se ve su mitad interior. Luz arriba-izquierda y
    #    abajo-derecha, oscuro (transparente) en el medio.
    edge = QLinearGradient(QPointF(left, top), QPointF(left + w, top + h))
    edge.setColorAt(0.00, _white(0.60 * k))
    edge.setColorAt(0.25, _white(0.12 * k))
    edge.setColorAt(0.50, _white(0.0))
    edge.setColorAt(0.75, _white(0.10 * k))
    edge.setColorAt(1.00, _white(0.38 * k))
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(QBrush(edge), bevel * 2))
    p.drawPath(path)

    # 5) Filo de luz de 1 px justo dentro del borde.
    p.setClipping(False)
    rim = QLinearGradient(QPointF(left, top), QPointF(left + w, top + h))
    rim.setColorAt(0.00, _white(0.95 * k))
    rim.setColorAt(0.40, _white(0.20 * k))
    rim.setColorAt(0.70, _white(0.14 * k))
    rim.setColorAt(1.00, _white(0.60 * k))
    inner = body.adjusted(1.0, 1.0, -1.0, -1.0)
    p.setPen(QPen(QBrush(rim), 1.0))
    p.drawPath(_rounded_path(inner, max(0.0, radius - 1.0)))
    p.restore()


# ---------------------------------------------------------------------- #
# Panel flotante
# ---------------------------------------------------------------------- #
def paint_panel(p: QPainter, bounds: QRectF, body: QRectF, radius: float,
                c: dict, dark: bool):
    """Pinta el panel en `p` (ya con antialiasing). `bounds` es todo el
    widget y `body` el cristal; la diferencia entre ambos es el margen
    reservado para la sombra."""
    inset = round(body.left() - bounds.left())

    # Sombra: capas concéntricas con caída cuadrática, recortadas para
    # que no oscurezcan el interior del cristal.
    steps = max(2, inset - 4)
    outside = QPainterPath()
    outside.addRect(bounds)
    outside = outside.subtracted(_rounded_path(body, radius))
    p.save()
    p.setClipPath(outside)
    p.setPen(Qt.NoPen)
    base = 0.11 if dark else 0.040
    for i in range(steps - 1, -1, -1):
        alpha = base * (1 - i / steps) ** 2
        p.setBrush(QColor(0, 0, 0, round(alpha * 255)))
        r = body.adjusted(-i, -i, i, i).translated(0, 3)
        p.drawRoundedRect(r, radius + i, radius + i)
    p.restore()

    # Relleno translúcido + un velo del color de acento.
    fill = QLinearGradient(0, body.top(), 0, body.bottom())
    if dark:
        fill.setColorAt(0.0, _white(0.10))
        fill.setColorAt(1.0, _white(0.035))
    else:
        fill.setColorAt(0.0, _white(0.66))
        fill.setColorAt(1.0, _white(0.34))
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(fill))
    p.drawRoundedRect(body, radius, radius)
    p.setBrush(_accent(c, 0.05))
    p.drawRoundedRect(body, radius, radius)

    _reflections(p, body, radius, dark, strength=1.0, bevel=5.0)

    # Filo exterior que separa el cristal del fondo.
    outline = QColor(255, 255, 255, 36) if dark else QColor(64, 96, 80, 70)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(outline, 1.0))
    p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


# ---------------------------------------------------------------------- #
# Barra lateral y tarjetas
# ---------------------------------------------------------------------- #
def paint_pill(p: QPainter, body: QRectF, selected: bool, c: dict, dark: bool):
    """Pastilla de cristal tras el elemento seleccionado o bajo el cursor.
    El QSS de la barra lateral debe dejar fondo y borde transparentes
    (`sidebar_hover_bg` / `sidebar_selected_bg` de este tema)."""
    radius = min(PILL_RADIUS, body.height() / 2)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)

    if selected:
        # Sombra corta bajo la pastilla.
        for i, a in ((3, 0.020), (2, 0.030), (1, 0.040)):
            p.setBrush(QColor(0, 0, 0, round(a * 255 * (2.2 if dark else 1.0))))
            p.drawRoundedRect(body.adjusted(-i * 0.4, 0, i * 0.4, i).translated(0, 1),
                              radius + i * 0.4, radius + i * 0.4)

    fill = QLinearGradient(0, body.top(), 0, body.bottom())
    if selected:
        top_a, bot_a = (0.20, 0.08) if dark else (0.96, 0.62)
    else:
        top_a, bot_a = (0.09, 0.04) if dark else (0.62, 0.32)
    fill.setColorAt(0.0, _white(top_a))
    fill.setColorAt(1.0, _white(bot_a))
    p.setBrush(QBrush(fill))
    p.drawRoundedRect(body, radius, radius)
    if selected:
        p.setBrush(_accent(c, 0.22 if dark else 0.12))
        p.drawRoundedRect(body, radius, radius)

    _reflections(p, body, radius, dark, strength=0.85 if selected else 0.5,
                 bevel=3.0 if selected else 2.0)

    outline = _accent(c, 0.55 if selected else 0.0)
    if not selected:
        outline = QColor(255, 255, 255, 40) if dark else QColor(64, 96, 80, 38)
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(outline, 1.0))
    p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.restore()


def paint_sheen(p: QPainter, body: QRectF, radius: float, strength: float,
                c: dict, dark: bool):
    """Reflejos sobre un widget existente (ver `SHEEN`)."""
    _reflections(p, body, radius, dark, strength=strength, bevel=3.0)