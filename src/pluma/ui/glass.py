"""Efecto "cristal líquido" de Pluma.

Qt Style Sheets solo sabe pintar rectángulos con un degradado y un borde
plano, y no puede desenfocar lo que hay detrás. Para acercarse al
Liquid Glass de Apple este módulo pinta el cristal a mano con QPainter:

* `paint_backdrop`      Fondo con manchas de color difuminadas. Un cristal
                        sobre un fondo liso no se ve; necesita algo que
                        "refractar". Como las manchas ya son suaves, el
                        resultado se lee como cristal esmerilado sin
                        necesidad de un blur real.
* `paint_reflections`   Los reflejos falsos: brillo curvo superior,
                        franja diagonal, rebote de luz inferior y bisel
                        interior con luz arriba-izquierda y abajo-derecha.
* `GlassPanel`          Panel flotante con esquinas redondeadas, sombra
                        suave, relleno translúcido, reflejos y borde.
                        Se pinta una sola vez en una caché (QPixmap) que
                        solo se regenera si cambian tamaño o tema.
* `SidebarItemDelegate` Pastilla de cristal para el elemento seleccionado
                        / bajo el cursor de la barra lateral.
* `install(app)`        Añade reflejos a todos los QFrame con
                        property("role") == "card" (y similares) sin
                        tener que tocar los paneles: coloca un overlay
                        transparente al ratón encima de cada uno.

Todo lee los colores de `theme` (esquema activo y acento), así que sigue
el modo claro/oscuro y el color de acento elegido por el usuario.
"""

from PySide6.QtCore import Qt, QObject, QEvent, QRectF, QPointF, QSize
from PySide6.QtGui import (QPainter, QPainterPath, QColor, QLinearGradient,
                           QRadialGradient, QPixmap, QPen, QBrush)
from PySide6.QtWidgets import (QWidget, QFrame, QGroupBox, QStyle,
                               QStyledItemDelegate)

from pluma.ui import theme


# ---------------------------------------------------------------------- #
# Utilidades
# ---------------------------------------------------------------------- #
def _white(alpha: float) -> QColor:
    return QColor(255, 255, 255, max(0, min(255, round(alpha * 255))))


def _is_dark() -> bool:
    return theme.current_scheme() == "dark"


def _accent(alpha: float = 1.0) -> QColor:
    color = QColor(theme.colors()["primary"])
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    return color


def _rounded_path(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


# ---------------------------------------------------------------------- #
# Fondo
# ---------------------------------------------------------------------- #
def paint_backdrop(p: QPainter, rect):
    """Manchas de color grandes y difusas sobre el degradado del QSS.

    Se dibuja encima del fondo de `QMainWindow` (que ya es un degradado)
    y debajo de todos los widgets.
    """
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    w, h = rect.width(), rect.height()
    reach = max(w, h)

    if _is_dark():
        blobs = [
            (0.10, 0.12, 0.55, _accent(0.34)),
            (0.88, 0.20, 0.50, QColor(104, 92, 214, 62)),
            (0.62, 1.02, 0.60, QColor(36, 142, 160, 56)),
        ]
    else:
        blobs = [
            (0.08, 0.14, 0.55, _accent(0.40)),
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
def paint_reflections(p: QPainter, body: QRectF, radius: float,
                      strength: float = 1.0, bevel: float = 5.0):
    """Pinta los brillos de un cristal dentro de `body` (redondeado).

    `strength` escala todas las opacidades (1.0 = panel grande,
    ~0.5 = tarjetas pequeñas). `bevel` es el grosor del borde refractivo.
    """
    k = strength * (0.55 if _is_dark() else 1.0)
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
class GlassPanel(QWidget):
    """Panel de cristal flotante con sombra y esquinas redondeadas.

    El widget reserva `inset` píxeles alrededor para la sombra, así que el
    layout interior debe usar ese mismo margen (ver `inset`).
    """

    def __init__(self, parent=None, radius: float = 22.0, inset: int = 12):
        super().__init__(parent)
        self.radius = radius
        self.inset = inset
        self._cache = None
        self._cache_key = None
        theme.signals.changed.connect(self._invalidate)

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
        dark = _is_dark()
        body = self.body_rect()
        radius = self.radius

        # Sombra: capas concéntricas con caída cuadrática, recortadas para
        # que no oscurezcan el interior del cristal.
        steps = max(2, self.inset - 4)
        outside = QPainterPath()
        outside.addRect(QRectF(self.rect()))
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
        p.setBrush(_accent(0.05))
        p.drawRoundedRect(body, radius, radius)

        paint_reflections(p, body, radius, strength=1.0, bevel=5.0)

        # Filo exterior que separa el cristal del fondo.
        outline = QColor(255, 255, 255, 36) if dark else QColor(64, 96, 80, 70)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(outline, 1.0))
        p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        p.end()
        return pm

    def paintEvent(self, _event):
        dpr = self.devicePixelRatioF()
        key = (self.size(), dpr, theme.current_scheme(), theme.colors()["primary"])
        if key != self._cache_key or self._cache is None:
            self._cache = self._render(dpr)
            self._cache_key = key
        p = QPainter(self)
        p.drawPixmap(0, 0, self._cache)


# ---------------------------------------------------------------------- #
# Elementos de la barra lateral
# ---------------------------------------------------------------------- #
class SidebarItemDelegate(QStyledItemDelegate):
    """Dibuja una pastilla de cristal tras el elemento seleccionado o bajo
    el cursor, y deja que el estilo pinte icono y texto encima.

    El QSS de `QListWidget#Sidebar::item` debe tener fondo y borde
    transparentes (la pastilla la pone este delegado).
    """

    MARGIN_X = 4
    MARGIN_Y = 2
    RADIUS = 12.0

    def paint(self, painter, option, index):
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected or hover:
            self._paint_pill(painter, option.rect, selected)
        super().paint(painter, option, index)

    def _paint_pill(self, p: QPainter, cell, selected: bool):
        dark = _is_dark()
        body = QRectF(cell).adjusted(self.MARGIN_X, self.MARGIN_Y,
                                     -self.MARGIN_X, -self.MARGIN_Y)
        radius = min(self.RADIUS, body.height() / 2)
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
            p.setBrush(_accent(0.22 if dark else 0.12))
            p.drawRoundedRect(body, radius, radius)

        paint_reflections(p, body, radius, strength=0.85 if selected else 0.5,
                          bevel=3.0 if selected else 2.0)

        outline = _accent(0.55 if selected else 0.0)
        if not selected:
            outline = QColor(255, 255, 255, 40) if dark else QColor(64, 96, 80, 38)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(outline, 1.0))
        p.drawRoundedRect(body.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        p.restore()


# ---------------------------------------------------------------------- #
# Reflejos automáticos para tarjetas
# ---------------------------------------------------------------------- #
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
        p = QPainter(self)
        # El filo de 1 px y el recorte quedan alineados con el borde QSS.
        body = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        paint_reflections(p, body, self.radius, strength=self.strength, bevel=3.0)


# role / clase -> (clave de theme.RADIUS, intensidad)
_SHEEN_ROLES = {"card": ("lg", 0.55), "toolbar-strip": ("md", 0.40), "field-row": ("md", 0.35)}


class _SheenInstaller(QObject):
    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Show:
            spec = self._spec_for(obj)
            if spec is not None and not hasattr(obj, "_glass_sheen"):
                radius_key, strength = spec
                sheen = _Sheen(obj, theme.RADIUS[radius_key], strength)
                obj._glass_sheen = sheen
                sheen.show()
                sheen.raise_()
        elif et == QEvent.Resize:
            sheen = getattr(obj, "_glass_sheen", None)
            if sheen is not None:
                sheen.setGeometry(obj.rect())
                sheen.raise_()
        return False

    @staticmethod
    def _spec_for(obj):
        if isinstance(obj, QGroupBox):
            return ("md", 0.40)
        if isinstance(obj, QFrame):
            return _SHEEN_ROLES.get(obj.property("role"))
        return None


_installer = None


def install(app):
    """Activa los reflejos automáticos en tarjetas. Idempotente."""
    global _installer
    if _installer is None:
        _installer = _SheenInstaller(app)
        app.installEventFilter(_installer)