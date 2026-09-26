"""Panel "Escenas".

Muy similar a "Personajes" (ficha de campos clave/valor compactos, con
más libertad todavía ya que los campos sugeridos son solo un punto de
partida), pero añade un vínculo con uno o varios capítulos de la
novela. Ese vínculo se muestra como "chips" pulsables (en vez de una
lista de casillas) para verlo y editarlo de un vistazo, y la lista de
escenas de la izquierda muestra como subtítulo con qué capítulos está
relacionada cada una.
"""

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                                QListWidgetItem, QPushButton, QLabel, QLineEdit,
                                QSplitter, QMessageBox, QScrollArea, QInputDialog,
                                QGroupBox, QStackedWidget, QLayout, QFrame, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, QRect, QPoint, QSize

from db import DEFAULT_SCENE_FIELDS
from panels.characters_panel import _FieldRow
from app_settings import settings, signals as settings_signals


class FlowLayout(QLayout):
    """Layout que coloca sus widgets en filas y los envuelve a la
    siguiente cuando no caben, como las etiquetas de un buscador. Se usa
    para mostrar los capítulos vinculados a una escena como "chips" en
    vez de una lista de casillas, más compacto y fácil de escanear de
    un vistazo."""

    def __init__(self, parent=None, margin=0, spacing=6):
        super().__init__(parent)
        if parent is not None:
            self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)
        self._items = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect, test_only):
        left, top, right, bottom = self.getContentsMargins()
        effective = rect.adjusted(left, top, -right, -bottom)
        x, y = effective.x(), effective.y()
        line_height = 0
        spacing = self.spacing()

        for item in self._items:
            next_x = x + item.sizeHint().width() + spacing
            if next_x - spacing > effective.right() and line_height > 0:
                x = effective.x()
                y += line_height + spacing
                next_x = x + item.sizeHint().width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))
            x = next_x
            line_height = max(line_height, item.sizeHint().height())
        return y + line_height - rect.y() + bottom


class _ChapterChip(QPushButton):
    """Botón conmutable que representa un capítulo enlazable a la escena."""

    def __init__(self, chapter_id, title, checked, parent=None):
        super().__init__(title, parent)
        self.chapter_id = chapter_id
        self.setCheckable(True)
        self.setChecked(checked)
        self.setProperty("variant", "chip")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)


class ScenesPanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = None
        self._current_scene_id = None
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

        title = QLabel("Escenas")
        title.setProperty("role", "section-title")
        left_layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setSpacing(2)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.list_widget, 1)

        buttons_row = QHBoxLayout()
        self.add_button = QPushButton("+ Añadir")
        self.add_button.setProperty("variant", "primary")
        self.add_button.clicked.connect(self.add_scene)
        self.remove_button = QPushButton("Eliminar")
        self.remove_button.setProperty("variant", "danger")
        self.remove_button.clicked.connect(self.remove_current_scene)
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
        icon = QLabel("🎬")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 40pt;")
        layout.addWidget(icon)
        message = QLabel("Todavía no hay escenas")
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("font-size: 13pt; font-weight: 600;")
        layout.addWidget(message)
        subtitle = QLabel("Añade una escena y enlázala con sus capítulos.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setProperty("role", "hint")
        layout.addWidget(subtitle)
        start_button = QPushButton("+ Añadir escena")
        start_button.setProperty("variant", "primary")
        start_button.clicked.connect(self.add_scene)
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

        self.title_edit = QLineEdit()
        self.title_edit.setProperty("variant", "heading")
        self.title_edit.setPlaceholderText("Título de la escena")
        self.title_edit.textEdited.connect(self._on_title_edited)
        right_layout.addWidget(self.title_edit)

        chapters_box = QGroupBox("Capítulos relacionados")
        chapters_box_layout = QVBoxLayout(chapters_box)

        self.chapters_empty_label = QLabel("Este proyecto todavía no tiene capítulos.")
        self.chapters_empty_label.setProperty("role", "hint")
        chapters_box_layout.addWidget(self.chapters_empty_label)

        self.chapters_scroll = QScrollArea()
        self.chapters_scroll.setWidgetResizable(True)
        self.chapters_scroll.setFrameShape(QFrame.NoFrame)
        self.chapters_scroll.setMaximumHeight(96)
        self.chapters_flow_container = QWidget()
        self.chapters_flow = FlowLayout(self.chapters_flow_container, margin=2, spacing=6)
        self.chapters_scroll.setWidget(self.chapters_flow_container)
        chapters_box_layout.addWidget(self.chapters_scroll)

        right_layout.addWidget(chapters_box)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.fields_container = QWidget()
        self.fields_layout = QVBoxLayout(self.fields_container)
        self.fields_layout.setContentsMargins(2, 2, 10, 2)
        self.fields_layout.setSpacing(6)
        self.fields_layout.addStretch(1)
        self.scroll_area.setWidget(self.fields_container)
        right_layout.addWidget(self.scroll_area, 1)

        self.add_field_button = QPushButton("+ Añadir aspecto")
        self.add_field_button.clicked.connect(self.add_custom_field)
        right_layout.addWidget(self.add_field_button)

        return right

    # ------------------------------------------------------------------ #
    def load_project(self, project_id: int):
        self._flush_pending_save()
        self.project_id = project_id
        self._current_scene_id = None
        self._reload_list()

    def _reload_list(self, select_id=None):
        self._loading = True
        self.list_widget.clear()
        scenes = self.db.list_scenes(self.project_id) if self.project_id else []
        chapters_by_id = {c["id"]: c["title"] for c in self._current_chapters()}
        target_row = None
        for row in scenes:
            item = QListWidgetItem(self._scene_item_text(row["id"], row["title"], chapters_by_id))
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
            self._current_scene_id = None
            self._clear_fields()
            self._show_empty_state()

    def _current_chapters(self):
        return self.db.list_chapters(self.project_id) if self.project_id else []

    def _chapter_subtitle(self, scene_id, chapters_by_id=None):
        if chapters_by_id is None:
            chapters_by_id = {c["id"]: c["title"] for c in self._current_chapters()}
        linked_ids = self.db.get_scene_chapter_links(scene_id)
        if not linked_ids:
            return "Sin capítulos vinculados"
        names = [chapters_by_id.get(cid, "(capítulo eliminado)") or "(sin título)" for cid in linked_ids]
        return ", ".join(names)

    def _scene_item_text(self, scene_id, title, chapters_by_id=None):
        subtitle = self._chapter_subtitle(scene_id, chapters_by_id)
        return f"{title or '(sin título)'}\n     {subtitle}"

    def _refresh_current_list_item(self):
        item = self.list_widget.currentItem()
        if item is None or self._current_scene_id is None:
            return
        item.setText(self._scene_item_text(self._current_scene_id, self.title_edit.text()))

    def _on_selection_changed(self, current, previous):
        if self._loading:
            return
        self._flush_pending_save()
        if current is None:
            self._current_scene_id = None
            self._clear_fields()
            self._show_empty_state()
            return
        self._load_scene(current.data(Qt.UserRole))

    def _load_scene(self, scene_id: int):
        row = self.db.get_scene(scene_id)
        if row is None:
            return
        self._loading = True
        self._current_scene_id = scene_id
        self.title_edit.setText(row["title"])
        self._reload_chapter_links(scene_id)
        self._clear_fields()
        for field in self.db.list_scene_fields(scene_id):
            self._add_field_row(field["id"], field["field_name"], field["field_value"])
        self._loading = False
        self.right_stack.setCurrentIndex(1)
        self.remove_button.setEnabled(True)

    def _reload_chapter_links(self, scene_id):
        while self.chapters_flow.count():
            item = self.chapters_flow.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        linked_ids = set(self.db.get_scene_chapter_links(scene_id))
        chapters = self._current_chapters()

        self.chapters_empty_label.setVisible(not chapters)
        self.chapters_scroll.setVisible(bool(chapters))

        for chapter in chapters:
            chip = _ChapterChip(chapter["id"], chapter["title"] or "(sin título)",
                                 chapter["id"] in linked_ids)
            chip.toggled.connect(self._on_chapter_chip_toggled)
            self.chapters_flow.addWidget(chip)

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
    def _on_title_edited(self, text):
        if self._current_scene_id is None:
            return
        self._refresh_current_list_item()
        self._schedule_save()

    def _on_chapter_chip_toggled(self, _checked):
        if self._loading or self._current_scene_id is None:
            return
        linked = [
            self.chapters_flow.itemAt(i).widget().chapter_id
            for i in range(self.chapters_flow.count())
            if self.chapters_flow.itemAt(i).widget().isChecked()
        ]
        self.db.set_scene_chapter_links(self._current_scene_id, linked)
        self._refresh_current_list_item()

    def _on_field_changed(self, row: _FieldRow):
        self._schedule_save()

    def _on_field_delete(self, row: _FieldRow):
        if row.field_id is not None:
            self.db.delete_scene_field(row.field_id)
        self.fields_layout.removeWidget(row)
        row.setParent(None)
        if row in self._field_rows:
            self._field_rows.remove(row)

    def _schedule_save(self):
        if self._loading or self._current_scene_id is None:
            return
        self._save_timer.start()

    def _save_fields(self):
        if self._current_scene_id is None:
            return
        self.db.update_scene(self._current_scene_id, title=self.title_edit.text().strip() or "Sin título")
        for row in self._field_rows:
            self.db.update_scene_field(row.field_id, field_name=row.field_name(), field_value=row.field_value())

    def _flush_pending_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_fields()

    # ------------------------------------------------------------------ #
    def add_scene(self):
        if self.project_id is None:
            return
        self._flush_pending_save()
        new_id = self.db.create_scene(self.project_id, title="Nueva escena")
        self._reload_list(select_id=new_id)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def remove_current_scene(self):
        if self._current_scene_id is None:
            return
        if settings.confirm_before_delete:
            ret = QMessageBox.question(
                self, "Eliminar escena",
                "¿Seguro que quieres eliminar esta escena?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.db.delete_scene(self._current_scene_id)
        self._current_scene_id = None
        self._reload_list()

    def add_custom_field(self):
        if self._current_scene_id is None:
            return
        name, ok = QInputDialog.getText(self, "Nuevo aspecto", "Nombre del aspecto:")
        if not ok or not name.strip():
            return
        field_id = self.db.add_scene_field(self._current_scene_id, name.strip(), "")
        self._add_field_row(field_id, name.strip(), "")