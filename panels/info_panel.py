"""Panel "Datos de la novela".

Ficha única (no hay lista de elementos, a diferencia del resto de
paneles) con la información general del proyecto: título, autor/a,
género, sinopsis y número de páginas. El título nace igual al nombre
del proyecto (ver `Database.create_project`) pero es editable de forma
independiente. Todo se autoguarda en SQLite igual que en el resto de
Pluma, con un pequeño retardo tras dejar de escribir.
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QLabel,
                                QLineEdit, QComboBox, QPlainTextEdit, QSpinBox,
                                QFrame, QScrollArea, QSizePolicy)
from PySide6.QtCore import Qt, QTimer

from db import DEFAULT_GENRES


class InfoPanel(QWidget):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.project_id = None
        self._loading = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self._save_info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        content = QWidget()
        content.setMaximumWidth(720)
        outer = QVBoxLayout(content)
        outer.setContentsMargins(28, 22, 28, 24)
        outer.setSpacing(16)

        title = QLabel("Datos de la novela")
        title.setProperty("role", "section-title")
        outer.addWidget(title)
        subtitle = QLabel("Información general de tu proyecto: aparecerá como portada y ficha de la obra.")
        subtitle.setProperty("role", "hint")
        subtitle.setWordWrap(True)
        outer.addWidget(subtitle)

        outer.addWidget(self._build_card())

        outer.addStretch(1)

        # Centra la tarjeta en vez de estirarla a todo el ancho de la
        # ventana, para que el formulario siga siendo cómodo de leer y
        # rellenar en pantallas anchas.
        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(content, 0, Qt.AlignHCenter | Qt.AlignTop)

        scroll.setWidget(wrapper)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)

    # ------------------------------------------------------------------ #
    def _build_card(self) -> QFrame:
        card = QFrame()
        card.setProperty("role", "card")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(24, 22, 24, 22)
        card_layout.setSpacing(16)

        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("Título de la novela")
        self.title_edit.textEdited.connect(self._schedule_save)
        form.addRow("Título", self.title_edit)

        self.author_edit = QLineEdit()
        self.author_edit.setPlaceholderText("Nombre del autor o autora")
        self.author_edit.textEdited.connect(self._schedule_save)
        form.addRow("Autor/a", self.author_edit)

        self.genre_combo = QComboBox()
        self.genre_combo.addItem("Sin especificar", "")
        for genre in DEFAULT_GENRES:
            self.genre_combo.addItem(genre, genre)
        self.genre_combo.currentIndexChanged.connect(self._schedule_save)
        form.addRow("Género", self.genre_combo)

        self.page_count_spin = QSpinBox()
        self.page_count_spin.setRange(0, 20000)
        self.page_count_spin.setSuffix(" páginas")
        self.page_count_spin.setSpecialValueText("Sin especificar")
        self.page_count_spin.valueChanged.connect(self._schedule_save)
        form.addRow("Extensión estimada", self.page_count_spin)

        card_layout.addLayout(form)

        divider = QFrame()
        divider.setProperty("role", "divider")
        card_layout.addWidget(divider)

        synopsis_label = QLabel("Sinopsis")
        synopsis_label.setStyleSheet("font-weight: 600;")
        card_layout.addWidget(synopsis_label)

        self.synopsis_edit = QPlainTextEdit()
        self.synopsis_edit.setPlaceholderText(
            "De qué trata la novela, en unas pocas frases..."
        )
        self.synopsis_edit.setMinimumHeight(140)
        self.synopsis_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.synopsis_edit.textChanged.connect(self._schedule_save)
        card_layout.addWidget(self.synopsis_edit)

        return card

    # ------------------------------------------------------------------ #
    # Ciclo de vida / carga de proyecto
    # ------------------------------------------------------------------ #
    def load_project(self, project_id: int):
        self._flush_pending_save()
        self.project_id = project_id
        self._load_info()

    def _load_info(self):
        if self.project_id is None:
            return
        row = self.db.get_project_info(self.project_id)
        if row is None:
            return
        self._loading = True
        self.title_edit.setText(row["title"] or row["name"])
        self.author_edit.setText(row["author"])
        genre_index = self.genre_combo.findData(row["genre"])
        self.genre_combo.setCurrentIndex(genre_index if genre_index >= 0 else 0)
        self.synopsis_edit.setPlainText(row["synopsis"])
        self.page_count_spin.setValue(row["page_count"])
        self._loading = False

    # ------------------------------------------------------------------ #
    # Autoguardado
    # ------------------------------------------------------------------ #
    def _schedule_save(self, *_args):
        if self._loading or self.project_id is None:
            return
        self._save_timer.start()

    def _save_info(self):
        if self.project_id is None:
            return
        self.db.update_project_info(
            self.project_id,
            title=self.title_edit.text().strip() or "Sin título",
            author=self.author_edit.text().strip(),
            genre=self.genre_combo.currentData() or "",
            synopsis=self.synopsis_edit.toPlainText(),
            page_count=self.page_count_spin.value(),
        )

    def _flush_pending_save(self):
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_info()
