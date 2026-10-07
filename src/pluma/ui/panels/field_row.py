"""Tarjeta de campo (nombre + valor + borrar) y lista reordenable de
tarjetas, compartidas por los paneles "Personajes" y "Escenas"."""

from PySide6.QtWidgets import (QApplication, QHBoxLayout, QVBoxLayout, QPushButton,
                                QLineEdit, QPlainTextEdit, QFrame, QLabel,
                                QScrollArea, QWidget)
from PySide6.QtCore import Qt, QSize, QMimeData, Signal
from PySide6.QtGui import QDrag

from pluma.ui import icons, theme


class _DragHandle(QLabel):
    """Tirador desde el que se arrastra una tarjeta para reordenarla."""

    def __init__(self, row):
        super().__init__(row)
        self.row = row
        self._press_pos = None
        self.setCursor(Qt.SizeAllCursor)
        self.setToolTip("Arrastra para reordenar")

    def mousePressEvent(self, event):
        self._press_pos = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self._press_pos is None or not event.buttons() & Qt.LeftButton:
            return
        distance = (event.position().toPoint() - self._press_pos).manhattanLength()
        if distance >= QApplication.startDragDistance():
            self._start_drag()

    def _start_drag(self):
        drag = QDrag(self)
        drag.setMimeData(QMimeData())
        drag.setPixmap(self.row.grab())
        drag.setHotSpot(self.mapTo(self.row, self._press_pos))
        self._press_pos = None
        drag.exec(Qt.MoveAction)


class FieldRow(QFrame):
    """Una tarjeta compacta de la ficha: nombre del campo + valor + borrar.

    El campo de valor crece con su contenido en lugar de reservar
    siempre un hueco fijo, para que fichas con muchos campos cortos
    ocupen poco espacio y las de texto largo se vean completas.
    """

    MIN_VALUE_HEIGHT = 30
    # Tope de seguridad, no de diseño: a partir de aquí el campo deja de
    # crecer y muestra su propia barra de scroll.
    MAX_VALUE_LINES = 100

    def __init__(self, field_id, field_name, field_value, on_change, on_delete, parent=None):
        super().__init__(parent)
        self.field_id = field_id
        self._on_change = on_change
        self._on_delete = on_delete
        self.setProperty("role", "field-row")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 6, 7)
        layout.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(4)
        self.drag_handle = _DragHandle(self)
        header.addWidget(self.drag_handle)
        self.name_edit = QLineEdit(field_name)
        self.name_edit.textEdited.connect(self._changed)
        # Un hijo que rechaza un arrastro no lo deja subir al padre, así que
        # los campos de texto no deben aceptar drops para que `FieldList`
        # reciba el de la tarjeta aunque se suelte encima de ellos.
        self.name_edit.setAcceptDrops(False)
        header.addWidget(self.name_edit, 1)

        self.delete_btn = QPushButton()
        self.delete_btn.setProperty("variant", "icon")
        self.delete_btn.setFixedSize(20, 20)
        self.delete_btn.setIconSize(QSize(13, 13))
        self.delete_btn.setToolTip("Eliminar este campo")
        self.delete_btn.clicked.connect(self._delete)
        header.addWidget(self.delete_btn)
        layout.addLayout(header)

        self.value_edit = QPlainTextEdit(field_value)
        self.value_edit.setPlaceholderText("Sin completar todavía…")
        self.value_edit.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.value_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.value_edit.setAcceptDrops(False)
        # Se emite al cambiar el texto y también al cambiar el ancho
        # (el reajuste de líneas), así que sustituye a `resizeEvent`.
        self.value_edit.document().documentLayout().documentSizeChanged.connect(self._autosize)
        self.value_edit.textChanged.connect(self._changed)
        layout.addWidget(self.value_edit)

        self._apply_theme()
        self._autosize()
        theme.signals.changed.connect(self._apply_theme)

    def _apply_theme(self, *_args):
        c = theme.colors()
        self.name_edit.setStyleSheet(
            "border: none; background: transparent; padding: 2px 0;"
            "font-weight: 600; font-size: 9.5pt; text-transform: uppercase; letter-spacing: 0.3px; "
            f"color: {c['text_secondary']};"
        )
        self.delete_btn.setIcon(icons.icon("x", c["text_muted"], size=13))
        self.drag_handle.setPixmap(icons.pixmap("grip", c["text_muted"], size=14))

    def _height_for_lines(self, lines: float) -> int:
        document = self.value_edit.document()
        line_height = self.value_edit.fontMetrics().lineSpacing()
        margins = 2 * (document.documentMargin() + self.value_edit.frameWidth())
        return int(lines * line_height + margins)

    def _autosize(self, *_args) -> None:
        # En QPlainTextEdit, `document().size().height()` cuenta líneas
        # (ya envueltas), no píxeles.
        lines = self.value_edit.document().size().height()
        needs_scroll = lines > self.MAX_VALUE_LINES
        self.value_edit.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if needs_scroll else Qt.ScrollBarAlwaysOff)
        height = self._height_for_lines(min(lines, self.MAX_VALUE_LINES))
        self.value_edit.setFixedHeight(max(self.MIN_VALUE_HEIGHT, height))

    def _changed(self, *_args):
        self._on_change(self)

    def _delete(self):
        self._on_delete(self)

    def field_name(self) -> str:
        return self.name_edit.text().strip() or "Campo"

    def field_value(self) -> str:
        return self.value_edit.toPlainText()


class FieldList(QScrollArea):
    """Lista vertical de `FieldRow` con scroll. Las tarjetas se reordenan
    arrastrándolas por su tirador; al soltar se emite `reordered` con los
    `field_id` en el nuevo orden."""

    reordered = Signal(list)

    AUTOSCROLL_MARGIN = 28
    AUTOSCROLL_STEP = 14

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[FieldRow] = []
        self.setWidgetResizable(True)
        self.setAcceptDrops(True)

        container = QWidget()
        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(2, 2, 10, 2)
        self._layout.setSpacing(6)
        self._layout.addStretch(1)
        self.setWidget(container)

        self._indicator = QFrame(container)
        self._indicator.setFixedHeight(2)
        self._indicator.hide()

    def rows(self) -> list[FieldRow]:
        return list(self._rows)

    def add_row(self, row: FieldRow):
        self._layout.insertWidget(len(self._rows), row)
        self._rows.append(row)

    def remove_row(self, row: FieldRow):
        self._layout.removeWidget(row)
        row.setParent(None)
        self._rows.remove(row)

    def clear(self):
        for row in self.rows():
            self.remove_row(row)

    # ------------------------------------------------------------------ #
    # Arrastrar y soltar
    # ------------------------------------------------------------------ #
    def _dragged_row(self, event):
        source = event.source()
        if isinstance(source, _DragHandle) and source.row in self._rows:
            return source.row
        return None

    def _drop_index(self, event) -> int:
        point = self.widget().mapFrom(self.viewport(), event.position().toPoint())
        for index, row in enumerate(self._rows):
            if point.y() < row.geometry().center().y():
                return index
        return len(self._rows)

    def dragEnterEvent(self, event):
        if self._dragged_row(event) is not None:
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._dragged_row(event) is None:
            return
        event.acceptProposedAction()
        self._autoscroll(event.position().toPoint().y())
        self._show_indicator(self._drop_index(event))

    def dragLeaveEvent(self, event):
        self._indicator.hide()

    def dropEvent(self, event):
        row = self._dragged_row(event)
        self._indicator.hide()
        if row is None:
            return
        event.acceptProposedAction()
        self._move_row(row, self._drop_index(event))

    def _move_row(self, row: FieldRow, index: int):
        old = self._rows.index(row)
        new = index - 1 if index > old else index
        if new == old:
            return
        self._rows.insert(new, self._rows.pop(old))
        self._layout.removeWidget(row)
        self._layout.insertWidget(new, row)
        self.reordered.emit([r.field_id for r in self._rows])

    def _show_indicator(self, index: int):
        spacing = self._layout.spacing()
        if index < len(self._rows):
            y = self._rows[index].geometry().top() - spacing // 2
        else:
            y = self._rows[-1].geometry().bottom() + spacing // 2
        ref = self._rows[0].geometry()
        self._indicator.setStyleSheet(f"background: {theme.colors()['text_secondary']};")
        self._indicator.setGeometry(ref.x(), y - 1, ref.width(), 2)
        self._indicator.raise_()
        self._indicator.show()

    def _autoscroll(self, y: int):
        bar = self.verticalScrollBar()
        if y < self.AUTOSCROLL_MARGIN:
            bar.setValue(bar.value() - self.AUTOSCROLL_STEP)
        elif y > self.viewport().height() - self.AUTOSCROLL_MARGIN:
            bar.setValue(bar.value() + self.AUTOSCROLL_STEP)