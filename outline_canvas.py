"""Lienzo de diagramas para la sección "Esquema".

Implementado sobre QGraphicsView/QGraphicsScene. Cada forma es un
`ShapeItem` (rectángulo, elipse, rombo o nota) que se puede mover,
redimensionar (tirando de la esquina inferior derecha) y renombrar
(doble clic). Las flechas (`ConnectionItem`) enlazan dos formas y
siguen su posición automáticamente cuando estas se mueven.

El widget no conoce SQLite directamente: emite señales de alto nivel
(`shapeCreated`, `shapeChanged`, `shapeDeleted`, `connectionCreated`,
`connectionDeleted`) para que el anfitrión (OutlinePanel) las traduzca
a operaciones de `Database`. Esto mantiene la lógica de dibujo
separada de la persistencia, igual que el resto de la aplicación.
"""

from PySide6.QtWidgets import (QGraphicsView, QGraphicsScene, QGraphicsItem,
                                QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPolygonItem,
                                QGraphicsLineItem, QGraphicsTextItem, QWidget, QVBoxLayout,
                                QToolBar, QToolButton, QButtonGroup, QColorDialog, QMenu,
                                QGraphicsSceneMouseEvent)
from PySide6.QtGui import (QBrush, QColor, QPen, QPolygonF, QPainter, QFont,
                            QAction, QActionGroup)
from PySide6.QtCore import Qt, QRectF, QPointF, QLineF, Signal, QObject

HANDLE_SIZE = 10
MIN_SHAPE_SIZE = 40

SHAPE_COLORS = ["#4C6EF5", "#F76707", "#2F9E44", "#E03131", "#AE3EC9", "#495057"]


class _Signals(QObject):
    """QGraphicsItem no es un QObject y no puede emitir señales por sí
    mismo; este pequeño puente permite que ShapeItem y ConnectionItem
    avisen de cambios sin duplicar lógica de notificación."""
    moved = Signal()
    editingFinished = Signal()


class _EditableLabel(QGraphicsTextItem):
    """QGraphicsTextItem que avisa (vía `signals.editingFinished`) cuando
    pierde el foco tras una edición, para que ShapeItem pueda confirmar
    el nuevo texto y notificar al anfitrión (que lo persiste en BD)."""

    def __init__(self, text, parent_shape):
        super().__init__(text, parent_shape)
        self.signals = _Signals()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.signals.editingFinished.emit()


class ShapeItem(QGraphicsItem):
    """Forma de diagrama: rectángulo, elipse, rombo o nota adhesiva.

    Se persiste con un `shape_id` (None mientras no se ha guardado la
    primera vez) para que el anfitrión pueda correlacionar este item
    gráfico con su fila en `outline_shapes`.
    """

    def __init__(self, shape_type: str, rect: QRectF, text: str = "",
                 color: str = SHAPE_COLORS[0], shape_id=None):
        super().__init__()
        self.shape_type = shape_type
        self.shape_id = shape_id
        self._rect = QRectF(0, 0, rect.width(), rect.height())
        self.setPos(rect.topLeft())
        self.color = QColor(color)
        self.signals = _Signals()

        self.setFlags(QGraphicsItem.ItemIsMovable | QGraphicsItem.ItemIsSelectable |
                      QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        self.setZValue(1)

        self._resizing = False
        self._resize_start_rect = None
        self._resize_start_pos = None

        self.label = _EditableLabel(text, self)
        self.label.setDefaultTextColor(QColor("#FFFFFF") if self._is_dark(self.color) else QColor("#1A1A1A"))
        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        font = QFont()
        font.setPointSize(10)
        self.label.setFont(font)
        self.label.signals.editingFinished.connect(self._on_label_focus_out)
        self._center_label()
        self._owner_canvas = None

        self.connections: list["ConnectionItem"] = []

    # -- utilidades ----------------------------------------------------- #
    @staticmethod
    def _is_dark(color: QColor) -> bool:
        return (0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()) < 140

    def _center_label(self):
        self.label.setTextWidth(max(self._rect.width() - 16, 20))
        lr = self.label.boundingRect()
        x = (self._rect.width() - lr.width()) / 2
        y = (self._rect.height() - lr.height()) / 2
        self.label.setPos(x, max(y, 4))

    def boundingRect(self) -> QRectF:
        return self._rect.adjusted(-2, -2, 2, 2)

    def shape_rect(self) -> QRectF:
        return QRectF(self._rect)

    def set_size(self, w: float, h: float):
        w = max(w, MIN_SHAPE_SIZE)
        h = max(h, MIN_SHAPE_SIZE)
        self.prepareGeometryChange()
        self._rect = QRectF(0, 0, w, h)
        self._center_label()
        self._notify_connections()

    def set_text(self, text: str):
        self.label.setPlainText(text)
        self._center_label()

    def set_color(self, color: QColor):
        self.color = color
        self.label.setDefaultTextColor(QColor("#FFFFFF") if self._is_dark(color) else QColor("#1A1A1A"))
        self.update()

    def _notify_connections(self):
        for conn in self.connections:
            conn.update_position()
        self.signals.moved.emit()

    # -- dibujo ----------------------------------------------------------#
    def paint(self, painter: QPainter, option, widget=None):
        pen = QPen(self.color.darker(130), 2)
        if self.isSelected():
            pen.setColor(QColor("#1971C2"))
            pen.setWidth(3)
        painter.setPen(pen)
        painter.setBrush(QBrush(self.color.lighter(150) if self.shape_type != "note" else QColor("#FFF3BF")))

        r = self._rect
        if self.shape_type == "rect":
            painter.drawRoundedRect(r, 6, 6)
        elif self.shape_type == "ellipse":
            painter.drawEllipse(r)
        elif self.shape_type == "diamond":
            poly = QPolygonF([
                QPointF(r.center().x(), r.top()),
                QPointF(r.right(), r.center().y()),
                QPointF(r.center().x(), r.bottom()),
                QPointF(r.left(), r.center().y()),
            ])
            painter.drawPolygon(poly)
        else:  # note
            painter.drawRect(r)

        if self.isSelected():
            painter.setBrush(QBrush(QColor("#1971C2")))
            painter.setPen(Qt.NoPen)
            painter.drawRect(self._handle_rect())

    def _handle_rect(self) -> QRectF:
        r = self._rect
        return QRectF(r.right() - HANDLE_SIZE, r.bottom() - HANDLE_SIZE, HANDLE_SIZE, HANDLE_SIZE)

    # -- interacción -------------------------------------------------- #
    def hoverMoveEvent(self, event):
        if self.isSelected() and self._handle_rect().contains(event.pos()):
            self.setCursor(Qt.SizeFDiagCursor)
        else:
            self.setCursor(Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if self.isSelected() and self._handle_rect().contains(event.pos()):
            self._resizing = True
            self._resize_start_rect = QRectF(self._rect)
            self._resize_start_pos = event.scenePos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._resizing:
            delta = event.scenePos() - self._resize_start_pos
            self.set_size(self._resize_start_rect.width() + delta.x(),
                           self._resize_start_rect.height() + delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._resizing:
            self._resizing = False
            self.signals.moved.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.label.setTextInteractionFlags(Qt.TextEditorInteraction)
        self.label.setFocus()
        cursor = self.label.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self.label.setTextCursor(cursor)
        event.accept()

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self._notify_connections()
        return super().itemChange(change, value)

    def finish_text_edit(self):
        self.label.setTextInteractionFlags(Qt.NoTextInteraction)
        self._center_label()

    def _on_label_focus_out(self):
        self.finish_text_edit()
        self.signals.editingFinished.emit()


class ConnectionItem(QGraphicsLineItem):
    """Flecha que enlaza dos ShapeItem y sigue su posición al moverlos."""

    def __init__(self, from_shape: ShapeItem, to_shape: ShapeItem, connection_id=None):
        super().__init__()
        self.from_shape = from_shape
        self.to_shape = to_shape
        self.connection_id = connection_id
        self.setZValue(0)
        self.setPen(QPen(QColor("#495057"), 2))
        from_shape.connections.append(self)
        to_shape.connections.append(self)
        self.update_position()

    def update_position(self):
        a = self.from_shape.sceneBoundingRect().center()
        b = self.to_shape.sceneBoundingRect().center()
        self.setLine(QLineF(a, b))

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        line = self.line()
        if line.length() == 0:
            return
        angle = line.angle()
        arrow_size = 12
        import math
        p1 = line.p2()
        a1 = math.radians(angle + 150)
        a2 = math.radians(angle - 150)
        arrow_p1 = p1 + QPointF(math.cos(a1) * arrow_size, -math.sin(a1) * arrow_size)
        arrow_p2 = p1 + QPointF(math.cos(a2) * arrow_size, -math.sin(a2) * arrow_size)
        painter.setBrush(QBrush(QColor("#495057")))
        painter.setPen(Qt.NoPen)
        painter.drawPolygon(QPolygonF([p1, arrow_p1, arrow_p2]))


SHAPE_LABELS = {"rect": "Rectángulo", "ellipse": "Elipse", "diamond": "Rombo", "note": "Nota"}


class OutlineScene(QGraphicsScene):
    """Escena que sabe crear formas al hacer clic cuando hay una
    herramienta de forma activa, y conectarlas cuando la herramienta
    activa es "connect"."""

    shapeRequested = Signal(str, QPointF)
    connectRequested = Signal(ShapeItem, ShapeItem)
    shapeTextEdited = Signal(ShapeItem)
    selectionRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active_tool = "select"
        self._connect_source = None
        self.setBackgroundBrush(QBrush(QColor("#F8F9FA")))

    def mousePressEvent(self, event):
        item = self.itemAt(event.scenePos(), self.views()[0].transform()) if self.views() else None
        shape = self._as_shape(item)

        if self.active_tool in SHAPE_LABELS and shape is None and item is None:
            self.shapeRequested.emit(self.active_tool, event.scenePos())
            return

        if self.active_tool == "connect":
            if shape is not None:
                if self._connect_source is None:
                    self._connect_source = shape
                    shape.setSelected(True)
                elif shape is not self._connect_source:
                    self.connectRequested.emit(self._connect_source, shape)
                    self._connect_source.setSelected(False)
                    self._connect_source = None
            return

        super().mousePressEvent(event)

    @staticmethod
    def _as_shape(item):
        while item is not None and not isinstance(item, ShapeItem):
            item = item.parentItem()
        return item


class OutlineCanvas(QWidget):
    """Widget completo: barra de herramientas + QGraphicsView."""

    shapeCreated = Signal(str, float, float)          # tipo, x, y
    shapeMoved = Signal(object)                        # ShapeItem
    shapeRenamed = Signal(object, str)                  # ShapeItem, texto
    shapeDeleted = Signal(object)                       # ShapeItem
    shapeRecolored = Signal(object, str)                # ShapeItem, color hex
    connectionCreated = Signal(object, object)          # from ShapeItem, to ShapeItem
    connectionDeleted = Signal(object)                  # ConnectionItem

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = OutlineScene(self)
        self.scene.setSceneRect(0, 0, 3000, 2000)
        self.view = QGraphicsView(self.scene, self)
        self.view.setRenderHint(QPainter.Antialiasing)
        self.view.setDragMode(QGraphicsView.RubberBandDrag)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_toolbar())
        layout.addWidget(self.view)

        self.scene.shapeRequested.connect(lambda t, p: self.shapeCreated.emit(t, p.x(), p.y()))
        self.scene.connectRequested.connect(lambda a, b: self.connectionCreated.emit(a, b))

        self._shape_items: dict[int, ShapeItem] = {}
        self._connection_items: list[ConnectionItem] = []

    def apply_theme(self, colors: dict):
        """Ajusta el fondo del lienzo al esquema de color activo. Las
        formas conservan sus propios colores (elegidos por el usuario),
        ya que son contenido, no "chrome" de la aplicación."""
        self.scene.setBackgroundBrush(QBrush(QColor(colors["surface_alt"])))

    def _build_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Herramientas de esquema", self)
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)

        def add_tool(key, label, tip):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setStatusTip(tip)
            action.triggered.connect(lambda: self._set_tool(key))
            self.tool_group.addAction(action)
            toolbar.addAction(action)
            return action

        self.select_action = add_tool("select", "Seleccionar", "Seleccionar y mover formas")
        self.select_action.setChecked(True)
        toolbar.addSeparator()
        add_tool("rect", "▭ Rectángulo", "Añadir un rectángulo (clic en el lienzo)")
        add_tool("ellipse", "◯ Elipse", "Añadir una elipse (clic en el lienzo)")
        add_tool("diamond", "◇ Rombo", "Añadir un rombo (clic en el lienzo)")
        add_tool("note", "▤ Nota", "Añadir una nota adhesiva (clic en el lienzo)")
        toolbar.addSeparator()
        add_tool("connect", "↗ Conectar", "Clic en una forma y luego en otra para unirlas con una flecha")
        toolbar.addSeparator()

        color_action = QAction("🎨 Color", self)
        color_action.setStatusTip("Cambiar el color de la forma seleccionada")
        color_action.triggered.connect(self._recolor_selected)
        toolbar.addAction(color_action)

        delete_action = QAction("🗑 Eliminar", self)
        delete_action.setStatusTip("Eliminar la forma o conexión seleccionada (o pulsa Supr)")
        delete_action.triggered.connect(self.delete_selected)
        toolbar.addAction(delete_action)

        return toolbar

    def _set_tool(self, key):
        self.scene.active_tool = key
        self.view.setDragMode(QGraphicsView.RubberBandDrag if key == "select" else QGraphicsView.NoDrag)

    # ------------------------------------------------------------------ #
    # Sincronización con la base de datos: el anfitrión llama a estos
    # métodos tras crear/leer filas para reflejar el estado en el lienzo.
    # ------------------------------------------------------------------ #
    def add_shape_item(self, shape_id, shape_type, x, y, w, h, text, color) -> ShapeItem:
        item = ShapeItem(shape_type, QRectF(x, y, w, h), text, color, shape_id=shape_id)
        self.scene.addItem(item)
        item.signals.moved.connect(lambda: self.shapeMoved.emit(item))
        item.signals.editingFinished.connect(lambda: self.shapeRenamed.emit(item, item.label.toPlainText()))
        self._shape_items[shape_id] = item
        return item

    def add_connection_item(self, connection_id, from_shape_id, to_shape_id) -> ConnectionItem | None:
        a = self._shape_items.get(from_shape_id)
        b = self._shape_items.get(to_shape_id)
        if not a or not b:
            return None
        conn = ConnectionItem(a, b, connection_id=connection_id)
        self.scene.addItem(conn)
        self._connection_items.append(conn)
        return conn

    def clear_canvas(self):
        self.scene.clear()
        self._shape_items.clear()
        self._connection_items.clear()

    def delete_selected(self):
        for item in list(self.scene.selectedItems()):
            if isinstance(item, ShapeItem):
                for conn in list(item.connections):
                    self._remove_connection(conn)
                self._shape_items.pop(item.shape_id, None)
                self.scene.removeItem(item)
                self.shapeDeleted.emit(item)

    def _remove_connection(self, conn: ConnectionItem):
        conn.from_shape.connections.remove(conn)
        conn.to_shape.connections.remove(conn)
        if conn in self._connection_items:
            self._connection_items.remove(conn)
        self.scene.removeItem(conn)
        self.connectionDeleted.emit(conn)

    def _recolor_selected(self):
        shapes = [i for i in self.scene.selectedItems() if isinstance(i, ShapeItem)]
        if not shapes:
            return
        color = QColorDialog.getColor(shapes[0].color, self, "Color de la forma")
        if not color.isValid():
            return
        for shape in shapes:
            shape.set_color(color)
            self.shapeRecolored.emit(shape, color.name())

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.delete_selected()
        else:
            super().keyPressEvent(event)