"""Panel "Exportar".

Vuelca el texto de la novela a un archivo: todos los capítulos o solo
los que marque el usuario, con una portada opcional generada con los
datos de "Datos de la novela", en .docx, .pdf, .odt, .txt o Markdown.
La conversión vive en `exporter`; este panel solo recoge las opciones
y pide la ruta de destino.
"""

import re

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QFrame,
                                QScrollArea, QRadioButton, QListWidget, QListWidgetItem,
                                QCheckBox, QComboBox, QPushButton, QFileDialog, QMessageBox,
                                QSizePolicy)
from PySide6.QtCore import Qt

from pluma.core.exporter import FORMATS, ExportError, export_chapters

_INVALID_FILE_NAME_CHARS = re.compile(r'[\\/:*?"<>|]')


class ExportPanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setMaximumWidth(920)
        outer = QVBoxLayout(content)
        outer.setContentsMargins(28, 22, 28, 24)
        outer.setSpacing(16)

        title = QLabel("Exportar")
        title.setProperty("role", "section-title")
        outer.addWidget(title)
        subtitle = QLabel("Guarda el texto de tu novela en un archivo.")
        subtitle.setProperty("role", "hint")
        outer.addWidget(subtitle)

        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)
        chapters_card = self._build_chapters_card()
        options_card = self._build_options_card()
        for card in (chapters_card, options_card):
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        cards_row.addWidget(chapters_card, 3, Qt.AlignTop)
        options_column = QVBoxLayout()
        options_column.setSpacing(16)
        options_column.addWidget(options_card, 0, Qt.AlignTop)

        self.export_button = QPushButton("Exportar…")
        self.export_button.setProperty("variant", "primary")
        self.export_button.clicked.connect(self.export)
        options_column.addWidget(self.export_button, 0, Qt.AlignRight)
        options_column.addStretch(1)
        cards_row.addLayout(options_column, 2)
        outer.addLayout(cards_row)
        outer.addStretch(1)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(content, 0, Qt.AlignHCenter | Qt.AlignTop)
        scroll.setWidget(wrapper)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self._update_state()

    # ------------------------------------------------------------------ #
    # Construcción de la UI
    # ------------------------------------------------------------------ #
    def _card(self, heading: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setProperty("role", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)
        label = QLabel(heading)
        label.setStyleSheet("font-weight: 600; font-size: 11pt;")
        card_layout.addWidget(label)
        return card, card_layout

    def _build_chapters_card(self) -> QFrame:
        card, layout = self._card("Capítulos")

        self.all_radio = QRadioButton("Todos los capítulos")
        self.all_radio.setChecked(True)
        self.all_radio.toggled.connect(self._on_scope_changed)
        self.selected_radio = QRadioButton("Solo los capítulos marcados")
        layout.addWidget(self.all_radio)
        layout.addWidget(self.selected_radio)

        self.summary_label = QLabel("")
        self.summary_label.setProperty("role", "muted")
        layout.addWidget(self.summary_label)

        self.chapters_list = QListWidget()
        self.chapters_list.setMinimumHeight(200)
        self.chapters_list.setSpacing(2)
        self.chapters_list.itemChanged.connect(self._update_state)
        layout.addWidget(self.chapters_list)

        buttons_row = QHBoxLayout()
        self.check_all_button = QPushButton("Marcar todos")
        self.check_all_button.clicked.connect(lambda: self._set_all_checked(True))
        self.uncheck_all_button = QPushButton("Desmarcar todos")
        self.uncheck_all_button.clicked.connect(lambda: self._set_all_checked(False))
        buttons_row.addWidget(self.check_all_button)
        buttons_row.addWidget(self.uncheck_all_button)
        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)
        return card

    def _build_options_card(self) -> QFrame:
        card, layout = self._card("Opciones")

        form = QFormLayout()
        form.setSpacing(12)
        form.setHorizontalSpacing(16)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.format_combo = QComboBox()
        self.format_combo.setMinimumHeight(30)
        for extension, (label, _write) in FORMATS.items():
            self.format_combo.addItem(f"{label} (.{extension})", extension)
        form.addRow("Formato", self.format_combo)
        layout.addLayout(form)

        self.cover_check = QCheckBox("Añadir una portada con los datos de la novela")
        self.cover_check.setChecked(True)
        layout.addWidget(self.cover_check)
        hint = QLabel("Usa el título, autor/a, género y sinopsis de «Datos de la novela».")
        hint.setProperty("role", "hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return card

    # ------------------------------------------------------------------ #
    # Carga de proyecto / lista de capítulos
    # ------------------------------------------------------------------ #
    def load_project(self, project_id: int):
        self.project_id = project_id
        self._reload_chapters()

    def refresh(self):
        """Al volver al panel: recoge capítulos nuevos, borrados o
        renombrados sin perder las marcas que el usuario ya puso."""
        self._reload_chapters(checked=self._checked_ids())

    def _reload_chapters(self, checked: set[int] | frozenset[int] = frozenset()):
        chapters = self.db.list_chapters(self.project_id) if self.project_id else []
        self.chapters_list.blockSignals(True)
        self.chapters_list.clear()
        for row in chapters:
            item = QListWidgetItem(row["title"] or "(sin título)")
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if row["id"] in checked else Qt.Unchecked)
            item.setData(Qt.UserRole, row["id"])
            self.chapters_list.addItem(item)
        self.chapters_list.blockSignals(False)
        self._update_state()

    def _ids_with_state(self, state) -> set[int]:
        items = (self.chapters_list.item(i) for i in range(self.chapters_list.count()))
        return {item.data(Qt.UserRole) for item in items if item.checkState() == state}

    def _checked_ids(self) -> set[int]:
        return self._ids_with_state(Qt.Checked)

    def _set_all_checked(self, checked: bool):
        state = Qt.Checked if checked else Qt.Unchecked
        for i in range(self.chapters_list.count()):
            self.chapters_list.item(i).setCheckState(state)

    def _on_scope_changed(self, *_args):
        self._update_state()

    def _update_state(self, *_args):
        total = self.chapters_list.count()
        only_selected = self.selected_radio.isChecked()
        self.chapters_list.setEnabled(only_selected)
        self.check_all_button.setEnabled(only_selected)
        self.uncheck_all_button.setEnabled(only_selected)
        count = len(self._checked_ids()) if only_selected else total
        self.summary_label.setText(
            f"{count} de {total} capítulos para exportar" if total
            else "Este proyecto todavía no tiene capítulos."
        )
        self.export_button.setEnabled(count > 0)

    # ------------------------------------------------------------------ #
    # Exportación
    # ------------------------------------------------------------------ #
    def export(self):
        extension = self.format_combo.currentData()
        path = self._ask_destination(extension)
        if not path:
            return
        info = self.db.get_project_info(self.project_id) if self.cover_check.isChecked() else None
        try:
            export_chapters(path, extension, self._chapters_to_export(), info)
        except (ExportError, OSError) as error:
            QMessageBox.warning(self, "No se pudo exportar", str(error))
            return
        QMessageBox.information(self, "Exportación completada", f"Se ha guardado:\n{path}")

    def _chapters_to_export(self):
        chapters = self.db.list_chapters(self.project_id)
        if self.all_radio.isChecked():
            return chapters
        checked = self._checked_ids()
        return [row for row in chapters if row["id"] in checked]

    def _ask_destination(self, extension: str) -> str:
        label = FORMATS[extension][0]
        path, _filter = QFileDialog.getSaveFileName(
            self, "Exportar novela", f"{self._default_file_name()}.{extension}",
            f"{label} (*.{extension})")
        if path and not path.lower().endswith(f".{extension}"):
            path += f".{extension}"
        return path

    def _default_file_name(self) -> str:
        info = self.db.get_project_info(self.project_id)
        return _INVALID_FILE_NAME_CHARS.sub("", info["title"] or info["name"]).strip() or "novela"