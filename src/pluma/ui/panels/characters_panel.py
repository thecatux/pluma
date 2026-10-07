"""Panel "Personajes".

Cada personaje tiene una ficha compuesta por tarjetas de campo
(nombre-de-campo + valor), inicializada con los campos habituales
(edad, apariencia, personalidad, motivación...) definidos en
`db.DEFAULT_CHARACTER_FIELDS`. El usuario puede renombrar cualquier
campo, borrar los que no necesite y añadir tantos campos propios como
quiera con "+ Añadir campo".
"""

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                                QAbstractItemView,
                                QListWidgetItem, QPushButton, QLabel, QLineEdit,
                                QSplitter, QMessageBox, QInputDialog,
                                QStackedWidget)
from PySide6.QtCore import Qt, QTimer

from pluma.core.app_settings import settings, signals as settings_signals
from pluma.core.db import DEFAULT_CHARACTER_FIELDS
from pluma.ui import icons, theme
from pluma.ui.panels.field_row import FieldList, FieldRow


class CharactersPanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = None
        self._current_character_id = None
        self._loading = False

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
        theme.signals.changed.connect(self._apply_empty_state_theme)

    def _apply_settings(self):
        self._save_timer.setInterval(settings.autosave_interval_ms)

    def _apply_empty_state_theme(self, *_args):
        self.empty_icon_label.setPixmap(icons.pixmap("user", theme.colors()["text_muted"], size=52))

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
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setSpacing(2)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.list_widget, 1)

        hint = QLabel("Arrastra un personaje para reordenarlo")
        hint.setProperty("role", "muted")
        left_layout.addWidget(hint)

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
        self.empty_icon_label = QLabel()
        self.empty_icon_label.setPixmap(icons.pixmap("user", theme.colors()["text_muted"], size=52))
        self.empty_icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_icon_label)
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
        self.avatar_label.setProperty("role", "avatar")
        header_row.addWidget(self.avatar_label)

        self.name_edit = QLineEdit()
        self.name_edit.setProperty("variant", "heading")
        self.name_edit.setPlaceholderText("Nombre del personaje")
        self.name_edit.textEdited.connect(self._on_name_edited)
        header_row.addWidget(self.name_edit, 1)
        right_layout.addLayout(header_row)

        self.fields = FieldList()
        self.fields.reordered.connect(self._on_fields_reordered)
        right_layout.addWidget(self.fields, 1)

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

    def _on_rows_moved(self, *_args):
        if self._loading or self.project_id is None:
            return
        ordered_ids = [
            self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.list_widget.count())
        ]
        self.db.reorder_characters(self.project_id, ordered_ids)
        self._reload_list(select_id=self._current_character_id)

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
        self.fields.clear()

    def _add_field_row(self, field_id, field_name, field_value):
        row = FieldRow(field_id, field_name, field_value, self._on_field_changed, self._on_field_delete)
        self.fields.add_row(row)
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

    def _on_field_changed(self, row: FieldRow):
        self._schedule_save()

    def _on_field_delete(self, row: FieldRow):
        if row.field_id is not None:
            self.db.delete_character_field(row.field_id)
        self.fields.remove_row(row)

    def _on_fields_reordered(self, ordered_ids):
        if self._current_character_id is not None:
            self.db.reorder_character_fields(self._current_character_id, ordered_ids)

    def _schedule_save(self):
        if self._loading or self._current_character_id is None:
            return
        self._save_timer.start()

    def _save_fields(self):
        if self._current_character_id is None:
            return
        self.db.update_character(self._current_character_id, name=self.name_edit.text().strip() or "Sin nombre")
        for row in self.fields.rows():
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