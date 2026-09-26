"""Panel "Personajes".

Cada personaje tiene una ficha compuesta por tarjetas de campo
(nombre-de-campo + valor), inicializada con los campos habituales
(edad, apariencia, personalidad, motivación...) definidos en
`db.DEFAULT_CHARACTER_FIELDS`. El usuario puede renombrar cualquier
campo, borrar los que no necesite y añadir tantos campos propios como
quiera con "+ Añadir campo".
"""

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                                QListWidgetItem, QPushButton, QLabel, QLineEdit,
                                QSplitter, QMessageBox, QScrollArea, QPlainTextEdit,
                                QInputDialog, QFrame, QStackedWidget)
from PySide6.QtCore import Qt, QTimer

import theme
from db import DEFAULT_CHARACTER_FIELDS
from app_settings import settings, signals as settings_signals


class _FieldRow(QFrame):
    """Una tarjeta compacta de la ficha: nombre del campo + valor + borrar.

    El campo de valor se ajusta automáticamente a su contenido (entre
    una y varias líneas) en lugar de reservar siempre un hueco fijo,
    para que fichas con muchos campos cortos ocupen mucho menos
    espacio y sean más rápidas de escanear.
    """

    MIN_VALUE_HEIGHT = 30
    MAX_VALUE_HEIGHT = 200

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

        self.delete_btn = QPushButton("✕")
        self.delete_btn.setProperty("variant", "icon")
        self.delete_btn.setFixedSize(18, 18)
        self.delete_btn.setToolTip("Eliminar este campo")
        self.delete_btn.clicked.connect(lambda: on_delete(self))
        header.addWidget(self.delete_btn)
        layout.addLayout(header)

        self.value_edit = QPlainTextEdit(field_value)
        self.value_edit.setPlaceholderText("Sin completar todavía…")
        self.value_edit.setStyleSheet("background: transparent; border: none; padding: 0;")
        self.value_edit.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.value_edit.textChanged.connect(self._autosize)
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

    def _autosize(self):
        target = int(self.value_edit.document().size().height()) + 10
        target = max(self.MIN_VALUE_HEIGHT, min(self.MAX_VALUE_HEIGHT, target))
        self.value_edit.setFixedHeight(target)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # El ancho disponible cambia el número de líneas envueltas, así
        # que hay que recalcular la altura tras cada redimensionado.
        self._autosize()

    def _changed(self, *_args):
        self._on_change(self)

    def field_name(self) -> str:
        return self.name_edit.text().strip() or "Campo"

    def field_value(self) -> str:
        return self.value_edit.toPlainText()


class CharactersPanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = None
        self._current_character_id = None
        self._loading = False
        self._field_rows: list[_FieldRow] = []

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(settings.autosave_interval_ms)
        self._save_timer.timeout.connect(self._save_fields)
        settings_signals.changed.connect(self._apply_settings)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self._build_list_column())
        splitter.addWidget(self._build_detail_column())
        splitter.setSizes([220, 660])
        splitter.setChildrenCollapsible(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._show_empty_state()

    def _apply_settings(self):
        self._save_timer.setInterval(settings.autosave_interval_ms)

    # ------------------------------------------------------------------ #
    def _build_list_column(self) -> QWidget:
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 16, 10, 14)
        left_layout.setSpacing(10)

        title = QLabel("Personajes")
        title.setProperty("role", "section-title")
        left_layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.list_widget, 1)

        buttons_row = QHBoxLayout()
        self.add_button = QPushButton("+ Añadir")
        self.add_button.setProperty("variant", "primary")
        self.add_button.clicked.connect(self.add_character)
        self.remove_button = QPushButton("Eliminar")
        self.remove_button.setProperty("variant", "danger")
        self.remove_button.clicked.connect(self.remove_current_character)
        buttons_row.addWidget(self.add_button, 1)
        buttons_row.addWidget(self.remove_button)
        left_layout.addLayout(buttons_row)

        return left

    def _build_detail_column(self) -> QWidget:
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._build_empty_state_widget())
        self.right_stack.addWidget(self._build_form_widget())
        return self.right_stack

    def _build_empty_state_widget(self) -> QWidget:
        empty = QWidget()
        layout = QVBoxLayout(empty)
        layout.addStretch(1)
        icon = QLabel("🧑")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 40pt;")
        layout.addWidget(icon)
        message = QLabel("Todavía no hay personajes")
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("font-size: 13pt; font-weight: 600;")
        layout.addWidget(message)
        subtitle = QLabel("Crea una ficha para dar vida a tu elenco.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setProperty("role", "hint")
        layout.addWidget(subtitle)
        start_button = QPushButton("+ Añadir personaje")
        start_button.setProperty("variant", "primary")
        start_button.clicked.connect(self.add_character)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(start_button)
        button_row.addStretch(1)
        layout.addSpacing(6)
        layout.addLayout(button_row)
        layout.addStretch(2)
        return empty

    def _build_form_widget(self) -> QWidget:
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 22, 24, 16)
        right_layout.setSpacing(12)

        header_row = QHBoxLayout()
        self.avatar_label = QLabel("?")
        self.avatar_label.setFixedSize(48, 48)
        self.avatar_label.setAlignment(Qt.AlignCenter)
        self.avatar_label.setStyleSheet(
            "background: #EDF1FF; color: #4059DB; border-radius: 24px; font-size: 16pt; font-weight: 700;"
        )
        header_row.addWidget(self.avatar_label)

        self.name_edit = QLineEdit()
        self.name_edit.setProperty("variant", "heading")
        self.name_edit.setPlaceholderText("Nombre del personaje")
        self.name_edit.textEdited.connect(self._on_name_edited)
        header_row.addWidget(self.name_edit, 1)
        right_layout.addLayout(header_row)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.fields_container = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(2, 2, 10, 2)
        self.fields_layout.setSpacing(6)
        self.fields_layout.addStretch(1)
        self.scroll_area.setWidget(self.fields_container)
        right_layout.addWidget(self.scroll_area, 1)

        self.add_field_button = QPushButton("+ Añadir campo")
        self.add_field_button.clicked.connect(self.add_custom_field)
        right_layout.addWidget(self.add_field_button)

        return right

    # ------------------------------------------------------------------ #
    def load_project(self, project_id: int):
        self._flush_pending_save()
        self.project_id = project_id
        self._current_character_id = None
        self._reload_list()

    def _reload_list(self, select_id=None):
        self._loading = True
        self.list_widget.clear()
        characters = self.db.list_characters(self.project_id) if self.project_id else []
        target_row = None
        for row in characters:
            item = QListWidgetItem(row["name"] or "(sin nombre)")
            item.setData(Qt.UserRole, row["id"])
            self.list_widget.addItem(item)
            if select_id is not None and row["id"] == select_id:
                target_row = self.list_widget.count() - 1
        self._loading = False
        if target_row is not None:
            self.list_widget.setCurrentRow(target_row)
        elif self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        else:
            self._current_character_id = None
            self._clear_fields()
            self._show_empty_state()

    def _on_selection_changed(self, current, previous):
        if self._loading:
            return
        self._flush_pending_save()
        if current is None:
            self._current_character_id = None
            self._clear_fields()
            self._show_empty_state()
            return
        self._load_character(current.data(Qt.UserRole))

    def _load_character(self, character_id: int):
        row = self.db.get_character(character_id)
        if row is None:
            return
        self._loading = True
        self._current_character_id = character_id
        self.name_edit.setText(row["name"])
        self._update_avatar(row["name"])
        self._clear_fields()
        for field in self.db.list_character_fields(character_id):
            self._add_field_row(field["id"], field["field_name"], field["field_value"])
        self._loading = False
        self.right_stack.setCurrentIndex(1)
        self.remove_button.setEnabled(True)

    def _update_avatar(self, name: str):
        initial = (name or "?").strip()[:1].upper() or "?"
        self.avatar_label.setText(initial)

    def _show_empty_state(self):
        self.right_stack.setCurrentIndex(0)
        self.remove_button.setEnabled(False)

    def _clear_fields(self):
        for row in self._field_rows:
            row.setParent(None)
        self._field_rows = []

    def _add_field_row(self, field_id, field_name, field_value):
        row = _FieldRow(field_id, field_name, field_value, self._on_field_changed, self._on_field_delete)
        self.fields_layout.insertWidget(self.fields_layout.count() - 1, row)
        self._field_rows.append(row)
        return row

    # ------------------------------------------------------------------ #
    # Autoguardado
    # ------------------------------------------------------------------ #
    def _on_name_edited(self, text):
        if self._current_character_id is None:
            return
        current_item = self.list_widget.currentItem()
        if current_item is not None:
            current_item.setText(text or "(sin nombre)")
        self._update_avatar(text)
        self._schedule_save()

    def _on_field_changed(self, row: _FieldRow):
        self._schedule_save()

    def _on_field_delete(self, row: _FieldRow):
        if row.field_id is not None:
            self.db.delete_character_field(row.field_id)
        self.fields_layout.removeWidget(row)
        row.setParent(None)
        if row in self._field_rows:
            self._field_rows.remove(row)

    def _schedule_save(self):
        if self._loading or self._current_character_id is None:
            return
        self._save_timer.start()

    def _save_fields(self):
        if self._current_character_id is None:
            return
        self.db.update_character(self._current_character_id, name=self.name_edit.text().strip() or "Sin nombre")
        for row in self._field_rows:
            self.db.update_character_field(row.field_id, field_name=row.field_name(), field_value=row.field_value())

    def _flush_pending_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_fields()

    # ------------------------------------------------------------------ #
    # Acciones
    # ------------------------------------------------------------------ #
    def add_character(self):
        if self.project_id is None:
            return
        self._flush_pending_save()
        new_id = self.db.create_character(self.project_id, name="Nuevo personaje")
        self._reload_list(select_id=new_id)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    def remove_current_character(self):
        if self._current_character_id is None:
            return
        if settings.confirm_before_delete:
            ret = QMessageBox.question(
                self, "Eliminar personaje",
                "¿Seguro que quieres eliminar este personaje?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.db.delete_character(self._current_character_id)
        self._current_character_id = None
        self._reload_list()

    def add_custom_field(self):
        if self._current_character_id is None:
            return
        name, ok = QInputDialog.getText(self, "Nuevo campo", "Nombre del campo:")
        if not ok or not name.strip():
            return
        field_id = self.db.add_character_field(self._current_character_id, name.strip(), "")
        self._add_field_row(field_id, name.strip(), "")