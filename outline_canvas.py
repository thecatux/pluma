"""Lienzo de la sección "Línea temporal".

Cada evento de la historia es un bloque (`_BlockCard`) con título,
fecha/orden libre, grupo opcional (capítulo, escena o lo que el
usuario quiera escribir) y una nota. Los bloques viven en una sola
fila que se puede arrastrar para reordenar (usando el propio
QListWidget en modo icono con reordenado interno, sin reinventar
drag&drop a mano). El color de cada bloque se deriva de su grupo, así
que agrupar es tan simple como escribir el mismo nombre en varios
bloques; unos chips encima de la fila permiten filtrar por grupo.

Igual que el resto de Pluma, este widget no toca SQLite: emite
señales de alto nivel para que `OutlinePanel` las traduzca a
operaciones de `Database`.
"""

from PySide6.QtWidgets import (QWidget, QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                                QLineEdit, QPlainTextEdit, QComboBox, QPushButton,
                                QListWidget, QListWidgetItem, QListView, QAbstractItemView,
                                QSizePolicy)
from PySide6.QtCore import Qt, QTimer, Signal

import theme
from app_settings import settings, signals as settings_signals

GROUP_COLORS = ["#4C6EF5", "#F76707", "#2F9E44", "#E03131", "#AE3EC9", "#0CA678", "#F59F00", "#1971C2"]
NO_GROUP_COLOR = "#ADB5BD"
NO_GROUP_LABEL = "Sin grupo"


def _color_for_group(group_name: str) -> str:
    if not group_name:
        return NO_GROUP_COLOR
    return GROUP_COLORS[sum(ord(ch) for ch in group_name) % len(GROUP_COLORS)]


class _BlockCard(QFrame):
    """Tarjeta de un evento. Se autoguarda con el mismo retardo que el
    resto de Pluma; los cambios de grupo se reflejan de inmediato en
    el color del borde y en los chips de filtro, sin esperar al
    guardado."""

    FIXED_WIDTH = 240
    MIN_NOTE_HEIGHT = 28
    MAX_NOTE_HEIGHT = 160

    def __init__(self, block_id, title, date_label, group_name, description,
                 known_groups, on_change, on_delete, on_group_edited, parent=None):
        super().__init__(parent)
        self.block_id = block_id
        self._on_change = on_change
        self._on_delete = on_delete
        self._on_group_edited = on_group_edited
        self.setFixedWidth(self.FIXED_WIDTH)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(settings.autosave_interval_ms)
        self._save_timer.timeout.connect(self._save)
        settings_signals.changed.connect(self._on_settings_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 10, 10)
        layout.setSpacing(5)

        header = QHBoxLayout()
        self.title_edit = QLineEdit(title)
        self.title_edit.setPlaceholderText("Título del evento")
        self.title_edit.setStyleSheet("border: none; background: transparent; font-weight: 600;")
        self.title_edit.textEdited.connect(self._schedule_save)
        header.addWidget(self.title_edit, 1)
        delete_btn = QPushButton("✕")
        delete_btn.setProperty("variant", "icon")
        delete_btn.setFixedSize(18, 18)
        delete_btn.setToolTip("Eliminar este evento")
        delete_btn.clicked.connect(lambda: self._on_delete(self.block_id))
        header.addWidget(delete_btn)
        layout.addLayout(header)

        self.date_edit = QLineEdit(date_label)
        self.date_edit.setPlaceholderText("Fecha u orden (opcional)")
        self.date_edit.textEdited.connect(self._schedule_save)
        layout.addWidget(self.date_edit)

        self.group_combo = QComboBox()
        self.group_combo.setEditable(True)
        self.group_combo.setInsertPolicy(QComboBox.NoInsert)
        self.group_combo.lineEdit().setPlaceholderText(NO_GROUP_LABEL)
        self._reload_group_suggestions(known_groups)
        self.group_combo.setCurrentText(group_name)
        self.group_combo.editTextChanged.connect(self._on_group_text_changed)
        layout.addWidget(self.group_combo)

        self.note_edit = QPlainTextEdit(description)
        self.note_edit.setPlaceholderText("Notas del evento (opcional)")
        self.note_edit.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.note_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.note_edit.textChanged.connect(self._autosize_note)
        self.note_edit.textChanged.connect(self._schedule_save)
        layout.addWidget(self.note_edit)

        self._group_color = _color_for_group(group_name)
        self._apply_theme()
        self._autosize_note()
        theme.signals.changed.connect(self._apply_theme)

    # -- estilo ---------------------------------------------------------- #
    def _apply_theme(self, *_args):
        c = theme.colors()
        self.setStyleSheet(
            f"_BlockCard {{ background: {c['surface']}; border: 1px solid {c['border']}; "
            f"border-left: 4px solid {self._group_color}; border-radius: {theme.RADIUS['md']}px; }}"
        )

    def _autosize_note(self):
        target = int(self.note_edit.document().size().height()) + 8
        target = max(self.MIN_NOTE_HEIGHT, min(self.MAX_NOTE_HEIGHT, target))
        self.note_edit.setFixedHeight(target)

    def _reload_group_suggestions(self, known_groups):
        current = self.group_combo.currentText() if self.group_combo.count() else ""
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItem("")
        self.group_combo.addItems(sorted(g for g in known_groups if g))
        self.group_combo.setCurrentText(current)
        self.group_combo.blockSignals(False)

    # -- edición ----------------------------------------------------------#
    def current_group(self) -> str:
        return self.group_combo.currentText().strip()

    def _on_group_text_changed(self, text):
        self._group_color = _color_for_group(text.strip())
        self._apply_theme()
        self._on_group_edited()
        self._schedule_save()

    def _on_settings_changed(self):
        self._save_timer.setInterval(settings.autosave_interval_ms)

    def _schedule_save(self, *_args):
        self._save_timer.start()

    def _save(self):
        self._on_change(self.block_id, {
            "title": self.title_edit.text().strip() or "Nuevo evento",
            "date_label": self.date_edit.text().strip(),
            "group_name": self.current_group(),
            "description": self.note_edit.toPlainText(),
        })

    def flush_pending_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save()


class _TimelineList(QListWidget):
    """QListWidget en modo icono horizontal: el reordenado interno de
    Qt ya resuelve el arrastrar-y-soltar, así que no hace falta
    implementar drag&drop a mano."""

    reordered = Signal()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.reordered.emit()


class TimelineCanvas(QWidget):
    addRequested = Signal()
    blockChanged = Signal(int, dict)
    blockDeleteRequested = Signal(int)
    blocksReordered = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_filters: set[str] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 14)
        layout.setSpacing(10)
        layout.addLayout(self._build_top_bar())

        self.list_widget = _TimelineList()
        self.list_widget.setObjectName("TimelineList")
        self.list_widget.setViewMode(QListView.IconMode)
        self.list_widget.setFlow(QListView.LeftToRight)
        self.list_widget.setWrapping(True)
        self.list_widget.setResizeMode(QListView.Adjust)
        self.list_widget.setMovement(QListView.Snap)
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setSelectionMode(QAbstractItemView.NoSelection)
        self.list_widget.setSpacing(12)
        self.list_widget.reordered.connect(self._on_reordered)
        layout.addWidget(self.list_widget, 1)

    def _build_top_bar(self) -> QHBoxLayout:
        top_bar = QHBoxLayout()
        top_bar.setSpacing(8)
        self.add_button = QPushButton("+ Añadir evento")
        self.add_button.setProperty("variant", "primary")
        self.add_button.clicked.connect(self.addRequested.emit)
        top_bar.addWidget(self.add_button)

        self.chips_layout = QHBoxLayout()
        self.chips_layout.setSpacing(6)
        top_bar.addLayout(self.chips_layout)
        top_bar.addStretch(1)
        return top_bar

    # ------------------------------------------------------------------ #
    # Sincronización con la base de datos
    # ------------------------------------------------------------------ #
    def set_blocks(self, rows):
        self.list_widget.clear()
        known_groups = sorted({row["group_name"] for row in rows if row["group_name"]})
        for row in rows:
            self._add_card(row["id"], row["title"], row["date_label"],
                            row["group_name"], row["description"], known_groups)
        self._refresh_chips()

    def _add_card(self, block_id, title, date_label, group_name, description, known_groups):
        card = _BlockCard(block_id, title, date_label, group_name, description, known_groups,
                           on_change=self.blockChanged.emit,
                           on_delete=self.blockDeleteRequested.emit,
                           on_group_edited=self._refresh_chips)
        item = QListWidgetItem()
        item.setData(Qt.UserRole, block_id)
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self.list_widget.addItem(item)
        item.setSizeHint(card.sizeHint())
        self.list_widget.setItemWidget(item, card)
        return card

    def flush_pending_saves(self):
        for i in range(self.list_widget.count()):
            card = self.list_widget.itemWidget(self.list_widget.item(i))
            if card is not None:
                card.flush_pending_save()

    def _on_reordered(self):
        ids = [self.list_widget.item(i).data(Qt.UserRole) for i in range(self.list_widget.count())]
        self.blocksReordered.emit(ids)

    # ------------------------------------------------------------------ #
    # Filtro por grupo
    # ------------------------------------------------------------------ #
    def _current_groups(self):
        names, has_ungrouped = set(), False
        for i in range(self.list_widget.count()):
            card = self.list_widget.itemWidget(self.list_widget.item(i))
            if card is None:
                continue
            name = card.current_group()
            if name:
                names.add(name)
            else:
                has_ungrouped = True
        return sorted(names), has_ungrouped

    def _refresh_chips(self):
        while self.chips_layout.count():
            widget = self.chips_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()

        groups, has_ungrouped = self._current_groups()
        self._active_filters &= set(groups) | ({NO_GROUP_LABEL} if has_ungrouped else set())
        labels = groups + ([NO_GROUP_LABEL] if has_ungrouped else [])
        for label in labels:
            chip = QPushButton(label)
            chip.setProperty("variant", "chip")
            chip.setCheckable(True)
            chip.setChecked(label in self._active_filters)
            chip.toggled.connect(lambda checked, name=label: self._on_chip_toggled(name, checked))
            self.chips_layout.addWidget(chip)

        for i in range(self.list_widget.count()):
            card = self.list_widget.itemWidget(self.list_widget.item(i))
            if isinstance(card, _BlockCard):
                card._reload_group_suggestions(groups)
        self._apply_filters()

    def _on_chip_toggled(self, name, checked):
        if checked:
            self._active_filters.add(name)
        else:
            self._active_filters.discard(name)
        self._apply_filters()

    def _apply_filters(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            card = self.list_widget.itemWidget(item)
            if card is None:
                continue
            name = card.current_group() or NO_GROUP_LABEL
            visible = not self._active_filters or name in self._active_filters
            item.setHidden(not visible)