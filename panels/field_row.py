"""Tarjeta de campo (nombre + valor + borrar) compartida por los paneles
"Personajes" y "Escenas"."""

from PySide6.QtWidgets import (QHBoxLayout, QVBoxLayout, QPushButton, QLineEdit,
                                QPlainTextEdit, QFrame)
from PySide6.QtCore import Qt, QSize

import icons
import theme


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
        self.setProperty("role", "field-row")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 6, 7)
        layout.setSpacing(3)

        header = QHBoxLayout()
        header.setSpacing(4)
        self.name_edit = QLineEdit(field_name)
        self.name_edit.textEdited.connect(self._changed)
        header.addWidget(self.name_edit, 1)

        self.delete_btn = QPushButton()
        self.delete_btn.setProperty("variant", "icon")
        self.delete_btn.setFixedSize(20, 20)
        self.delete_btn.setIconSize(QSize(13, 13))
        self.delete_btn.setToolTip("Eliminar este campo")
        self.delete_btn.clicked.connect(lambda: on_delete(self))
        header.addWidget(self.delete_btn)
        layout.addLayout(header)

        self.value_edit = QPlainTextEdit(field_value)
        self.value_edit.setPlaceholderText("Sin completar todavía…")
        self.value_edit.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.value_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
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

    def field_name(self) -> str:
        return self.name_edit.text().strip() or "Campo"

    def field_value(self) -> str:
        return self.value_edit.toPlainText()