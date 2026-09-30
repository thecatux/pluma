"""Lienzo de la sección "Línea temporal".

Es un lienzo de verdad (QGraphicsView): se desplaza arrastrando el
fondo, se hace zoom con Ctrl+rueda y se puede ajustar la vista al
contenido. Los eventos cuelgan de una línea continua con un nodo por
evento y hay dos disposiciones:

- "Línea": un único eje; las tarjetas se alternan arriba y abajo.
- "Carriles": un carril por grupo; arrastrar un evento a otro carril
  le cambia el grupo.

Contenido del módulo (de abajo a arriba):
- Helpers de color/texto y paleta derivada del tema.
- `EventItem`, `TrackItem`, `GapHandle`: elementos gráficos del lienzo.
- `TimelineInspector`: panel lateral para editar el evento seleccionado.
- `TimelineView`: vista con zoom, desplazamiento y atajos.
- `TimelineCanvas`: barra superior + vista + inspector; es lo que usa
  `OutlinePanel`.

Igual que el resto de Pluma, este widget no toca SQLite: emite señales
de alto nivel para que `OutlinePanel` las traduzca a operaciones de
`Database`. El lienzo mantiene su propia copia en memoria de los
bloques (`self._blocks`) para repintar al instante sin releer la base.
"""

from functools import lru_cache

from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                                QPlainTextEdit, QComboBox, QPushButton, QCheckBox, QColorDialog,
                                QGraphicsView, QGraphicsScene, QGraphicsLineItem,
                                QGraphicsSimpleTextItem, QGraphicsObject, QGraphicsItem,
                                QApplication, QScrollArea, QMenu, QFileDialog, QMessageBox)
from PySide6.QtCore import (Qt, QTimer, Signal, QSize, QPointF, QPoint, QRectF,
                             QPropertyAnimation, QEasingCurve)
from PySide6.QtGui import (QPainter, QPainterPath, QPen, QColor, QIcon, QPixmap, QImage, QPolygonF,
                            QFont, QFontMetricsF, QPalette, QTextLayout, QTextOption)

import icons
import theme
from app_settings import settings, signals as settings_signals



# ====================================================================== #
# Colores, texto y elementos gráficos del lienzo
# ====================================================================== #

GROUP_COLORS = ["#4C6EF5", "#F76707", "#2F9E44", "#E03131", "#AE3EC9", "#0CA678", "#F59F00", "#1971C2"]
NO_GROUP_COLOR = "#ADB5BD"
NO_GROUP_LABEL = "Sin grupo"


def color_for_group(group_name: str) -> str:
    if not group_name:
        return NO_GROUP_COLOR
    return GROUP_COLORS[sum(ord(ch) for ch in group_name) % len(GROUP_COLORS)]


def block_color(block: dict) -> str:
    """Color manual del bloque si lo tiene; si no, el de su grupo."""
    return (block.get("color") or "").strip() or color_for_group((block.get("group_name") or "").strip())


# ---------------------------------------------------------------------- #
# Paleta derivada del tema (con caché que se invalida al cambiar de tema)
# ---------------------------------------------------------------------- #
_PAL = None


def _reset_palette(*_args):
    global _PAL
    _PAL = None


theme.signals.changed.connect(_reset_palette)


def palette_colors() -> dict:
    global _PAL
    if _PAL is None:
        c = theme.colors()
        app_pal = QApplication.palette()

        def pick(key, role):
            value = c.get(key)
            return QColor(value) if value else app_pal.color(role)

        _PAL = {
            "background": pick("bg", QPalette.Window),
            "surface": pick("surface", QPalette.Base),
            "surface_alt": pick("surface_alt", QPalette.AlternateBase),
            "border": pick("border", QPalette.Mid),
            "border_strong": pick("border_strong", QPalette.Mid),
            "text": pick("text", QPalette.Text),
            "text_secondary": pick("text_secondary", QPalette.Text),
            "text_muted": pick("text_muted", QPalette.PlaceholderText),
            "accent": pick("primary", QPalette.Highlight),
        }
    return _PAL


def _with_alpha(color: QColor, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c


@lru_cache(maxsize=64)
def _icon_pixmap(name: str, color_hex: str, size: int):
    return icons.pixmap(name, color_hex, size)


def wrap_text(text: str, font: QFont, width: float, max_lines: int) -> list[str]:
    """Parte `text` en líneas de ancho <= `width` y, si se pasa de
    `max_lines`, elide con "…" la última."""
    text = " ".join((text or "").split())
    if not text:
        return []
    layout = QTextLayout(text, font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    spans = []
    layout.beginLayout()
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(width)
        spans.append((line.textStart(), line.textLength()))
    layout.endLayout()
    lines = [text[s:s + n].strip() for s, n in spans]
    if len(lines) > max_lines:
        rest = " ".join(text[spans[max_lines - 1][0]:].split())
        lines = lines[:max_lines - 1] + [QFontMetricsF(font).elidedText(rest, Qt.ElideRight, width)]
    return lines


# ---------------------------------------------------------------------- #
# Evento
# ---------------------------------------------------------------------- #
class EventItem(QGraphicsObject):
    dragging = Signal(object)          # mientras se arrastra
    dragFinished = Signal(object)      # al soltar tras un arrastre real
    activated = Signal(object)         # doble clic
    contextRequested = Signal(object, object)  # (item, QPoint global)

    CARD_W = 210
    PAD = 10
    ACCENT_W = 5
    NODE_R = 7
    MILESTONE_R = 10
    FOOTER_H = 18
    AXIS_DATE_W = 140

    exporting = False  # True mientras se exporta a imagen (sin selección)

    def __init__(self, block: dict, chapter_title: str = ""):
        super().__init__()
        self.block = block
        self.chapter_title = chapter_title
        self.side = 1            # +1 tarjeta debajo, -1 encima
        self.stem = 44
        self.axis_date = False   # fecha junto al nodo, en vez de dentro de la tarjeta
        self.free_y = False      # permitir arrastre vertical (modo carriles)
        self.home = QPointF(0, 0)

        self._pressing = False
        self._dragging = False
        self._press_scene = QPointF()
        self._hover = False
        self._anim = None
        self._h = 60.0

        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable
                      | QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)
        self._relayout_text()

    # -- API -------------------------------------------------------------- #
    def refresh(self):
        self._relayout_text()

    def configure(self, side: int, stem: float, axis_date: bool, free_y: bool):
        self.free_y = free_y
        if (side, stem, axis_date) != (self.side, self.stem, self.axis_date):
            self.side, self.stem, self.axis_date = side, stem, axis_date
            self._relayout_text()

    def set_dimmed(self, dimmed: bool):
        self.setOpacity(0.22 if dimmed else 1.0)

    @property
    def card_height(self) -> float:
        return self._h

    def animate_to(self, pos: QPointF, duration: int = 200):
        if self._anim is None:
            self._anim = QPropertyAnimation(self, b"pos")
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.stop()
        if (self.pos() - pos).manhattanLength() < 0.5:
            self.setPos(pos)
            return
        self._anim.setDuration(duration)
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(pos)
        self._anim.start()

    def stop_animation(self):
        if self._anim is not None:
            self._anim.stop()

    # -- geometría ------------------------------------------------------- #
    def _relayout_text(self):
        self.prepareGeometryChange()
        b = self.block
        base = QApplication.font()
        size = base.pointSizeF() if base.pointSizeF() > 0 else 10.0
        self._f_title = QFont(base)
        self._f_title.setPointSizeF(size + 0.5)
        self._f_title.setBold(True)
        self._f_body = QFont(base)
        self._f_body.setPointSizeF(size - 0.5)
        self._f_small = QFont(base)
        self._f_small.setPointSizeF(size - 1.5)
        self._lh_title = QFontMetricsF(self._f_title).lineSpacing()
        self._lh_body = QFontMetricsF(self._f_body).lineSpacing()
        self._lh_small = QFontMetricsF(self._f_small).lineSpacing()

        self._milestone = bool(b.get("is_milestone"))
        self._group = (b.get("group_name") or "").strip()
        self._date = (b.get("date_label") or "").strip()
        raw_title = (b.get("title") or "").strip()
        self._title_placeholder = not raw_title
        inner_w = self._inner_w()
        title_w = inner_w - (18 if self._milestone else 0)
        self._title_lines = wrap_text(raw_title or "Nuevo evento", self._f_title, title_w, 2)
        self._note_lines = wrap_text(b.get("description") or "", self._f_body, inner_w, 3)
        self._date_in_card = bool(self._date) and not self.axis_date
        self._has_footer = bool(self._group or self.chapter_title)

        h = self.PAD
        if self._date_in_card:
            h += self._lh_small + 3
        h += len(self._title_lines) * self._lh_title
        if self._note_lines:
            h += 4 + len(self._note_lines) * self._lh_body
        if self._has_footer:
            h += 8 + self.FOOTER_H
        h += self.PAD
        self._h = max(h, 54.0)
        self.update()

    def _inner_w(self) -> float:
        return self.CARD_W - self.ACCENT_W - self.PAD * 2

    def _node_r(self) -> float:
        return self.MILESTONE_R if self._milestone else self.NODE_R

    def _card_rect(self) -> QRectF:
        if self.side > 0:
            return QRectF(-self.CARD_W / 2, self.stem, self.CARD_W, self._h)
        return QRectF(-self.CARD_W / 2, -self.stem - self._h, self.CARD_W, self._h)

    def _axis_date_rect(self) -> QRectF:
        r = self._node_r()
        h = self._lh_small + 2
        y = -r - 6 - h if self.side > 0 else r + 6
        return QRectF(-self.AXIS_DATE_W / 2, y, self.AXIS_DATE_W, h)

    def boundingRect(self) -> QRectF:
        r = self._node_r()
        rect = self._card_rect().united(QRectF(-r - 4, -r - 4, 2 * r + 8, 2 * r + 8))
        if self.axis_date and self._date:
            rect = rect.united(self._axis_date_rect())
        return rect.adjusted(-8, -8, 8, 8)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self._card_rect(), 10, 10)
        r = self._node_r() + 2
        path.addEllipse(QPointF(0, 0), r, r)
        return path

    # -- pintado ----------------------------------------------------------- #
    def paint(self, p: QPainter, option, widget=None):
        pal = palette_colors()
        color = QColor(block_color(self.block))
        selected = self.isSelected() and not EventItem.exporting
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        card = self._card_rect()
        r = self._node_r()

        # tallo
        y_edge = card.top() if self.side > 0 else card.bottom()
        p.setPen(QPen(color, 1.6))
        p.drawLine(QPointF(0, self.side * r), QPointF(0, y_edge))

        # nodo
        if self._milestone:
            p.setPen(QPen(color, 2.5))
            p.setBrush(pal["background"])
            p.drawEllipse(QPointF(0, 0), r, r)
            p.setPen(Qt.NoPen)
            p.setBrush(color)
            p.drawEllipse(QPointF(0, 0), 5, 5)
        else:
            p.setPen(QPen(pal["background"], 2.5))
            p.setBrush(color)
            p.drawEllipse(QPointF(0, 0), r, r)

        # fecha junto al nodo
        if self.axis_date and self._date:
            p.setFont(self._f_small)
            p.setPen(pal["text_secondary"])
            fm = QFontMetricsF(self._f_small)
            text = fm.elidedText(self._date, Qt.ElideRight, self.AXIS_DATE_W)
            p.drawText(self._axis_date_rect(), Qt.AlignHCenter | Qt.AlignVCenter, text)

        # tarjeta
        path = QPainterPath()
        path.addRoundedRect(card, 10, 10)
        if selected:
            p.setPen(Qt.NoPen)
            p.setBrush(_with_alpha(color, 50))
            p.drawRoundedRect(card.adjusted(-4, -4, 4, 4), 13, 13)
        if selected:
            border = QPen(color, 2)
        elif self._hover:
            border = QPen(_with_alpha(color, 170), 1.4)
        else:
            border = QPen(pal["border"], 1)
        p.setPen(border)
        p.setBrush(pal["surface"])
        p.drawPath(path)
        p.save()
        p.setClipPath(path)
        p.fillRect(QRectF(card.left(), card.top(), self.ACCENT_W, card.height()), color)
        p.restore()

        x = card.left() + self.ACCENT_W + self.PAD
        w = self._inner_w()
        y = card.top() + self.PAD

        if self._date_in_card:
            p.setFont(self._f_small)
            p.setPen(pal["text_secondary"])
            text = QFontMetricsF(self._f_small).elidedText(self._date, Qt.ElideRight, w)
            p.drawText(QRectF(x, y, w, self._lh_small), Qt.AlignLeft | Qt.AlignVCenter, text)
            y += self._lh_small + 3

        title_font = QFont(self._f_title)
        title_font.setItalic(self._title_placeholder)
        p.setFont(title_font)
        p.setPen(pal["text_muted"] if self._title_placeholder else pal["text"])
        for line in self._title_lines:
            p.drawText(QRectF(x, y, w, self._lh_title), Qt.AlignLeft | Qt.AlignVCenter, line)
            y += self._lh_title

        if self._milestone:
            pm = _icon_pixmap("star", color.name(), 14)
            p.drawPixmap(QPointF(card.right() - self.PAD - 12, card.top() + self.PAD + 1), pm)

        if self._note_lines:
            y += 4
            p.setFont(self._f_body)
            p.setPen(pal["text_secondary"])
            for line in self._note_lines:
                p.drawText(QRectF(x, y, w, self._lh_body), Qt.AlignLeft | Qt.AlignVCenter, line)
                y += self._lh_body

        if self._has_footer:
            y += 8
            fx = x
            if self._group:
                fm = QFontMetricsF(self._f_small)
                pill_w = min(fm.horizontalAdvance(self._group) + 14, w * 0.6)
                pill = QRectF(fx, y, pill_w, self.FOOTER_H)
                p.setPen(Qt.NoPen)
                p.setBrush(_with_alpha(color, 40))
                p.drawRoundedRect(pill, self.FOOTER_H / 2, self.FOOTER_H / 2)
                p.setFont(self._f_small)
                p.setPen(color)
                p.drawText(pill, Qt.AlignCenter, fm.elidedText(self._group, Qt.ElideRight, pill_w - 12))
                fx += pill_w + 8
            if self.chapter_title and fx < x + w - 30:
                pm = _icon_pixmap("book", pal["text_muted"].name(), 13)
                p.drawPixmap(QPointF(fx, y + (self.FOOTER_H - 13) / 2), pm)
                fm = QFontMetricsF(self._f_small)
                p.setFont(self._f_small)
                p.setPen(pal["text_muted"])
                avail = x + w - (fx + 17)
                p.drawText(QRectF(fx + 17, y, avail, self.FOOTER_H), Qt.AlignLeft | Qt.AlignVCenter,
                           fm.elidedText(self.chapter_title, Qt.ElideRight, avail))

    # -- interacción --------------------------------------------------------#
    def hoverEnterEvent(self, event):
        self._hover = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hover = False
        self.update()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionChange and self._pressing and not self.free_y:
            return QPointF(value.x(), self.home.y())
        if change == QGraphicsItem.ItemPositionHasChanged and self._dragging:
            self.dragging.emit(self)
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            event.setModifiers(Qt.NoModifier)  # un solo evento seleccionado/arrastrado a la vez
            self.stop_animation()
            self._pressing = True
            self._dragging = False
            self._press_scene = event.scenePos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pressing and not self._dragging:
            if (event.scenePos() - self._press_scene).manhattanLength() > QApplication.startDragDistance():
                self._dragging = True
                self.setZValue(10)
                self.setCursor(Qt.ClosedHandCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() != Qt.LeftButton:
            return
        was_dragging = self._dragging
        self._pressing = False
        self._dragging = False
        self.setZValue(1)
        self.unsetCursor()
        if was_dragging:
            self.dragFinished.emit(self)
        else:
            self.setPos(self.home)  # un simple clic no debe desplazar el bloque

    def mouseDoubleClickEvent(self, event):
        self.activated.emit(self)
        event.accept()

    def contextMenuEvent(self, event):
        self.setSelected(True)
        self.contextRequested.emit(self, event.screenPos())
        event.accept()


# ---------------------------------------------------------------------- #
# Línea (eje principal o carril)
# ---------------------------------------------------------------------- #
class TrackItem(QGraphicsItem):
    def __init__(self, x0, x1, y=0.0, label="", color=None, band_h=0.0, arrow=False,
                 thickness=3.0, band_top=34.0):
        super().__init__()
        self.x0, self.x1, self.y = x0, x1, y
        self.label = label
        self.color = QColor(color) if color else None
        self.band_h = band_h
        self.band_top = band_top
        self.arrow = arrow
        self.thickness = thickness
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.setZValue(-1)

    def boundingRect(self) -> QRectF:
        if self.band_h:
            return QRectF(self.x0, self.y - self.band_top, self.x1 - self.x0, self.band_h)
        return QRectF(self.x0 - 8, self.y - 12, self.x1 - self.x0 + 30, 24)

    def paint(self, p: QPainter, option, widget=None):
        pal = palette_colors()
        p.setRenderHint(QPainter.Antialiasing)
        if self.band_h:
            p.setPen(Qt.NoPen)
            p.setBrush(_with_alpha(pal["surface_alt"], 200))
            p.drawRoundedRect(self.boundingRect(), 14, 14)
        color = self.color or pal["text_muted"]
        line_color = _with_alpha(color, 200 if not self.band_h else 150)
        pen = QPen(line_color, self.thickness, Qt.SolidLine, Qt.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(self.x0, self.y), QPointF(self.x1, self.y))
        if self.arrow:
            p.setPen(Qt.NoPen)
            p.setBrush(line_color)
            p.drawPolygon(QPolygonF([QPointF(self.x1 + 14, self.y), QPointF(self.x1 - 1, self.y - 7),
                                     QPointF(self.x1 - 1, self.y + 7)]))
        if self.label:
            font = QApplication.font()
            size = font.pointSizeF() if font.pointSizeF() > 0 else 10.0
            font.setPointSizeF(size - 1)
            font.setBold(True)
            fm = QFontMetricsF(font)
            text = fm.elidedText(self.label, Qt.ElideRight, 150)
            pw = fm.horizontalAdvance(text) + 18
            pill = QRectF(self.x0 + 12, self.y - self.band_top + 8, pw, 20)
            p.setPen(Qt.NoPen)
            p.setBrush(_with_alpha(color, 45))
            p.drawRoundedRect(pill, 10, 10)
            p.setFont(font)
            p.setPen(color)
            p.drawText(pill, Qt.AlignCenter, text)


# ---------------------------------------------------------------------- #
# Botón "+" entre dos nodos
# ---------------------------------------------------------------------- #
class GapHandle(QGraphicsObject):
    clicked = Signal(int)
    R = 10

    def __init__(self, index: int, x: float):
        super().__init__()
        self.index = index
        self.setPos(x, 0)
        self.setAcceptHoverEvents(True)
        self.setToolTip("Insertar un evento aquí")
        self.setZValue(0.5)
        self.setOpacity(0.3)

    def boundingRect(self) -> QRectF:
        return QRectF(-self.R - 2, -self.R - 2, 2 * self.R + 4, 2 * self.R + 4)

    def hoverEnterEvent(self, event):
        self.setOpacity(1.0)

    def hoverLeaveEvent(self, event):
        self.setOpacity(0.3)

    def paint(self, p: QPainter, option, widget=None):
        if EventItem.exporting:
            return
        pal = palette_colors()
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(pal["accent"], 1.5))
        p.setBrush(pal["surface"])
        p.drawEllipse(QPointF(0, 0), self.R, self.R)
        p.drawLine(QPointF(-4, 0), QPointF(4, 0))
        p.drawLine(QPointF(0, -4), QPointF(0, 4))

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.contains(event.pos()):
            index = self.index
            QTimer.singleShot(0, lambda: self.clicked.emit(index))
        event.accept()


# ====================================================================== #
# Inspector (panel lateral de edición)
# ====================================================================== #

class TimelineInspector(QFrame):
    liveChanged = Signal(int, dict)
    saveRequested = Signal(int, dict)
    deleteRequested = Signal(int)
    duplicateRequested = Signal(int)
    closeRequested = Signal()

    WIDTH = 292
    SWATCH = 18

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TimelineInspector")
        self.setFixedWidth(self.WIDTH)
        self._block_id = None
        self._loading = False
        self._color = ""
        self._chapters: list[tuple[int, str]] = []

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(settings.autosave_interval_ms)
        self._save_timer.timeout.connect(self._save)
        settings_signals.changed.connect(lambda: self._save_timer.setInterval(settings.autosave_interval_ms))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(6)

        head = QHBoxLayout()
        title = QLabel("Evento")
        title.setProperty("role", "section-title")
        head.addWidget(title, 1)
        self.close_btn = QPushButton()
        self.close_btn.setProperty("variant", "icon")
        self.close_btn.setFixedSize(24, 24)
        self.close_btn.setToolTip("Cerrar (Esc)")
        self.close_btn.clicked.connect(self.closeRequested.emit)
        head.addWidget(self.close_btn)
        layout.addLayout(head)

        layout.addWidget(self._caption("Título"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Título del evento")
        self.title_edit.textEdited.connect(self._on_edited)
        layout.addWidget(self.title_edit)

        layout.addWidget(self._caption("Fecha u orden"))
        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText("Ej.: Año 312, Día 3, Verano…")
        self.date_edit.textEdited.connect(self._on_edited)
        layout.addWidget(self.date_edit)

        layout.addWidget(self._caption("Grupo"))
        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        self.group_combo.setInsertPolicy(QComboBox.NoInsert)
        self.group_combo.lineEdit().setPlaceholderText(NO_GROUP_LABEL)
        self.group_combo.editTextChanged.connect(self._on_edited)
        layout.addWidget(self.group_combo)

        layout.addWidget(self._caption("Color"))
        layout.addLayout(self._build_swatches())

        self.milestone_check = QCheckBox("Hito importante")
        self.milestone_check.setToolTip("Destaca el nodo y marca la tarjeta con una estrella")
        self.milestone_check.toggled.connect(self._on_edited)
        layout.addWidget(self.milestone_check)

        layout.addWidget(self._caption("Capítulo vinculado"))
        self.chapter_combo = QComboBox()
        self.chapter_combo.currentIndexChanged.connect(self._on_edited)
        layout.addWidget(self.chapter_combo)

        layout.addWidget(self._caption("Notas"))
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("Notas del evento (opcional)")
        self.note_edit.setMinimumHeight(110)
        self.note_edit.textChanged.connect(self._on_edited)
        layout.addWidget(self.note_edit, 1)

        footer = QHBoxLayout()
        self.dup_btn = QPushButton(" Duplicar")
        self.dup_btn.clicked.connect(lambda: self._emit_for_block(self.duplicateRequested))
        footer.addWidget(self.dup_btn)
        self.del_btn = QPushButton(" Eliminar")
        self.del_btn.setProperty("variant", "danger")
        self.del_btn.clicked.connect(lambda: self._emit_for_block(self.deleteRequested))
        footer.addWidget(self.del_btn)
        layout.addLayout(footer)

        self._apply_theme()
        theme.signals.changed.connect(self._apply_theme)

    # -- construcción ---------------------------------------------------- #
    @staticmethod
    def _caption(text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("InspectorCaption")
        return label

    def _build_swatches(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        self.auto_btn = QPushButton("Auto")
        self.auto_btn.setProperty("variant", "chip")
        self.auto_btn.setCheckable(True)
        self.auto_btn.setToolTip("Usar el color del grupo")
        self.auto_btn.clicked.connect(lambda: self._pick_color(""))
        row.addWidget(self.auto_btn)
        self._swatches: list[tuple[QPushButton, str]] = []
        for hex_color in GROUP_COLORS:
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(self.SWATCH, self.SWATCH)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, c=hex_color: self._pick_color(c))
            self._swatches.append((btn, hex_color))
            row.addWidget(btn)
        self.custom_btn = QPushButton()
        self.custom_btn.setCheckable(True)
        self.custom_btn.setFixedSize(self.SWATCH, self.SWATCH)
        self.custom_btn.setCursor(Qt.PointingHandCursor)
        self.custom_btn.setToolTip("Otro color…")
        self.custom_btn.clicked.connect(self._pick_custom_color)
        row.addWidget(self.custom_btn)
        row.addStretch(1)
        return row

    def _apply_theme(self, *_args):
        c = theme.colors()
        self.setStyleSheet(
            f"#TimelineInspector {{ background: {c['surface']}; border: none; border-left: 1px solid {c['border']}; }} "
            f"#InspectorCaption {{ color: {c['text_muted']}; font-size: 9pt; padding-top: 4px; }}"
        )
        self.close_btn.setIcon(icons.icon("x", c["text_muted"], size=14))
        self.close_btn.setIconSize(QSize(14, 14))
        self.dup_btn.setIcon(icons.icon("copy", c["text_secondary"], size=15))
        self.del_btn.setIcon(icons.icon("trash", c["danger"], size=15))
        for btn, hex_color in self._swatches:
            btn.setStyleSheet(self._swatch_css(hex_color, c))
        self._refresh_custom_button()

    def _swatch_css(self, fill: str, c: dict) -> str:
        return (f"QPushButton {{ background: {fill}; border: 2px solid transparent; border-radius: {self.SWATCH // 2}px; "
                f"padding: 0; min-width: 0; min-height: 0; }}"
                f"QPushButton:checked {{ border: 2px solid {c['text']}; }}")

    # -- datos --------------------------------------------------------------#
    def show_block(self, block: dict, known_groups: list[str], chapters: list[tuple[int, str]]):
        self.flush_pending_save()
        self._loading = True
        self._block_id = block["id"]
        self._chapters = chapters
        self.title_edit.setText(block.get("title") or "")
        self.title_edit.setCursorPosition(0)
        self.date_edit.setText(block.get("date_label") or "")
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("")
        self.group_combo.addItems(sorted(g for g in known_groups if g))
        self.group_combo.setCurrentText(block.get("group_name") or "")
        self.group_combo.blockSignals(False)
        self.milestone_check.setChecked(bool(block.get("is_milestone")))
        self.chapter_combo.blockSignals(True)
        self.chapter_combo.clear()
        self.chapter_combo.addItem("Sin vincular", None)
        for chapter_id, chapter_title in chapters:
            self.chapter_combo.addItem(chapter_title or "(sin título)", chapter_id)
        index = self.chapter_combo.findData(block.get("chapter_id"))
        self.chapter_combo.setCurrentIndex(max(index, 0))
        self.chapter_combo.blockSignals(False)
        self.note_edit.setPlainText(block.get("description") or "")
        self._set_color(block.get("color") or "")
        self._loading = False

    def clear(self):
        self.flush_pending_save()
        self._block_id = None

    def focus_title(self):
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def current_block_id(self):
        return self._block_id

    # -- color ----------------------------------------------------------------#
    def _set_color(self, value: str):
        self._color = value
        self.auto_btn.setChecked(value == "")
        for btn, hex_color in self._swatches:
            btn.setChecked(value.lower() == hex_color.lower())
        self._refresh_custom_button()

    def _refresh_custom_button(self):
        c = theme.colors()
        palette = {h.lower() for h in GROUP_COLORS}
        is_custom = bool(self._color) and self._color.lower() not in palette
        self.custom_btn.setChecked(is_custom)
        if is_custom:
            self.custom_btn.setIcon(QIcon())
            self.custom_btn.setStyleSheet(self._swatch_css(self._color, c))
        else:
            self.custom_btn.setIcon(icons.icon("plus", c["text_muted"], size=12))
            self.custom_btn.setIconSize(QSize(12, 12))
            self.custom_btn.setStyleSheet(
                f"QPushButton {{ background: transparent; border: 1px dashed {c['text_muted']}; "
                f"border-radius: {self.SWATCH // 2}px; padding: 0; min-width: 0; min-height: 0; }}")

    def _pick_color(self, value: str):
        self._set_color(value)
        self._on_edited()

    def _pick_custom_color(self):
        initial = QColor(self._color) if self._color else QColor(GROUP_COLORS[0])
        chosen = QColorDialog.getColor(initial, self, "Color del evento")
        if chosen.isValid():
            self._pick_color(chosen.name())
        else:
            self._set_color(self._color)

    # -- emisión -------------------------------------------------------------#
    def _fields(self) -> dict:
        return {
            "title": self.title_edit.text(),
            "date_label": self.date_edit.text().strip(),
            "group_name": self.group_combo.currentText().strip(),
            "description": self.note_edit.toPlainText(),
            "color": self._color,
            "is_milestone": int(self.milestone_check.isChecked()),
            "chapter_id": self.chapter_combo.currentData(),
        }

    def _on_edited(self, *_args):
        if self._loading or self._block_id is None:
            return
        self.liveChanged.emit(self._block_id, self._fields())
        self._save_timer.start()

    def _save(self):
        if self._block_id is None:
            return
        fields = self._fields()
        fields["title"] = fields["title"].strip() or "Nuevo evento"
        self.saveRequested.emit(self._block_id, fields)

    def flush_pending_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save()

    def _emit_for_block(self, signal):
        if self._block_id is not None:
            self.flush_pending_save()
            signal.emit(self._block_id)


@lru_cache(maxsize=64)
def _dot_icon(color_hex: str, d: int = 10) -> QIcon:
    pm = QPixmap(d * 2, d * 2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(color_hex))
    p.drawEllipse(1, 1, d * 2 - 2, d * 2 - 2)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


# ---------------------------------------------------------------------- #
# Vista
# ---------------------------------------------------------------------- #
class TimelineView(QGraphicsView):
    zoomChanged = Signal(float)
    keyAction = Signal(str)
    backgroundDoubleClicked = Signal(QPointF)
    backgroundContext = Signal(QPointF, QPoint)

    MIN_ZOOM = 0.25
    MAX_ZOOM = 2.5

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom = 1.0
        self.horizontal_wheel = True
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setFrameShape(QFrame.NoFrame)
        self.setFocusPolicy(Qt.StrongFocus)

    # -- zoom ---------------------------------------------------------------#
    @property
    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, value: float):
        value = max(self.MIN_ZOOM, min(self.MAX_ZOOM, value))
        self.resetTransform()
        self.scale(value, value)
        self._zoom = value
        self.zoomChanged.emit(value)

    def zoom_by(self, factor: float, under_mouse: bool = False):
        target = max(self.MIN_ZOOM, min(self.MAX_ZOOM, self._zoom * factor))
        factor = target / self._zoom
        if abs(factor - 1) < 1e-6:
            return
        if not under_mouse:
            self.setTransformationAnchor(QGraphicsView.AnchorViewCenter)
        self.scale(factor, factor)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._zoom = target
        self.zoomChanged.emit(target)

    def reset_zoom(self):
        center = self.mapToScene(self.viewport().rect().center())
        self.set_zoom(1.0)
        self.centerOn(center)

    def fit_rect(self, rect: QRectF, max_zoom: float = 1.0):
        vw, vh = max(self.viewport().width(), 1), max(self.viewport().height(), 1)
        z = min(vw / max(rect.width(), 1), vh / max(rect.height(), 1))
        self.set_zoom(min(z, max_zoom))
        self.centerOn(rect.center())

    def fit_zoom_for(self, rect: QRectF) -> float:
        vw, vh = max(self.viewport().width(), 1), max(self.viewport().height(), 1)
        return min(vw / max(rect.width(), 1), vh / max(rect.height(), 1))

    def show_start(self, rect: QRectF):
        """Vista inicial: encaja todo si sigue siendo legible; si no,
        zoom 100% mostrando el comienzo de la línea."""
        if self.fit_zoom_for(rect) >= 0.6:
            self.fit_rect(rect)
            return
        self.set_zoom(1.0)
        vw, vh = self.viewport().width(), self.viewport().height()
        cy = rect.center().y() if rect.height() < vh else rect.top() + vh / 2
        self.centerOn(QPointF(rect.left() + vw / 2 - 20, cy))

    # -- eventos ----------------------------------------------------------- #
    def _interactive_at(self, pos) -> bool:
        return any(isinstance(i, (EventItem, GapHandle)) for i in self.items(pos))

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if delta:
                self.zoom_by(1.15 ** (delta / 120.0), under_mouse=True)
            event.accept()
            return
        if (self.horizontal_wheel and event.pixelDelta().isNull() and event.angleDelta().y()
                and not event.modifiers() & Qt.ShiftModifier):
            bar = self.horizontalScrollBar()
            bar.setValue(bar.value() - event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and not self._interactive_at(event.position().toPoint()):
            self.backgroundDoubleClicked.emit(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event):
        if self._interactive_at(event.pos()):
            super().contextMenuEvent(event)
            return
        self.backgroundContext.emit(self.mapToScene(event.pos()), event.globalPos())
        event.accept()

    def keyPressEvent(self, event):
        k, m = event.key(), event.modifiers()
        ctrl, alt = bool(m & Qt.ControlModifier), bool(m & Qt.AltModifier)
        action = None
        if k in (Qt.Key_Delete, Qt.Key_Backspace):
            action = "delete"
        elif ctrl and k == Qt.Key_D:
            action = "duplicate"
        elif k == Qt.Key_Left:
            action = "move_prev" if alt else "prev"
        elif k == Qt.Key_Right:
            action = "move_next" if alt else "next"
        elif k == Qt.Key_Escape:
            action = "deselect"
        elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_F2):
            action = "edit"
        elif ctrl and k in (Qt.Key_Plus, Qt.Key_Equal):
            action = "zoom_in"
        elif ctrl and k == Qt.Key_Minus:
            action = "zoom_out"
        elif ctrl and k == Qt.Key_0:
            action = "zoom_reset"
        if action:
            self.keyAction.emit(action)
            event.accept()
            return
        super().keyPressEvent(event)

    def drawBackground(self, painter, rect):
        pal = palette_colors()
        painter.fillRect(rect, pal["background"])
        if self._zoom < 0.5:
            return
        step = 28
        color = QColor(pal["border"])
        color.setAlpha(170)
        pen = QPen(color, 2)
        pen.setCosmetic(True)
        painter.setPen(pen)
        left = int(rect.left() // step) * step
        top = int(rect.top() // step) * step
        points = []
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                points.append(QPointF(x, y))
                y += step
            x += step
        painter.drawPoints(QPolygonF(points))


# ---------------------------------------------------------------------- #
# Lienzo completo (barra + vista + inspector)
# ---------------------------------------------------------------------- #
class TimelineCanvas(QWidget):
    addRequested = Signal(int, str)        # (posición de inserción, grupo inicial)
    blockChanged = Signal(int, dict)
    blockDeleteRequested = Signal(int)
    blockDuplicateRequested = Signal(int)
    blocksReordered = Signal(list)

    STEP_LINE = 150
    STEP_LANES = 232
    STEM_LINE = 46
    STEM_LANES = 30
    LANE_TOP = 34

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blocks: list[dict] = []
        self._items: dict[int, EventItem] = {}
        self._decor: list = []
        self._marker = None
        self._lane_names: list[str] = []
        self._lane_h = 0.0
        self._content_rect = QRectF()
        self._chapters: list[tuple[int, str]] = []
        self._mode = "line"
        self._filters: set[str] = set()
        self._query = ""
        self._rebuilding = False
        self._initial_view_pending = False
        self._tool_buttons: list[QPushButton] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.scene = QGraphicsScene(self)
        self.view = TimelineView(self.scene)
        body.addWidget(self.view, 1)
        self.inspector = TimelineInspector()
        self.inspector.hide()
        body.addWidget(self.inspector)
        root.addLayout(body, 1)

        self.view.keyAction.connect(self._on_key_action)
        self.view.backgroundDoubleClicked.connect(self._on_background_double_click)
        self.view.backgroundContext.connect(self._on_background_context)
        self.view.zoomChanged.connect(self._on_zoom_changed)
        self.scene.selectionChanged.connect(self._on_selection_changed)
        self.inspector.liveChanged.connect(self._on_live_changed)
        self.inspector.saveRequested.connect(self.blockChanged.emit)
        self.inspector.deleteRequested.connect(self.blockDeleteRequested.emit)
        self.inspector.duplicateRequested.connect(self.blockDuplicateRequested.emit)
        self.inspector.closeRequested.connect(self.scene.clearSelection)

        self._apply_theme()
        theme.signals.changed.connect(self._apply_theme)

    # ------------------------------------------------------------------ #
    # Barra superior
    # ------------------------------------------------------------------ #
    def _tool_button(self, icon_name, tooltip, checkable=False) -> QPushButton:
        btn = QPushButton()
        btn.setProperty("variant", "icon")
        btn.setProperty("icon_name", icon_name)
        btn.setCheckable(checkable)
        btn.setFixedSize(32, 30)
        btn.setIconSize(QSize(17, 17))
        btn.setToolTip(tooltip)
        self._tool_buttons.append(btn)
        return btn

    def _build_toolbar(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 10, 14, 6)
        v.setSpacing(6)

        row = QHBoxLayout()
        row.setSpacing(6)
        self.add_button = QPushButton("+ Añadir evento")
        self.add_button.setProperty("variant", "primary")
        self.add_button.clicked.connect(self._on_add_button)
        row.addWidget(self.add_button)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Buscar evento…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(200)
        self.search_edit.textChanged.connect(self._on_query_changed)
        self._search_action = self.search_edit.addAction(QIcon(), QLineEdit.LeadingPosition)
        row.addWidget(self.search_edit)

        self.count_label = QLabel("")
        self.count_label.setProperty("role", "muted")
        row.addWidget(self.count_label)
        row.addStretch(1)

        self.line_btn = self._tool_button("timeline", "Disposición en línea", checkable=True)
        self.lanes_btn = self._tool_button("lanes", "Disposición por carriles (un carril por grupo)", checkable=True)
        self.line_btn.setChecked(True)
        self.line_btn.clicked.connect(lambda: self._set_mode("line"))
        self.lanes_btn.clicked.connect(lambda: self._set_mode("lanes"))
        row.addWidget(self.line_btn)
        row.addWidget(self.lanes_btn)
        row.addSpacing(8)

        self.zoom_out_btn = self._tool_button("minus", "Alejar (Ctrl + −)")
        self.zoom_out_btn.clicked.connect(lambda: self.view.zoom_by(1 / 1.25))
        self.zoom_label = QPushButton("100%")
        self.zoom_label.setProperty("variant", "icon")
        self.zoom_label.setFixedSize(52, 30)
        self.zoom_label.setToolTip("Volver al 100% (Ctrl + 0)")
        self.zoom_label.clicked.connect(lambda: self.view.reset_zoom())
        self._tool_buttons.append(self.zoom_label)
        self.zoom_in_btn = self._tool_button("plus", "Acercar (Ctrl + +)")
        self.zoom_in_btn.clicked.connect(lambda: self.view.zoom_by(1.25))
        self.fit_btn = self._tool_button("expand", "Ajustar la vista a todo el contenido")
        self.fit_btn.clicked.connect(self.fit_view)
        for w in (self.zoom_out_btn, self.zoom_label, self.zoom_in_btn, self.fit_btn):
            row.addWidget(w)
        row.addSpacing(8)
        self.export_btn = self._tool_button("image", "Exportar la línea temporal como imagen PNG")
        self.export_btn.clicked.connect(self.export_png)
        row.addWidget(self.export_btn)
        v.addLayout(row)

        self.chips_scroll = QScrollArea()
        self.chips_scroll.setWidgetResizable(True)
        self.chips_scroll.setFrameShape(QFrame.NoFrame)
        self.chips_scroll.setFixedHeight(40)
        self.chips_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.chips_host = QWidget()
        self.chips_host.setObjectName("ChipsHost")
        self.chips_host.setStyleSheet("#ChipsHost { background: transparent; }")
        self.chips_layout = QHBoxLayout(self.chips_host)
        self.chips_layout.setContentsMargins(0, 0, 0, 4)
        self.chips_layout.setSpacing(6)
        self.chips_scroll.setWidget(self.chips_host)
        self.chips_scroll.hide()
        v.addWidget(self.chips_scroll)
        return box

    def _apply_theme(self, *_args):
        c = theme.colors()
        css = (f"QPushButton {{ border: none; border-radius: 6px; background: transparent; color: {c['text_secondary']}; }} "
               f"QPushButton:hover {{ background: {c['surface_alt']}; }} "
               f"QPushButton:checked {{ background: {c['primary_light']}; }}")
        for btn in self._tool_buttons:
            btn.setStyleSheet(css)
            name = btn.property("icon_name")
            if name:
                color = c["primary"] if btn.isCheckable() and btn.isChecked() else c["text_secondary"]
                btn.setIcon(icons.icon(name, color, size=17))
        self._search_action.setIcon(icons.icon("search", c["text_muted"], size=15))
        self.scene.update()
        self.view.viewport().update()

    def _refresh_mode_icons(self):
        c = theme.colors()
        for btn in (self.line_btn, self.lanes_btn):
            color = c["primary"] if btn.isChecked() else c["text_secondary"]
            btn.setIcon(icons.icon(btn.property("icon_name"), color, size=17))

    # ------------------------------------------------------------------ #
    # Sincronización con la base de datos
    # ------------------------------------------------------------------ #
    def set_blocks(self, rows, chapters=None, reset_view=False):
        self.inspector.clear()
        selected_id = self.selected_id()
        if chapters is not None:
            self._chapters = list(chapters)
        self._blocks = [self._normalize(row) for row in rows]

        h_val = self.view.horizontalScrollBar().value()
        v_val = self.view.verticalScrollBar().value()

        self._rebuilding = True
        self.scene.clear()
        self._items.clear()
        self._decor.clear()
        self._marker = None
        for block in self._blocks:
            self._make_item(block)
        self._relayout(animate=False)
        self._refresh_chips()
        self._rebuilding = False

        if reset_view:
            self._schedule_initial_view()
        else:
            self.view.horizontalScrollBar().setValue(h_val)
            self.view.verticalScrollBar().setValue(v_val)
        if selected_id in self._items and not reset_view:
            self._items[selected_id].setSelected(True)
        self._on_selection_changed()

    @staticmethod
    def _normalize(row) -> dict:
        d = dict(row)
        d.setdefault("color", "")
        d.setdefault("is_milestone", 0)
        d.setdefault("chapter_id", None)
        return d

    def set_chapters(self, chapters):
        self._chapters = list(chapters)

    def _chapter_title(self, chapter_id) -> str:
        for cid, title in self._chapters:
            if cid == chapter_id:
                return title or ""
        return ""

    def _make_item(self, block) -> EventItem:
        item = EventItem(block, self._chapter_title(block.get("chapter_id")))
        item.dragging.connect(self._on_item_dragging)
        item.dragFinished.connect(self._on_item_drag_finished)
        item.activated.connect(self._on_item_activated)
        item.contextRequested.connect(self._on_item_context)
        self.scene.addItem(item)
        self._items[block["id"]] = item
        return item

    def flush_pending_saves(self):
        self.inspector.flush_pending_save()

    def _ordered_items(self) -> list[EventItem]:
        return [self._items[b["id"]] for b in self._blocks if b["id"] in self._items]

    def _group_names(self) -> list[str]:
        return sorted({(b["group_name"] or "").strip() for b in self._blocks if (b["group_name"] or "").strip()})

    # ------------------------------------------------------------------ #
    # Disposición
    # ------------------------------------------------------------------ #
    def _set_mode(self, mode: str):
        self.line_btn.setChecked(mode == "line")
        self.lanes_btn.setChecked(mode == "lanes")
        self._refresh_mode_icons()
        if mode == self._mode:
            return
        self._mode = mode
        self.view.horizontal_wheel = mode == "line"
        self._relayout(animate=True)
        self._schedule_initial_view()

    def _place(self, item: EventItem, pos: QPointF, animate: bool):
        item.home = pos
        if animate:
            item.animate_to(pos)
        else:
            item.stop_animation()
            item.setPos(pos)

    def _relayout(self, animate=False):
        for d in self._decor:
            if d.scene() is self.scene:
                self.scene.removeItem(d)
        self._decor.clear()
        items = self._ordered_items()
        if self._mode == "lanes":
            self._layout_lanes(items, animate)
        else:
            self._layout_line(items, animate)
        self._update_scene_rect(items)

    def _add_decor(self, item):
        self.scene.addItem(item)
        self._decor.append(item)

    def _layout_line(self, items, animate):
        step, n = self.STEP_LINE, len(items)
        self._lane_names = []
        for i, it in enumerate(items):
            it.configure(side=-1 if i % 2 == 0 else 1, stem=self.STEM_LINE, axis_date=True, free_y=False)
            self._place(it, QPointF(i * step, 0), animate)
        x0 = -step * 0.75
        x1 = max(n - 1, 0) * step + step * 0.75 + (220 if n == 0 else 0)
        self._add_decor(TrackItem(x0, x1, 0, arrow=True, thickness=3))
        for k in range(n + 1):
            gap = GapHandle(k, (k - 0.5) * step)
            gap.clicked.connect(self._on_gap_clicked)
            self._add_decor(gap)
        self._add_empty_hint(n, QPointF(x0 + 40, -70))

    def _layout_lanes(self, items, animate):
        step, n = self.STEP_LANES, len(items)
        for it in items:
            it.configure(side=1, stem=self.STEM_LANES, axis_date=False, free_y=True)
        names = []
        for b in self._blocks:
            g = (b["group_name"] or "").strip()
            if g not in names:
                names.append(g)
        if "" in names:
            names.remove("")
            names.append("")
        if not names:
            names = [""]
        self._lane_names = names
        card_max = max((it.card_height for it in items), default=60.0)
        lane_h = card_max + self.STEM_LANES + self.LANE_TOP + 22
        self._lane_h = lane_h
        for i, it in enumerate(items):
            lane = names.index((it.block["group_name"] or "").strip())
            self._place(it, QPointF(i * step, lane * lane_h), animate)
        x0 = -step * 0.5 - 60
        x1 = max(n - 1, 0) * step + step * 0.5 + (160 if n == 0 else 40)
        for lane, name in enumerate(names):
            self._add_decor(TrackItem(x0, x1, lane * lane_h, label=name or NO_GROUP_LABEL,
                                       color=color_for_group(name), band_h=lane_h - 8,
                                       thickness=2.5, band_top=self.LANE_TOP))
        self._add_empty_hint(n, QPointF(x0 + 120, 20))

    def _add_empty_hint(self, n, pos):
        if n:
            return
        hint = QGraphicsSimpleTextItem("Aún no hay eventos.\nHaz doble clic en el lienzo o pulsa «Añadir evento».")
        hint.setBrush(palette_colors()["text_muted"])
        hint.setPos(pos)
        hint.setAcceptedMouseButtons(Qt.NoButton)
        self._add_decor(hint)

    def _update_scene_rect(self, items):
        rect = QRectF()
        for it in items:
            rect = rect.united(it.boundingRect().translated(it.home))
        for d in self._decor:
            if not isinstance(d, GapHandle):
                rect = rect.united(d.sceneBoundingRect())
        if rect.isNull():
            rect = QRectF(-200, -100, 400, 200)
        self._content_rect = rect
        self.scene.setSceneRect(rect.adjusted(-500, -350, 500, 350))

    # ------------------------------------------------------------------ #
    # Vista: zoom, ajuste, exportación
    # ------------------------------------------------------------------ #
    def _schedule_initial_view(self):
        self._initial_view_pending = True
        if self.isVisible():
            QTimer.singleShot(0, self._apply_initial_view)

    def showEvent(self, event):
        super().showEvent(event)
        if self._initial_view_pending:
            QTimer.singleShot(0, self._apply_initial_view)

    def _apply_initial_view(self):
        if not self._initial_view_pending:
            return
        self._initial_view_pending = False
        self.view.show_start(self._content_rect.adjusted(-40, -40, 40, 40))

    def fit_view(self):
        self.view.fit_rect(self._content_rect.adjusted(-40, -40, 40, 40))

    def _on_zoom_changed(self, value: float):
        self.zoom_label.setText(f"{round(value * 100)}%")

    def export_png(self):
        path, _ = QFileDialog.getSaveFileName(self, "Exportar línea temporal", "linea_temporal.png",
                                              "Imagen PNG (*.png)")
        if not path:
            return
        if not path.lower().endswith(".png"):
            path += ".png"
        rect = self._content_rect.adjusted(-40, -40, 40, 40)
        scale = 2
        image = QImage(int(rect.width() * scale), int(rect.height() * scale), QImage.Format_ARGB32_Premultiplied)
        image.fill(palette_colors()["background"])
        painter = QPainter(image)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        EventItem.exporting = True
        try:
            self.scene.render(painter, QRectF(image.rect()), rect)
        finally:
            EventItem.exporting = False
            painter.end()
        if not image.save(path):
            QMessageBox.warning(self, "Exportar", "No se pudo guardar la imagen.")

    # ------------------------------------------------------------------ #
    # Selección e inspector
    # ------------------------------------------------------------------ #
    def selected_item(self):
        for it in self.scene.selectedItems():
            if isinstance(it, EventItem):
                return it
        return None

    def selected_id(self):
        it = self.selected_item() if self._items else None
        return it.block["id"] if it is not None else None

    def _on_selection_changed(self):
        if self._rebuilding:
            return
        it = self.selected_item()
        if it is None:
            self.inspector.clear()
            self.inspector.hide()
            return
        self.inspector.show_block(it.block, self._group_names(), self._chapters)
        self.inspector.show()

    def select_block(self, block_id, center=True, focus_title=False):
        it = self._items.get(block_id)
        if it is None:
            return
        self.scene.clearSelection()
        it.setSelected(True)
        if center:
            self.view.centerOn(it.home)
        else:
            self.view.ensureVisible(it.sceneBoundingRect(), 80, 80)
        if focus_title:
            self.inspector.focus_title()

    def _on_item_activated(self, item):
        item.setSelected(True)
        self.inspector.focus_title()

    def _on_live_changed(self, block_id, fields):
        it = self._items.get(block_id)
        if it is None:
            return
        old_group = (it.block["group_name"] or "").strip()
        old_height = it.card_height
        it.block.update(fields)
        it.chapter_title = self._chapter_title(fields.get("chapter_id"))
        it.refresh()
        group_changed = fields["group_name"] != old_group
        if group_changed:
            self._refresh_chips()
        if self._mode == "lanes" and (group_changed or abs(it.card_height - old_height) > 0.5):
            self._relayout(animate=group_changed)
        else:
            self._update_scene_rect(self._ordered_items())
        self._apply_filters()

    def _update_block(self, item: EventItem, fields: dict):
        """Cambio hecho desde el lienzo (menú, arrastre…): actualiza la
        copia local, avisa al panel y resincroniza el inspector."""
        self.inspector.flush_pending_save()
        item.block.update(fields)
        item.chapter_title = self._chapter_title(item.block.get("chapter_id"))
        item.refresh()
        self.blockChanged.emit(item.block["id"], fields)
        if "group_name" in fields:
            self._refresh_chips()
        if item.isSelected():
            self.inspector.show_block(item.block, self._group_names(), self._chapters)

    # ------------------------------------------------------------------ #
    # Arrastre y reordenado
    # ------------------------------------------------------------------ #
    def _drop_index(self, item):
        others = [it for it in self._ordered_items() if it is not item]
        cx = item.pos().x()
        return sum(1 for o in others if o.home.x() < cx), others

    def _on_item_dragging(self, item):
        index, others = self._drop_index(item)
        if not others:
            self._hide_marker()
            return
        step = self.STEP_LINE if self._mode == "line" else self.STEP_LANES
        if index == 0:
            x = others[0].home.x() - step / 2
        elif index == len(others):
            x = others[-1].home.x() + step / 2
        else:
            x = (others[index - 1].home.x() + others[index].home.x()) / 2
        if self._marker is None or self._marker.scene() is None:
            self._marker = QGraphicsLineItem()
            pen = QPen(palette_colors()["accent"], 2, Qt.DashLine)
            pen.setCosmetic(True)
            self._marker.setPen(pen)
            self._marker.setZValue(5)
            self.scene.addItem(self._marker)
        r = self._content_rect
        self._marker.setLine(x, r.top(), x, r.bottom())

    def _hide_marker(self):
        if self._marker is not None and self._marker.scene() is self.scene:
            self.scene.removeItem(self._marker)
        self._marker = None

    def _on_item_drag_finished(self, item):
        self._hide_marker()
        index, others = self._drop_index(item)
        ids = [o.block["id"] for o in others]
        ids.insert(index, item.block["id"])
        order_changed = ids != [b["id"] for b in self._blocks]

        if self._mode == "lanes" and self._lane_names and self._lane_h:
            lane = max(0, min(len(self._lane_names) - 1, int(round(item.pos().y() / self._lane_h))))
            new_group = self._lane_names[lane]
            if new_group != (item.block["group_name"] or "").strip():
                self._update_block(item, {"group_name": new_group})
        if order_changed:
            self._apply_order(ids)
            self.blocksReordered.emit(ids)
        self._relayout(animate=True)

    def _apply_order(self, ids):
        by_id = {b["id"]: b for b in self._blocks}
        self._blocks = [by_id[i] for i in ids]

    def _move_selected(self, delta: int):
        it = self.selected_item()
        if it is None:
            return
        ids = [b["id"] for b in self._blocks]
        i = ids.index(it.block["id"])
        j = i + delta
        if not 0 <= j < len(ids):
            return
        ids[i], ids[j] = ids[j], ids[i]
        self._apply_order(ids)
        self.blocksReordered.emit(ids)
        self._relayout(animate=True)
        self.view.ensureVisible(QRectF(it.home.x() - 120, it.home.y() - 60, 240, 120), 60, 60)

    # ------------------------------------------------------------------ #
    # Alta de eventos
    # ------------------------------------------------------------------ #
    def _default_group(self) -> str:
        if len(self._filters) == 1:
            name = next(iter(self._filters))
            return "" if name == NO_GROUP_LABEL else name
        return ""

    def _request_add(self, index: int, group: str):
        QTimer.singleShot(0, lambda: self.addRequested.emit(index, group))

    def _on_add_button(self):
        it = self.selected_item()
        ordered = self._ordered_items()
        index = ordered.index(it) + 1 if it in ordered else len(ordered)
        group = (it.block["group_name"] or "").strip() if it is not None else self._default_group()
        self._request_add(index, group)

    def _insertion_for(self, pos: QPointF):
        index = sum(1 for it in self._ordered_items() if it.home.x() < pos.x())
        group = self._default_group()
        if self._mode == "lanes" and self._lane_names and self._lane_h:
            lane = int((pos.y() + self.LANE_TOP) // self._lane_h)
            lane = max(0, min(len(self._lane_names) - 1, lane))
            group = self._lane_names[lane]
        return index, group

    def _on_background_double_click(self, pos: QPointF):
        self._request_add(*self._insertion_for(pos))

    def _on_gap_clicked(self, index: int):
        self._request_add(index, self._default_group())

    # ------------------------------------------------------------------ #
    # Menús contextuales
    # ------------------------------------------------------------------ #
    def _on_background_context(self, pos: QPointF, global_pos: QPoint):
        menu = QMenu(self)
        a_add = menu.addAction("Añadir evento aquí")
        menu.addSeparator()
        a_fit = menu.addAction("Ajustar vista al contenido")
        a_export = menu.addAction("Exportar como PNG…")
        chosen = menu.exec(global_pos)
        if chosen is a_add:
            self._request_add(*self._insertion_for(pos))
        elif chosen is a_fit:
            self.fit_view()
        elif chosen is a_export:
            QTimer.singleShot(0, self.export_png)

    def _on_item_context(self, item: EventItem, global_pos: QPoint):
        ordered = self._ordered_items()
        i = ordered.index(item)
        block_id = item.block["id"]
        group = (item.block["group_name"] or "").strip()
        menu = QMenu(self)
        a_edit = menu.addAction("Editar")
        a_dup = menu.addAction("Duplicar")
        a_ms = menu.addAction("Quitar hito" if item.block.get("is_milestone") else "Marcar como hito")
        menu.addSeparator()
        a_before = menu.addAction("Insertar evento antes")
        a_after = menu.addAction("Insertar evento después")
        menu.addSeparator()
        a_prev = menu.addAction("Mover antes")
        a_prev.setEnabled(i > 0)
        a_next = menu.addAction("Mover después")
        a_next.setEnabled(i < len(ordered) - 1)
        menu.addSeparator()
        a_del = menu.addAction("Eliminar")
        chosen = menu.exec(global_pos)
        if chosen is None:
            return
        if chosen is a_edit:
            self.inspector.focus_title()
        elif chosen is a_dup:
            QTimer.singleShot(0, lambda: self._emit_duplicate(block_id))
        elif chosen is a_ms:
            value = 0 if item.block.get("is_milestone") else 1
            QTimer.singleShot(0, lambda: self._update_block(item, {"is_milestone": value}))
        elif chosen is a_before:
            self._request_add(i, group)
        elif chosen is a_after:
            self._request_add(i + 1, group)
        elif chosen is a_prev:
            QTimer.singleShot(0, lambda: self._move_selected(-1))
        elif chosen is a_next:
            QTimer.singleShot(0, lambda: self._move_selected(1))
        elif chosen is a_del:
            QTimer.singleShot(0, lambda: self.blockDeleteRequested.emit(block_id))

    def _emit_duplicate(self, block_id):
        self.inspector.flush_pending_save()
        self.blockDuplicateRequested.emit(block_id)

    # ------------------------------------------------------------------ #
    # Teclado
    # ------------------------------------------------------------------ #
    def _on_key_action(self, action: str):
        if action == "deselect":
            self.scene.clearSelection()
            return
        if action == "zoom_in":
            self.view.zoom_by(1.25)
            return
        if action == "zoom_out":
            self.view.zoom_by(1 / 1.25)
            return
        if action == "zoom_reset":
            self.view.reset_zoom()
            return
        it = self.selected_item()
        if it is None:
            return
        if action == "delete":
            self.blockDeleteRequested.emit(it.block["id"])
        elif action == "duplicate":
            self._emit_duplicate(it.block["id"])
        elif action == "edit":
            self.inspector.focus_title()
        elif action in ("prev", "next"):
            ordered = self._ordered_items()
            j = ordered.index(it) + (-1 if action == "prev" else 1)
            if 0 <= j < len(ordered):
                self.select_block(ordered[j].block["id"], center=False)
        elif action == "move_prev":
            self._move_selected(-1)
        elif action == "move_next":
            self._move_selected(1)

    # ------------------------------------------------------------------ #
    # Filtros (chips por grupo + búsqueda): atenúan en vez de ocultar,
    # para que la posición en la línea se conserve.
    # ------------------------------------------------------------------ #
    def _current_groups(self):
        names, has_ungrouped = set(), False
        for b in self._blocks:
            g = (b["group_name"] or "").strip()
            if g:
                names.add(g)
            else:
                has_ungrouped = True
        return sorted(names), has_ungrouped

    def _refresh_chips(self):
        while self.chips_layout.count():
            widget = self.chips_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        groups, has_ungrouped = self._current_groups()
        labels = groups + ([NO_GROUP_LABEL] if has_ungrouped else [])
        self._filters &= set(labels)
        for label in labels:
            chip = QPushButton(label)
            chip.setProperty("variant", "chip")
            chip.setCheckable(True)
            chip.setIcon(_dot_icon(color_for_group("" if label == NO_GROUP_LABEL else label)))
            chip.setIconSize(QSize(10, 10))
            chip.setChecked(label in self._filters)
            chip.toggled.connect(lambda checked, name=label: self._on_chip_toggled(name, checked))
            self.chips_layout.addWidget(chip)
        self.chips_layout.addStretch(1)
        self.chips_scroll.setVisible(len(labels) > 1 or bool(self._filters))
        self._apply_filters()

    def _on_chip_toggled(self, name, checked):
        if checked:
            self._filters.add(name)
        else:
            self._filters.discard(name)
        self._apply_filters()

    def _on_query_changed(self, text):
        self._query = text.strip().lower()
        self._apply_filters()

    def _apply_filters(self):
        visible = 0
        for it in self._ordered_items():
            b = it.block
            group = (b["group_name"] or "").strip() or NO_GROUP_LABEL
            ok_group = not self._filters or group in self._filters
            haystack = " ".join((b.get("title") or "", b.get("date_label") or "", b["group_name"] or "",
                                 b.get("description") or "")).lower()
            ok_query = not self._query or self._query in haystack
            match = ok_group and ok_query
            it.set_dimmed(not match)
            visible += match
        total = len(self._blocks)
        if not total:
            self.count_label.setText("")
        elif visible == total:
            self.count_label.setText(f"{total} evento" + ("s" if total != 1 else ""))
        else:
            self.count_label.setText(f"{visible} de {total} eventos")