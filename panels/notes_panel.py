"""Panel "Notas".

Apuntes libres sin ninguna relación estructural con capítulos,
personajes o escenas: ideas sueltas, referencias, recordatorios... Cada
nota tiene un título y contenido de texto enriquecido, con la fecha de
última modificación visible.
"""

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                                QListWidgetItem, QPushButton, QLabel, QLineEdit,
                                QSplitter, QMessageBox, QStackedWidget, QFrame)
from PySide6.QtCore import Qt, QTimer

from editor_widget import RichTextEditor
from app_settings import settings, signals as settings_signals


class NotesPanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = None
        self._current_note_id = None
        self._loading = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(settings.autosave_interval_ms)
        self._save_timer.timeout.connect(self._save_current_note)
        settings_signals.changed.connect(self._apply_settings)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self._build_list_column())
        splitter.addWidget(self._build_editor_column())
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

        title = QLabel("Notas")
        title.setProperty("role", "section-title")
        left_layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.list_widget, 1)

        buttons_row = QHBoxLayout()
        self.add_button = QPushButton("+ Añadir")
        self.add_button.setProperty("variant", "primary")
        self.add_button.clicked.connect(self.add_note)
        self.remove_button = QPushButton("Eliminar")
        self.remove_button.setProperty("variant", "danger")
        self.remove_button.clicked.connect(self.remove_current_note)
        buttons_row.addWidget(self.add_button, 1)
        buttons_row.addWidget(self.remove_button)
        left_layout.addLayout(buttons_row)

        return left

    def _build_editor_column(self) -> QWidget:
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._build_empty_state_widget())
        self.right_stack.addWidget(self._build_editor_widget())
        return self.right_stack

    def _build_empty_state_widget(self) -> QWidget:
        empty = QWidget()
        layout = QVBoxLayout(empty)
        layout.addStretch(1)
        icon = QLabel("🗒️")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 40pt;")
        layout.addWidget(icon)
        message = QLabel("Todavía no hay notas")
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("font-size: 13pt; font-weight: 600;")
        layout.addWidget(message)
        subtitle = QLabel("Apunta aquí cualquier idea suelta.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setProperty("role", "hint")
        layout.addWidget(subtitle)
        start_button = QPushButton("+ Añadir nota")
        start_button.setProperty("variant", "primary")
        start_button.clicked.connect(self.add_note)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(start_button)
        button_row.addStretch(1)
        layout.addSpacing(6)
        layout.addLayout(button_row)
        layout.addStretch(2)
        return empty

    def _build_editor_widget(self) -> QWidget:
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(28, 22, 28, 16)
        right_layout.setSpacing(8)

        self.title_edit = QLineEdit()
        self.title_edit.setProperty("variant", "heading")
        self.title_edit.setPlaceholderText("Título de la nota")
        self.title_edit.textEdited.connect(self._on_title_edited)
        right_layout.addWidget(self.title_edit)

        self.updated_label = QLabel("")
        self.updated_label.setProperty("role", "muted")
        right_layout.addWidget(self.updated_label)

        toolbar_frame = QFrame()
        toolbar_frame.setProperty("role", "toolbar-strip")
        toolbar_frame_layout = QVBoxLayout(toolbar_frame)
        toolbar_frame_layout.setContentsMargins(0, 0, 0, 0)

        self.editor = RichTextEditor(placeholder="Escribe tu nota aquí...")
        self.editor.contentChanged.connect(self._schedule_save)
        self.editor.text_edit.setFrameShape(QFrame.NoFrame)
        self.editor.text_edit.setStyleSheet(
            "QTextEdit { background: transparent; border: none; padding: 14px 6px; }"
        )
        # Solo se aplica aquí (construcción del panel, antes de cargar
        # ningún proyecto) y en `add_note` al crear una nota nueva.
        # Cambiar los Ajustes con una nota ya abierta (`_apply_settings`,
        # más abajo) no debe tocar el formato del texto ya escrito.
        self.editor.apply_default_font(settings.editor_font_family, settings.editor_font_size)
        toolbar_frame_layout.addWidget(self.editor.create_format_toolbar())
        right_layout.addWidget(toolbar_frame)
        right_layout.addWidget(self.editor, 1)

        return right

    def load_project(self, project_id: int):
        self._flush_pending_save()
        self.project_id = project_id
        self._current_note_id = None
        self._reload_list()

    def _reload_list(self, select_id=None):
        self._loading = True
        self.list_widget.clear()
        notes = self.db.list_notes(self.project_id) if self.project_id else []
        target_row = None
        for row in notes:
            item = QListWidgetItem(row["title"] or "(sin título)")
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
            self._current_note_id = None
            self._show_empty_state()
            self.updated_label.setText("")

    def _on_selection_changed(self, current, previous):
        if self._loading:
            return
        self._flush_pending_save()
        if current is None:
            self._current_note_id = None
            self._show_empty_state()
            return
        self._load_note(current.data(Qt.UserRole))

    def _load_note(self, note_id: int):
        row = self.db.get_note(note_id)
        if row is None:
            return
        self._loading = True
        self._current_note_id = note_id
        self.title_edit.setText(row["title"])
        self.editor.set_html(row["content"])
        self.updated_label.setText(f"Última edición: {row['updated_at']}" if row["updated_at"] else "")
        self._loading = False
        self.right_stack.setCurrentIndex(1)
        self.remove_button.setEnabled(True)

    def _show_empty_state(self):
        self.right_stack.setCurrentIndex(0)
        self.remove_button.setEnabled(False)

    def _schedule_save(self):
        if self._loading or self._current_note_id is None:
            return
        self._save_timer.start()

    def _on_title_edited(self, text):
        if self._current_note_id is None:
            return
        current_item = self.list_widget.currentItem()
        if current_item is not None:
            current_item.setText(text or "(sin título)")
        self._schedule_save()

    def _save_current_note(self):
        if self._current_note_id is None:
            return
        self.db.update_note(
            self._current_note_id,
            title=self.title_edit.text().strip() or "Sin título",
            content=self.editor.to_html(),
        )
        row = self.db.get_note(self._current_note_id)
        if row is not None:
            self.updated_label.setText(f"Última edición: {row['updated_at']}")

    def _flush_pending_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_current_note()

    def add_note(self):
        if self.project_id is None:
            return
        self._flush_pending_save()
        new_id = self.db.create_note(self.project_id, title="Nueva nota")
        self._reload_list(select_id=new_id)
        self.editor.apply_default_font(settings.editor_font_family, settings.editor_font_size)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def remove_current_note(self):
        if self._current_note_id is None:
            return
        if settings.confirm_before_delete:
            ret = QMessageBox.question(
                self, "Eliminar nota",
                "¿Seguro que quieres eliminar esta nota?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.db.delete_note(self._current_note_id)
        self._current_note_id = None
        self._reload_list()