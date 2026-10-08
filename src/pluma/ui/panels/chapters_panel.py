"""Panel "Capítulos".

Lista de capítulos en la izquierda (reordenable libremente por
arrastre gracias a QAbstractItemView.InternalMove), con el número de
orden y el recuento de palabras de cada uno como referencia rápida.
A la derecha, un área de escritura centrada en el contenido: título
grande, sinopsis opcional plegable y el editor de texto enriquecido.
Todo se autoguarda en SQLite al escribir (con un pequeño retardo para
no golpear la base de datos en cada pulsación de tecla) y un indicador
discreto confirma cuándo se ha guardado.

Incluye además un "modo enfoque" (botón o Ctrl+Shift+F) que oculta la
lista de capítulos y la barra de formato para que lo único visible sea
el propio texto, con márgenes que se ensanchan según el ancho de la
ventana para mantener una columna de lectura cómoda en vez de líneas
que ocupen todo el ancho de la pantalla. Esos márgenes solo afectan a
la columna de texto (`_content_layout`): la cabecera con el título y
el propio botón de modo enfoque vive en un layout aparte con márgenes
fijos, así que el botón no se desplaza hacia el centro al activarlo.
"""

from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QListWidget,
                                QListWidgetItem, QAbstractItemView, QPushButton,
                                QLabel, QLineEdit, QSplitter, QMessageBox, QPlainTextEdit,
                                QStackedWidget, QFrame, QToolButton)
from PySide6.QtCore import Qt, QTimer, QEvent, QSize
from PySide6.QtGui import QKeySequence, QShortcut

from pluma.core.app_settings import settings, signals as settings_signals
from pluma.ui import icons, theme
from pluma.ui.editor_widget import RichTextEditor

# Márgenes del área de escritura en modo normal y ancho ideal de la
# columna de texto cuando está activo el modo enfoque.
_NORMAL_MARGINS = (28, 22, 28, 16)
_FOCUS_TOP_BOTTOM = (40, 26)
_FOCUS_TEXT_WIDTH = 760
_FOCUS_MIN_SIDE_MARGIN = 24


class ChaptersPanel(QWidget):
    """Panel lateral con la lista de capítulos y el editor de texto enriquecido."""

    def __init__(self, db, parent=None):
        """Inicializa el panel, construye el splitter y conecta señales."""
        super().__init__(parent)
        self.db = db
        self.project_id = None
        self._current_chapter_id = None
        self._loading = False
        self._focus_mode = False

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(settings.autosave_interval_ms)
        self._save_timer.timeout.connect(self._save_current_content)

        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.setInterval(1800)
        self._status_timer.timeout.connect(self._clear_save_status)

        self.list_column = self._build_list_column()

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(self.list_column)
        splitter.addWidget(self._build_editor_column())
        splitter.setSizes([240, 700])
        splitter.setChildrenCollapsible(False)
        self.splitter = splitter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        self._focus_shortcut = QShortcut(QKeySequence("Ctrl+Shift+F"), self)
        self._focus_shortcut.activated.connect(self.focus_button.toggle)

        self._apply_theme()
        theme.signals.changed.connect(self._apply_theme)
        settings_signals.changed.connect(self._apply_settings)

        self._show_empty_state()

    def _apply_settings(self):
        # No reiniciamos un guardado ya en marcha, solo el retardo que se
        # usará la próxima vez; y refrescamos el tiempo de lectura, que
        # depende de la velocidad de lectura configurada.
        self._save_timer.setInterval(settings.autosave_interval_ms)
        self._update_word_count()

    def _apply_theme(self, *_args):
        """Aplica los colores del tema activo a los controles del panel."""
        c = theme.colors()
        self.synopsis_toggle.setStyleSheet(
            f"QToolButton {{ border: none; color: {c['text_secondary']}; font-weight: 600; padding: 2px 0; }}"
            f"QToolButton:hover {{ color: {c['text']}; }}"
        )
        self._icon_color = c["text_secondary"]
        self._refresh_synopsis_icon()
        self._refresh_focus_icon()
        self.empty_icon_label.setPixmap(icons.pixmap("book", c["text_muted"], size=52))

    # ------------------------------------------------------------------ #
    # Construcción de la UI
    # ------------------------------------------------------------------ #
    def _build_list_column(self) -> QWidget:
        """Construye la columna izquierda con la lista de capítulos y botones de acción."""
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(14, 16, 10, 14)
        left_layout.setSpacing(10)

        title_row = QHBoxLayout()
        title = QLabel("Capítulos")
        title.setProperty("role", "section-title")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.total_words_label = QLabel("")
        self.total_words_label.setProperty("role", "muted")
        title_row.addWidget(self.total_words_label)
        left_layout.addLayout(title_row)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.MoveAction)
        self.list_widget.setSpacing(2)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self.list_widget, 1)

        hint = QLabel("Arrastra un capítulo para reordenarlo")
        hint.setProperty("role", "muted")
        left_layout.addWidget(hint)

        buttons_row = QHBoxLayout()
        self.add_button = QPushButton("+ Añadir")
        self.add_button.setProperty("variant", "primary")
        self.add_button.clicked.connect(self.add_chapter)
        self.remove_button = QPushButton("Eliminar")
        self.remove_button.setProperty("variant", "danger")
        self.remove_button.clicked.connect(self.remove_current_chapter)
        buttons_row.addWidget(self.add_button, 1)
        buttons_row.addWidget(self.remove_button)
        left_layout.addLayout(buttons_row)

        return left

    def _build_editor_column(self) -> QWidget:
        """Construye la columna derecha con el estado vacío y el editor apilados."""
        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(self._build_empty_state_widget())
        self.right_stack.addWidget(self._build_editor_widget())
        return self.right_stack

    def _build_empty_state_widget(self) -> QWidget:
        """Construye la vista de estado vacío cuando no existen capítulos."""
        empty = QWidget()
        layout = QVBoxLayout(empty)
        layout.addStretch(1)
        self.empty_icon_label = QLabel()
        self.empty_icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_icon_label)
        message = QLabel("Todavía no hay capítulos")
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet("font-size: 13pt; font-weight: 600;")
        layout.addWidget(message)
        subtitle = QLabel("Crea el primero para empezar a escribir tu novela.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setProperty("role", "hint")
        layout.addWidget(subtitle)
        start_button = QPushButton("+ Añadir capítulo")
        start_button.setProperty("variant", "primary")
        start_button.clicked.connect(self.add_chapter)
        button_row = QHBoxLayout()
        button_row.addStretch(1)
        button_row.addWidget(start_button)
        button_row.addStretch(1)
        layout.addSpacing(6)
        layout.addLayout(button_row)
        layout.addStretch(2)
        return empty

    def _build_editor_widget(self) -> QWidget:
        """Construye el área de edición del capítulo (cabecera, sinopsis, editor y estadísticas)."""
        right = QWidget()
        # `right_layout` (el layout raíz) mantiene SIEMPRE los márgenes
        # normales: aquí solo vive la cabecera (título + botón de modo
        # enfoque), así que el botón no se desplaza al activar el modo
        # enfoque. Lo que sí se estrecha para centrar la columna de
        # lectura es `self._content_layout`, un layout anidado que
        # cuelga por debajo y contiene sinopsis, barra de formato,
        # editor y estadísticas.
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(*_NORMAL_MARGINS)
        right_layout.setSpacing(8)
        self.editor_container = right
        right.installEventFilter(self)

        header_row = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setProperty("variant", "heading")
        self.title_edit.setPlaceholderText("Título del capítulo")
        self.title_edit.textEdited.connect(self._on_title_edited)
        header_row.addWidget(self.title_edit, 1)

        save_status = QWidget()
        save_status_layout = QHBoxLayout(save_status)
        save_status_layout.setContentsMargins(0, 0, 0, 0)
        save_status_layout.setSpacing(4)
        self.save_status_icon = QLabel()
        self.save_status_icon.setFixedSize(12, 12)
        self.save_status_icon.setVisible(False)
        save_status_layout.addWidget(self.save_status_icon)
        self.save_status_label = QLabel("")
        self.save_status_label.setProperty("role", "muted")
        save_status_layout.addWidget(self.save_status_label)
        header_row.addWidget(save_status)

        self.focus_button = QToolButton()
        self.focus_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.focus_button.setText("Modo enfoque")
        self.focus_button.setCheckable(True)
        self.focus_button.setCursor(Qt.PointingHandCursor)
        self.focus_button.setToolTip(
            "Oculta la lista de capítulos y la barra de formato para escribir sin distracciones "
            "(Ctrl+Shift+F)"
        )
        self.focus_button.toggled.connect(self._toggle_focus_mode)
        header_row.addWidget(self.focus_button)

        right_layout.addLayout(header_row)

        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(8)
        right_layout.addLayout(self._content_layout, 1)
        content_layout = self._content_layout

        self.synopsis_toggle = QToolButton()
        self.synopsis_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.synopsis_toggle.setText("Sinopsis (opcional)")
        self.synopsis_toggle.setCheckable(True)
        self.synopsis_toggle.setCursor(Qt.PointingHandCursor)
        self.synopsis_toggle.toggled.connect(self._on_synopsis_toggled)
        content_layout.addWidget(self.synopsis_toggle)

        self.synopsis_edit = QPlainTextEdit()
        self.synopsis_edit.setMaximumHeight(72)
        self.synopsis_edit.setPlaceholderText("Resumen breve de lo que ocurre en este capítulo…")
        self.synopsis_edit.textChanged.connect(self._schedule_save)
        self.synopsis_edit.setVisible(False)
        content_layout.addWidget(self.synopsis_edit)

        self.toolbar_frame = QFrame()
        toolbar_frame = self.toolbar_frame
        toolbar_frame.setProperty("role", "toolbar-strip")
        toolbar_frame_layout = QVBoxLayout(toolbar_frame)
        toolbar_frame_layout.setContentsMargins(0, 0, 0, 0)

        self.editor = RichTextEditor(placeholder="Escribe el contenido del capítulo...")
        self.editor.contentChanged.connect(self._schedule_save)
        self.editor.contentChanged.connect(self._update_word_count)
        self.editor.text_edit.setFrameShape(QFrame.NoFrame)
        self.editor.text_edit.setStyleSheet(
            "QTextEdit { background: transparent; border: none; padding: 14px 6px; line-height: 1.5; }"
        )
        # Solo se aplica aquí (construcción del panel, antes de cargar
        # ningún proyecto) y en `add_chapter` al crear un capítulo nuevo.
        # Cambiar los Ajustes con un capítulo ya abierto (`_apply_settings`,
        # más abajo) no debe tocar el formato del texto ya escrito.
        self.editor.apply_default_font(settings.editor_font_family, settings.editor_font_size)
        toolbar_frame_layout.addWidget(self.editor.create_format_toolbar())
        content_layout.addWidget(toolbar_frame)
        content_layout.addWidget(self.editor, 1)

        stats_row = QHBoxLayout()
        self.word_count_label = QLabel("0 palabras")
        self.word_count_label.setProperty("role", "muted")
        self.char_count_label = QLabel("0 caracteres")
        self.char_count_label.setProperty("role", "muted")
        self.reading_time_label = QLabel("~0 min de lectura")
        self.reading_time_label.setProperty("role", "muted")
        stats_row.addWidget(self.word_count_label)
        stats_row.addWidget(self._dot_separator())
        stats_row.addWidget(self.char_count_label)
        stats_row.addWidget(self._dot_separator())
        stats_row.addWidget(self.reading_time_label)
        stats_row.addStretch(1)
        content_layout.addLayout(stats_row)

        return right

    @staticmethod
    def _dot_separator() -> QLabel:
        """Crea un separador de punto tipográfico para la barra de estadísticas."""
        dot = QLabel("·")
        dot.setProperty("role", "muted")
        return dot

    def _on_synopsis_toggled(self, checked: bool):
        """Muestra u oculta el campo de sinopsis según el estado del botón."""
        self._refresh_synopsis_icon()
        self.synopsis_edit.setVisible(checked)

    def _refresh_synopsis_icon(self):
        """Actualiza el icono del botón de sinopsis según su estado desplegado/colapsado."""
        name = "chevron-down" if self.synopsis_toggle.isChecked() else "chevron-right"
        self.synopsis_toggle.setIcon(icons.icon(name, self._icon_color, size=14))

    def _refresh_focus_icon(self):
        """Actualiza el icono del botón de modo enfoque según su estado activo/inactivo."""
        name = "x" if self.focus_button.isChecked() else "expand"
        self.focus_button.setIcon(icons.icon(name, self._icon_color, size=14))

    # ------------------------------------------------------------------ #
    # Modo enfoque
    # ------------------------------------------------------------------ #
    def _toggle_focus_mode(self, checked: bool):
        """Activa o desactiva el modo enfoque, ocultando o mostrando la lista y la barra de formato."""
        self._focus_mode = checked
        self.list_column.setVisible(not checked)
        self.toolbar_frame.setVisible(not checked)
        self.focus_button.setText("Salir del enfoque" if checked else "Modo enfoque")
        self._refresh_focus_icon()
        if checked:
            self._update_focus_margins()
        else:
            self._content_layout.setContentsMargins(0, 0, 0, 0)

    def _update_focus_margins(self):
        # Los márgenes que estrechan la columna de texto se aplican
        # solo a `_content_layout`, nunca a la cabecera: así el botón
        # de modo enfoque se queda fijo en su sitio (arriba a la
        # derecha) en vez de acercarse al centro según se angosta la
        # columna. El ancho disponible para esa columna descuenta los
        # márgenes fijos de la cabecera, que siguen ahí siempre.
        available = self.editor_container.width() - _NORMAL_MARGINS[0] - _NORMAL_MARGINS[2]
        side = max(_FOCUS_MIN_SIDE_MARGIN, (available - _FOCUS_TEXT_WIDTH) // 2)
        top, bottom = _FOCUS_TOP_BOTTOM
        self._content_layout.setContentsMargins(side, top, side, bottom)

    def eventFilter(self, obj, event):
        """Recalcula los márgenes del modo enfoque cuando el contenedor cambia de tamaño."""
        if obj is self.editor_container and event.type() == QEvent.Resize and self._focus_mode:
            self._update_focus_margins()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        """Saluda Escape como atajo para salir del modo enfoque."""
        if self._focus_mode and event.key() == Qt.Key_Escape:
            self.focus_button.setChecked(False)
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ #
    # Ciclo de vida / carga de proyecto
    # ------------------------------------------------------------------ #
    def load_project(self, project_id: int):
        """Guarda el estado pendiente y recarga la lista de capítulos del proyecto indicado."""
        self._flush_pending_save()
        self.project_id = project_id
        self._current_chapter_id = None
        self._reload_list(select_id=None)

    def _reload_list(self, select_id=None):
        """Recarga la lista de capítulos desde la base de datos y selecciona uno opcionalmente."""
        self._loading = True
        self.list_widget.clear()
        # `word_count` viene cacheado desde SQLite: no hace falta volver
        # a interpretar el HTML de cada capítulo solo para listarlos.
        chapters = self.db.list_chapters(self.project_id) if self.project_id else []
        target_row = None
        for index, row in enumerate(chapters, start=1):
            words = row["word_count"]
            item = QListWidgetItem(f"{index}.  {row['title'] or '(sin título)'}\n     {words} palabras")
            item.setData(Qt.UserRole, row["id"])
            self.list_widget.addItem(item)
            if select_id is not None and row["id"] == select_id:
                target_row = self.list_widget.count() - 1
        self._loading = False
        self._refresh_total_words()
        if target_row is not None:
            self.list_widget.setCurrentRow(target_row)
        elif self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)
        else:
            self._current_chapter_id = None
            self._show_empty_state()

    # ------------------------------------------------------------------ #
    # Selección y edición
    # ------------------------------------------------------------------ #
    def _on_selection_changed(self, current: QListWidgetItem, previous: QListWidgetItem):
        """Carga el capítulo seleccionado en el editor o muestra el estado vacío."""
        if self._loading:
            return
        self._flush_pending_save()
        if current is None:
            self._current_chapter_id = None
            self._show_empty_state()
            return
        chapter_id = current.data(Qt.UserRole)
        self._load_chapter(chapter_id)

    def _load_chapter(self, chapter_id: int):
        """Lee el capítulo de la base de datos y lo muestra en el editor."""
        row = self.db.get_chapter(chapter_id)
        if row is None:
            return
        self._loading = True
        self._current_chapter_id = chapter_id
        self.title_edit.setText(row["title"])
        self.synopsis_edit.setPlainText(row["synopsis"])
        self.synopsis_toggle.setChecked(bool(row["synopsis"]))
        self.editor.set_html(row["content"])
        self._clear_save_status()
        self._loading = False
        self.right_stack.setCurrentIndex(1)
        self.remove_button.setEnabled(True)
        self._update_word_count()
        # Autocuración para capítulos creados antes de que existiera la
        # columna `word_count` cacheada: se recalcula una única vez (aquí
        # sí hace falta interpretar el HTML) y se guarda, así que las
        # próximas veces ya sale directo de SQLite sin volver a parsear.
        if row["word_count"] == 0 and row["content"]:
            self.db.update_chapter(chapter_id, word_count=self.editor.word_count())
            self._refresh_total_words()

    def _show_empty_state(self):
        """Muestra la pantalla vacía y desactiva el botón de eliminar."""
        self.right_stack.setCurrentIndex(0)
        self.remove_button.setEnabled(False)

    def _update_word_count(self):
        """Actualiza las estadísticas de palabras, caracteres y tiempo de lectura."""
        words = self.editor.word_count()
        chars = len(self.editor.text_edit.toPlainText())
        minutes = max(1, round(words / settings.reading_speed_wpm)) if words else 0
        self.word_count_label.setText(f"{words} palabras")
        self.char_count_label.setText(f"{chars} caracteres")
        self.reading_time_label.setText(f"~{minutes} min de lectura" if words else "0 min de lectura")
        current_item = self.list_widget.currentItem()
        if current_item is not None and not self._loading:
            row = self.list_widget.currentRow() + 1
            title = self.title_edit.text() or "(sin título)"
            current_item.setText(f"{row}.  {title}\n     {words} palabras")

    def _refresh_total_words(self):
        """Actualiza la etiqueta de total de palabras del proyecto en la cabecera de la lista."""
        if self.project_id is None:
            self.total_words_label.setText("")
            return
        total = self.db.total_word_count(self.project_id)
        self.total_words_label.setText(f"{total} palabras en total" if total else "")

    # ------------------------------------------------------------------ #
    # Autoguardado
    # ------------------------------------------------------------------ #
    def _clear_save_status(self):
        """Oculta el indicador de estado de guardado."""
        self.save_status_icon.setVisible(False)
        self.save_status_label.setText("")

    def _schedule_save(self):
        """Inicia (o reinicia) el temporizador de autoguardado si el editor está activo."""
        if self._loading or self._current_chapter_id is None:
            return
        self.save_status_icon.setVisible(False)
        self.save_status_label.setText("Escribiendo…")
        self._save_timer.start()

    def _on_title_edited(self, _text):
        """Actualiza el recuento de palabras en la lista y programa el autoguardado."""
        if self._current_chapter_id is None:
            return
        self._update_word_count()
        self._schedule_save()

    def _save_current_content(self):
        """Persiste el capítulo actual en la base de datos y actualiza el indicador de estado."""
        if self._current_chapter_id is None:
            return
        self.db.update_chapter(
            self._current_chapter_id,
            title=self.title_edit.text().strip() or "Sin título",
            synopsis=self.synopsis_edit.toPlainText(),
            content=self.editor.to_html(),
            # Se guarda el recuento ya calculado por el propio editor en
            # vez de volver a interpretar el HTML recién guardado.
            word_count=self.editor.word_count(),
        )
        self._refresh_total_words()
        self.save_status_icon.setPixmap(icons.pixmap("check", theme.colors()["success"], size=12))
        self.save_status_icon.setVisible(True)
        self.save_status_label.setText("Guardado")
        self._status_timer.start()

    def _flush_pending_save(self):
        """Cancela el temporizador y guarda inmediatamente si hay un guardado pendiente."""
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_current_content()

    # ------------------------------------------------------------------ #
    # Acciones de lista
    # ------------------------------------------------------------------ #
    def add_chapter(self):
        """Crea un nuevo capítulo al final de la lista y lo selecciona para edición."""
        if self.project_id is None:
            return
        self._flush_pending_save()
        n = self.db.count_chapters(self.project_id) + 1
        new_id = self.db.create_chapter(self.project_id, title=f"Capítulo {n}")
        self._reload_list(select_id=new_id)
        self.editor.apply_default_font(settings.editor_font_family, settings.editor_font_size)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def remove_current_chapter(self):
        """Elimina el capítulo seleccionado (con confirmación opcional) y recarga la lista."""
        if self._current_chapter_id is None:
            return
        if settings.confirm_before_delete:
            ret = QMessageBox.question(
                self, "Eliminar capítulo",
                "¿Seguro que quieres eliminar este capítulo? Esta acción no se puede deshacer.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if ret != QMessageBox.Yes:
                return
        self.db.delete_chapter(self._current_chapter_id)
        self._current_chapter_id = None
        self._reload_list()

    def _on_rows_moved(self, *_args):
        """Persiste el nuevo orden de capítulos en la base de datos y refresca la lista."""
        if self._loading or self.project_id is None:
            return
        ordered_ids = [
            self.list_widget.item(i).data(Qt.UserRole) for i in range(self.list_widget.count())
        ]
        self.db.reorder_chapters(ordered_ids)
        self._reload_list(select_id=self._current_chapter_id)