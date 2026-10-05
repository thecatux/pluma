"""Panel flotante de búsqueda y reemplazo para RichTextEditor.

Es un hijo del propio editor (no una ventana aparte ni un elemento del
layout): se coloca en la esquina superior derecha por encima del texto,
de modo que abrirlo o cerrarlo nunca mueve ni redimensiona nada de la
interfaz existente.

Decisiones de diseño
--------------------
- Búsqueda sobre el texto plano (`toPlainText()`), que tiene la misma
  longitud que el documento de Qt (los separadores de bloque cuentan
  como un carácter, igual que en las posiciones de QTextCursor). Los
  índices se calculan en unidades UTF-16 para que cuadren con Qt aunque
  haya emoji u otros caracteres fuera del plano básico.
- Mayúsculas y tildes se ignoran normalizando carácter a carácter
  (siempre 1 a 1), así un índice del texto normalizado es también un
  índice del documento. La eñe nunca se pliega a la ene.
- Los resultados se resaltan con `setExtraSelections`: no modifican el
  documento, no tocan el historial de deshacer ni disparan el
  autoguardado. Solo se crean resaltados para la zona visible, así que
  buscar una letra suelta en un capítulo enorme sigue siendo instantáneo.
- Reemplazar usa QTextCursor dentro de beginEditBlock/endEditBlock:
  "Reemplazar todo" es un único paso de deshacer y emite una sola
  señal de cambio (un único autoguardado). El texto nuevo conserva el
  formato (fuente, negrita, color...) del texto reemplazado.
"""

import re
import unicodedata
from bisect import bisect_left, bisect_right

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                                QTextEdit, QToolButton, QVBoxLayout, QWidget)

from pluma.ui import icons, theme

# ---------------------------------------------------------------------- #
# Normalización (funciones puras)
# ---------------------------------------------------------------------- #
_ASTRAL = re.compile("[\U00010000-\U0010FFFF]")
_KEEP_DISTINCT = frozenset("ñÑ")


def _to_utf16_units(text: str) -> str:
    """Sustituye cada carácter fuera del plano básico por su par
    sustituto, para que los índices de Python coincidan con los de Qt."""
    if not _ASTRAL.search(text):
        return text

    def split(match):
        cp = ord(match.group()) - 0x10000
        return chr(0xD800 + (cp >> 10)) + chr(0xDC00 + (cp & 0x3FF))

    return _ASTRAL.sub(split, text)


def _accent_table(chars) -> dict:
    table = {}
    for ch in chars:
        if ch < "\u0080" or ch in _KEEP_DISTINCT:
            continue
        decomposed = unicodedata.normalize("NFD", ch)
        if len(decomposed) > 1 and all(unicodedata.combining(x) for x in decomposed[1:]):
            table[ord(ch)] = decomposed[0]
    return table


def _fold(text: str, match_case: bool, ignore_accents: bool) -> str:
    """Normaliza `text` conservando su longitud exacta."""
    if not match_case:
        lowered = text.lower()
        if len(lowered) != len(text):  # p. ej. "İ" se expande al pasar a minúscula
            lowered = "".join(c.lower() if len(c.lower()) == 1 else c for c in text)
        text = lowered
    if ignore_accents and not text.isascii():
        table = _accent_table(set(text))
        if table:
            text = text.translate(table)
    return text


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


class FindReplaceBar(QFrame):
    WIDTH = 410
    MARGIN = 12
    MAX_VISIBLE_HIGHLIGHTS = 1500
    SMALL_DOC_CHARS = 200_000  # por debajo se busca en cada pulsación, sin espera

    def __init__(self, host: QWidget, text_edit: QTextEdit):
        super().__init__(host)
        self.host = host
        self.text_edit = text_edit

        self._starts: list = []
        self._len = 0
        self._needle_folded = ""
        self._flags = (False, False, False)
        self._current = -1
        self._plain = ""
        self._folded_cache: dict = {}
        self._dirty = True
        self._busy = False
        self._icon_buttons: list = []

        self._build_ui()

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(120)
        self._search_timer.timeout.connect(self._run_search)

        self._edit_timer = QTimer(self)
        self._edit_timer.setSingleShot(True)
        self._edit_timer.timeout.connect(self._refresh_after_edit)

        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.setInterval(2500)
        self._flash_timer.timeout.connect(self._update_counter)

        document = self.text_edit.document()
        document.contentsChanged.connect(self._on_document_changed)
        scrollbar = self.text_edit.verticalScrollBar()
        scrollbar.valueChanged.connect(self._apply_highlights)
        scrollbar.rangeChanged.connect(lambda *_: self.reposition())

        self.find_edit.textChanged.connect(self._on_query_changed)
        for button in (self.case_button, self.word_button, self.accent_button):
            button.toggled.connect(self._on_query_changed)
        self.prev_button.clicked.connect(self.go_previous)
        self.next_button.clicked.connect(self.go_next)
        self.close_button.clicked.connect(self.close_bar)
        self.toggle_button.clicked.connect(lambda: self.set_replace_visible(self.replace_row.isHidden()))
        self.replace_button.clicked.connect(self.replace_current)
        self.replace_all_button.clicked.connect(self.replace_all)

        for watched in (self.find_edit, self.replace_edit, self.text_edit):
            watched.installEventFilter(self)
        host.installEventFilter(self)

        self._apply_theme()
        theme.signals.changed.connect(self._apply_theme)
        self.hide()

    # ------------------------------------------------------------------ #
    # Construcción de la interfaz
    # ------------------------------------------------------------------ #
    def _tool_button(self, icon_name: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setToolTip(tooltip)
        button.setIconSize(QSize(16, 16))
        button.setFixedSize(26, 26)
        self._icon_buttons.append((button, icon_name))
        return button

    def _option_button(self, text: str, tooltip: str) -> QToolButton:
        button = QToolButton(self)
        button.setText(text)
        button.setToolTip(tooltip)
        button.setCheckable(True)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        button.setFixedHeight(26)
        return button

    def _build_ui(self):
        self.setObjectName("findBar")
        self.setFrameShape(QFrame.NoFrame)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # Fila 1: buscar
        row = QHBoxLayout()
        row.setSpacing(4)
        self.toggle_button = self._tool_button("chevron-right", "Mostrar reemplazo (Ctrl+H)")
        self.find_edit = QLineEdit(self)
        self.find_edit.setPlaceholderText("Buscar")
        self.counter = QLabel("", self)
        self.counter.setProperty("role", "muted")
        self.counter.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.counter.setMinimumWidth(92)
        self.prev_button = self._tool_button("chevron-up", "Anterior (Mayús+Intro)")
        self.next_button = self._tool_button("chevron-down", "Siguiente (Intro)")
        self.close_button = self._tool_button("x", "Cerrar (Esc)")
        row.addWidget(self.toggle_button)
        row.addWidget(self.find_edit, 1)
        row.addWidget(self.counter)
        row.addWidget(self.prev_button)
        row.addWidget(self.next_button)
        row.addWidget(self.close_button)
        root.addLayout(row)

        # Fila 2: opciones
        options = QHBoxLayout()
        options.setSpacing(4)
        options.addSpacing(26 + 4)
        self.case_button = self._option_button("Aa", "Distinguir mayúsculas y minúsculas")
        self.word_button = self._option_button("Palabra completa", "Solo palabras completas")
        self.accent_button = self._option_button("Ignorar tildes", "Tratar á, é, í, ó, ú, ü como a, e, i, o, u (la ñ sigue siendo distinta)")
        options.addWidget(self.case_button)
        options.addWidget(self.word_button)
        options.addWidget(self.accent_button)
        options.addStretch(1)
        root.addLayout(options)

        # Fila 3: reemplazar (oculta hasta que se pide)
        self.replace_row = QWidget(self)
        replace_layout = QHBoxLayout(self.replace_row)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        replace_layout.setSpacing(4)
        replace_layout.addSpacing(26 + 4)
        self.replace_edit = QLineEdit(self.replace_row)
        self.replace_edit.setPlaceholderText("Reemplazar con")
        self.replace_button = QPushButton("Reemplazar", self.replace_row)
        self.replace_button.setToolTip("Reemplazar esta coincidencia y pasar a la siguiente")
        self.replace_all_button = QPushButton("Todo", self.replace_row)
        self.replace_all_button.setToolTip("Reemplazar todas las coincidencias (se deshace con Ctrl+Z)")
        for button in (self.replace_button, self.replace_all_button):
            button.setAutoDefault(False)
            button.setFocusPolicy(Qt.TabFocus)
        replace_layout.addWidget(self.replace_edit, 1)
        replace_layout.addWidget(self.replace_button)
        replace_layout.addWidget(self.replace_all_button)
        root.addWidget(self.replace_row)
        self.replace_row.hide()

    # ------------------------------------------------------------------ #
    # Tema
    # ------------------------------------------------------------------ #
    def _apply_theme(self, *_args):
        c = theme.colors()
        self.setStyleSheet(f"""
            QFrame#findBar {{
                background: {c['surface']};
                border: 1px solid {c['border_strong']};
                border-radius: 10px;
            }}
            #findBar QToolButton {{
                border: none;
                border-radius: 6px;
                padding: 3px 8px;
                background: transparent;
                color: {c['text']};
            }}
            #findBar QToolButton:hover {{ background: {c['surface_alt']}; }}
            #findBar QToolButton:checked {{
                background: {c['primary_light']};
                color: {c['primary_text']};
            }}
            #findBar QLineEdit {{ padding: 4px 8px; }}
            #findBar QLineEdit[nomatch="true"] {{
                border: 1px solid {c['danger']};
                background: {c['danger_light']};
            }}
            #findBar QPushButton {{ padding: 4px 12px; min-height: 18px; }}
        """)
        self._refresh_icons()

        match = QColor(c["primary"])
        match.setAlpha(80)
        self._match_format = QTextCharFormat()
        self._match_format.setBackground(match)
        self._current_format = QTextCharFormat()
        self._current_format.setBackground(QColor(c["primary"]))
        self._current_format.setForeground(QColor(c["on_primary"]))
        self._apply_highlights()

    def _make_icon(self, name: str) -> QIcon:
        c = theme.colors()
        result = QIcon()
        result.addPixmap(icons.pixmap(name, c["text"], size=16), QIcon.Normal, QIcon.Off)
        result.addPixmap(icons.pixmap(name, c["text_muted"], size=16), QIcon.Disabled, QIcon.Off)
        return result

    def _refresh_icons(self):
        for button, name in self._icon_buttons:
            if button is self.toggle_button:
                name = "chevron-right" if self.replace_row.isHidden() else "chevron-down"
            button.setIcon(self._make_icon(name))

    # ------------------------------------------------------------------ #
    # Mostrar / ocultar / colocar
    # ------------------------------------------------------------------ #
    def set_replace_visible(self, visible: bool):
        self.replace_row.setVisible(visible)
        self.toggle_button.setToolTip("Ocultar reemplazo" if visible else "Mostrar reemplazo (Ctrl+H)")
        self._refresh_icons()
        self.reposition()

    def open_bar(self, replace: bool = False):
        if replace:
            self.set_replace_visible(True)
        read_only = self.text_edit.isReadOnly()
        self.replace_edit.setEnabled(not read_only)
        self.replace_button.setEnabled(not read_only)
        self.replace_all_button.setEnabled(not read_only)

        cursor = self.text_edit.textCursor()
        if cursor.hasSelection():
            selected = cursor.selectedText()
            if len(selected) <= 120 and "\u2029" not in selected and "\u2028" not in selected:
                self.find_edit.blockSignals(True)
                self.find_edit.setText(selected.replace("\u00a0", " "))
                self.find_edit.blockSignals(False)

        self.show()
        self.reposition()
        self.raise_()
        if replace and self.find_edit.text() and not read_only:
            self.replace_edit.setFocus()
            self.replace_edit.selectAll()
        else:
            self.find_edit.setFocus()
            self.find_edit.selectAll()
        self._run_search()

    def close_bar(self):
        cursor = self.text_edit.textCursor()
        if (self._current >= 0 and self._current < len(self._starts)
                and cursor.position() == self._starts[self._current]):
            # Deja la coincidencia actual seleccionada para seguir editando.
            self.text_edit.setTextCursor(self._cursor_for(self._starts[self._current], self._len))
        self._search_timer.stop()
        self._edit_timer.stop()
        self.hide()
        self._current = -1
        self.text_edit.setExtraSelections([])
        self.text_edit.setFocus()

    def reposition(self):
        width = max(260, min(self.WIDTH, self.host.width() - 2 * self.MARGIN))
        self.setFixedWidth(width)
        self.layout().activate()
        self.adjustSize()
        scrollbar = self.text_edit.verticalScrollBar()
        inset = self.MARGIN + (scrollbar.width() if scrollbar.isVisible() else 0)
        self.move(max(self.MARGIN, self.host.width() - self.width() - inset), self.MARGIN)

    def eventFilter(self, obj, event):
        kind = event.type()
        if obj is self.host:
            if kind == QEvent.Resize and self.isVisible():
                self.reposition()
                self._apply_highlights()
            return False
        if kind == QEvent.KeyPress and self.isVisible():
            key = event.key()
            if key == Qt.Key_Escape:
                self.close_bar()
                return True
            if key == Qt.Key_F3 and obj in (self.find_edit, self.text_edit):
                self.go_previous() if event.modifiers() & Qt.ShiftModifier else self.go_next()
                return True
            if key in (Qt.Key_Return, Qt.Key_Enter):
                if obj is self.find_edit:
                    self.go_previous() if event.modifiers() & Qt.ShiftModifier else self.go_next()
                    return True
                if obj is self.replace_edit:
                    self.replace_current()
                    return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------ #
    # Búsqueda
    # ------------------------------------------------------------------ #
    def _on_document_changed(self):
        self._dirty = True
        if self._busy or not self.isVisible():
            return
        small = self.text_edit.document().characterCount() < self.SMALL_DOC_CHARS
        self._edit_timer.start(0 if small else 150)

    def _on_query_changed(self, *_args):
        self._flash_timer.stop()
        if self.text_edit.document().characterCount() < self.SMALL_DOC_CHARS:
            self._search_timer.stop()
            self._run_search()
        else:
            self._search_timer.start()

    def _folded_text(self, match_case: bool, ignore_accents: bool) -> str:
        if self._dirty:
            self._plain = _to_utf16_units(self.text_edit.document().toPlainText())
            self._folded_cache.clear()
            self._dirty = False
        key = (match_case, ignore_accents)
        folded = self._folded_cache.get(key)
        if folded is None:
            folded = _fold(self._plain, match_case, ignore_accents)
            self._folded_cache[key] = folded
        return folded

    def _find_all(self):
        """Recalcula la lista de posiciones de inicio de cada coincidencia."""
        self._starts = []
        self._len = 0
        needle = self.find_edit.text()
        if not needle:
            return
        match_case = self.case_button.isChecked()
        whole_word = self.word_button.isChecked()
        ignore_accents = self.accent_button.isChecked()
        self._flags = (match_case, whole_word, ignore_accents)

        haystack = self._folded_text(match_case, ignore_accents)
        folded_needle = _fold(_to_utf16_units(needle), match_case, ignore_accents)
        self._needle_folded = folded_needle
        length = len(folded_needle)
        self._len = length

        plain = self._plain
        total = len(plain)
        check_start = whole_word and _is_word_char(folded_needle[0])
        check_end = whole_word and _is_word_char(folded_needle[-1])
        find = haystack.find
        starts = []
        pos = find(folded_needle, 0)
        while pos != -1:
            end = pos + length
            if ((not check_start or pos == 0 or not _is_word_char(plain[pos - 1]))
                    and (not check_end or end >= total or not _is_word_char(plain[end]))):
                starts.append(pos)
                pos = find(folded_needle, end)
            else:
                pos = find(folded_needle, pos + 1)
        self._starts = starts

    def _cursor_for(self, start: int, length: int = 0) -> QTextCursor:
        cursor = QTextCursor(self.text_edit.document())
        cursor.setPosition(start)
        if length:
            cursor.setPosition(start + length, QTextCursor.KeepAnchor)
        return cursor

    def _run_search(self):
        """Búsqueda nueva (el usuario escribe o cambia una opción): salta
        a la primera coincidencia desde el cursor."""
        self._find_all()
        if not self._starts:
            self._current = -1
            self._update_counter()
            self._apply_highlights()
            return
        cursor = self.text_edit.textCursor()
        index = bisect_left(self._starts, cursor.selectionStart())
        if index >= len(self._starts):
            index = 0
        self._select_match(index)

    def _refresh_after_edit(self):
        """El texto cambió mientras el panel está abierto: se recalculan
        las coincidencias sin mover el cursor del usuario."""
        if not self.isVisible():
            return
        self._find_all()
        position = self.text_edit.textCursor().position()
        index = bisect_left(self._starts, position)
        self._current = index if index < len(self._starts) and self._starts[index] == position else -1
        self._update_counter()
        self._apply_highlights()

    def _select_match(self, index: int):
        self._flash_timer.stop()
        self._current = index
        cursor = self._cursor_for(self._starts[index])
        self.text_edit.setTextCursor(cursor)  # también desplaza la vista hasta el cursor
        self._reveal(cursor)
        self._update_counter()
        self._apply_highlights()

    def _reveal(self, cursor: QTextCursor):
        """Si la coincidencia quedó tapada por el panel, desplaza el texto."""
        if not self.isVisible():
            return
        viewport = self.text_edit.viewport()
        rect = self.text_edit.cursorRect(cursor)
        top_left = viewport.mapFromGlobal(self.mapToGlobal(QPoint(0, 0)))
        bar = QRect(top_left, self.size())
        if rect.top() < bar.bottom() + 8 and rect.right() > bar.left() - 60 and rect.bottom() > bar.top():
            scrollbar = self.text_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.value() - (bar.bottom() + 16 - rect.top()))

    def go_next(self):
        self._go(True)

    def go_previous(self):
        self._go(False)

    def _go(self, forward: bool):
        if not self._starts:
            self._run_search()
            return
        if self._dirty:  # el texto cambió desde la última búsqueda
            self._find_all()
            if not self._starts:
                self._current = -1
                self._update_counter()
                self._apply_highlights()
                return
        position = self.text_edit.textCursor().position()
        count = len(self._starts)
        if 0 <= self._current < count and self._starts[self._current] == position:
            index = self._current + (1 if forward else -1)
        else:
            index = bisect_left(self._starts, position) - (0 if forward else 1)
        self._select_match(index % count)

    # ------------------------------------------------------------------ #
    # Resaltado y contador
    # ------------------------------------------------------------------ #
    def _apply_highlights(self, *_args):
        editor = self.text_edit
        if not self.isVisible() or not self._starts:
            editor.setExtraSelections([])
            return
        viewport = editor.viewport()
        first = editor.cursorForPosition(QPoint(0, 0)).position()
        last = editor.cursorForPosition(QPoint(viewport.width(), viewport.height())).position()
        lo = bisect_left(self._starts, first - self._len)
        hi = min(bisect_right(self._starts, last), lo + self.MAX_VISIBLE_HIGHLIGHTS)
        document = editor.document()
        selections = []
        for i in range(lo, hi):
            selection = QTextEdit.ExtraSelection()
            cursor = QTextCursor(document)
            cursor.setPosition(self._starts[i])
            cursor.setPosition(self._starts[i] + self._len, QTextCursor.KeepAnchor)
            selection.cursor = cursor
            selection.format = self._current_format if i == self._current else self._match_format
            selections.append(selection)
        editor.setExtraSelections(selections)

    def _flash(self, message: str):
        self.counter.setText(message)
        self._flash_timer.start()

    def _update_counter(self):
        if self._flash_timer.isActive():
            return
        count = len(self._starts)
        has_query = bool(self.find_edit.text())
        if not has_query:
            text = ""
        elif count == 0:
            text = "Sin resultados"
        elif self._current >= 0:
            text = f"{self._current + 1} de {count}"
        else:
            text = "1 resultado" if count == 1 else f"{count} resultados"
        self.counter.setText(text)

        no_match = has_query and count == 0
        if self.find_edit.property("nomatch") != no_match:
            self.find_edit.setProperty("nomatch", no_match)
            self.find_edit.style().unpolish(self.find_edit)
            self.find_edit.style().polish(self.find_edit)
        for button in (self.prev_button, self.next_button):
            button.setEnabled(count > 0)
        can_replace = count > 0 and not self.text_edit.isReadOnly()
        self.replace_button.setEnabled(can_replace)
        self.replace_all_button.setEnabled(can_replace)

    # ------------------------------------------------------------------ #
    # Reemplazo
    # ------------------------------------------------------------------ #
    def _matches_needle(self, cursor: QTextCursor) -> bool:
        """Comprueba que el texto bajo `cursor` sigue siendo una coincidencia
        (red de seguridad: nunca se reemplaza algo que no sea lo buscado)."""
        selected = cursor.selectedText().replace("\u00a0", " ")
        match_case, _word, ignore_accents = self._flags
        return _fold(_to_utf16_units(selected), match_case, ignore_accents) == self._needle_folded

    def _insert_keeping_format(self, cursor: QTextCursor, probe: QTextCursor, text: str):
        probe.setPosition(cursor.selectionStart() + 1)
        cursor.insertText(text, probe.charFormat())

    def replace_current(self):
        if self.text_edit.isReadOnly() or not self._starts:
            return
        if self._dirty:
            self._find_all()
            if not self._starts:
                self._update_counter()
                return
        position = self.text_edit.textCursor().position()
        if not (0 <= self._current < len(self._starts) and self._starts[self._current] == position):
            # Primer clic: solo localiza la coincidencia, como en cualquier editor.
            self._go(True)
            return
        cursor = self._cursor_for(self._starts[self._current], self._len)
        if not self._matches_needle(cursor):
            self._find_all()
            self._refresh_after_edit()
            return

        self._busy = True
        try:
            probe = QTextCursor(self.text_edit.document())
            self._insert_keeping_format(cursor, probe, self.replace_edit.text())
        finally:
            self._busy = False
        end = cursor.position()
        self._dirty = True
        self._find_all()
        if self._starts:
            index = bisect_left(self._starts, end)
            self._select_match(index if index < len(self._starts) else 0)
        else:
            cursor.clearSelection()
            self.text_edit.setTextCursor(cursor)
            self._current = -1
            self._update_counter()
            self._apply_highlights()

    def replace_all(self):
        if self.text_edit.isReadOnly():
            return
        if self._dirty:
            self._find_all()
        starts = list(self._starts)
        if not starts:
            return
        replacement = self.replace_edit.text()
        document = self.text_edit.document()
        cursor = QTextCursor(document)
        probe = QTextCursor(document)
        replaced = 0

        self._busy = True
        cursor.beginEditBlock()
        try:
            # De atrás hacia delante para que las posiciones pendientes no se muevan.
            for start in reversed(starts):
                cursor.setPosition(start)
                cursor.setPosition(start + self._len, QTextCursor.KeepAnchor)
                if not self._matches_needle(cursor):
                    continue
                self._insert_keeping_format(cursor, probe, replacement)
                replaced += 1
        finally:
            cursor.endEditBlock()
            self._busy = False

        self._dirty = True
        self._find_all()
        self._current = -1
        self._apply_highlights()
        self._update_counter()
        if replaced:
            self._flash("1 reemplazo" if replaced == 1 else f"{replaced} reemplazos")