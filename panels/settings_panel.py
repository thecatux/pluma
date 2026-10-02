"""Panel "Ajustes".

A diferencia del resto de paneles, no hay nada que cargar por
proyecto: los ajustes son globales a la aplicación (autoguardado,
editor, comportamiento) y se guardan con QSettings a través de
`app_settings`, igual que ya hacía el tema con `theme.ThemeController`.
También reúne aquí las acciones sobre la propia base de datos
(ubicación, copia de seguridad) que antes no tenían ningún sitio en
la interfaz.
"""

import os
import time

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
                                QLabel, QFrame, QScrollArea, QSlider, QSpinBox, QCheckBox,
                                QComboBox, QPushButton, QFileDialog, QMessageBox,
                                QSizePolicy, QColorDialog)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QFontDatabase, QDesktopServices

import icons
import theme
from app_settings import settings


class _ResponsiveCardGrid(QWidget):
    """Coloca las tarjetas en dos columnas cuando hay ancho de sobra y
    las apila en una sola cuando la ventana se estrecha, en vez de
    dejarlas siempre en una única columna fija con hueco muerto al
    lado. Las tarjetas se reparten fila a fila (no por bloques), así
    que la altura desigual entre ellas no deja columnas descompensadas.
    """

    BREAKPOINT = 760  # ancho por debajo del cual se cae a una columna

    def __init__(self, cards, parent=None):
        super().__init__(parent)
        self._cards = cards
        self._columns = 0
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(16)
        for card in self._cards:
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._relayout(2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        columns = 2 if self.width() >= self.BREAKPOINT else 1
        if columns != self._columns:
            self._relayout(columns)

    def _relayout(self, columns: int):
        self._columns = columns
        while self._grid.count():
            self._grid.takeAt(0)
        for col in range(2):
            self._grid.setColumnStretch(col, 1 if col < columns else 0)
        for index, card in enumerate(self._cards):
            row, col = divmod(index, columns)
            self._grid.addWidget(card, row, col, Qt.AlignTop)


class SettingsPanel(QWidget):
    def __init__(self, db, theme_controller=None, parent=None):
        super().__init__(parent)
        self.db = db
        self.theme_controller = theme_controller
        self._loading = False

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setMaximumWidth(1180)
        content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        outer = QVBoxLayout(content)
        outer.setContentsMargins(28, 22, 28, 24)
        outer.setSpacing(16)

        title = QLabel("Ajustes")
        title.setProperty("role", "section-title")
        outer.addWidget(title)
        subtitle = QLabel("Preferencias de la aplicación: se aplican a todos los proyectos.")
        subtitle.setProperty("role", "hint")
        outer.addWidget(subtitle)

        # Las tarjetas se reparten en una rejilla de dos columnas que se
        # aprovecha del ancho disponible en pantallas anchas y se apila
        # en una sola columna en ventanas estrechas (ver
        # `_ResponsiveCardGrid`), en vez de dejar una sola columna fija
        # con espacio vacío al lado.
        cards = [
            self._build_appearance_card(),
            self._build_editing_card(),
            self._build_editor_card(),
            self._build_data_card(),
        ]
        self._card_grid = _ResponsiveCardGrid(cards)
        outer.addWidget(self._card_grid)
        outer.addStretch(1)

        # A diferencia de otros paneles (Datos de la novela), Ajustes no
        # se centra: es una página de configuración de estilo
        # tradicional, anclada a la izquierda, que crece con el ancho de
        # la ventana (hasta un máximo razonable para que las líneas no
        # se hagan eternas) en lugar de quedarse en una columna fija con
        # hueco muerto al lado.
        wrapper = QWidget()
        wrapper_layout = QHBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(content, 1)
        scroll.setWidget(wrapper)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

        self._load_values()

    # ------------------------------------------------------------------ #
    # Tarjetas
    # ------------------------------------------------------------------ #
    def _card(self, heading: str, hint: str = "") -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setProperty("role", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(12)

        label = QLabel(heading)
        label.setStyleSheet("font-weight: 600; font-size: 11pt;")
        card_layout.addWidget(label)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setProperty("role", "hint")
            hint_label.setWordWrap(True)
            card_layout.addWidget(hint_label)
        return card, card_layout

    def _form(self) -> QFormLayout:
        """Formulario de estilo tradicional: etiquetas alineadas a la
        derecha, pegadas a su control, en lugar de sueltas a la
        izquierda con el control lejos en un bloque centrado."""
        form = QFormLayout()
        form.setSpacing(12)
        form.setHorizontalSpacing(16)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        return form

    def _build_appearance_card(self) -> QFrame:
        card, layout = self._card("Apariencia", "Elige cómo se ve Pluma.")
        if self.theme_controller is not None:
            form = self._form()
            self.theme_combo = QComboBox()
            self.theme_combo.setMinimumHeight(30)
            self.theme_combo.addItem(theme.MODE_LABELS["auto"], "auto")
            self.theme_combo.addItem(theme.MODE_LABELS["light"], "light")
            self.theme_combo.addItem(theme.MODE_LABELS["dark"], "dark")
            self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
            form.addRow("Tema", self.theme_combo)

            accent_row = QHBoxLayout()
            accent_row.setSpacing(8)
            self.accent_swatch = QPushButton()
            self.accent_swatch.setFixedSize(24, 24)
            self.accent_swatch.setAccessibleName("Elegir color de acento")
            self.accent_swatch.clicked.connect(self._choose_accent_color)
            accent_row.addWidget(self.accent_swatch)

            self.accent_value_label = QLabel()
            self.accent_value_label.setMinimumWidth(72)
            accent_row.addWidget(self.accent_value_label)

            choose_accent_button = QPushButton("Elegir...")
            choose_accent_button.clicked.connect(self._choose_accent_color)
            accent_row.addWidget(choose_accent_button)

            self.reset_accent_button = QPushButton("Restaurar")
            self.reset_accent_button.clicked.connect(
                lambda: self.theme_controller.set_accent_color(None)
            )
            accent_row.addWidget(self.reset_accent_button)
            accent_row.addStretch(1)
            form.addRow("Color de acento", accent_row)
            theme.signals.changed.connect(self._refresh_accent_display)
            self._refresh_accent_display()

            layout.addLayout(form)
        return card

    def _build_editing_card(self) -> QFrame:
        card, layout = self._card(
            "Autoguardado y comportamiento",
            "Pluma guarda automáticamente mientras escribes; aquí puedes ajustar cuánto espera "
            "tras dejar de teclear.",
        )
        form = self._form()

        autosave_row = QHBoxLayout()
        self.autosave_slider = QSlider(Qt.Horizontal)
        self.autosave_slider.setRange(200, 3000)
        self.autosave_slider.setSingleStep(100)
        self.autosave_slider.setPageStep(200)
        self.autosave_slider.valueChanged.connect(self._on_autosave_slider_changed)
        self.autosave_value_label = QLabel("")
        self.autosave_value_label.setMinimumWidth(70)
        autosave_row.addWidget(self.autosave_slider, 1)
        autosave_row.addWidget(self.autosave_value_label)
        form.addRow("Retardo de autoguardado", autosave_row)

        self.reading_speed_spin = QSpinBox()
        self.reading_speed_spin.setMinimumHeight(30)
        self.reading_speed_spin.setRange(100, 600)
        self.reading_speed_spin.setSingleStep(10)
        self.reading_speed_spin.setSuffix(" palabras/min")
        self.reading_speed_spin.valueChanged.connect(self._on_reading_speed_changed)
        form.addRow("Velocidad de lectura", self.reading_speed_spin)

        layout.addLayout(form)

        self.confirm_delete_check = QCheckBox("Pedir confirmación antes de eliminar")
        self.confirm_delete_check.toggled.connect(self._on_confirm_delete_toggled)
        layout.addWidget(self.confirm_delete_check)

        return card

    def _build_editor_card(self) -> QFrame:
        card, layout = self._card(
            "Editor de texto",
            "Fuente y tamaño con los que se abre el editor en capítulos y notas nuevas "
            "(el texto ya escrito conserva su propio formato).",
        )
        form = self._form()

        self.font_combo = QComboBox()
        self.font_combo.setMinimumHeight(32)
        self.font_combo.setMaxVisibleItems(14)
        self.font_combo.addItems(sorted(QFontDatabase.families()))
        self.font_combo.currentTextChanged.connect(self._on_font_family_changed)
        form.addRow("Tipo de letra", self.font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setMinimumHeight(32)
        self.font_size_spin.setRange(6, 72)
        self.font_size_spin.setSuffix(" pt")
        self.font_size_spin.valueChanged.connect(self._on_font_size_changed)
        form.addRow("Tamaño", self.font_size_spin)

        layout.addLayout(form)

        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        reset_button = QPushButton("Restaurar valores por defecto")
        reset_button.clicked.connect(self._on_reset_defaults)
        reset_row.addWidget(reset_button)
        layout.addLayout(reset_row)

        return card

    def _build_data_card(self) -> QFrame:
        card, layout = self._card(
            "Datos",
            "Todos tus proyectos viven en un único archivo de base de datos SQLite.",
        )

        path_row = QHBoxLayout()
        path_label = QLabel(self.db.path)
        path_label.setWordWrap(True)
        path_label.setStyleSheet("font-family: monospace;")
        path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        path_row.addWidget(path_label, 1)
        layout.addLayout(path_row)

        buttons_row = QHBoxLayout()
        open_folder_button = QPushButton("Abrir carpeta de datos")
        open_folder_button.clicked.connect(self._open_data_folder)
        backup_button = QPushButton("Crear copia de seguridad...")
        backup_button.setProperty("variant", "primary")
        backup_button.clicked.connect(self._create_backup)
        buttons_row.addWidget(open_folder_button)
        buttons_row.addWidget(backup_button)
        buttons_row.addStretch(1)
        layout.addLayout(buttons_row)

        backup_status_row = QHBoxLayout()
        backup_status_row.setContentsMargins(0, 0, 0, 0)
        backup_status_row.setSpacing(4)
        self.backup_status_icon = QLabel()
        self.backup_status_icon.setFixedSize(13, 13)
        self.backup_status_icon.setVisible(False)
        backup_status_row.addWidget(self.backup_status_icon)
        self.backup_status_label = QLabel("")
        self.backup_status_label.setProperty("role", "muted")
        backup_status_row.addWidget(self.backup_status_label)
        backup_status_row.addStretch(1)
        layout.addLayout(backup_status_row)

        return card

    # ------------------------------------------------------------------ #
    # Carga inicial de valores
    # ------------------------------------------------------------------ #
    def _load_values(self):
        self._loading = True
        if self.theme_controller is not None:
            index = self.theme_combo.findData(self.theme_controller.mode)
            self.theme_combo.setCurrentIndex(index if index >= 0 else 0)

        self.autosave_slider.setValue(settings.autosave_interval_ms)
        self._update_autosave_label(settings.autosave_interval_ms)
        self.reading_speed_spin.setValue(settings.reading_speed_wpm)
        self.confirm_delete_check.setChecked(settings.confirm_before_delete)

        font_index = self.font_combo.findText(settings.editor_font_family)
        if font_index >= 0:
            self.font_combo.setCurrentIndex(font_index)
        self.font_size_spin.setValue(settings.editor_font_size)
        self._loading = False

    # ------------------------------------------------------------------ #
    # Manejadores
    # ------------------------------------------------------------------ #
    def _on_theme_changed(self, _index):
        if self._loading or self.theme_controller is None:
            return
        self.theme_controller.set_mode(self.theme_combo.currentData())

    def _choose_accent_color(self):
        current = QColor(self.theme_controller.accent_color)
        selected = QColorDialog.getColor(current, self, "Color de acento")
        if selected.isValid():
            self.theme_controller.set_accent_color(selected.name())

    def _refresh_accent_display(self, *_args):
        color = self.theme_controller.accent_color
        self.accent_value_label.setText(color.upper())
        self.accent_swatch.setStyleSheet(
            f"background-color: {color}; border: 1px solid {theme.colors()['border_strong']}; "
            "border-radius: 5px; padding: 0;"
        )
        self.reset_accent_button.setEnabled(self.theme_controller.has_custom_accent)

    def _update_autosave_label(self, value: int):
        self.autosave_value_label.setText(f"{value / 1000:.1f} s")

    def _on_autosave_slider_changed(self, value: int):
        self._update_autosave_label(value)
        if self._loading:
            return
        settings.autosave_interval_ms = value

    def _on_reading_speed_changed(self, value: int):
        if self._loading:
            return
        settings.reading_speed_wpm = value

    def _on_confirm_delete_toggled(self, checked: bool):
        if self._loading:
            return
        settings.confirm_before_delete = checked

    def _on_font_family_changed(self, family: str):
        if self._loading or not family:
            return
        settings.editor_font_family = family

    def _on_font_size_changed(self, value: int):
        if self._loading:
            return
        settings.editor_font_size = value

    def _on_reset_defaults(self):
        settings.reset_to_defaults()
        self._load_values()

    # ------------------------------------------------------------------ #
    # Datos
    # ------------------------------------------------------------------ #
    def _open_data_folder(self):
        folder = os.path.dirname(os.path.abspath(self.db.path))
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _create_backup(self):
        default_name = f"pluma-copia-{time.strftime('%Y%m%d-%H%M%S')}.db"
        default_dir = os.path.dirname(os.path.abspath(self.db.path))
        dest_path, _ = QFileDialog.getSaveFileName(
            self, "Guardar copia de seguridad", os.path.join(default_dir, default_name),
            "Base de datos SQLite (*.db)",
        )
        if not dest_path:
            return
        try:
            self.db.backup_to(dest_path)
        except Exception as e:
            QMessageBox.warning(self, "No se pudo crear la copia", str(e))
            return
        self.backup_status_icon.setPixmap(icons.pixmap("check", theme.colors()["success"], size=13))
        self.backup_status_icon.setVisible(True)
        self.backup_status_label.setText(f"Copia guardada en {dest_path}")

    # ------------------------------------------------------------------ #
    # Interfaz esperada por MainWindow (no depende de un proyecto)
    # ------------------------------------------------------------------ #
    def load_project(self, project_id):
        pass